from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from pydantic import ValidationError

from knoarbor.audit.token_ledger import append_chat_token_records, current_timestamp
from knoarbor.core.config import ModelRetryConfig, default_config_path, load_config
from knoarbor.core.errors import ModelOutputError, UserInputError
from knoarbor.core.schemas.chat import (
    ChatAnswerDraft,
    ChatEvent,
    ChatMessageItem,
    ChatRequest,
    ChatResponse,
    ChatRunLink,
    ChatSessionRecord,
    ChatToolPlan,
    ChatToolTraceItem,
)
from knoarbor.core.schemas.memory import MemoryCandidate, MemoryRecord
from knoarbor.services.chat_answer import ChatAnswerSynthesizer, messages_chars, parse_json_object
from knoarbor.services.chat_citations import answer_cleanup_citations, clean_answer_citation_paths, final_citations
from knoarbor.services.chat_context import ChatContextEngine, latest_user_text, memory_target, session_target
from knoarbor.services.chat_model_call import run_chat_model_call
from knoarbor.services.chat_retrieval_policy import ChatPlanAdjustment, ChatRetrievalPolicy
from knoarbor.services.chat_tools import ChatToolExecutor
from knoarbor.runtime import runtime_logger
from knoarbor.semantic.contracts import load_prompt
from knoarbor.semantic.llm import ChatClient, ChatCompletionRequest, ChatMessage, ModelGateway

if TYPE_CHECKING:
    from knoarbor.services import ApplicationServices


ANSWER_SYNTHESIS_PROMPT = load_prompt("wiki_chat_answer.md")
TOOL_PLAN_PROMPT = load_prompt("wiki_chat_tool_plan.md")
LOGGER = runtime_logger(__name__)


@dataclass
class ChatAgentService:
    """Bounded KnoArbor chat agent over existing wiki/runtime services."""

    client_factory: Callable[[ChatRequest], ChatClient] | None = None
    context_engine: ChatContextEngine = field(default_factory=ChatContextEngine)

    def chat(self, request: ChatRequest, services: ApplicationServices) -> ChatResponse:
        started = time.perf_counter()
        client = self.client_factory(request) if self.client_factory else _client_from_request(request)
        chat_target = session_target(request)
        existing_session = services.chat_sessions.load_existing(chat_target.path, request.session_id)
        chat_id = request.session_id or (existing_session.session_id if existing_session else None)
        if chat_id is None:
            chat_id = services.chat_sessions.new_session_id()
        context = self.context_engine.build(
            request,
            services,
            chat_id=chat_id,
            existing_session=existing_session,
            system_prompt=ANSWER_SYNTHESIS_PROMPT,
        )
        effective_request = request.model_copy(update={"messages": context.conversation_messages, "session_id": chat_id})
        loop = _ChatLoop(
            request=effective_request,
            current_messages=context.conversation_messages,
            services=services,
            client=client,
            chat_id=chat_id,
            initial_messages=context.model_messages,
            existing_session=existing_session,
            model_retry=load_config(Path(request.config_path).expanduser().resolve() if request.config_path else default_config_path()).models.retry,
            memory_used=context.memory_used,
            warnings=context.warnings,
        )
        response = loop.run()
        response.stats.update(
            {
                "chat_id": response.session_id,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
                "provider": getattr(client, "provider", response.stats.get("provider")),
                "model": getattr(client, "model", response.stats.get("model")),
                "retrieval_strategy": response.stats.get("retrieval_strategy", "canonical_evidence"),
                "session_vault_id": chat_target.vault_id,
                "session_vault_name": chat_target.vault_name,
            }
        )
        record = services.chat_sessions.persist_response(
            chat_target.path,
            response=response,
            request_messages=context.conversation_messages,
            vault_id=chat_target.vault_id,
            vault_name=chat_target.vault_name,
        )
        response.session_id = record.session_id
        if request.append_ledger:
            _append_chat_ledger(request, response, loop.call_records)
        return response


