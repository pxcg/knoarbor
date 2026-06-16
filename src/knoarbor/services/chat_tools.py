from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from knoarbor.core.errors import UserInputError
from knoarbor.core.schemas.chat import ChatCitation, ChatRequest, ChatSessionRecord, ChatToolPlan, ChatToolTraceItem
from knoarbor.core.schemas.wiki_query import WikiSearchRequest, WikiSearchResult
from knoarbor.core.vaults import VIRTUAL_ALL_VAULT_ID
from knoarbor.entrypoints.vault_selection import resolve_single_vault
from knoarbor.retrieval.answer_selection import query_prefers_source_page
from knoarbor.services.chat_context import latest_user_text
from knoarbor.services.chat_evidence import ChatEvidencePlanner, search_result_to_chat_payload

if TYPE_CHECKING:
    from knoarbor.services import ApplicationServices


ChatToolEventCallback = Callable[[str, str, str | None, int | None, str | None], None]


@dataclass
class ChatToolExecutor:
    """Executes KnoArbor-owned chat tools.

    This layer owns tool semantics and query/read/reuse payload assembly. The
    chat agent owns orchestration and model calls.
    """

    request: ChatRequest
    services: ApplicationServices
    existing_session: ChatSessionRecord | None = None
    event_callback: ChatToolEventCallback | None = None
    evidence_planner: ChatEvidencePlanner = field(default_factory=ChatEvidencePlanner)

    def execute(self, plan: ChatToolPlan, query: str) -> list[ChatToolTraceItem]:
        observations: list[ChatToolTraceItem] = []
        for index, call in enumerate(plan.tool_calls[:4], start=1):
            tool_name = call.name
            self._event("tool_call_started", f"Running chat tool: {tool_name}.", tool_name, index, None)
            try:
                if tool_name == "query_wiki":
                    observation = self._query_wiki(_with_default_query(call.arguments, query))
                elif tool_name == "read_wiki_page":
                    observation = self._read_wiki_page(call.arguments)
                elif tool_name == "reuse_context":
                    observation = self._reuse_context(call.arguments)
                else:
                    observation = self._answer_directly(call.arguments)
            except Exception as exc:  # noqa: BLE001 - tool failures become model-visible observations.
                observation = ChatToolTraceItem(
                    tool=tool_name,
                    arguments=call.arguments,
                    status="error",
                    summary=f"Tool failed: {exc}",
                    result={"error": str(exc)},
                )
            observations.append(observation)
            self._event(
                "tool_call_failed" if observation.status == "error" else "tool_call_finished",
                observation.summary,
                observation.tool,
                index,
                observation.status,
            )
        if not observations:
            observations.append(self._query_wiki({"query": query, "mode": "balanced", "max_results": 6}))
        return observations

    def _query_wiki(self, arguments: dict[str, Any]) -> ChatToolTraceItem:
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
            for result in _ordered_chat_citations(response.results, primary_pages, prefer_sources=query_prefers_source_page(query))
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
            "primary_page": _chat_primary_page_payload(primary) if primary else None,
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
        return ChatToolTraceItem(tool="query_wiki", arguments=arguments, summary=f"Found {len(response.results)} wiki result(s).", citations=citations, result=result)

    def _read_wiki_page(self, arguments: dict[str, Any]) -> ChatToolTraceItem:
        page_path = str(arguments.get("page_path") or arguments.get("path") or "").strip()
        if not page_path:
            raise UserInputError("read_wiki_page requires page_path")
        original_page_path = page_path
        page_path = _answer_page_for_source_read(page_path, latest_user_text(self.request.messages), self.existing_session) or page_path
        requested_vault_id = _concrete_argument_vault_id(arguments, self.request.vault_id)
        if requested_vault_id is None:
            requested_vault_id = _vault_id_for_prior_page(page_path, self.existing_session)
        vault = resolve_single_vault(
            self.request.vault_path,
            requested_vault_id,
            self.request.config_path,
        )
        page = self.services.wiki_pages.read_page(vault.path, page_path, vault_id=vault.vault_id, vault_name=vault.vault_name)
        citation = ChatCitation(kind="page", role="primary", path=page.path, title=page.summary.title, vault_id=vault.vault_id, vault_name=vault.vault_name, vault_path=str(vault.path))
        result = {
            "path": page.path,
            "title": page.summary.title,
            "summary": page.summary.summary,
            "content": page.content,
            "metadata": page.metadata,
            "vault_id": vault.vault_id,
            "vault_name": vault.vault_name,
            "vault_path": str(vault.path),
            "truncated": False,
        }
        summary = f"Read wiki page {page.path}."
        if original_page_path != page_path:
            summary = f"Read wiki page {page.path} instead of source digest {original_page_path}."
        return ChatToolTraceItem(tool="read_wiki_page", arguments=arguments, summary=summary, citations=[citation], result=result)

    def _reuse_context(self, arguments: dict[str, Any]) -> ChatToolTraceItem:
        prior = _latest_reusable_trace(self.existing_session, arguments.get("page_paths"))
        if prior is None:
            return self._query_wiki(_with_default_query(arguments, latest_user_text(self.request.messages)))
        return ChatToolTraceItem(
            tool="reuse_context",
            arguments=arguments,
            summary="Reused prior chat evidence.",
            citations=prior.citations,
            result=prior.result,
        )

    def _answer_directly(self, arguments: dict[str, Any]) -> ChatToolTraceItem:
        return ChatToolTraceItem(
            tool="answer_directly",
            arguments=arguments,
            summary=str(arguments.get("reason") or "No wiki lookup requested."),
            status="skipped",
            result={"evidence_pack": {"schema_version": "chat_evidence_pack.v1", "kind": "direct_answer", "warnings": ["No wiki evidence was requested by the planner."]}},
        )

    def _event(self, event_type: str, message: str, tool: str | None, turn: int | None, status: str | None) -> None:
        if self.event_callback:
            self.event_callback(event_type, message, tool, turn, status)


