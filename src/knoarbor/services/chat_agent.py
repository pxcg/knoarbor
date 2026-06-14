from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from pydantic import ValidationError

from knoarbor.audit.token_ledger import append_chat_token_records, current_timestamp
from knoarbor.core.config import default_config_path, load_config
from knoarbor.core.errors import ModelOutputError, UserInputError
from knoarbor.core.schemas.chat import (
    ChatAgentDecision,
    ChatCitation,
    ChatEvent,
    ChatMessageItem,
    ChatRequest,
    ChatResponse,
    ChatRunLink,
    ChatToolTraceItem,
)
from knoarbor.core.schemas.ingest_run import IngestRunRequest
from knoarbor.core.schemas.maintenance import MaintenanceScope, MaintenanceScopeSource
from knoarbor.core.schemas.memory import MemoryCandidate, MemoryRecord
from knoarbor.core.schemas.wiki_lint import LintRunRequest
from knoarbor.core.schemas.wiki_query import WikiSearchRequest, WikiSearchResult
from knoarbor.core.vaults import VIRTUAL_ALL_VAULT_ID
from knoarbor.entrypoints.vault_selection import resolve_single_vault
from knoarbor.services.chat_evidence import ChatEvidencePlanner, search_result_to_chat_payload
from knoarbor.services.chat_context import ChatContextEngine, latest_user_text, memory_target, session_target
from knoarbor.semantic.llm import ChatClient, ChatCompletionRequest, ChatMessage, ModelGateway

if TYPE_CHECKING:
    from knoarbor.services import ApplicationServices