@dataclass
class _ChatLoop:
    request: ChatRequest
    current_messages: list[ChatMessageItem]
    services: ApplicationServices
    client: ChatClient
    chat_id: str
    initial_messages: list[ChatMessage]
    existing_session: ChatSessionRecord | None = None
    model_retry: ModelRetryConfig = field(default_factory=ModelRetryConfig)
    answer_synthesizer: ChatAnswerSynthesizer = field(default_factory=ChatAnswerSynthesizer)
    trace: list[ChatToolTraceItem] = field(default_factory=list)
    events: list[ChatEvent] = field(default_factory=list)
    run_links: list[ChatRunLink] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    model_calls: int = 0
    total_usage: dict[str, int] = field(default_factory=dict)
    call_records: list[dict[str, object]] = field(default_factory=list)
    memory_used: list[MemoryRecord] = field(default_factory=list)
    memory_candidates: list[MemoryCandidate] = field(default_factory=list)
    memory_writes: list[MemoryRecord] = field(default_factory=list)
    retrieval_policy: ChatRetrievalPolicy = field(default_factory=ChatRetrievalPolicy)
    plan_adjustments: list[ChatPlanAdjustment] = field(default_factory=list)

    def run(self) -> ChatResponse:
        self._event("chat_started", message="Chat request started.")
        query = latest_user_text(self.current_messages)
        executor = ChatToolExecutor(
            request=self.request,
            services=self.services,
            existing_session=self.existing_session,
            event_callback=self._tool_event,
        )
        observations: list[ChatToolTraceItem] = []
        plans: list[ChatToolPlan] = []
        executed_signatures: set[str] = set()
        stop_reason = "max_turns"
        max_evidence_rounds = max(1, self.request.max_turns - 1)
        evidence_round = 0
        for evidence_round in range(1, max_evidence_rounds + 1):
            plan = self._plan_tools(query, observations=observations, turn=evidence_round)
            plans.append(plan)
            if _plan_is_finish(plan):
                if observations or _query_allows_direct_answer(query):
                    stop_reason = "planner_finished"
                    break
                plan = ChatToolPlan(
                    tool_calls=[{"name": "query_wiki", "arguments": {"query": query, "mode": "balanced", "max_results": 6}}],
                    reason="Planner tried to finish without evidence; KnoArbor requires wiki evidence for knowledge questions.",
                    confidence=min(plan.confidence, 0.5),
                )
                plans[-1] = plan
            executable_plan = _executable_plan(plan)
            if not executable_plan.tool_calls:
                stop_reason = "no_executable_tools"
                break
            signatures = [_tool_signature(call.name, call.arguments) for call in executable_plan.tool_calls]
            if all(signature in executed_signatures for signature in signatures):
                stop_reason = "repeated_tool_plan"
                break
            executed_signatures.update(signatures)
            round_observations = executor.execute(executable_plan, query)
            observations.extend(round_observations)
            self.trace.extend(round_observations)
            if _plan_contains_direct_answer(executable_plan):
                stop_reason = "direct_answer"
                break
            if not _needs_more_evidence(round_observations):
                stop_reason = "evidence_sufficient"
                break
        answer_turn = evidence_round + 1
        self._event("model_call_started", message="Calling chat answer model.", turn=answer_turn, payload={"phase": "answer"})
        answer_result = self.answer_synthesizer.synthesize(
            client=self.client,
            request=self.request,
            initial_messages=self.initial_messages,
            current_messages=self.current_messages,
            existing_session=self.existing_session,
            observations=observations,
            turn=answer_turn,
            max_tokens=_max_tokens(self.request),
            retry=self.model_retry,
        )
        self.model_calls += 1
        _merge_usage(self.total_usage, answer_result.completion.usage)
        self._event(
            "model_call_finished",
            message="Chat answer model call finished.",
            turn=answer_turn,
            payload={"usage": answer_result.completion.usage, "elapsed_seconds": answer_result.completion.elapsed_seconds},
        )
        self.call_records.append(answer_result.call_record)
        response = self._answer_response(answer_result.draft, turns=answer_turn)
        response.stats["retrieval_strategy"] = "model_planned_tools"
        response.stats["tool_plan"] = plans[0].model_dump() if plans else {}
        response.stats["tool_plans"] = [plan.model_dump() for plan in plans]
        response.stats["evidence_rounds"] = len(plans)
        response.stats["evidence_stop_reason"] = stop_reason
        response.stats["plan_adjustments"] = [adjustment.__dict__ for adjustment in self.plan_adjustments]
        return response

    def _plan_tools(self, query: str, *, observations: list[ChatToolTraceItem], turn: int) -> ChatToolPlan:
        messages = _tool_plan_messages(self.initial_messages, self.existing_session, observations, query=query)
        prompt_chars = messages_chars(messages)
        self._event("model_call_started", message="Calling chat tool planner.", turn=turn, payload={"phase": "tool_plan"})
        call = run_chat_model_call(
            client=self.client,
            request=ChatCompletionRequest(
                messages=messages,
                temperature=0,
                max_tokens=min(_max_tokens(self.request) or 4096, 4096),
            ),
            retry=self.model_retry,
            phase="tool_plan",
            turn=turn,
            prompt_chars=prompt_chars,
        )
        completion = call.completion
        self.model_calls += 1
        _merge_usage(self.total_usage, completion.usage)
        self._event(
            "model_call_finished",
            message="Chat tool planner finished.",
            turn=turn,
            payload={"usage": completion.usage, "elapsed_seconds": completion.elapsed_seconds},
        )
        self.call_records.append(call.call_record)
        plan = _parse_tool_plan(completion.content)
        if not plan.tool_calls:
            return ChatToolPlan(tool_calls=[{"name": "query_wiki", "arguments": {"query": query}}], reason="Planner returned no action.", confidence=0.0)
        guarded = _guard_tool_plan(plan, query)
        adjusted, adjustment = self.retrieval_policy.adjust_plan(
            guarded,
            query=query,
            existing_session=self.existing_session,
            observations=observations,
        )
        if adjustment:
            self.plan_adjustments.append(adjustment)
        return adjusted

    def _answer_response(self, draft: ChatAnswerDraft, turns: int) -> ChatResponse:
        citations = final_citations(draft.citations, self.trace, answer=draft.answer)
        answer = clean_answer_citation_paths(draft.answer, answer_cleanup_citations(self.trace, citations), latest_user_text=latest_user_text(self.current_messages))
        self._capture_memory()
        self._event("final_answer_ready", message="Final chat answer is ready.", turn=turns, payload={"citation_count": len(citations)})
        return ChatResponse(
            session_id=self.request.session_id,
            answer=answer,
            messages=[*self.request.messages, ChatMessageItem(role="assistant", content=answer)],
            citations=citations,
            tool_trace=self.trace if self.request.include_trace else [],
            events=self.events,
            run_links=self.run_links,
            memory_used=self.memory_used,
            memory_candidates=self.memory_candidates,
            memory_writes=self.memory_writes,
            stats=self._stats(turns),
            warnings=self.warnings,
        )

    def _stats(self, turns: int) -> dict[str, Any]:
        return {
            "turns": turns,
            "model_calls": self.model_calls,
            "tool_calls": len(self.trace),
            "memory_used": len(self.memory_used),
            "memory_candidates": len(self.memory_candidates),
            "memory_writes": len(self.memory_writes),
            "usage": dict(self.total_usage),
            "total_tokens": self.total_usage.get("total_tokens", 0),
        }

    def _capture_memory(self) -> None:
        target = memory_target(self.request)
        if target is None:
            return
        config = load_config(Path(self.request.config_path).expanduser().resolve() if self.request.config_path else default_config_path())
        candidates, writes = self.services.memory.capture_explicit_memory(
            vault_path=target.path,
            vault_id=target.vault_id,
            messages=self.current_messages,
            config=config.memory,
            chat_id=self.chat_id,
        )
        self.memory_candidates = candidates
        self.memory_writes = writes

    def _event(
        self,
        event_type: str,
        *,
        message: str = "",
        tool: str | None = None,
        turn: int | None = None,
        status: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        event = ChatEvent(
            event_type=event_type,  # type: ignore[arg-type]
            created_at=current_timestamp(),
            message=message,
            tool=tool,
            turn=turn,
            status=status,  # type: ignore[arg-type]
            payload=payload or {},
        )
        self.events.append(event)
        LOGGER.info(
            "chat_event chat_id=%s event=%s turn=%s tool=%s status=%s usage=%s elapsed_seconds=%s",
            self.chat_id,
            event_type,
            turn,
            tool or "-",
            status or "-",
            _event_usage(payload),
            _event_elapsed(payload),
        )

    def _tool_event(self, event_type: str, message: str, tool: str | None, turn: int | None, status: str | None) -> None:
        self._event(event_type, message=message, tool=tool, turn=turn, status=status)

def _client_from_request(request: ChatRequest) -> ChatClient:
    config = load_config(Path(request.config_path).expanduser().resolve() if request.config_path else default_config_path())
    provider = request.provider or config.models.default_provider
    if not provider:
        raise UserInputError("No model provider configured for chat.")
    provider_config = config.models.providers.get(provider)
    if provider_config is None:
        raise UserInputError(f"Unknown model provider: {provider}")
    return ModelGateway.from_config(provider, provider_config, timeout_seconds=config.models.request_timeout_seconds)


def _max_tokens(request: ChatRequest) -> int | None:
    if request.max_tokens is not None:
        return request.max_tokens
    config = load_config(Path(request.config_path).expanduser().resolve() if request.config_path else default_config_path())
    return config.models.resolve_max_tokens(request.provider)


def _append_chat_ledger(request: ChatRequest, response: ChatResponse, calls: list[dict[str, object]]) -> None:
    vault = session_target(request)
    tool_plan = response.stats.get("tool_plan") if isinstance(response.stats.get("tool_plan"), dict) else {}
    first_call = (tool_plan.get("tool_calls") or [{}])[0] if isinstance(tool_plan.get("tool_calls"), list) else {}
    first_arguments = first_call.get("arguments") if isinstance(first_call, dict) else {}
    retrieval_mode = first_arguments.get("mode") if isinstance(first_arguments, dict) else None
    append_chat_token_records(
        vault.path,
        {
            "chat_id": response.stats.get("chat_id"),
            "created_at": current_timestamp(),
            "finished_at": current_timestamp(),
            "mode": retrieval_mode or "model_planned",
            "provider": response.stats.get("provider"),
            "model": response.stats.get("model"),
            "calls": calls,
            "citations": [citation.model_dump() for citation in response.citations],
            "tool_trace": [item.model_dump() for item in response.tool_trace],
        },
    )


def _event_usage(payload: dict[str, Any] | None) -> str:
    if not payload:
        return "-"
    usage = payload.get("usage")
    if not isinstance(usage, dict):
        return "-"
    total = usage.get("total_tokens")
    prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")
    if total is None and prompt is None and completion is None:
        return "-"
    return f"total={total or 0},prompt={prompt or 0},completion={completion or 0}"


def _event_elapsed(payload: dict[str, Any] | None) -> str:
    if not payload or payload.get("elapsed_seconds") is None:
        return "-"
    return str(payload.get("elapsed_seconds"))


def _parse_tool_plan(content: str) -> ChatToolPlan:
    payload = parse_json_object(content)
    try:
        return ChatToolPlan.model_validate(payload)
    except (ValidationError, ValueError) as exc:
        raise ModelOutputError(f"Chat tool planner returned invalid JSON: {exc}") from exc


def _tool_plan_messages(
    initial_messages: list[ChatMessage],
    existing_session: ChatSessionRecord | None,
    observations: list[ChatToolTraceItem] | None = None,
    *,
    query: str,
) -> list[ChatMessage]:
    planning_state = {
        "latest_user_message": query,
        "recent_user_messages": _recent_user_messages(initial_messages),
        "recent_turns": _planner_recent_turns(existing_session),
        "workspace_context": _workspace_planning_context(initial_messages),
        "prior_evidence_context": _prior_evidence_context(existing_session),
        "current_turn_evidence_context": _current_evidence_context(observations or []),
    }
    return [
        ChatMessage(role="system", content=TOOL_PLAN_PROMPT),
        ChatMessage(role="user", content=json.dumps({"planning_state": planning_state}, ensure_ascii=False)),
    ]


def _recent_user_messages(messages: list[ChatMessage]) -> list[str]:
    return _unique_strings([message.content for message in messages if message.role == "user"])[-6:]


def _planner_recent_turns(existing_session: ChatSessionRecord | None) -> list[dict[str, object]]:
    if existing_session is None:
        return []
    turns = []
    for turn in existing_session.turns[-4:]:
        answer_paths, source_paths = _turn_evidence_page_roles(turn.tool_trace)
        turns.append(
            {
                "index": turn.index,
                "user_message": _compact_text(turn.user_message.content, 500),
                "citation_paths": [citation.path for citation in turn.citations if citation.path],
                "answer_page_paths": answer_paths,
                "source_page_paths": source_paths,
                "tool_summaries": _unique_strings([item.summary for item in turn.tool_trace if item.summary])[-4:],
            }
        )
    return turns


def _turn_evidence_page_roles(trace: list[ChatToolTraceItem]) -> tuple[list[str], list[str]]:
    answer_page_paths: list[str] = []
    source_page_paths: list[str] = []
    for item in trace:
        tool_answer_paths, tool_source_paths = _evidence_page_roles(item.result.get("evidence_pack"))
        answer_page_paths.extend(tool_answer_paths)
        source_page_paths.extend(tool_source_paths)
        if item.tool == "read_wiki_page" and item.result.get("path"):
            path = str(item.result["path"])
            if path.startswith("sources/"):
                source_page_paths.append(path)
            else:
                answer_page_paths.append(path)
    return _unique_strings(answer_page_paths), _unique_strings(source_page_paths)


def _compact_text(text: str, max_chars: int) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max(0, max_chars - 1)].rstrip() + "…"


