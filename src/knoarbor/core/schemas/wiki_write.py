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
    question: str = Field(..., min_length=1)
    answer: str = Field(..., min_length=1)
    summary: str = Field(..., min_length=1)
    key_points: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.8, ge=0, le=1)
    model_provider: str = "external"
    model_name: str = "semantic-workflow"
    patches: list[WikiPatchInput] = Field(default_factory=list)

    @field_validator("title", "page_dir", "question", "answer", "summary", "model_provider", "model_name")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("wiki draft text fields cannot be empty")
        return text


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
    obsidian_vault_path: str = Field(..., min_length=1)
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
    question: str
    answer: str
    summary: str
    key_points: list[str]
    tags: list[str]
    confidence: float = Field(ge=0, le=1)
    model_provider: str
    model_name: str
    patches: list[WikiPatchInput] = Field(default_factory=list)


class VaultWriteResult(BaseModel):
    path: Path
    content: str
    created: bool
    related_links: list[str]
    content_hash: str
    write_details: dict[str, Any] = Field(default_factory=dict)
