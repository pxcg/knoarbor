from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from pydantic import ValidationError

from knoarbor.audit.token_ledger import append_chat_token_records, current_timestamp
from knoarbor.core.config import default_config_path, load_config
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
from knoarbor.services.chat_answer import ChatAnswerSynthesizer, clean_answer_citation_paths, final_citations, messages_chars, parse_json_object
from knoarbor.services.chat_context import ChatContextEngine, latest_user_text, memory_target, session_target
from knoarbor.services.chat_tools import ChatToolExecutor
from knoarbor.semantic.contracts import load_prompt
from knoarbor.semantic.llm import ChatClient, ChatCompletionRequest, ChatMessage, ModelGateway

if TYPE_CHECKING:
    from knoarbor.services import ApplicationServices


ANSWER_SYNTHESIS_PROMPT = load_prompt("wiki_chat_answer.md")
TOOL_PLAN_PROMPT = load_prompt("wiki_chat_tool_plan.md")


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
            current_messages=request.messages,
            services=services,
            client=client,
            chat_id=chat_id,
            initial_messages=context.model_messages,
            existing_session=existing_session,
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

    def run(self) -> ChatResponse:
        self._event("chat_started", message="Chat request started.")
        query = latest_user_text(self.current_messages)
        plan = self._plan_tools(query)
        executor = ChatToolExecutor(
            request=self.request,
            services=self.services,
            existing_session=self.existing_session,
            event_callback=self._tool_event,
        )
        observations = executor.execute(plan, query)
        self.trace.extend(observations)
        self._event("model_call_started", message="Calling chat answer model.", turn=2, payload={"phase": "answer"})
        answer_result = self.answer_synthesizer.synthesize(
            client=self.client,
            request=self.request,
            initial_messages=self.initial_messages,
            current_messages=self.current_messages,
            observations=observations,
            turn=2,
            max_tokens=_max_tokens(self.request),
        )
        self.model_calls += 1
        _merge_usage(self.total_usage, answer_result.completion.usage)
        self._event(
            "model_call_finished",
            message="Chat answer model call finished.",
            turn=2,
            payload={"usage": answer_result.completion.usage, "elapsed_seconds": answer_result.completion.elapsed_seconds},
        )
        self.call_records.append(answer_result.call_record)
        response = self._answer_response(answer_result.draft, turns=2)
        response.stats["retrieval_strategy"] = "model_planned_tools"
        response.stats["tool_plan"] = plan.model_dump()
        return response

    def _plan_tools(self, query: str) -> ChatToolPlan:
        messages = _tool_plan_messages(self.initial_messages, self.existing_session)
        prompt_chars = messages_chars(messages)
        call_started = time.perf_counter()
        self._event("model_call_started", message="Calling chat tool planner.", turn=1, payload={"phase": "tool_plan"})
        completion = self.client.complete(
            ChatCompletionRequest(
                messages=messages,
                temperature=0,
                max_tokens=min(_max_tokens(self.request) or 1024, 1024),
            )
        )
        self.model_calls += 1
        _merge_usage(self.total_usage, completion.usage)
        self._event(
            "model_call_finished",
            message="Chat tool planner finished.",
            turn=1,
            payload={"usage": completion.usage, "elapsed_seconds": completion.elapsed_seconds},
        )
        self.call_records.append(
            {
                **completion.usage,
                "provider": completion.provider,
                "model": completion.model,
                "turn": 1,
                "phase": "tool_plan",
                "prompt_chars": prompt_chars,
                "elapsed_seconds": completion.elapsed_seconds or round(time.perf_counter() - call_started, 3),
                "tokens_per_second": completion.tokens_per_second,
            }
        )
        plan = _parse_tool_plan(completion.content)
        if not plan.tool_calls:
            return ChatToolPlan(tool_calls=[{"name": "query_wiki", "arguments": {"query": query}}], reason="Planner returned no action.", confidence=0.0)
        return _guard_tool_plan(plan, query)

    def _answer_response(self, draft: ChatAnswerDraft, turns: int) -> ChatResponse:
        citations = final_citations(draft.citations, self.trace)
        answer = clean_answer_citation_paths(draft.answer, citations, latest_user_text=latest_user_text(self.current_messages))
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
        self.events.append(
            ChatEvent(
                event_type=event_type,  # type: ignore[arg-type]
                created_at=current_timestamp(),
                message=message,
                tool=tool,
                turn=turn,
                status=status,  # type: ignore[arg-type]
                payload=payload or {},
            )
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


def _parse_tool_plan(content: str) -> ChatToolPlan:
    payload = parse_json_object(content)
    try:
        return ChatToolPlan.model_validate(payload)
    except (ValidationError, ValueError) as exc:
        raise ModelOutputError(f"Chat tool planner returned invalid JSON: {exc}") from exc


def _tool_plan_messages(initial_messages: list[ChatMessage], existing_session: ChatSessionRecord | None) -> list[ChatMessage]:
    messages = [ChatMessage(role="system", content=TOOL_PLAN_PROMPT), *initial_messages[1:]]
    prior = _prior_evidence_context(existing_session)
    if prior:
        messages.insert(2, ChatMessage(role="system", content=f"Prior evidence context:\n{json.dumps(prior, ensure_ascii=False)}"))
    return messages


def _guard_tool_plan(plan: ChatToolPlan, query: str) -> ChatToolPlan:
    if not plan.tool_calls:
        return plan
    if any(call.name != "answer_directly" for call in plan.tool_calls):
        return plan
    if _query_allows_direct_answer(query):
        return plan
    return ChatToolPlan(
        tool_calls=[{"name": "query_wiki", "arguments": {"query": query, "mode": "balanced", "max_results": 6}}],
        reason=f"Planner selected answer_directly for a knowledge request; KnoArbor requires wiki evidence. {plan.reason}".strip(),
        confidence=min(plan.confidence, 0.5),
    )


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
    trace_items = [item for turn in recent_turns for item in turn.tool_trace] or existing_session.tool_trace
    for item in trace_items[-4:]:
        if item.status != "ok":
            continue
        if item.tool not in {"query_wiki", "search_wiki", "read_wiki_page", "reuse_context"}:
            continue
        reusable_tools.append(
            {
                "tool": item.tool,
                "summary": item.summary,
                "arguments": item.arguments,
                "citation_paths": [citation.path for citation in item.citations if citation.path],
                "has_evidence_pack": isinstance(item.result.get("evidence_pack"), dict),
            }
        )
    return {
        "session_id": existing_session.session_id,
        "citations": citations,
        "reusable_tools": reusable_tools,
    }


def _merge_usage(target: dict[str, int], usage: dict[str, int]) -> None:
    for key, value in usage.items():
        target[key] = target.get(key, 0) + int(value)
