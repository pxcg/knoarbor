from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


IngestReviewDecisionValue = Literal["approve", "reject", "revise"]
IngestReviewRiskLevel = Literal["low", "medium", "high"]
IngestWriteSafety = Literal["safe_create", "safe_update", "needs_revision", "reject"]


class IngestReviewDimensionScores(BaseModel):
    source_support: float = Field(..., ge=0, le=1)
    page_boundary: float = Field(..., ge=0, le=1)
    directory_fit: float = Field(..., ge=0, le=1)
    duplication_risk: float = Field(..., ge=0, le=1)
    relation_quality: float = Field(..., ge=0, le=1)
    completeness: float = Field(..., ge=0, le=1)
    maintainability: float = Field(..., ge=0, le=1)
    patch_safety: float = Field(..., ge=0, le=1)


class IngestReviewChecks(BaseModel):
    operation_aligned: bool
    page_boundary_clear: bool
    directory_fit: bool
    source_supported: bool
    not_duplicate: bool
    relation_quality: bool
    complete_enough: bool
    maintainable: bool
    patch_safe: bool
    write_safe: bool


class IngestDraftReviewDecision(BaseModel):
    operation_index: int = Field(..., ge=0)
    decision: IngestReviewDecisionValue
    quality_score: float = Field(..., ge=0, le=1)
    risk_level: IngestReviewRiskLevel
    write_safety: IngestWriteSafety
    reason: str = Field(..., min_length=1)
    required_changes: list[str] = Field(default_factory=list)
    dimension_scores: IngestReviewDimensionScores
    checks: IngestReviewChecks


class IngestDraftReview(BaseModel):
    schema_version: Literal["ingest_draft_review.v2"] = "ingest_draft_review.v2"
    decisions: list[IngestDraftReviewDecision] = Field(default_factory=list)
    batch_decision: Literal["approve", "partial", "reject"]
    summary: str = Field(..., min_length=1)
    warnings: list[str] = Field(default_factory=list)
