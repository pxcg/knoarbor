from __future__ import annotations

from knoarbor.core.schemas.source_digest import SourceDigest
from knoarbor.core.schemas.wiki_draft_batch import WikiDraftBatchItem
from knoarbor.core.schemas.wiki_page_plan import WikiPageOperation, WikiPagePlan
from knoarbor.core.schemas.wiki_write import WikiPatchInput


def build_source_digest_drafts_from_plan(
    page_plan: WikiPagePlan,
    source_digest: SourceDigest,
) -> list[WikiDraftBatchItem]:
    """Build source digest audit drafts without model compilation."""

    return [
        _source_digest_draft_from_operation(index, operation, source_digest)
        for index, operation in enumerate(page_plan.operations)
        if operation.page_dir == "sources" and operation.action in {"create", "update"}
    ]


def _source_digest_draft_from_operation(
    operation_index: int,
    operation: WikiPageOperation,
    source_digest: SourceDigest,
) -> WikiDraftBatchItem:
    title = operation.title or source_digest.source.title or "Source Digest"
    summary = source_digest.summary or _source_digest_audit_summary(source_digest)
    question = operation.knowledge_object or source_digest.source_focus or title
    source_file = source_digest.raw_source or source_digest.source.source_path or source_digest.source.source_id
    evidence = _source_digest_evidence_rows(source_digest)
    claims = _source_digest_contribution_rows(source_digest)
    unresolved = [f"{item.item_id}: {item.reason}" for item in source_digest.unresolved_items]
    patches = (
        _source_digest_update_patches(
            source_digest=source_digest,
            source_file=source_file or "",
            summary=summary,
            evidence=evidence,
            claims=claims,
            unresolved=unresolved,
        )
        if operation.action == "update"
        else []
    )
    return WikiDraftBatchItem(
        operation_index=operation_index,
        write_action=operation.action,
        target_page=operation.target_page,
        source_file=source_file,
        title=title,
        page_dir="sources",
        canonical_path=operation.canonical_path or "",
        legacy_paths=list(operation.legacy_paths),
        page_kind=operation.page_kind or "source_digest",
        subject_kind=operation.subject_kind or "source",
        facets=list(operation.facets),
        question=question,
        answer=summary,
        summary=summary,
        claims=claims,
        evidence=evidence,
        key_points=unresolved,
        source_digest_ids=_merge_strings(list(operation.source_digest_ids), [source_digest.digest_id]),
        confidence=source_digest.confidence,
        model_provider="knoarbor",
        model_name="deterministic-source-digest",
        patches=patches,
    )


def _source_digest_audit_summary(source_digest: SourceDigest) -> str:
    raw_pointer = source_digest.raw_source or source_digest.source.source_path or source_digest.source.source_id or "not recorded"
    return (
        f"Audit record for {source_digest.source.title or source_digest.digest_id}. "
        f"Source units: {len(source_digest.units)}. "
        f"Contributions: {len(source_digest.contribution_map)}. "
        f"Unresolved items: {len(source_digest.unresolved_items)}. "
        f"Raw pointer: {raw_pointer}."
    )


def _source_digest_evidence_rows(source_digest: SourceDigest) -> list[str]:
    source_path = source_digest.raw_source or source_digest.source.source_path or source_digest.source.source_id or source_digest.digest_id
    rows: list[str] = []
    for index, unit in enumerate(source_digest.units, start=1):
        basis = " ".join((unit.summary or unit.evidence.excerpt or "source unit").replace("|", "/").split())
        rows.append(f"U{index} | {source_path} | unit:{unit.index} | {basis[:220]} | high")
    if rows:
        return rows
    return [f"U1 | {source_path} | source-level | source digest compiled from this raw source | medium"]


def _source_digest_contribution_rows(source_digest: SourceDigest) -> list[str]:
    return [
        f"{item.item_id}: {item.contribution}"
        for item in source_digest.contribution_map
        if item.contribution.strip()
    ]


def _source_digest_update_patches(
    *,
    source_digest: SourceDigest,
    source_file: str,
    summary: str,
    evidence: list[str],
    claims: list[str],
    unresolved: list[str],
) -> list[WikiPatchInput]:
    return [
        WikiPatchInput(operation="replace_section", section="Audit Summary", content=summary),
        WikiPatchInput(operation="replace_section", section="Source Units", content=_source_units_table(evidence, source_file)),
        WikiPatchInput(operation="replace_section", section="Contribution Map", content=_contribution_table(claims)),
        WikiPatchInput(operation="replace_section", section="Unresolved / Rejected", content=_unresolved_list(unresolved)),
        WikiPatchInput(
            operation="replace_section",
            section="Raw Source",
            content=f"- Raw source: {source_file or source_digest.digest_id}\n- Content hash: {source_digest.content_hash or 'not recorded'}",
        ),
    ]


def _source_units_table(items: list[str], fallback_source: str) -> str:
    rows = ["| Unit | Source | Range | Basis | Confidence |", "|---|---|---|---|---|"]
    for index, item in enumerate(items, start=1):
        parts = [part.strip() for part in item.split("|")]
        if len(parts) >= 5:
            rows.append("| " + " | ".join(parts[:5]) + " |")
        else:
            rows.append(f"| U{index} | {fallback_source} | source-level | {item} | medium |")
    return "\n".join(rows)


def _contribution_table(items: list[str]) -> str:
    if not items:
        return "- No accepted contribution map was generated."
    rows = ["| Item | Contribution | Evidence Units | Target Page |", "|---|---|---|---|"]
    for index, item in enumerate(items, start=1):
        item_id, _, contribution = item.partition(":")
        rows.append(f"| {item_id.strip() or f'C{index}'} | {contribution.strip() or item} | U{index} | source digest |")
    return "\n".join(rows)


def _unresolved_list(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- No unresolved or rejected material recorded."


def _merge_strings(left: list[str], right: list[str]) -> list[str]:
    result: list[str] = []
    for item in [*left, *right]:
        if item and item not in result:
            result.append(item)
    return result