def _latest_reusable_trace(existing_session: ChatSessionRecord | None, page_paths: object = None) -> ChatToolTraceItem | None:
    if existing_session is None:
        return None
    requested = {str(path) for path in page_paths or [] if str(path).strip()} if isinstance(page_paths, list) else set()
    turn_trace = [item for turn in existing_session.turns for item in turn.tool_trace]
    for item in reversed(turn_trace or existing_session.tool_trace):
        if item.status != "ok":
            continue
        if item.tool not in {"query_wiki", "search_wiki", "reuse_context"}:
            continue
        if not isinstance(item.result.get("evidence_pack"), dict):
            continue
        if requested:
            citation_paths = {citation.path for citation in item.citations if citation.path}
            if not requested.intersection(citation_paths):
                continue
        return item
    return None


def _with_default_query(arguments: dict[str, Any], query: str) -> dict[str, Any]:
    output = dict(arguments)
    if not str(output.get("query") or "").strip():
        output["query"] = query
    if output.get("mode") not in {"balanced", "deep", "quick"}:
        output["mode"] = "balanced"
    if "max_results" not in output:
        output["max_results"] = 6
    return output


def _vault_id_for_prior_page(page_path: str, existing_session: ChatSessionRecord | None) -> str | None:
    if existing_session is None:
        return None
    turn_citations = [citation for turn in existing_session.turns for citation in turn.citations]
    for citation in turn_citations or existing_session.citations:
        if citation.path == page_path and citation.vault_id and citation.vault_id != VIRTUAL_ALL_VAULT_ID:
            return citation.vault_id
    turn_trace = [item for turn in existing_session.turns for item in turn.tool_trace]
    for item in turn_trace or existing_session.tool_trace:
        for citation in item.citations:
            if citation.path == page_path and citation.vault_id and citation.vault_id != VIRTUAL_ALL_VAULT_ID:
                return citation.vault_id
    return None


def _answer_page_for_source_read(page_path: str, query: str, existing_session: ChatSessionRecord | None) -> str | None:
    if not page_path.startswith("sources/") or query_prefers_source_page(query) or existing_session is None:
        return None
    trace_items = [item for turn in existing_session.turns for item in turn.tool_trace] or existing_session.tool_trace
    for item in reversed(trace_items):
        pack = item.result.get("evidence_pack")
        if not isinstance(pack, dict):
            continue
        answer_path = _first_answer_page_path(pack)
        if answer_path:
            return answer_path
    return None


def _first_answer_page_path(pack: dict[str, Any]) -> str | None:
    for key in ("primary_pages", "supporting_pages"):
        pages = pack.get(key) if isinstance(pack.get(key), list) else []
        for page in pages:
            if not isinstance(page, dict) or not page.get("path"):
                continue
            path = str(page["path"])
            if page.get("type") != "source" and not path.startswith("sources/"):
                return path
    primary_page = pack.get("primary_page")
    if isinstance(primary_page, dict) and primary_page.get("path"):
        path = str(primary_page["path"])
        if primary_page.get("type") != "source" and not path.startswith("sources/"):
            return path
    return None


def _primary_first_results(results: list[WikiSearchResult], primary: WikiSearchResult | list[WikiSearchResult] | None) -> list[WikiSearchResult]:
    if primary is None:
        return results
    primary_pages = primary if isinstance(primary, list) else [primary]
    primary_keys = {(result.path, result.vault_id) for result in primary_pages}
    return [*primary_pages, *[result for result in results if (result.path, result.vault_id) not in primary_keys]]


def _ordered_chat_citations(results: list[WikiSearchResult], primary: WikiSearchResult | list[WikiSearchResult] | None, *, prefer_sources: bool) -> list[WikiSearchResult]:
    ordered = _primary_first_results(results, primary)
    if prefer_sources:
        return ordered
    answer_pages = [result for result in ordered if result.type != "source"]
    source_pages = [result for result in ordered if result.type == "source"]
    return [*answer_pages, *source_pages]


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