def _workspace_planning_context(messages: list[ChatMessage]) -> dict[str, object]:
    for message in messages:
        if message.role != "system" or not message.content.startswith("Workspace context:"):
            continue
        _, _, raw = message.content.partition("\n")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}
    return {}


def _guard_tool_plan(plan: ChatToolPlan, query: str) -> ChatToolPlan:
    if not plan.tool_calls:
        return plan
    if any(call.name not in {"answer_directly", "finish_answer"} for call in plan.tool_calls):
        return plan
    if any(call.name == "finish_answer" for call in plan.tool_calls):
        return plan
    if _query_allows_direct_answer(query):
        return plan
    return ChatToolPlan(
        tool_calls=[{"name": "query_wiki", "arguments": {"query": query, "mode": "balanced", "max_results": 6}}],
        reason=f"Planner selected answer_directly for a knowledge request; KnoArbor requires wiki evidence. {plan.reason}".strip(),
        confidence=min(plan.confidence, 0.5),
    )


def _plan_is_finish(plan: ChatToolPlan) -> bool:
    return bool(plan.tool_calls) and all(call.name == "finish_answer" for call in plan.tool_calls)


def _plan_contains_direct_answer(plan: ChatToolPlan) -> bool:
    return any(call.name == "answer_directly" for call in plan.tool_calls)


