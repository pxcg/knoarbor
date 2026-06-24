from __future__ import annotations

from typing import Any

from knoarbor.core.schemas.source_digest import SourceDigest
from knoarbor.core.schemas.wiki_draft_batch import WikiDraftBatch, WikiDraftBatchItem
from knoarbor.core.schemas.wiki_page_plan import WikiPagePlan


def project_draft_batch_from_page_assembly(
    draft_batch: WikiDraftBatch,
    page_assembly: dict[str, object],
    wiki_page_plan: WikiPagePlan | None = None,
    source_digest: SourceDigest | None = None,
) -> WikiDraftBatch:
    """Project deterministic assembly fields onto model-authored drafts.

    The model remains responsible for readable summary/synthesis text. The
    auditable wiki body fields are derived from selected knowledge atoms so
    claims, relations, and evidence keep stable IDs and source traces.
    """

    assembly_by_index = _assembly_by_operation_index(page_assembly)
    if not assembly_by_index:
        assembly_by_index = {}
    operations_by_index = {
        index: operation
        for index, operation in enumerate(wiki_page_plan.operations)
    } if wiki_page_plan is not None else {}

    drafts: list[WikiDraftBatchItem] = []
    for draft in draft_batch.drafts:
        assembly = assembly_by_index.get(draft.operation_index)
        operation = operations_by_index.get(draft.operation_index)
        draft = _project_operation_trace(draft, operation)
        if not assembly or draft.page_dir == "sources":
            if draft.page_dir == "sources" and source_digest is not None:
                draft = _project_source_digest_draft(draft, source_digest)
            drafts.append(draft)
            continue
        drafts.append(_project_draft(draft, assembly))
    return draft_batch.model_copy(update={"drafts": drafts})


def _project_operation_trace(draft: WikiDraftBatchItem, operation: object) -> WikiDraftBatchItem:
    if operation is None:
        return draft
    source_digest_ids = _merge_strings(
        draft.source_digest_ids,
        [str(item).strip() for item in getattr(operation, "source_digest_ids", []) if str(item).strip()],
    )
    update: dict[str, object] = {"source_digest_ids": source_digest_ids}
    canonical_path = str(getattr(operation, "canonical_path", "") or "").strip()
    if canonical_path and not draft.canonical_path:
        update["canonical_path"] = canonical_path
    page_kind = str(getattr(operation, "page_kind", "") or "").strip()
    if page_kind and not draft.page_kind:
        update["page_kind"] = page_kind
    subject_kind = str(getattr(operation, "subject_kind", "") or "").strip()
    if subject_kind and not draft.subject_kind:
        update["subject_kind"] = subject_kind
    facets = [str(item).strip() for item in getattr(operation, "facets", []) if str(item).strip()]
    if facets and not draft.facets:
        update["facets"] = facets
    return draft.model_copy(update=update)


def _project_draft(draft: WikiDraftBatchItem, assembly: dict[str, object]) -> WikiDraftBatchItem:
    source_digest_ids = _merge_strings(draft.source_digest_ids, _strings(assembly.get("source_digest_ids")))
    atom_ids = _merge_strings(draft.atom_ids, _strings(assembly.get("atom_ids")))
    return draft.model_copy(
        update={
            "claims": _claim_rows(assembly),
            "entities": _strings(assembly.get("entities")),
            "relations": _relation_rows(assembly),
            "evidence": _evidence_rows(assembly),
            "source_digest_ids": source_digest_ids,
            "atom_ids": atom_ids,
        }
    )


def _project_source_digest_draft(draft: WikiDraftBatchItem, source_digest: SourceDigest) -> WikiDraftBatchItem:
    source_path = source_digest.raw_source or source_digest.source.source_path or draft.source_file or ""
    evidence = [
        _source_unit_evidence_row(unit_index=index, source_path=source_path, summary=unit.summary or unit.evidence.excerpt)
        for index, unit in enumerate(source_digest.units, start=1)
    ]
    if not evidence:
        evidence = [f"U1 | {source_path or source_digest.digest_id} | source-level | source digest compiled from this raw source | medium"]
    claims = [
        f"C{index}: {item.contribution}"
        for index, item in enumerate(source_digest.contribution_map, start=1)
        if item.contribution.strip()
    ]
    update: dict[str, object] = {
        "source_digest_ids": _merge_strings(draft.source_digest_ids, [source_digest.digest_id]),
        "evidence": evidence,
        "claims": claims,
        "key_points": [f"{item.item_id}: {item.reason}" for item in source_digest.unresolved_items],
    }
    if source_digest.summary.strip():
        update["summary"] = source_digest.summary.strip()
    if source_digest.source_focus.strip() and not draft.question.strip():
        update["question"] = source_digest.source_focus.strip()
    return draft.model_copy(update=update)


def _source_unit_evidence_row(*, unit_index: int, source_path: str, summary: str) -> str:
    basis = _clean_cell(summary, limit=220) or "source unit"
    return f"U{unit_index} | {source_path} | unit:{unit_index - 1} | {basis} | high"


def _claim_rows(assembly: dict[str, object]) -> list[str]:
    rows: list[str] = []
    for item in _dicts(assembly.get("claims")):
        text = str(item.get("text") or "").strip()
        number = str(item.get("number") or "").strip()
        if text:
            rows.append(text)
        elif number:
            rows.append(f"{number}. {item.get('claim_id', '')}".strip())
    return rows


def _relation_rows(assembly: dict[str, object]) -> list[str]:
    return [str(item.get("triple") or "").strip() for item in _dicts(assembly.get("relations")) if str(item.get("triple") or "").strip()]


def _evidence_rows(assembly: dict[str, object]) -> list[str]:
    rows: list[str] = []
    for item in _dicts(assembly.get("evidence")):
        claim = str(item.get("claim") or "").strip()
        source = str(item.get("source") or "").strip()
        source_range = str(item.get("range") or "").strip()
        basis = _clean_cell(str(item.get("basis") or "").strip())
        confidence = str(item.get("confidence") or "").strip()
        if claim and source and source_range and basis and confidence:
            rows.append(f"{claim} | {source} | {source_range} | {basis} | {confidence}")
    return rows


def _clean_cell(value: str, *, limit: int = 500) -> str:
    text = " ".join(value.replace("|", "/").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _assembly_by_operation_index(payload: dict[str, object]) -> dict[int, dict[str, object]]:
    result: dict[int, dict[str, object]] = {}
    operations = payload.get("operations")
    if not isinstance(operations, list):
        return result
    for item in operations:
        if isinstance(item, dict) and isinstance(item.get("operation_index"), int):
            result[item["operation_index"]] = item
    return result


def _dicts(value: object) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _strings(value: object) -> list[str]:
    return [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else []


def _merge_strings(left: list[str], right: list[str]) -> list[str]:
    result: list[str] = []
    for item in [*left, *right]:
        if item and item not in result:
            result.append(item)
    return result
