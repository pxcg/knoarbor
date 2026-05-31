from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


LintReviewDecisionValue = Literal["approve", "defer", "reject"]
LintReviewNecessity = Literal["necessary", "redundant", "incomplete", "unsupported"]
LintReviewCorrectness = Literal["correct", "questionable", "incorrect"]
LintReviewCompleteness = Literal["complete", "partial", "blocked"]
LintReviewExecutorFit = Literal[
    "supported_by_draft_write",
    "supported_by_wiki_operation",
    "supported_by_refresh_request",
    "supported_by_report_only",
    "unsupported",
]
LintReviewRiskLevel = Literal["safe", "low", "medium", "high"]


class LintMaintenanceReviewDecision(BaseModel):
    operation_index: int = Field(..., ge=0)
    decision: LintReviewDecisionValue
    necessity: LintReviewNecessity
    correctness: LintReviewCorrectness
    completeness: LintReviewCompleteness
    executor_fit: LintReviewExecutorFit
    risk_level: LintReviewRiskLevel
    confidence: float = Field(..., ge=0, le=1)
    reason: str = Field(..., min_length=1)
    constraints: list[str] = Field(default_factory=list)
    required_followups: list[str] = Field(default_factory=list)


class LintMaintenanceReview(BaseModel):
    schema_version: Literal["lint_maintenance_review.v1"] = "lint_maintenance_review.v1"
    decisions: list[LintMaintenanceReviewDecision] = Field(default_factory=list)
    summary: str = Field(..., min_length=1)
    warnings: list[str] = Field(default_factory=list)