def _executable_plan(plan: ChatToolPlan) -> ChatToolPlan:
    return plan.model_copy(update={"tool_calls": [call for call in plan.tool_calls if call.name != "finish_answer"]})


def _tool_signature(name: str, arguments: dict[str, Any]) -> str:
    return json.dumps({"name": name, "arguments": arguments}, ensure_ascii=False, sort_keys=True)


def _needs_more_evidence(observations: list[ChatToolTraceItem]) -> bool:
    if not observations:
        return True
    if any(item.status == "error" for item in observations):
        return True
    if any(item.tool == "read_wiki_page" and item.status == "ok" for item in observations):
        return False
    for item in observations:
        pack = item.result.get("evidence_pack")
        if not isinstance(pack, dict):
            continue
        coverage = pack.get("evidence_coverage") if isinstance(pack.get("evidence_coverage"), dict) else {}
        if pack.get("recommended_action") != "answer_from_evidence":
            return True
        if coverage.get("status") == "weak":
            return True
        if not pack.get("primary_pages") and not pack.get("primary_page"):
            return True
    return False


def _current_evidence_context(observations: list[ChatToolTraceItem]) -> dict[str, object]:
    if not observations:
        return {}
    items = []
    primary_paths: list[str] = []
    coverage_statuses: list[str] = []
    recommended_actions: list[str] = []
    missing_facets: list[str] = []
    executed_queries: list[str] = []
    failed_tools: list[str] = []
    for item in observations[-6:]:
        pack = item.result.get("evidence_pack")
        coverage = pack.get("evidence_coverage") if isinstance(pack, dict) and isinstance(pack.get("evidence_coverage"), dict) else {}
        item_primary_paths = [str(page.get("path")) for page in pack.get("primary_pages", []) if page.get("path")] if isinstance(pack, dict) else []
        if isinstance(pack, dict) and pack.get("primary_page") and isinstance(pack.get("primary_page"), dict) and pack["primary_page"].get("path"):
            item_primary_paths.append(str(pack["primary_page"]["path"]))
        primary_paths.extend(item_primary_paths)
        if item.status == "error":
            failed_tools.append(item.tool)
        if isinstance(coverage, dict) and coverage.get("status"):
            coverage_statuses.append(str(coverage["status"]))
        if isinstance(coverage, dict):
            missing_facets.extend(str(facet) for facet in coverage.get("missing_facets", []) if str(facet).strip())
        if isinstance(pack, dict) and pack.get("recommended_action"):
            recommended_actions.append(str(pack["recommended_action"]))
        if item.tool == "query_wiki" and item.arguments.get("query"):
            executed_queries.append(str(item.arguments["query"]))
        items.append(
            {
                "tool": item.tool,
                "status": item.status,
                "summary": item.summary,
                "arguments": item.arguments,
                "citation_paths": [citation.path for citation in item.citations if citation.path],
                "recommended_action": pack.get("recommended_action") if isinstance(pack, dict) else None,
                "coverage_status": coverage.get("status") if isinstance(coverage, dict) else None,
                "primary_paths": item_primary_paths,
            }
        )
    return {
        "summary": {
            "has_primary_page": bool(primary_paths),
            "primary_paths": _unique_strings(primary_paths),
            "coverage_statuses": _unique_strings(coverage_statuses),
            "recommended_actions": _unique_strings(recommended_actions),
            "missing_facets": _unique_strings(missing_facets),
            "executed_queries": _unique_strings(executed_queries),
            "failed_tools": _unique_strings(failed_tools),
            "needs_more_evidence": _needs_more_evidence(observations),
            "recommended_next_step": _recommended_next_evidence_step(observations),
        },
        "observations": items,
    }


