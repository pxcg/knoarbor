from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


WikiWriteAction = Literal["create", "update", "merge"]
WikiPatchOperation = Literal["append_section", "replace_section", "merge_list"]


class WikiPatchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: WikiPatchOperation
    section: str = Field(..., min_length=1)
    content: str | None = None
    heading: str | None = None
    items: list[str] = Field(default_factory=list)
    max_items: int | None = Field(default=None, ge=0, le=50)

    @field_validator("section")
    @classmethod
    def strip_section(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("patch section cannot be empty")
        return text

    @field_validator("items", mode="before")
    @classmethod
    def null_items_to_empty_list(cls, value: Any) -> Any:
        return [] if value is None else value


class WikiDraftWriteResponse(BaseModel):
    wiki_file_path: str
    wiki_md_content: str
    stats: dict[str, Any]


class WikiDraftInput(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    title: str = Field(..., min_length=1)
    page_dir: str = Field(..., min_length=1)
    canonical_path: str | None = None
    legacy_paths: list[str] = Field(default_factory=list)
    page_kind: str = ""
    subject_kind: str = ""
    role: str = ""
    facets: list[str] = Field(default_factory=list)
    question: str = Field(..., min_length=1)
    summary: str = Field(..., min_length=1)
    claims: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    relations: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    synthesis: str = Field(..., min_length=1)
    unresolved_items: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.8, ge=0, le=1)
    model_provider: str = "external"
    model_name: str = "semantic-workflow"
    patches: list[WikiPatchInput] = Field(default_factory=list)
    source_digest_ids: list[str] = Field(default_factory=list)
    atom_ids: list[str] = Field(default_factory=list)

    @field_validator("title", "page_dir", "question", "summary", "synthesis", "model_provider", "model_name")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("wiki draft text fields cannot be empty")
        return text

    @field_validator("legacy_paths", "facets", "source_digest_ids", "atom_ids", mode="before")
    @classmethod
    def normalize_id_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("wiki draft trace fields must be lists")
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            text = str(item).strip()
            if text and text not in seen:
                normalized.append(text)
                seen.add(text)
        return normalized

    @field_validator("claims", "entities", "relations", "evidence", mode="before")
    @classmethod
    def normalize_optional_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("wiki draft evidence fields must be lists")
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            text = str(item).strip()
            if text and text not in seen:
                normalized.append(text)
                seen.add(text)
        return normalized


class WikiDraftBatchWriteItem(BaseModel):
    wiki_draft: WikiDraftInput
    write_action: WikiWriteAction = "create"
    target_page: str | None = None
    source_file: str | None = None
    display_source_file: str | None = None
    operation_index: int | None = None
    expected_related_pages: list[str] = Field(default_factory=list)


class WikiDraftBatchWriteRequest(BaseModel):
    drafts: list[WikiDraftBatchWriteItem] = Field(..., min_length=1)
    vault_path: str = Field(..., min_length=1)
    auto_related_links: bool = True
    provenance_related_links: bool | None = None


class WikiDraftBatchWriteResponse(BaseModel):
    results: list[WikiDraftWriteResponse]
    stats: dict[str, Any]


class WikiDraft(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    title: str
    page_dir: str
    page_type: str
    canonical_path: str = ""
    legacy_paths: list[str] = Field(default_factory=list)
    page_kind: str = ""
    subject_kind: str = ""
    role: str = "knowledge_page"
    facets: list[str] = Field(default_factory=list)
    question: str
    summary: str
    claims: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    relations: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    synthesis: str
    unresolved_items: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    model_provider: str
    model_name: str
    patches: list[WikiPatchInput] = Field(default_factory=list)
    source_digest_ids: list[str] = Field(default_factory=list)
    atom_ids: list[str] = Field(default_factory=list)


class VaultWriteResult(BaseModel):
    path: Path
    content: str
    created: bool
    related_links: list[str]
    content_hash: str
    canonical_path: str = ""
    legacy_paths: list[str] = Field(default_factory=list)
    page_kind: str = ""
    subject_kind: str = ""
    role: str = ""
    facets: list[str] = Field(default_factory=list)
    write_details: dict[str, Any] = Field(default_factory=dict)
