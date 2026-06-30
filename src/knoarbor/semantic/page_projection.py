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
        drafts.append(_project_draft(draft, assembly, source_digest))
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
    return draft.model_copy(update=update)


def _project_draft(draft: WikiDraftBatchItem, assembly: dict[str, object], source_digest: SourceDigest | None = None) -> WikiDraftBatchItem:
    source_digest_ids = _merge_strings(draft.source_digest_ids, _strings(assembly.get("source_digest_ids")))
    atom_ids = _merge_strings(draft.atom_ids, _strings(assembly.get("atom_ids")))
    attachments = _draft_attachments(draft, source_digest)
    return draft.model_copy(
        update={
            "claims": _claim_rows(assembly),
            "entities": _strings(assembly.get("entities")),
            "relations": _relation_rows(assembly),
            "evidence": _evidence_rows(assembly),
            "source_digest_ids": source_digest_ids,
            "atom_ids": atom_ids,
            "attachments": attachments,
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
        "attachments": _dedupe_attachment_dicts([attachment.model_dump() for attachment in source_digest.attachments]),
        "claims": claims,
        "unresolved_items": [f"{item.item_id}: {item.reason}" for item in source_digest.unresolved_items],
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


def _draft_attachments(draft: WikiDraftBatchItem, source_digest: SourceDigest | None) -> list[dict[str, object]]:
    if source_digest is not None and source_digest.attachments:
        llm_descriptions = _llm_attachment_descriptions(draft)
        merged: list[dict[str, object]] = []
        for attachment in source_digest.attachments:
            item = attachment.model_dump()
            name = str(item.get("name") or "").strip()
            llm_description = llm_descriptions.get(name, "") if name else ""
            existing_description = str(item.get("description") or "").strip()
            if llm_description and (not existing_description or not _looks_generic_attachment_description(llm_description)):
                item["description"] = llm_description
            merged.append(item)
        return _dedupe_attachment_dicts(merged)
    return _dedupe_attachment_dicts(list(draft.attachments))


def _llm_attachment_descriptions(draft: WikiDraftBatchItem) -> dict[str, str]:
    descriptions: dict[str, str] = {}
    for item in draft.attachments:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        desc = str(item.get("description") or "").strip()
        if name and desc:
            descriptions[name] = desc
    return descriptions


def _dedupe_attachment_dicts(items: list[dict[str, object]]) -> list[dict[str, object]]:
    deduped: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in items:
        identity = _attachment_identity(item)
        if identity and identity in seen:
            continue
        if identity:
            seen.add(identity)
        deduped.append(item)
    return deduped


def _attachment_identity(item: dict[str, object]) -> str:
    for field in ("content_hash", "relative_path", "path", "name"):
        value = str(item.get(field) or "").strip()
        if value:
            return f"{field}:{value}"
    return ""


def _looks_generic_attachment_description(value: str) -> bool:
    text = " ".join(value.strip().lower().split())
    if not text:
        return True
    generic_values = {
        "image",
        "picture",
        "product image",
        "product picture",
        "attachment image",
        "产品图片",
        "产品图",
        "图片",
        "附件图片",
    }
    return text in generic_values or (len(text) <= 18 and any(term in text for term in ("产品图片", "product image")))
