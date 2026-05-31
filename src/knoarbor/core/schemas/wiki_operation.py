from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


WikiOperationAction = Literal[
    "rename_page",
    "merge_pages",
    "delete_page",
    "update_frontmatter",
    "replace_wikilink",
    "normalize_wikilink",
    "attach_related_pages",
    "attach_source_digest",
    "remove_related_links",
    "deduplicate_section_items",
    "remove_adjacent_duplicate_headings",
    "add_missing_section",
    "update_source_field",
]


class WikiOperationInput(BaseModel):
    operation_id: str = Field(..., min_length=1)
    action: WikiOperationAction
    target_page: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)
    risk_level: Literal["safe", "low", "medium", "high"]
    confidence: float = Field(..., ge=0, le=1)
    expected_effect: str = Field(..., min_length=1)
    before_hash: str | None = None
    related_pages: list[str] = Field(default_factory=list)
    new_path: str | None = None
    new_title: str | None = None
    old_target: str | None = None
    new_target: str | None = None
    link_text: str | None = None
    section: str | None = None
    section_content: str | None = None
    source_file: str | None = None
    source_pages: list[str] = Field(default_factory=list)
    frontmatter: dict[str, str] = Field(default_factory=dict)
    archive_sources: bool = True

    @field_validator("operation_id", "target_page", "reason", "expected_effect")
    @classmethod
    def strip_operation_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("wiki operation text fields cannot be empty")
        return text


class WikiOperationApplyRequest(BaseModel):
    obsidian_vault_path: str = Field(..., min_length=1)
    operations: list[WikiOperationInput] = Field(..., min_length=1)
    ledger_path: str = "maintenance/operation_ledger.jsonl"


class WikiOperationApplyResult(BaseModel):
    operation_id: str
    action: WikiOperationAction
    status: Literal["applied", "skipped"]
    target_page: str
    output_page: str | None = None
    archived_pages: list[str] = Field(default_factory=list)
    before_hash: str | None = None
    after_hash: str | None = None
    ledger_path: str
    details: dict[str, Any] = Field(default_factory=dict)


class WikiOperationApplyResponse(BaseModel):
    results: list[WikiOperationApplyResult]
    stats: dict[str, Any]
