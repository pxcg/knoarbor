from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

from knoarbor.core.schemas.chat import ChatCitation, ChatToolTraceItem
from knoarbor.services.chat_evidence import canonical_raw_evidence


@dataclass(frozen=True)
class ChatAnswerPresentation:
    """Public citation view for a generated chat answer."""

    answer: str
    citations: list[ChatCitation]
    hidden_evidence_count: int = 0
    warnings: list[str] = field(default_factory=list)


def resolve_answer_presentation(
    decision_citations: list[ChatCitation],
    trace: list[ChatToolTraceItem],
    *,
    answer: str,
) -> ChatAnswerPresentation:
    """Align model-visible evidence with answer-visible public citations.

    Evidence packs may contain many candidate pages. Public citations are the
    smaller answer-facing set: explicit answer references are authoritative
    after validation and renumbering; otherwise answer-bearing tool evidence is
    shown, while navigation-only observations stay out of the source list.
    """

    evidence_pool = _answer_evidence_citations(trace)
    observed_pool = _observed_citations(trace)
    selected = _validated_decision_citations(decision_citations, evidence_pool or observed_pool)
    reference_pool = selected or evidence_pool or observed_pool
    references = _referenced_indexes(answer, reference_pool)
    if references.valid:
        citations = _unique_citations([reference_pool[index - 1] for index in references.valid])
        return ChatAnswerPresentation(
            answer=_renumber_answer_citations(answer, references.valid),
            citations=citations,
            hidden_evidence_count=_hidden_count(reference_pool, citations),
            warnings=references.warnings,
        )

    if selected:
        return ChatAnswerPresentation(
            answer=answer,
            citations=selected,
            hidden_evidence_count=_hidden_count(evidence_pool or observed_pool, selected),
            warnings=references.warnings,
        )

    public_evidence = evidence_pool
    return ChatAnswerPresentation(
        answer=answer,
        citations=public_evidence,
        hidden_evidence_count=_hidden_count(reference_pool, public_evidence),
        warnings=references.warnings,
    )


def answer_cleanup_citations(trace: list[ChatToolTraceItem], final_answer_citations: list[ChatCitation]) -> list[ChatCitation]:
    """Return observed page citations that may appear as raw paths in answers."""

    observed = _observed_citations(trace)
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


@dataclass(frozen=True)
class _ReferenceIndexes:
    valid: list[int]
    warnings: list[str]


def _referenced_indexes(answer: str, citations: list[ChatCitation]) -> _ReferenceIndexes:
    indexes, invalid = _collect_reference_indexes(answer, citations, r"[\[［](\d+)[\]］]")
    return _ReferenceIndexes(valid=indexes, warnings=_reference_warnings(invalid))


def _collect_reference_indexes(answer: str, citations: list[ChatCitation], pattern: str) -> tuple[list[int], list[int]]:
    indexes: list[int] = []
    invalid: list[int] = []
    for match in re.finditer(pattern, answer):
        number = int(match.group(1))
        if number < 1 or number > len(citations):
            if number not in invalid:
                invalid.append(number)
            continue
        if number not in indexes:
            indexes.append(number)
    return indexes, invalid


def _reference_warnings(invalid: list[int]) -> list[str]:
    warnings: list[str] = []
    if invalid:
        warnings.append(f"Ignored citation reference(s) outside the evidence range: {', '.join(str(item) for item in invalid)}.")
    return warnings


def _renumber_answer_citations(answer: str, referenced_indexes: list[int]) -> str:
    index_map = {old: new for new, old in enumerate(referenced_indexes, start=1)}

    def replace(match: re.Match[str]) -> str:
        number = int(match.group(1))
        replacement = index_map.get(number)
        if replacement is None:
            return match.group(0)
        return f"[{replacement}]"

    return re.sub(r"[\[［](\d+)[\]］]", replace, answer)


def _validated_decision_citations(decision_citations: list[ChatCitation], observed: list[ChatCitation]) -> list[ChatCitation]:
    if not decision_citations:
        return []
    if not observed:
        return _unique_citations(decision_citations)
    output: list[ChatCitation] = []
    for citation in decision_citations:
        matched = _match_observed(citation, observed)
        if matched:
            output.append(citation.model_copy(update={
                "path": citation.path or matched.path,
                "title": citation.title or matched.title,
                "vault_id": citation.vault_id or matched.vault_id,
                "vault_name": citation.vault_name or matched.vault_name,
                "vault_path": citation.vault_path or matched.vault_path,
                "evidence_id": citation.evidence_id or matched.evidence_id,
                "raw_revision_id": citation.raw_revision_id or matched.raw_revision_id,
                "source_unit_id": citation.source_unit_id or matched.source_unit_id,
                "reason": citation.reason or matched.reason,
            }))
    return _unique_citations(output)


