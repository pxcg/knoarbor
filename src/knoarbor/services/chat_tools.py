from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from knoarbor.core.errors import UserInputError
from knoarbor.core.schemas.chat import ChatCitation, ChatRequest, ChatSessionRecord, ChatToolPlan, ChatToolTraceItem
from knoarbor.core.schemas.image_generation import ImageGenerationRequest
from knoarbor.core.schemas.wiki_query import WikiSearchRequest, WikiSearchResult
from knoarbor.core.vaults import VIRTUAL_ALL_VAULT_ID
from knoarbor.core.vault_selection import resolve_single_vault, resolve_vault_group
from knoarbor.retrieval.answer_selection import query_prefers_source_page
from knoarbor.services.chat_context import latest_user_text
from knoarbor.services.chat_evidence import CHAT_EVIDENCE_PACK_SCHEMA_VERSION, ChatEvidencePlanner, search_result_to_chat_payload
from knoarbor.services.chat_generated_images import store_chat_generated_image
from knoarbor.services.wiki_attachments import attachments_for_wiki_page

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
                elif tool_name == "list_wiki_pages":
                    observation = self._list_wiki_pages(call.arguments)
                elif tool_name == "read_wiki_page":
                    observation = self._read_wiki_page(call.arguments)
                elif tool_name == "inspect_wiki_relations":
                    observation = self._inspect_wiki_relations(call.arguments)
                elif tool_name == "list_vaults":
                    observation = self._list_vaults(call.arguments)
                elif tool_name == "reuse_context":
                    observation = self._reuse_context(call.arguments)
                elif tool_name == "generate_image":
                    observation = self._generate_image(_with_default_prompt(call.arguments, query))
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
        primary_pages = response.primary_pages or _derive_primary_pages_from_ranked_results(response.results, query)
        primary = primary_pages[0] if primary_pages else None
        primary_paths = {item.path for item in primary_pages}
        supporting = (
            response.supporting_pages
            or [
                item
                for item in response.results
                if primary_pages
                and item.path not in primary_paths
                and not _is_source_result(item)
            ]
        )[:5]
        source_pages = (response.source_pages or [item for item in response.results if _is_source_result(item)])[:5]
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

    def _list_wiki_pages(self, arguments: dict[str, Any]) -> ChatToolTraceItem:
        query = str(arguments.get("query") or "").strip().lower()
        page_dirs = {str(item).strip() for item in arguments.get("page_dirs", []) if str(item).strip()}
        max_results = _bounded_int(arguments.get("max_results"), default=40, minimum=1, maximum=120)
        vaults = self._resolve_tool_vaults(arguments)
        grouped_pages: list[dict[str, Any]] = []
        citations: list[ChatCitation] = []
        total_pages = 0
        for vault in vaults:
            response = self.services.wiki_pages.list_pages(vault.path, vault_id=vault.vault_id, vault_name=vault.vault_name)
            pages = [_page_summary_payload(page) for page in response.pages]
            total_pages += len(pages)
            filtered = [_with_vault_identity(page, vault) for page in pages if _page_matches(page, query=query, page_dirs=page_dirs)]
            grouped_pages.extend(filtered[:max(0, max_results - len(grouped_pages))])
            citations.extend(
                ChatCitation(
                    kind="page",
                    role="supporting",
                    path=str(page.get("path")),
                    title=str(page.get("title") or ""),
                    vault_id=vault.vault_id,
                    vault_name=vault.vault_name,
                    vault_path=str(vault.path),
                    reason="Listed as a maintained wiki page.",
                )
                for page in filtered[: max(0, max_results - len(citations))]
                if page.get("path")
            )
            if len(grouped_pages) >= max_results:
                break
        result = {
            "query": query,
            "page_dirs": sorted(page_dirs),
            "total_pages": total_pages,
            "returned_pages": len(grouped_pages),
            "pages": grouped_pages,
        }
        return ChatToolTraceItem(
            tool="list_wiki_pages",
            arguments=arguments,
            summary=f"Listed {len(grouped_pages)} wiki page(s).",
            citations=citations,
            result=result,
        )

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
        if _needs_page_reference_resolution(page_path):
            resolved_page_path = _resolve_page_reference(self.services, vault, page_path)
            if resolved_page_path:
                page_path = resolved_page_path
        page = self.services.wiki_pages.read_page(vault.path, page_path, vault_id=vault.vault_id, vault_name=vault.vault_name)
        citation = ChatCitation(kind="page", role="primary", path=page.path, title=page.summary.title, vault_id=vault.vault_id, vault_name=vault.vault_name, vault_path=str(vault.path))
        result = {
            "path": page.path,
            "title": page.summary.title,
            "summary": page.summary.summary,
            "content": page.content,
            "attachments": attachments_for_wiki_page(vault.path, page.content),
            "metadata": page.metadata,
            "vault_id": vault.vault_id,
            "vault_name": vault.vault_name,
            "vault_path": str(vault.path),
            "truncated": False,
        }
        summary = f"Read wiki page {page.path}."
        if original_page_path.startswith("sources/") and original_page_path != page_path:
            summary = f"Read wiki page {page.path} instead of source digest {original_page_path}."
        elif original_page_path != page_path:
            summary = f"Read wiki page {page.path} after resolving requested page reference {original_page_path}."
        return ChatToolTraceItem(tool="read_wiki_page", arguments=arguments, summary=summary, citations=[citation], result=result)

    def _inspect_wiki_relations(self, arguments: dict[str, Any]) -> ChatToolTraceItem:
        page_path = str(arguments.get("page_path") or arguments.get("path") or "").strip()
        if not page_path:
            raise UserInputError("inspect_wiki_relations requires page_path")
        requested_vault_id = _concrete_argument_vault_id(arguments, self.request.vault_id)
        if requested_vault_id is None:
            requested_vault_id = _vault_id_for_prior_page(page_path, self.existing_session)
        vault = resolve_single_vault(self.request.vault_path, requested_vault_id, self.request.config_path)
        relations = self.services.wiki_pages.page_relations(vault.path, page_path, vault_id=vault.vault_id, vault_name=vault.vault_name)
        outgoing = [_link_payload(link) for link in relations.outgoing_pages]
        incoming = [_link_payload(link) for link in relations.incoming_pages]
        citations = [
            ChatCitation(
                kind="page",
                role="supporting",
                path=path,
                title=path.rsplit("/", 1)[-1].removesuffix(".md"),
                vault_id=vault.vault_id,
                vault_name=vault.vault_name,
                vault_path=str(vault.path),
                reason="Linked page discovered from page relationship inspection.",
            )
            for path in _unique_strings([str(item.get("target_path") or item.get("source") or "") for item in [*outgoing, *incoming]])
            if path
        ]
        result = {
            "path": relations.path,
            "vault_id": vault.vault_id,
            "vault_name": vault.vault_name,
            "vault_path": str(vault.path),
            "outgoing_pages": outgoing,
            "incoming_pages": incoming,
        }
        return ChatToolTraceItem(
            tool="inspect_wiki_relations",
            arguments=arguments,
            summary=f"Inspected page relations for {relations.path}: {len(outgoing)} outgoing, {len(incoming)} incoming.",
            citations=citations,
            result=result,
        )

    def _list_vaults(self, arguments: dict[str, Any]) -> ChatToolTraceItem:
        response = self.services.vaults.list_vaults(config_path=str(arguments.get("config_path") or self.request.config_path or "").strip() or None)
        vaults = [vault.model_dump() for vault in response.vaults]
        return ChatToolTraceItem(
            tool="list_vaults",
            arguments=arguments,
            summary=f"Listed {len(vaults)} configured vault(s).",
            result={
                "schema_version": response.schema_version,
                "config_path": response.config_path,
                "default_vault_id": response.default_vault_id,
                "vaults": vaults,
            },
        )

    def _reuse_context(self, arguments: dict[str, Any]) -> ChatToolTraceItem:
        if not arguments.get("page_paths"):
            combined = _combined_reusable_trace(self.existing_session, self.evidence_planner)
            if combined is not None:
                return combined
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
            result={
                "evidence_pack": {
                    "schema_version": CHAT_EVIDENCE_PACK_SCHEMA_VERSION,
                    "kind": "direct_answer",
                    "warnings": ["No wiki evidence was requested by the planner."],
                }
            },
        )

    def _generate_image(self, arguments: dict[str, Any]) -> ChatToolTraceItem:
        prompt = _required_text(arguments, "prompt")
        provider = _optional_text(arguments, "provider")
        request = ImageGenerationRequest(
            prompt=prompt,
            negative_prompt=_optional_text(arguments, "negative_prompt"),
            resolution=_optional_text(arguments, "resolution"),
            num_inference_steps=_optional_bounded_int(arguments.get("num_inference_steps"), minimum=1, maximum=200),
            guidance=_optional_float(arguments.get("guidance")),
            response_format=arguments.get("response_format") if arguments.get("response_format") in {"url", "b64_json"} else None,
            extra_body=arguments.get("extra_body") if isinstance(arguments.get("extra_body"), dict) else {},
        )
        response = self.services.image_generation.generate(request, config_path=self.request.config_path, provider_name=provider)
        images: list[dict[str, object]] = []
        for index, image in enumerate(response.images, start=1):
            src = image.markdown_src()
            if not src:
                continue
            stored = store_chat_generated_image(
                image,
                vault_path=self.request.vault_path,
                session_id=self.request.session_id,
                index=index,
            )
            display_src = stored.src if stored else src
            images.append(
                {
                    "index": index,
                    "src": display_src,
                    "markdown": f"![Generated image {index}]({display_src})",
                    "mime_type": image.mime_type,
                    "revised_prompt": image.revised_prompt,
                    "stored_path": stored.path if stored else None,
                    "original_src": stored.original_src if stored else src,
                }
            )
        return ChatToolTraceItem(
            tool="generate_image",
            arguments=arguments,
            summary=f"Generated {len(images)} image(s) with {response.provider}/{response.model}.",
            result={
                "schema_version": response.schema_version,
                "provider": response.provider,
                "model": response.model,
                "prompt": response.prompt,
                "images": images,
                "usage": response.usage,
            },
        )

    def _resolve_tool_vaults(self, arguments: dict[str, Any]):
        vault_id = _concrete_argument_vault_id(arguments, self.request.vault_id)
        vault_ids = [str(item) for item in arguments.get("vault_ids", self.request.vault_ids) or [] if str(item).strip()]
        all_vaults = bool(arguments.get("all_vaults", self.request.all_vaults or self.request.vault_id == VIRTUAL_ALL_VAULT_ID))
        return resolve_vault_group(
            vault_path=self.request.vault_path,
            vault_id=vault_id,
            vault_ids=vault_ids,
            all_vaults=all_vaults,
            config_path=self.request.config_path,
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


def _combined_reusable_trace(existing_session: ChatSessionRecord | None, evidence_planner: ChatEvidencePlanner) -> ChatToolTraceItem | None:
    if existing_session is None:
        return None
    trace_items = [item for turn in existing_session.turns[-6:] for item in turn.tool_trace]
    reusable = [
        item
        for item in trace_items
        if item.status == "ok"
        and (
            (item.tool in {"query_wiki", "reuse_context"} and isinstance(item.result.get("evidence_pack"), dict))
            or item.tool == "read_wiki_page"
        )
    ]
    if not reusable:
        return None
    session_pack = evidence_planner.build_session_pack(reusable)
    if session_pack is None:
        return None
    return ChatToolTraceItem(
        tool="reuse_context",
        arguments={"scope": "recent_session_evidence"},
        summary=f"Reused recent session evidence from {len(reusable)} tool result(s).",
        citations=_unique_citations([citation for item in reusable for citation in item.citations]),
        result={"evidence_pack": session_pack.payload},
    )


def _unique_citations(citations: list[ChatCitation]) -> list[ChatCitation]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[ChatCitation] = []
    for citation in citations:
        identity = (citation.kind, citation.vault_id or citation.vault_path or "", citation.path or citation.run_id or "")
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(citation)
    return unique


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
    if (
        not _path_looks_like_source_digest(page_path)
        or query_prefers_source_page(query)
        or _query_prefers_source_read(query)
        or existing_session is None
    ):
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
            if not _is_source_page_payload(page):
                return path
    primary_page = pack.get("primary_page")
    if isinstance(primary_page, dict) and primary_page.get("path"):
        path = str(primary_page["path"])
        if not _is_source_page_payload(primary_page):
            return path
    return None


def _query_prefers_source_read(query: str) -> bool:
    text = query.lower()
    source_read_terms = {
        "reference",
        "references",
        "citation",
        "citations",
        "cited",
        "basis",
        "raw material",
        "参考",
        "引用",
        "依据",
        "材料",
        "原文",
    }
    return any(term in text for term in source_read_terms)


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
    answer_pages = [result for result in ordered if not _is_source_result(result)]
    source_pages = [result for result in ordered if _is_source_result(result)]
    return [*answer_pages, *source_pages]


def _derive_primary_pages_from_ranked_results(results: list[WikiSearchResult], query: str) -> list[WikiSearchResult]:
    """Derive a primary page only when the retrieval response lacks one.

    Retrieval owns answer set classification. This deterministic derivation
    keeps older or minimal providers usable while preserving the ranked order
    and source-page preference rules.
    """

    primary = _derive_primary_page_from_ranked_results(results, query)
    return [primary] if primary else []


def _derive_primary_page_from_ranked_results(results: list[WikiSearchResult], query: str) -> WikiSearchResult | None:
    if query_prefers_source_page(query):
        return results[0] if results else None
    for result in results:
        if result.role == "primary":
            return result
    for result in results:
        if not _is_source_result(result):
            return result
    return results[0] if results else None


def _chat_supporting_page_payload(item: WikiSearchResult) -> dict[str, object]:
    return {
        "path": item.path,
        "title": item.title,
        "page_role": item.page_role,
        "role": item.role,
        "score": item.score,
        "relevance": item.relevance,
        "summary": item.summary,
        "claims": item.claims[:6],
        "content": item.content or "",
        "attachments": attachments_for_wiki_page(item.vault_path, item.content or ""),
        "content_truncated": item.content_truncated,
        "vault_id": item.vault_id,
        "vault_name": item.vault_name,
        "atom_traces": [trace.model_dump() for trace in item.atom_traces],
    }


def _chat_primary_page_payload(item: WikiSearchResult) -> dict[str, object]:
    return {
        "path": item.path,
        "title": item.title,
        "page_role": item.page_role,
        "role": item.role,
        "score": item.score,
        "relevance": item.relevance,
        "summary": item.summary,
        "claims": item.claims[:8],
        "content": item.content or "",
        "attachments": attachments_for_wiki_page(item.vault_path, item.content or ""),
        "content_truncated": item.content_truncated,
        "vault_id": item.vault_id,
        "vault_name": item.vault_name,
        "atom_traces": [trace.model_dump() for trace in item.atom_traces],
    }


def _page_summary_payload(page) -> dict[str, object]:
    return {
        "path": page.path,
        "canonical_path": page.canonical_path,
        "directory": page.directory,
        "title": page.title,
        "page_role": page.role,
        "updated": page.updated,
        "entities": page.entities,
        "summary": page.summary,
        "headings": page.headings,
    }


def _is_source_result(result: WikiSearchResult) -> bool:
    return (
        result.role == "source"
        or result.page_role == "source_digest"
        or _path_looks_like_source_digest(result.path)
    )


def _is_source_page_payload(page: dict[str, Any]) -> bool:
    answer_role = str(page.get("role") or "")
    page_role = str(page.get("page_role") or "")
    path = str(page.get("path") or "")
    return (
        answer_role == "source"
        or page_role == "source_digest"
        or _path_looks_like_source_digest(path)
    )


def _path_looks_like_source_digest(path: str) -> bool:
    return path.startswith("sources/")


def _with_vault_identity(page: dict[str, object], vault) -> dict[str, object]:
    output = dict(page)
    output["vault_id"] = vault.vault_id
    output["vault_name"] = vault.vault_name
    output["vault_path"] = str(vault.path)
    return output


def _page_matches(page: dict[str, object], *, query: str, page_dirs: set[str]) -> bool:
    normalized_page_dirs = {_normalize_page_filter_value(item) for item in page_dirs}
    page_identity = {
        _normalize_page_filter_value(page.get("directory")),
    }
    if normalized_page_dirs and not page_identity.intersection(normalized_page_dirs):
        return False
    if not query:
        return True
    haystack = " ".join(
        [
            str(page.get("path") or ""),
            str(page.get("title") or ""),
            str(page.get("summary") or ""),
            " ".join(str(entity) for entity in page.get("entities", []) if isinstance(entity, str)),
            " ".join(str(heading) for heading in page.get("headings", []) if isinstance(heading, str)),
        ]
    ).lower()
    return query in haystack


def _normalize_page_filter_value(value: object) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def _resolve_page_reference(services, vault, requested: str) -> str | None:
    requested_key = _page_reference_key(requested)
    if not requested_key:
        return None
    response = services.wiki_pages.list_pages(vault.path, vault_id=vault.vault_id, vault_name=vault.vault_name)
    pages = [_page_summary_payload(page) for page in response.pages]
    exact_matches = [
        str(page["path"])
        for page in pages
        if _page_reference_key(str(page.get("path") or "")) == requested_key
        or _page_reference_key(str(page.get("path") or "").removesuffix(".md")) == requested_key
    ]
    if len(exact_matches) == 1:
        return exact_matches[0]
    title_matches = [
        str(page["path"])
        for page in pages
        if _page_reference_key(str(page.get("title") or "")) == requested_key
        or _page_reference_key(str(page.get("path") or "").rsplit("/", 1)[-1].removesuffix(".md")) == requested_key
    ]
    unique = _unique_strings(title_matches)
    if len(unique) == 1:
        return unique[0]
    if len(unique) > 1:
        raise UserInputError(f"Ambiguous wiki page reference: {requested}")
    return None


def _needs_page_reference_resolution(page_path: str) -> bool:
    return "/" not in page_path


def _page_reference_key(value: str) -> str:
    cleaned = value.strip().removesuffix(".md").lower()
    if not cleaned:
        return ""
    return "".join(char for char in cleaned if char.isalnum())


def _link_payload(link) -> dict[str, object]:
    return {
        "source": link.source,
        "target": link.target,
        "target_path": link.target_path,
        "resolved": link.resolved,
    }


def _required_text(arguments: dict[str, Any], key: str) -> str:
    value = str(arguments.get(key) or "").strip()
    if not value:
        raise UserInputError(f"Chat tool argument is required: {key}")
    return value


def _optional_text(arguments: dict[str, Any], key: str) -> str | None:
    value = str(arguments.get(key) or "").strip()
    return value or None


def _with_default_prompt(arguments: dict[str, Any], query: str) -> dict[str, Any]:
    output = dict(arguments)
    if not str(output.get("prompt") or "").strip():
        output["prompt"] = query
    return output


def _bounded_int(value: object, *, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value) if value is not None else default
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def _optional_bounded_int(value: object, *, minimum: int, maximum: int) -> int | None:
    if value is None or value == "":
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return max(minimum, min(maximum, number))


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _concrete_argument_vault_id(arguments: dict[str, Any], request_vault_id: str | None) -> str | None:
    value = arguments.get("vault_id", request_vault_id)
    vault_id = str(value).strip() if value is not None else ""
    if not vault_id or vault_id == VIRTUAL_ALL_VAULT_ID:
        return None
    return vault_id


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique
