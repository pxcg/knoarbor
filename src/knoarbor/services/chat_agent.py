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
    ChatAnswerDraft,
    ChatCitation,
    ChatEvent,
    ChatMessageItem,
    ChatRequest,
    ChatResponse,
    ChatRunLink,
    ChatToolTraceItem,
)
from knoarbor.core.schemas.memory import MemoryCandidate, MemoryRecord
from knoarbor.core.schemas.wiki_query import WikiSearchRequest, WikiSearchResult
from knoarbor.core.vaults import VIRTUAL_ALL_VAULT_ID
from knoarbor.retrieval.answer_selection import query_prefers_source_page
from knoarbor.services.chat_evidence import ChatEvidencePlanner, search_result_to_chat_payload
from knoarbor.services.chat_context import ChatContextEngine, latest_user_text, memory_target, session_target
from knoarbor.semantic.contracts import load_prompt
from knoarbor.semantic.llm import ChatClient, ChatCompletionRequest, ChatMessage, ModelGateway

if TYPE_CHECKING:
    from knoarbor.services import ApplicationServices


ANSWER_SYNTHESIS_PROMPT = load_prompt("wiki_chat_answer.md")


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
        self._event("chat_started", message="Chat request started.")
        query = latest_user_text(self.current_messages)
        retrieval = _plan_chat_retrieval(query)
        self._event("tool_call_started", message="Searching wiki before answer synthesis.", tool="search_wiki", turn=1)
        observation = self._tool_search_wiki(
            {
                "query": query,
                "mode": retrieval["mode"],
                "max_results": retrieval["max_results"],
            }
        )
        self.trace.append(observation)
        self._event(
            "tool_call_failed" if observation.status == "error" else "tool_call_finished",
            message=observation.summary,
            tool=observation.tool,
            turn=1,
            status=observation.status,
        )
        messages.append(ChatMessage(role="user", content=self._evidence_prompt(observation)))

        prompt_chars = _messages_chars(messages)
        call_started = time.perf_counter()
        self._event("model_call_started", message="Calling chat answer model.", turn=1)
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
            message="Chat answer model call finished.",
            turn=1,
            payload={"usage": completion.usage, "elapsed_seconds": completion.elapsed_seconds},
        )
        self.call_records.append(
            {
                **completion.usage,
                "provider": completion.provider,
                "model": completion.model,
                "turn": 1,
                "prompt_chars": prompt_chars,
                "elapsed_seconds": completion.elapsed_seconds or round(time.perf_counter() - call_started, 3),
                "tokens_per_second": completion.tokens_per_second,
            }
        )
        draft = _parse_answer_draft(completion.content)
        response = self._answer_response(draft, turns=1)
        response.stats["retrieval_strategy"] = "canonical_evidence"
        response.stats["retrieval_policy"] = retrieval
        return response

    def _evidence_prompt(self, observation: ChatToolTraceItem) -> str:
        payload = self.evidence_planner.project_tool_observation(
            observation.tool,
            observation.status,
            observation.summary,
            observation.result,
        )
        return json.dumps(
            {
                "user_question": latest_user_text(self.current_messages),
                "tool_observation": payload,
            },
            ensure_ascii=False,
        )

    def _tool_search_wiki(self, arguments: dict[str, Any]) -> ChatToolTraceItem:
        query = _required_text(arguments, "query")
        max_results = _bounded_int(arguments.get("max_results"), default=6, minimum=1, maximum=12)
        requested_vault_id = _concrete_argument_vault_id(arguments, self.request.vault_id)
        request = WikiSearchRequest(
            config_path=self.request.config_path,
            vault_path=self.request.vault_path,
            vault_id=requested_vault_id,
            vault_ids=[str(item) for item in arguments.get("vault_ids", self.request.vault_ids) or []],
            all_vaults=bool(arguments.get("all_vaults", self.request.all_vaults or self.request.vault_id == VIRTUAL_ALL_VAULT_ID)),
            query=query,
            mode=arguments.get("mode") if arguments.get("mode") in {"quick", "balanced", "deep"} else "balanced",
            page_dirs=[str(item) for item in arguments.get("page_dirs", []) if str(item).strip()],
            max_results=max_results,
            record_query=False,
            write_report=False,
            caller="chat",
        )
        response = self.services.wiki_search.search(request)
        primary_pages = response.primary_pages or _fallback_primary_results(response.results, query)
        primary = primary_pages[0] if primary_pages else None
        primary_paths = {item.path for item in primary_pages}
        supporting = (
            response.supporting_pages
            or [
                item
                for item in response.results
                if primary_pages
                and item.path not in primary_paths
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
            for result in _primary_first_results(response.results, primary_pages)
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
            "primary_pages": [_chat_primary_page_payload(item) for item in primary_pages],
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
            primary_pages=result["primary_pages"],
            supporting_pages=result["supporting_pages"],
            source_pages=result["source_pages"],
            results=result["results"],
            warnings=response.warnings,
        ).payload
        return ChatToolTraceItem(tool="search_wiki", arguments=arguments, summary=f"Found {len(response.results)} wiki result(s).", citations=citations, result=result)

    def _answer_response(self, draft: ChatAnswerDraft, turns: int) -> ChatResponse:
        citations = _final_citations(draft.citations, self.trace)
        answer = _clean_answer_citation_paths(draft.answer, citations, latest_user_text=latest_user_text(self.current_messages))
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
            "mode": (response.stats.get("retrieval_policy") or {}).get("mode", "balanced"),
            "provider": response.stats.get("provider"),
            "model": response.stats.get("model"),
            "calls": calls,
            "citations": [citation.model_dump() for citation in response.citations],
            "tool_trace": [item.model_dump() for item in response.tool_trace],
        },
    )