def _recommended_next_evidence_step(observations: list[ChatToolTraceItem]) -> str:
    if not observations:
        return "query_wiki"
    if any(item.status == "error" for item in observations):
        return "retry_or_refine_tool"
    if not _needs_more_evidence(observations):
        return "finish_answer"
    for item in observations:
        pack = item.result.get("evidence_pack")
        if not isinstance(pack, dict):
            continue
        primary_pages = pack.get("primary_pages") if isinstance(pack.get("primary_pages"), list) else []
        if primary_pages:
            first = primary_pages[0]
            if isinstance(first, dict) and first.get("path"):
                return "read_wiki_page"
        if pack.get("recommended_action") == "read_primary_if_detail_needed":
            return "read_wiki_page"
    return "query_wiki"


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def _query_allows_direct_answer(query: str) -> bool:
    text = query.strip().lower()
    if not text:
        return True
    direct_phrases = {
        "hi",
        "hello",
        "hey",
        "你好",
        "您好",
        "你是谁",
        "你能做什么",
        "你可以做什么",
        "help",
        "帮助",
        "怎么用",
        "如何使用",
    }
    if text in direct_phrases:
        return True
    ui_terms = ("按钮", "页面", "界面", "设置", "菜单", "sidebar", "ui", "interface")
    return any(term in text for term in ui_terms) and not any(term in text for term in ("是什么", "原理", "架构", "区别", "对比", "流程", "机制"))


