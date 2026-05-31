from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


WikiRelationAction = Literal["create", "update", "skip"]
WikiPageDir = Literal["sources", "entities", "concepts", "comparisons", "queries", "claims", "timelines", "workflows"]


class WikiRelatedPage(BaseModel):
    path: str = Field(..., min_length=1)
    title: str = ""
    relation: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)


class WikiCandidatePage(BaseModel):
    path: str = Field(..., min_length=1)
    title: str = ""
    match_reason: str = Field(..., min_length=1)


class WikiRelationOperation(BaseModel):
    action: WikiRelationAction
    target_page: str | None = None
    page_dir: WikiPageDir
    title: str | None = None
    knowledge_object: str | None = None
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

    @model_validator(mode="after")
    def validate_target_page(self) -> WikiRelationOperation:
        if self.action == "update" and not self.target_page:
            raise ValueError(f"{self.action} operation requires target_page")
        if self.action in {"create", "skip"} and self.target_page:
            raise ValueError(f"{self.action} operation must not set target_page")
        if self.action in {"create", "update"}:
            if not self.title or not self.title.strip():
                raise ValueError(f"{self.action} operation requires title")
            if not self.knowledge_object or not self.knowledge_object.strip():
                raise ValueError(f"{self.action} operation requires knowledge_object")
        if self.action == "skip":
            self.title = (self.title or "Skipped source").strip()
            self.knowledge_object = (self.knowledge_object or "No durable wiki object").strip()
        return self


class WikiRelationPlan(BaseModel):
    operations: list[WikiRelationOperation] = Field(..., min_length=1)
    overall_summary: str = Field(..., min_length=1)
    confidence: float = Field(default=0.8, ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_skip_is_exclusive(self) -> WikiRelationPlan:
        actions = {operation.action for operation in self.operations}
        if "skip" in actions and len(actions) > 1:
            raise ValueError("skip cannot be mixed with actionable operations")
        return self
