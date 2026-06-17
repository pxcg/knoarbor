from __future__ import annotations

import re
from typing import Any

from knoarbor.core.schemas.chat import ChatCitation, ChatToolTraceItem


def final_citations(decision_citations: list[ChatCitation], trace: list[ChatToolTraceItem], *, answer: str = "") -> list[ChatCitation]:
    """Select public chat citations from model choices and observed tool evidence.

    Citation selection is a product contract rather than answer generation:
    model-chosen citations are accepted only when they are backed by observed
    tool evidence; evidence packs provide the preferred page set for wiki
    search and reused context; page-bearing tools without an evidence pack still
    expose their page citations so the UI can show sources and follow-ups.
    """

    trace_citations = [citation for item in trace for citation in item.citations]
    if decision_citations:
        if not trace_citations:
            return _unique_citations(decision_citations)
        validated = [_enrich_citation(citation, trace_citations) for citation in decision_citations]
        validated = [citation for citation in validated if _citation_is_trace_supported(citation, trace_citations)]
        if validated:
            return _unique_citations(validated)
    evidence_citations = _evidence_pack_citations(trace)
    referenced = _referenced_citations(answer, evidence_citations)
    if referenced:
        return _unique_citations(referenced)
    primary = [citation for citation in evidence_citations if citation.role == "primary"]
    if primary:
        return _unique_citations(primary[:4])
    if evidence_citations:
        return _unique_citations(evidence_citations[:4])
    return _unique_citations(trace_citations[:4])


def answer_cleanup_citations(trace: list[ChatToolTraceItem], final_answer_citations: list[ChatCitation]) -> list[ChatCitation]:
    """Return observed page citations that may appear as raw paths in answers."""

    observed = [citation for item in trace for citation in item.citations]
    observed.extend(_evidence_pack_citations(trace))
    observed.extend(final_answer_citations)
    return _unique_citations(observed)


def clean_answer_citation_paths(answer: str, citations: list[ChatCitation], *, latest_user_text: str) -> str:
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


def _referenced_citations(answer: str, citations: list[ChatCitation]) -> list[ChatCitation]:
    indexes = []
    for match in re.finditer(r"\[(\d{1,2})\]", answer):
        number = int(match.group(1))
        if number < 1 or number > len(citations) or number in indexes:
            continue
        indexes.append(number)
    return [citations[index - 1] for index in indexes]


def _evidence_pack_citations(trace: list[ChatToolTraceItem]) -> list[ChatCitation]:
    citations: list[ChatCitation] = []
    for item in trace:
        pack = item.result.get("evidence_pack")
        if isinstance(pack, dict):
            citations.extend(_pack_citations(pack))
            continue
        if item.tool == "read_wiki_page" and item.citations:
            citations.extend(item.citations)
    return _unique_citations(citations)


def _pack_citations(pack: dict[str, Any]) -> list[ChatCitation]:
    citation_pages = pack.get("citation_pages")
    if isinstance(citation_pages, list) and citation_pages:
        return [_page_payload_citation(page) for page in citation_pages if isinstance(page, dict) and page.get("path")]
    pages: list[tuple[str, dict[str, Any]]] = []
    for role, key in (("primary", "primary_pages"), ("supporting", "supporting_pages"), ("source", "source_pages")):
        value = pack.get(key)
        if isinstance(value, list):
            pages.extend((role, page) for page in value if isinstance(page, dict) and page.get("path"))
    primary_page = pack.get("primary_page")
    if isinstance(primary_page, dict) and primary_page.get("path"):
        pages.insert(0, ("primary", primary_page))
    return [_page_payload_citation(page, role=role) for role, page in pages]


def _page_payload_citation(page: dict[str, Any], *, role: str | None = None) -> ChatCitation:
    return ChatCitation(
        kind="page",
        role=_citation_role(str(page.get("role") or role or "supporting")),
        path=str(page.get("path")),
        title=str(page.get("title") or ""),
        vault_id=str(page.get("vault_id")) if page.get("vault_id") else None,
        vault_name=str(page.get("vault_name")) if page.get("vault_name") else None,
        vault_path=str(page.get("vault_path")) if page.get("vault_path") else None,
        reason=str(page.get("reason") or page.get("summary") or ""),
    )


def _citation_role(role: str) -> str:
    return role if role in {"primary", "supporting", "source", "further_reading"} else "supporting"


def _answer_allows_file_paths(latest_user_text: str) -> bool:
    path_terms = {"路径", "文件名", "文件路径", "path", "file path", "filename", "page path"}
    return any(term in latest_user_text for term in path_terms)