def _match_observed(citation: ChatCitation, observed: list[ChatCitation]) -> ChatCitation | None:
    target = _citation_target(citation)
    for item in observed:
        same_vault = not citation.vault_id or not item.vault_id or citation.vault_id == item.vault_id
        if item.kind == citation.kind and _citation_target(item) == target and same_vault:
            return item
    return None


def _answer_evidence_citations(trace: list[ChatToolTraceItem]) -> list[ChatCitation]:
    raw_evidence = canonical_raw_evidence(trace)
    if raw_evidence:
        return [_source_unit_payload_citation(item) for item in raw_evidence]
    citations: list[ChatCitation] = []
    for item in trace:
        pack = item.result.get("evidence_pack")
        if isinstance(pack, dict):
            citations.extend(_pack_citations(pack))
            continue
    return _unique_citations(citations)


def _observed_citations(trace: list[ChatToolTraceItem]) -> list[ChatCitation]:
    citations: list[ChatCitation] = []
    for item in trace:
        citations.extend(item.citations)
        pack = item.result.get("evidence_pack")
        if isinstance(pack, dict):
            citations.extend(_pack_citations(pack))
    return _unique_citations(citations)


def _pack_citations(pack: dict[str, Any]) -> list[ChatCitation]:
    citation_evidence = pack.get("citation_evidence")
    if isinstance(citation_evidence, list) and citation_evidence:
        return [_source_unit_payload_citation(item) for item in citation_evidence if isinstance(item, dict) and item.get("source_unit_id")]
    citation_pages = pack.get("citation_pages")
    if isinstance(citation_pages, list) and citation_pages:
        return [_page_payload_citation(page) for page in citation_pages if isinstance(page, dict) and page.get("path")]
    return []


def _source_unit_payload_citation(item: dict[str, Any]) -> ChatCitation:
    return ChatCitation(
        kind="raw_evidence",
        role="source",
        path=str(item.get("source_path")) if item.get("source_path") else None,
        title=str(item.get("title") or item.get("source_unit_id") or ""),
        vault_id=str(item.get("vault_id")) if item.get("vault_id") else None,
        vault_name=str(item.get("vault_name")) if item.get("vault_name") else None,
        vault_path=str(item.get("vault_path")) if item.get("vault_path") else None,
        evidence_id=str(item.get("evidence_id")) if item.get("evidence_id") else None,
        raw_revision_id=str(item.get("raw_revision_id")) if item.get("raw_revision_id") else None,
        source_unit_id=str(item.get("source_unit_id")),
        char_start=int(item["char_start"]) if item.get("char_start") is not None else None,
        char_end=int(item["char_end"]) if item.get("char_end") is not None else None,
        reason=str(item.get("reason") or "Raw source unit used as answer evidence."),
    )


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


def _hidden_count(reference_pool: list[ChatCitation], public_citations: list[ChatCitation]) -> int:
    public_keys = {_citation_source_key(citation) for citation in public_citations}
    return len([citation for citation in reference_pool if _citation_source_key(citation) not in public_keys])


def _unique_citations(citations: list[ChatCitation] | Any) -> list[ChatCitation]:
    seen: set[tuple[str, str, str, int | None, int | None]] = set()
    unique: list[ChatCitation] = []
    for citation in citations:
        target = _citation_target(citation)
        vault_identity = citation.vault_id or citation.vault_path or ""
        if not vault_identity and any(existing.kind == citation.kind and _citation_target(existing) == target and (existing.vault_id or existing.vault_path) for existing in unique):
            continue
        if vault_identity:
            unique = [
                existing
                for existing in unique
                if not (
                    existing.kind == citation.kind
                    and _citation_target(existing) == target
                    and not (existing.vault_id or existing.vault_path)
                )
            ]
            seen = {_citation_key(existing) for existing in unique}
        identity = _citation_key(citation)
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(citation)
    return unique


def _citation_key(citation: ChatCitation) -> tuple[str, str, str, int | None, int | None]:
    return (
        citation.kind,
        _citation_target(citation),
        citation.vault_id or citation.vault_path or "",
        citation.char_start,
        citation.char_end,
    )


def _citation_source_key(citation: ChatCitation) -> tuple[str, str, str]:
    return (citation.kind, _citation_target(citation), citation.vault_id or citation.vault_path or "")


def _citation_target(citation: ChatCitation) -> str:
    return citation.evidence_id or citation.source_unit_id or citation.path or citation.run_id or ""


def _answer_allows_file_paths(latest_user_text: str) -> bool:
    path_terms = {"路径", "文件名", "文件路径", "path", "file path", "filename", "page path"}
    return any(term in latest_user_text for term in path_terms)