def _prior_evidence_context(existing_session: ChatSessionRecord | None) -> dict[str, object]:
    if existing_session is None:
        return {}
    recent_turns = existing_session.turns[-4:]
    turn_citations = [citation for turn in recent_turns for citation in turn.citations]
    citations = [citation.model_dump(mode="json") for citation in (turn_citations or existing_session.citations)[:8]]
    reusable_tools = []
    answer_page_paths: list[str] = []
    source_page_paths: list[str] = []
    trace_items = [item for turn in recent_turns for item in turn.tool_trace] or existing_session.tool_trace
    for item in trace_items[-4:]:
        if item.status != "ok":
            continue
        if item.tool not in {"query_wiki", "search_wiki", "read_wiki_page", "reuse_context"}:
            continue
        pack = item.result.get("evidence_pack")
        tool_answer_paths, tool_source_paths = _evidence_page_roles(pack)
        answer_page_paths.extend(tool_answer_paths)
        source_page_paths.extend(tool_source_paths)
        reusable_tools.append(
            {
                "tool": item.tool,
                "summary": item.summary,
                "arguments": item.arguments,
                "citation_paths": [citation.path for citation in item.citations if citation.path],
                "has_evidence_pack": isinstance(item.result.get("evidence_pack"), dict),
                "answer_page_paths": tool_answer_paths,
                "source_page_paths": tool_source_paths,
            }
        )
    return {
        "session_id": existing_session.session_id,
        "citations": citations,
        "answer_page_paths": _unique_strings(answer_page_paths),
        "source_page_paths": _unique_strings(source_page_paths),
        "preferred_read_pages": _unique_strings(answer_page_paths),
        "reusable_tools": reusable_tools,
    }


