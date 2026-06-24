from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


WikiPagePlanAction = Literal["create", "update", "skip"]
WikiPageDir = Literal["sources", "entities", "concepts", "comparisons", "queries", "timelines", "workflows"]


class WikiRelatedPage(BaseModel):
    path: str = Field(..., min_length=1)
    title: str = ""
    relation: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)


class WikiCandidatePage(BaseModel):
    path: str = Field(..., min_length=1)
    title: str = ""
    match_reason: str = Field(..., min_length=1)


class WikiPageOperation(BaseModel):
    action: WikiPagePlanAction
    target_page: str | None = None
    page_dir: WikiPageDir | None = None
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
    related_pages: list[WikiRelatedPage] = Field(default_factory=list)
    candidate_pages: list[WikiCandidatePage] = Field(default_factory=list)
    decision_reason: str = Field(..., min_length=1)

    @field_validator("target_page")
    @classmethod
    def blank_target_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None

    @field_validator("canonical_path")
    @classmethod
    def blank_canonical_path_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip().lstrip("/")
        return text or None

    @field_validator("legacy_paths", "facets", "selected_claim_ids", "selected_relation_ids", "source_digest_ids", mode="before")
    @classmethod
    def normalize_id_list(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        ids: list[str] = []
        for item in value if isinstance(value, list) else []:
            text = str(item).strip()
            if text and text not in ids:
                ids.append(text)
        return ids

    @model_validator(mode="after")
    def validate_target_page(self) -> WikiPageOperation:
        if self.action == "update" and not self.target_page:
            raise ValueError(f"{self.action} operation requires target_page")
        if self.action in {"create", "skip"} and self.target_page:
            raise ValueError(f"{self.action} operation must not set target_page")
        if self.action in {"create", "update"}:
            if not self.page_dir:
                raise ValueError(f"{self.action} operation requires page_dir")
            if not self.title or not self.title.strip():
                raise ValueError(f"{self.action} operation requires title")
            if not self.knowledge_object or not self.knowledge_object.strip():
                raise ValueError(f"{self.action} operation requires knowledge_object")
            if not self.source_digest_ids:
                raise ValueError(f"{self.action} operation requires source_digest_ids")
            if self.page_dir != "sources" and not self.selected_claim_ids:
                raise ValueError(f"{self.action} non-source operation requires selected_claim_ids")
        if self.action == "skip":
            self.title = (self.title or "Skipped source").strip()
            self.knowledge_object = (self.knowledge_object or "No durable wiki object").strip()
        return self


class WikiPagePlan(BaseModel):
    operations: list[WikiPageOperation] = Field(..., min_length=1)
    overall_summary: str = Field(..., min_length=1)
    confidence: float = Field(default=0.8, ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def canonicalize_skip_operations(self) -> WikiPagePlan:
        actionable = [operation for operation in self.operations if operation.action != "skip"]
        if actionable and len(actionable) != len(self.operations):
            self.operations = actionable
            self.warnings.append("Dropped redundant skip operation because actionable page operations were present.")
        return self
