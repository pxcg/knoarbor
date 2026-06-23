from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


CompilePageRole = Literal["target", "related", "candidate"]
CompilePageContentKind = Literal["full", "excerpt", "profile", "missing"]


class CompileCurrentContent(BaseModel):
    title: str = ""
    source_type: str = ""
    source_app: str = ""
    source_id: str | None = None
    source_path: str | None = None
    primary_content: str = ""
    content_unit_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class CompileOperationContext(BaseModel):
    operation_index: int = Field(..., ge=0)
    action: str
    target_page: str | None = None
    page_dir: str | None = None
    canonical_path: str | None = None
    legacy_paths: list[str] = Field(default_factory=list)
    page_kind: str | None = None
    subject_kind: str | None = None
    facets: list[str] = Field(default_factory=list)
    title: str | None = None
    knowledge_object: str | None = None
    selected_claim_ids: list[str] = Field(default_factory=list)
    selected_relation_ids: list[str] = Field(default_factory=list)
    source_digest_ids: list[str] = Field(default_factory=list)
    decision_reason: str = ""


class CompilePageContext(BaseModel):
    path: str
    role: CompilePageRole
    content_kind: CompilePageContentKind
    exists: bool
    title: str = ""
    summary: str = ""
    key_points: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    headings: list[str] = Field(default_factory=list)
    source: str | None = None
    content: str = ""
    truncated: bool = False
    original_content_length: int = 0
    error: str | None = None


class CompilePageContextGroups(BaseModel):
    targets: list[CompilePageContext] = Field(default_factory=list)
    related: list[CompilePageContext] = Field(default_factory=list)
    candidates: list[CompilePageContext] = Field(default_factory=list)


class IngestCompileContext(BaseModel):
    schema_version: Literal["ingest_compile_context.v1"] = "ingest_compile_context.v1"
    source: dict[str, object] = Field(default_factory=dict)
    current_content: CompileCurrentContent
    operations: list[CompileOperationContext] = Field(default_factory=list)
    page_context: CompilePageContextGroups = Field(default_factory=CompilePageContextGroups)
    context_policy: str = "target_full_related_excerpt_candidate_profile"
    stats: dict[str, object] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