CHAT_LINT_MODES = {
    "deterministic",
    "structural",
    "quality",
    "full",
    "semantic_structural",
    "semantic_quality",
    "semantic_full",
}


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
        context = self.context_engine.build(request, services, chat_id=chat_id, existing_session=existing_session)
        effective_request = request.model_copy(update={"messages": context.conversation_messages, "session_id": chat_id})
        loop = _ChatLoop(
            request=effective_request,
            current_messages=request.messages,
            services=services,
            client=client,
            chat_id=chat_id,
            initial_messages=context.model_messages,
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
    evidence_planner: ChatEvidencePlanner = field(default_factory=ChatEvidencePlanner)
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
        messages = list(self.initial_messages)
        seen_tool_calls: set[str] = set()
        self._event("chat_started", message="Chat request started.")
        for turn in range(self.request.max_turns):
            prompt_chars = _messages_chars(messages)
            call_started = time.perf_counter()
            self._event("model_call_started", message="Calling chat model.", turn=turn + 1)
            completion = self.client.complete(
                ChatCompletionRequest(
                    messages=messages,
                    temperature=0.1,
                    max_tokens=_max_tokens(self.request),
                )
            )
            self.model_calls += 1
            _merge_usage(self.total_usage, completion.usage)
            self._event(
                "model_call_finished",
                message="Chat model call finished.",
                turn=turn + 1,
                payload={"usage": completion.usage, "elapsed_seconds": completion.elapsed_seconds},
            )
            self.call_records.append(
                {
                    **completion.usage,
                    "provider": completion.provider,
                    "model": completion.model,
                    "turn": turn + 1,
                    "prompt_chars": prompt_chars,
                    "elapsed_seconds": completion.elapsed_seconds or round(time.perf_counter() - call_started, 3),
                    "tokens_per_second": completion.tokens_per_second,
                }
            )
            decision = _parse_decision(completion.content)
            if decision.type == "final":
                return self._final_response(decision, turn + 1)

            call_key = json.dumps({"tool": decision.tool, "arguments": decision.arguments}, sort_keys=True, ensure_ascii=False)
            if call_key in seen_tool_calls:
                self.warnings.append(f"Repeated tool call stopped: {decision.tool}")
                return self._fallback_response("我已经尝试过相同的查询步骤，但没有得到新的信息。请补充更具体的页面、报告或主题。", turn + 1)
            seen_tool_calls.add(call_key)

            self._event("tool_call_started", message=f"Calling chat tool {decision.tool}.", tool=decision.tool, turn=turn + 1)
            observation = self._execute_tool(decision.tool or "", decision.arguments)
            self.trace.append(observation)
            self._event(
                "tool_call_failed" if observation.status == "error" else "tool_call_finished",
                message=observation.summary,
                tool=observation.tool,
                turn=turn + 1,
                status=observation.status,
            )
            messages.append(ChatMessage(role="assistant", content=completion.content))
            messages.append(ChatMessage(role="user", content=self._tool_observation_text(observation)))

        self.warnings.append("Max chat agent turns reached.")
        self._event("chat_stopped", message="Max chat agent turns reached.")
        return self._fallback_response("我已经达到本轮对话的工具调用上限。可以换一个更具体的问题，或指定要读取的页面、报告或运行 ID。", self.request.max_turns)

    def _execute_tool(self, tool: str, arguments: dict[str, Any]) -> ChatToolTraceItem:
        try:
            if tool == "search_wiki":
                return self._tool_search_wiki(arguments)
            if tool == "read_wiki_page":
                return self._tool_read_wiki_page(arguments)
            if tool == "list_wiki_pages":
                return self._tool_list_wiki_pages(arguments)
            if tool == "read_report":
                return self._tool_read_report(arguments)
            if tool == "list_runs":
                return self._tool_list_runs(arguments)
            if tool == "list_sources":
                return self._tool_list_sources(arguments)
            if _is_side_effect_tool(tool) and not _side_effect_allowed(tool, latest_user_text(self.current_messages)):
                return ChatToolTraceItem(
                    tool=tool,
                    arguments=arguments,
                    status="skipped",
                    summary="Side-effect tool requires an explicit user request.",
                    result={"reason": "explicit_user_intent_required"},
                )
            if tool == "start_ingest":
                return self._tool_start_ingest(arguments)
            if tool == "start_lint":
                return self._tool_start_lint(arguments)
            if tool == "cancel_run":
                return self._tool_cancel_run(arguments)
            raise UserInputError(f"Unknown chat tool: {tool}")
        except Exception as exc:
            return ChatToolTraceItem(tool=tool, arguments=arguments, status="error", summary=str(exc), result={"error": str(exc)})

    def _tool_search_wiki(self, arguments: dict[str, Any]) -> ChatToolTraceItem:
        query = _required_text(arguments, "query")
        max_results = _bounded_int(arguments.get("max_results"), default=6, minimum=1, maximum=12)
        max_primary_chars = _bounded_int(arguments.get("max_primary_chars"), default=20000, minimum=2000, maximum=50000)
        requested_vault_id = _concrete_argument_vault_id(arguments, self.request.vault_id)
        request = WikiSearchRequest(
            config_path=self.request.config_path,
            vault_path=self.request.vault_path,
            vault_id=requested_vault_id,
            vault_ids=[str(item) for item in arguments.get("vault_ids", self.request.vault_ids) or []],
            all_vaults=bool(arguments.get("all_vaults", self.request.all_vaults or self.request.vault_id == VIRTUAL_ALL_VAULT_ID)),
            query=query,
            mode=arguments.get("mode") if arguments.get("mode") in {"quick", "balanced", "deep"} else self.request.mode,
            page_dirs=[str(item) for item in arguments.get("page_dirs", []) if str(item).strip()],
            max_results=max_results,
            include_content=True,
            max_chars_per_page=max_primary_chars,
            record_query=False,
            write_report=False,
            caller="chat",
        )
        response = self.services.wiki_search.search(request)
        primary = response.primary_pages[0] if response.primary_pages else _fallback_primary_result(response.results, query)
        supporting = (
            response.supporting_pages
            or [
                item
                for item in response.results
                if primary
                and item.path != primary.path
                and item.type != "source"
            ]
        )[:5]
        source_pages = (response.source_pages or [item for item in response.results if item.role == "source" or item.type == "source"])[:5]
        citations = [
            ChatCitation(
                kind="page",
                role=result.role,
                path=result.path,
                title=result.title,
                vault_id=result.vault_id,
                vault_name=result.vault_name,
                vault_path=result.vault_path,
                reason=result.reason,
            )
            for result in _primary_first_results(response.results, primary)
        ]
        result = {
            "query": response.query,
            "result_count": len(response.results),
            "answer_scope": response.answer_scope.model_dump(),
            "answer_set": response.answer_set.model_dump(),
            "evidence_coverage": response.evidence_coverage.model_dump(),
            "retrieval": {
                "mode": response.retrieval_mode,
                "scoring_model": response.trace.get("scoring_model") or response.stats.get("scoring_model"),
            },
            "primary_page": {
                "path": primary.path,
                "title": primary.title,
                "type": primary.type,
                "score": primary.score,
                "relevance": primary.relevance,
                "summary": primary.summary,
                "key_points": primary.key_points[:8],
                "content": primary.content or "",
                "content_truncated": primary.content_truncated,
                "vault_id": primary.vault_id,
                "vault_name": primary.vault_name,
            }
            if primary
            else None,
            "supporting_pages": [_chat_supporting_page_payload(item) for item in supporting],
            "source_pages": [_chat_supporting_page_payload(item) for item in source_pages],
            "results": [search_result_to_chat_payload(item) for item in response.results],
            "warnings": response.warnings,
        }
        result["evidence_pack"] = self.evidence_planner.build_search_pack(
            query=response.query,
            result_count=len(response.results),
            answer_scope=result["answer_scope"],
            answer_set=result["answer_set"],
            evidence_coverage=result["evidence_coverage"],
            primary_page=result["primary_page"],
            supporting_pages=result["supporting_pages"],
            source_pages=result["source_pages"],
            results=result["results"],
            warnings=response.warnings,
        ).payload
        return ChatToolTraceItem(tool="search_wiki", arguments=arguments, summary=f"Found {len(response.results)} wiki result(s).", citations=citations, result=result)

    def _tool_read_wiki_page(self, arguments: dict[str, Any]) -> ChatToolTraceItem:
        path = _required_text(arguments, "path")
        max_chars = _bounded_int(arguments.get("max_chars"), default=12000, minimum=1000, maximum=50000)
        vault = resolve_single_vault(None if "vault_id" in arguments else self.request.vault_path, _concrete_argument_vault_id(arguments, self.request.vault_id), self.request.config_path)
        page = self.services.wiki_pages.read_page(vault.path, path, vault_id=vault.vault_id, vault_name=vault.vault_name)
        content = page.content
        truncated = len(content) > max_chars
        result = {
            "path": page.path,
            "title": page.summary.title,
            "summary": page.summary.summary,
            "content": content[:max_chars],
            "truncated": truncated,
            "outbound_links": [link.model_dump() for link in page.outbound_links],
            "backlinks": [link.model_dump() for link in page.backlinks],
        }
        citation = ChatCitation(kind="page", path=page.path, title=page.summary.title, vault_id=vault.vault_id, vault_name=vault.vault_name, vault_path=str(vault.path))
        return ChatToolTraceItem(tool="read_wiki_page", arguments=arguments, summary=f"Read page {page.path}{' (truncated)' if truncated else ''}.", citations=[citation], result=result)

    def _tool_list_wiki_pages(self, arguments: dict[str, Any]) -> ChatToolTraceItem:
        vault = resolve_single_vault(None if "vault_id" in arguments else self.request.vault_path, _concrete_argument_vault_id(arguments, self.request.vault_id), self.request.config_path)
        pages = self.services.wiki_pages.list_pages(vault.path, vault_id=vault.vault_id, vault_name=vault.vault_name).pages
        page_dir = str(arguments.get("page_dir") or "").strip()
        if page_dir:
            pages = [page for page in pages if page.directory == page_dir]
        limit = _bounded_int(arguments.get("limit"), default=30, minimum=1, maximum=100)
        selected = pages[:limit]
        return ChatToolTraceItem(
            tool="list_wiki_pages",
            arguments=arguments,
            summary=f"Listed {len(selected)} page(s).",
            citations=[ChatCitation(kind="page", path=page.path, title=page.title, vault_id=vault.vault_id, vault_name=vault.vault_name, vault_path=str(vault.path)) for page in selected],
            result={"pages": [page.model_dump() for page in selected], "total_pages": len(pages)},
        )

    def _tool_read_report(self, arguments: dict[str, Any]) -> ChatToolTraceItem:
        path = _required_text(arguments, "path")
        max_chars = _bounded_int(arguments.get("max_chars"), default=12000, minimum=1000, maximum=50000)
        vault = resolve_single_vault(None if "vault_id" in arguments else self.request.vault_path, _concrete_argument_vault_id(arguments, self.request.vault_id), self.request.config_path)
        report = self.services.wiki_reports.read_report(vault.path, path, vault_id=vault.vault_id, vault_name=vault.vault_name)
        content = report.content
        truncated = len(content) > max_chars
        citation = ChatCitation(kind="report", path=report.path, title=report.summary.title, vault_id=vault.vault_id, vault_name=vault.vault_name, vault_path=str(vault.path))
        return ChatToolTraceItem(
            tool="read_report",
            arguments=arguments,
            summary=f"Read report {report.path}{' (truncated)' if truncated else ''}.",
            citations=[citation],
            result={"path": report.path, "title": report.summary.title, "kind": report.summary.kind, "content": content[:max_chars], "truncated": truncated},
        )

    def _tool_list_runs(self, arguments: dict[str, Any]) -> ChatToolTraceItem:
        vault = resolve_single_vault(None if "vault_id" in arguments else self.request.vault_path, _concrete_argument_vault_id(arguments, self.request.vault_id), self.request.config_path)
        limit = _bounded_int(arguments.get("limit"), default=10, minimum=1, maximum=50)
        active_only = bool(arguments.get("active_only", False))
        response = self.services.runs.list(str(vault.path), active_only=active_only, limit=limit, vault_id=vault.vault_id, vault_name=vault.vault_name)
        citations = [ChatCitation(kind="run", run_id=run.run_id, title=run.message, vault_id=run.vault_id, vault_name=run.vault_name, vault_path=run.vault_path) for run in response.runs]
        return ChatToolTraceItem(tool="list_runs", arguments=arguments, summary=f"Listed {len(response.runs)} run(s).", citations=citations, result={"runs": [run.model_dump() for run in response.runs]})

    def _tool_list_sources(self, arguments: dict[str, Any]) -> ChatToolTraceItem:
        response = self.services.source_catalog.list_catalog(config_path=self.request.config_path)
        return ChatToolTraceItem(tool="list_sources", arguments=arguments, summary=f"Listed {len(response.connectors)} source connector(s).", result=response.model_dump())

    def _tool_start_ingest(self, arguments: dict[str, Any]) -> ChatToolTraceItem:
        connector_names = [str(item) for item in arguments.get("connector_names", []) if str(item).strip()]
        request = IngestRunRequest(config_path=self.request.config_path, vault_path=self.request.vault_path, vault_id=self.request.vault_id, connector_names=connector_names or None, write=True, write_report=True, append_ledger=True)
        started = self.services.runs.start_ingest(request, self.services.ingest.run)
        self.run_links.append(ChatRunLink(flow="ingest", run_id=started.run_id, status=started.status, vault_id=started.run.vault_id, vault_name=started.run.vault_name, vault_path=started.run.vault_path))
        return ChatToolTraceItem(tool="start_ingest", arguments=arguments, summary=f"Queued ingest run {started.run_id}.", result=started.model_dump())

    def _tool_start_lint(self, arguments: dict[str, Any]) -> ChatToolTraceItem:
        requested_mode = str(arguments.get("mode") or "deterministic")
        mode = requested_mode if requested_mode in CHAT_LINT_MODES else "deterministic"
        scope = MaintenanceScope(
            scope_id="chat:manual",
            trigger="manual",
            source=MaintenanceScopeSource(kind="chat"),
            global_checks=["structure", "provenance", "graph"],
            reason="Queued from KnoArbor chat by explicit user request.",
        )
        request = LintRunRequest(config_path=self.request.config_path, vault_path=self.request.vault_path, vault_id=self.request.vault_id, scope=scope, mode=mode, write_report=True, append_ledger=True)
        started = self.services.runs.start_lint(request, self.services.wiki_linter.run_maintenance)
        self.run_links.append(ChatRunLink(flow="lint", run_id=started.run_id, status=started.status, vault_id=started.run.vault_id, vault_name=started.run.vault_name, vault_path=started.run.vault_path))
        return ChatToolTraceItem(tool="start_lint", arguments=arguments, summary=f"Queued lint run {started.run_id}.", result=started.model_dump())

    def _tool_cancel_run(self, arguments: dict[str, Any]) -> ChatToolTraceItem:
        run_id = _required_text(arguments, "run_id")
        vault = resolve_single_vault(self.request.vault_path, self.request.vault_id, self.request.config_path)
        run = self.services.runs.cancel(str(vault.path), run_id, vault_id=vault.vault_id, vault_name=vault.vault_name)
        return ChatToolTraceItem(tool="cancel_run", arguments=arguments, summary=f"Cancellation requested for {run.run_id}.", result=run.model_dump())

    def _final_response(self, decision: ChatAgentDecision, turns: int) -> ChatResponse:
        citations = _final_citations(decision.citations, self.trace)
        answer = _clean_answer_citation_paths(decision.answer or "", citations, latest_user_text=latest_user_text(self.current_messages))
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

    def _fallback_response(self, answer: str, turns: int) -> ChatResponse:
        self._capture_memory()
        return ChatResponse(
            session_id=self.request.session_id,
            answer=answer,
            messages=[*self.request.messages, ChatMessageItem(role="assistant", content=answer)],
            citations=_unique_citations(citation for item in self.trace for citation in item.citations),
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

    def _tool_observation_text(self, observation: ChatToolTraceItem) -> str:
        return json.dumps(
            self.evidence_planner.project_tool_observation(
                observation.tool,
                observation.status,
                observation.summary,
                observation.result,
            ),
            ensure_ascii=False,
        )


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
    append_chat_token_records(
        vault.path,
        {
            "chat_id": response.stats.get("chat_id"),
            "created_at": current_timestamp(),
            "finished_at": current_timestamp(),
            "mode": request.mode,
            "provider": response.stats.get("provider"),
            "model": response.stats.get("model"),
            "calls": calls,
            "citations": [citation.model_dump() for citation in response.citations],
            "tool_trace": [item.model_dump() for item in response.tool_trace],
        },
    )


def _parse_decision(content: str) -> ChatAgentDecision:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        payload = json.loads(text)
        return ChatAgentDecision.model_validate(payload)
    except (json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise ModelOutputError(f"Chat agent returned invalid decision JSON: {exc}") from exc


def _primary_first_results(results: list[WikiSearchResult], primary: WikiSearchResult | None) -> list[WikiSearchResult]:
    if primary is None:
        return results
    return [primary, *[result for result in results if not (result.path == primary.path and result.vault_id == primary.vault_id)]]


def _fallback_primary_result(results: list[WikiSearchResult], query: str) -> WikiSearchResult | None:
    if _query_prefers_source_page(query):
        return results[0] if results else None
    for result in results:
        if result.role == "primary":
            return result
    for result in results:
        if result.type != "source":
            return result
    return results[0] if results else None


def _query_prefers_source_page(query: str) -> bool:
    text = query.lower()
    return any(term in text for term in {"source", "provenance", "raw", "digest", "来源", "原始", "溯源", "出处", "source digest"})


def _chat_supporting_page_payload(item: WikiSearchResult) -> dict[str, object]:
    excerpt_limit = 1800 if item.type != "source" else 900
    return {
        "path": item.path,
        "title": item.title,
        "type": item.type,
        "role": item.role,
        "score": item.score,
        "relevance": item.relevance,
        "summary": item.summary,
        "key_points": item.key_points[:6],
        "content_excerpt": (item.content or "")[:excerpt_limit],
        "content_truncated": bool(item.content and len(item.content) > excerpt_limit),
        "vault_id": item.vault_id,
        "vault_name": item.vault_name,
    }



def _messages_chars(messages: list[ChatMessage]) -> int:
    return sum(len(message.content) for message in messages)


def _required_text(arguments: dict[str, Any], key: str) -> str:
    value = str(arguments.get(key) or "").strip()
    if not value:
        raise UserInputError(f"Chat tool argument is required: {key}")
    return value


def _bounded_int(value: object, *, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value) if value is not None else default
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def _concrete_argument_vault_id(arguments: dict[str, Any], fallback: str | None) -> str | None:
    value = arguments.get("vault_id", fallback)
    vault_id = str(value).strip() if value is not None else ""
    if not vault_id or vault_id == VIRTUAL_ALL_VAULT_ID:
        return None
    return vault_id


def _merge_usage(target: dict[str, int], usage: dict[str, int]) -> None:
    for key, value in usage.items():
        target[key] = target.get(key, 0) + int(value)


def _unique_citations(citations: list[ChatCitation] | Any) -> list[ChatCitation]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[ChatCitation] = []
    for citation in citations:
        target = citation.path or citation.run_id or ""
        vault_identity = citation.vault_id or citation.vault_path or ""
        if not vault_identity and any(existing.kind == citation.kind and (existing.path or existing.run_id or "") == target and (existing.vault_id or existing.vault_path) for existing in unique):
            continue
        if vault_identity:
            unique = [
                existing
                for existing in unique
                if not (
                    existing.kind == citation.kind
                    and (existing.path or existing.run_id or "") == target
                    and not (existing.vault_id or existing.vault_path)
                )
            ]
            seen = {
                (existing.kind, existing.path or existing.run_id or "", existing.vault_id or existing.vault_path or "")
                for existing in unique
            }
        identity = (citation.kind, target, vault_identity)
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(citation)
    return unique


def _final_citations(decision_citations: list[ChatCitation], trace: list[ChatToolTraceItem]) -> list[ChatCitation]:
    trace_citations = [citation for item in trace for citation in item.citations]
    if decision_citations:
        return _unique_citations([_enrich_citation(citation, trace_citations) for citation in decision_citations])
    return _unique_citations(trace_citations[:4])


def _enrich_citation(citation: ChatCitation, trace_citations: list[ChatCitation]) -> ChatCitation:
    target = citation.path or citation.run_id or ""
    for trace_citation in trace_citations:
        if trace_citation.kind == citation.kind and (trace_citation.path or trace_citation.run_id or "") == target:
            return trace_citation.model_copy(
                update={
                    "title": citation.title or trace_citation.title,
                    "reason": citation.reason or trace_citation.reason,
                }
            )
    return citation


def _clean_answer_citation_paths(answer: str, citations: list[ChatCitation], *, latest_user_text: str) -> str:
    if _answer_allows_file_paths(latest_user_text):
        return answer
    cleaned = answer
    for citation in citations:
        if citation.kind != "page" or not citation.path:
            continue
        replacement = citation.title or citation.path.rsplit("/", 1)[-1].removesuffix(".md")
        path = citation.path
        cleaned = re.sub(rf"\[([^\]]+)\]\({re.escape(path)}\)", r"\1", cleaned)
        cleaned = cleaned.replace(f"`{path}`", replacement)
        cleaned = cleaned.replace(path, replacement)
    return cleaned


def _answer_allows_file_paths(latest_user_text: str) -> bool:
    path_terms = {"路径", "文件名", "文件路径", "path", "file path", "filename", "page path"}
    return any(term in latest_user_text for term in path_terms)


def _latest_user_text(request: ChatRequest) -> str:
    for message in reversed(request.messages):
        if message.role == "user":
            return message.content.lower()
    return ""


def _is_side_effect_tool(tool: str) -> bool:
    return tool in {"start_ingest", "start_lint", "cancel_run"}


def _side_effect_allowed(tool: str, user_text: str) -> bool:
    intent_markers = {
        "start_ingest": (
            "ingest",
            "compile",
            "import",
            "add",
            "sync",
            "update",
            "write",
            "编译",
            "摄入",
            "导入",
            "加入",
            "同步",
            "更新",
            "写入",
        ),
        "start_lint": (
            "lint",
            "maintain",
            "repair",
            "fix",
            "check",
            "diagnose",
            "治理",
            "维护",
            "修复",
            "检查",
            "诊断",
            "校验",
        ),
        "cancel_run": (
            "cancel",
            "stop",
            "abort",
            "取消",
            "停止",
            "中止",
            "终止",
        ),
    }
    return any(marker in user_text for marker in intent_markers.get(tool, ()))
