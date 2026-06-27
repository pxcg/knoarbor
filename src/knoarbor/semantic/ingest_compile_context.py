from __future__ import annotations

import re
from typing import Any, cast

from knoarbor.core.schemas.ingest_compile_context import (
    CompileCurrentContent,
    CompilePageContentKind,
    CompileOperationContext,
    CompilePageContext,
    CompilePageContextGroups,
    CompilePageRole,
    IngestCompileContext,
)
from knoarbor.core.schemas.knowledge_extract import KnowledgeExtract
from knoarbor.core.schemas.wiki_page_plan import WikiPagePlan


def build_ingest_compile_context(
    knowledge_extract: KnowledgeExtract,
    page_plan: WikiPagePlan,
    candidate_page_context: dict[str, Any] | None = None,
) -> IngestCompileContext:
    pages = _page_groups(candidate_page_context or {})
    return IngestCompileContext(
        source=knowledge_extract.source.model_dump(),
        current_content=CompileCurrentContent(
            title=knowledge_extract.source.title,
            source_type=knowledge_extract.source.source_type,
            source_app=knowledge_extract.source.source_app,
            source_id=knowledge_extract.source.source_id,
            source_path=knowledge_extract.source.source_path,
            primary_content=knowledge_extract.compile_context.primary_content,
            content_unit_count=len(knowledge_extract.content_units),
            warnings=list(knowledge_extract.warnings),
        ),
        attachments=_compile_attachments(knowledge_extract.attachments),
        operations=[
            CompileOperationContext(
                operation_index=index,
                action=operation.action,
                target_page=operation.target_page,
                page_dir=operation.page_dir,
                canonical_path=operation.canonical_path,
                title=operation.title,
                knowledge_object=operation.knowledge_object,
                selected_claim_ids=list(operation.selected_claim_ids),
                selected_relation_ids=list(operation.selected_relation_ids),
                source_digest_ids=list(operation.source_digest_ids),
                decision_reason=operation.decision_reason,
            )
            for index, operation in enumerate(page_plan.operations)
            if operation.action != "skip"
        ],
        page_context=pages,
        context_policy=str((candidate_page_context or {}).get("stats", {}).get("context_policy") or "target_full_related_excerpt_candidate_profile"),
        stats=dict((candidate_page_context or {}).get("stats", {}) or {}),
        warnings=list((candidate_page_context or {}).get("warnings", []) or []),
    )


def _page_groups(candidate_page_context: dict[str, Any]) -> CompilePageContextGroups:
    groups = CompilePageContextGroups()
    for raw_page in candidate_page_context.get("pages", []) or []:
        if not isinstance(raw_page, dict):
            continue
        page = CompilePageContext(
            path=str(raw_page.get("path") or ""),
            role=_page_role(raw_page.get("context_role")),
            content_kind=_content_kind(raw_page.get("content_kind")),
            exists=bool(raw_page.get("exists")),
            title=str(raw_page.get("title") or ""),
            summary=str(raw_page.get("summary") or ""),
            claim_points=[str(item) for item in raw_page.get("claim_points", []) or []],
            entities=[str(item) for item in raw_page.get("entities", []) or []],
            relations=_relation_rows(raw_page.get("relations")),
            headings=[str(item) for item in raw_page.get("headings", []) or []],
            source=raw_page.get("source") if isinstance(raw_page.get("source"), str) else None,
            content=str(raw_page.get("content") or ""),
            truncated=bool(raw_page.get("truncated")),
            original_content_length=int(raw_page.get("original_content_length") or 0),
            error=raw_page.get("error") if isinstance(raw_page.get("error"), str) else None,
        )
        if page.role == "target":
            groups.targets.append(page)
        elif page.role == "related":
            groups.related.append(page)
        else:
            groups.candidates.append(page)
    return groups


def _page_role(value: object) -> CompilePageRole:
    if value in {"target", "related", "candidate"}:
        return cast(CompilePageRole, value)
    return "candidate"


def _content_kind(value: object) -> CompilePageContentKind:
    if value in {"full", "excerpt", "profile", "missing"}:
        return cast(CompilePageContentKind, value)
    return "missing"


def _relation_rows(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        subject = str(item.get("subject") or "").strip()
        predicate = str(item.get("predicate") or "").strip()
        obj = str(item.get("object") or "").strip()
        claim = str(item.get("claim") or "").strip().upper()
        if subject and predicate and obj:
            rows.append({"subject": subject, "predicate": predicate, "object": obj, "claim": claim})
    return rows


def _compile_attachments(raw_attachments: list[dict[str, object]]) -> list[dict[str, object]]:
    """Build a lightweight attachment summary for the compile context.

    The LLM receives name, attachment_type, readable topic, caption, and path so it
    can generate human-readable descriptions. Raw MinerU content and binary
    hashes are excluded to keep the prompt compact.
    """
    items: list[dict[str, object]] = []
    for item in raw_attachments:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        caption = _attachment_text(item.get("caption") or metadata.get("caption") or metadata.get("image_caption") or metadata.get("table_caption"))
        topic = _attachment_text(item.get("topic") or item.get("title") or caption)
        summary: dict[str, object] = {
            "name": name,
            "attachment_type": str(item.get("attachment_type") or "file"),
            "relative_path": str(item.get("relative_path") or ""),
        }
        if topic:
            summary["topic"] = topic
        if caption:
            summary["caption"] = caption
        desc = _attachment_text(item.get("description"))
        if desc:
            summary["mineru_description"] = desc
        sub_type = str(metadata.get("sub_type") or "").strip()
        if sub_type:
            summary["sub_type"] = sub_type
        items.append(summary)
    return items


def _attachment_text(value: object, *, limit: int = 180) -> str:
    if isinstance(value, list):
        text = " ".join(str(part).strip() for part in value if str(part).strip())
    else:
        text = str(value or "").strip()
    if not text:
        return ""
    if re.search(r"<\s*(table|tr|td|th)\b", text, flags=re.IGNORECASE):
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if _looks_like_hash_filename(text):
        return ""
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def _looks_like_hash_filename(value: str) -> bool:
    path_name = value.strip().rsplit("/", 1)[-1]
    stem = path_name.rsplit(".", 1)[0]
    return bool(re.fullmatch(r"[0-9a-fA-F]{24,}", stem))
