from __future__ import annotations

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
from knoarbor.core.schemas.wiki_relation_plan import WikiRelationPlan


def build_ingest_compile_context(
    knowledge_extract: KnowledgeExtract,
    relation_plan: WikiRelationPlan,
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
        operations=[
            CompileOperationContext(
                operation_index=index,
                action=operation.action,
                target_page=operation.target_page,
                page_dir=operation.page_dir,
                title=operation.title,
                knowledge_object=operation.knowledge_object,
                decision_reason=operation.decision_reason,
            )
            for index, operation in enumerate(relation_plan.operations)
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
            key_points=[str(item) for item in raw_page.get("key_points", []) or []],
            tags=[str(item) for item in raw_page.get("tags", []) or []],
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