def _evidence_page_roles(pack: object) -> tuple[list[str], list[str]]:
    if not isinstance(pack, dict):
        return [], []
    answer_paths: list[str] = []
    source_paths: list[str] = []
    for key in ("primary_pages", "supporting_pages"):
        pages = pack.get(key) if isinstance(pack.get(key), list) else []
        for page in pages:
            if not isinstance(page, dict) or not page.get("path"):
                continue
            path = str(page["path"])
            if page.get("type") == "source" or path.startswith("sources/"):
                source_paths.append(path)
            else:
                answer_paths.append(path)
    primary_page = pack.get("primary_page")
    if isinstance(primary_page, dict) and primary_page.get("path"):
        path = str(primary_page["path"])
        if primary_page.get("type") == "source" or path.startswith("sources/"):
            source_paths.append(path)
        else:
            answer_paths.append(path)
    pages = pack.get("source_pages") if isinstance(pack.get("source_pages"), list) else []
    for page in pages:
        if isinstance(page, dict) and page.get("path"):
            source_paths.append(str(page["path"]))
    return _unique_strings(answer_paths), _unique_strings(source_paths)


def _merge_usage(target: dict[str, int], usage: dict[str, int]) -> None:
    for key, value in usage.items():
        target[key] = target.get(key, 0) + int(value)