def _parse_answer_draft(content: str) -> ChatAnswerDraft:
    payload = _parse_json_object(content)
    try:
        return ChatAnswerDraft.model_validate(payload)
    except (ValidationError, ValueError) as exc:
        raise ModelOutputError(f"Chat answer model returned invalid JSON: {exc}") from exc


def _parse_json_object(content: str) -> dict[str, Any]:
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
    except json.JSONDecodeError as exc:
        raise ModelOutputError(f"Chat model returned invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ModelOutputError("Chat model returned JSON that is not an object.")
    return payload


def _primary_first_results(results: list[WikiSearchResult], primary: WikiSearchResult | list[WikiSearchResult] | None) -> list[WikiSearchResult]:
    if primary is None:
        return results
    primary_pages = primary if isinstance(primary, list) else [primary]
    primary_keys = {(result.path, result.vault_id) for result in primary_pages}
    return [*primary_pages, *[result for result in results if (result.path, result.vault_id) not in primary_keys]]


def _fallback_primary_results(results: list[WikiSearchResult], query: str) -> list[WikiSearchResult]:
    primary = _fallback_primary_result(results, query)
    return [primary] if primary else []


def _fallback_primary_result(results: list[WikiSearchResult], query: str) -> WikiSearchResult | None:
    if query_prefers_source_page(query):
        return results[0] if results else None
    for result in results:
        if result.role == "primary":
            return result
    for result in results:
        if result.type != "source":
            return result
    return results[0] if results else None

def _chat_supporting_page_payload(item: WikiSearchResult) -> dict[str, object]:
    return {
        "path": item.path,
        "title": item.title,
        "type": item.type,
        "role": item.role,
        "score": item.score,
        "relevance": item.relevance,
        "summary": item.summary,
        "key_points": item.key_points[:6],
        "content": item.content or "",
        "content_truncated": item.content_truncated,
        "vault_id": item.vault_id,
        "vault_name": item.vault_name,
    }


def _chat_primary_page_payload(item: WikiSearchResult) -> dict[str, object]:
    return {
        "path": item.path,
        "title": item.title,
        "type": item.type,
        "role": item.role,
        "score": item.score,
        "relevance": item.relevance,
        "summary": item.summary,
        "key_points": item.key_points[:8],
        "content": item.content or "",
        "content_truncated": item.content_truncated,
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
        if not trace_citations:
            return _unique_citations(decision_citations)
        validated = [_enrich_citation(citation, trace_citations) for citation in decision_citations]
        validated = [citation for citation in validated if _citation_is_trace_supported(citation, trace_citations)]
        if validated:
            return _unique_citations(validated)
    return _unique_citations(trace_citations[:4])


def _citation_is_trace_supported(citation: ChatCitation, trace_citations: list[ChatCitation]) -> bool:
    target = citation.path or citation.run_id or ""
    return any(
        trace_citation.kind == citation.kind and (trace_citation.path or trace_citation.run_id or "") == target
        for trace_citation in trace_citations
    )


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


def _plan_chat_retrieval(query: str) -> dict[str, object]:
    text = query.lower()
    broad_terms = {
        "对比",
        "比较",
        "区别",
        "联系",
        "完整",
        "详细",
        "深入",
        "系统",
        "架构",
        "方案",
        "如何",
        "为什么",
        "总结",
        "compare",
        "comparison",
        "difference",
        "architecture",
        "system",
        "design",
        "deep",
        "detailed",
        "explain",
        "how",
        "why",
        "summarize",
    }
    focused_terms = {
        "是什么",
        "定义",
        "含义",
        "哪个页面",
        "列出",
        "打开",
        "what is",
        "definition",
        "list",
        "open",
    }
    if any(term in text for term in broad_terms) or len(query) >= 80:
        return {"mode": "deep", "max_results": 8, "reason": "broad_or_comparative_question"}
    if any(term in text for term in focused_terms) and len(query) <= 40:
        return {"mode": "balanced", "max_results": 5, "reason": "focused_question"}
    return {"mode": "balanced", "max_results": 6, "reason": "standard_question"}
