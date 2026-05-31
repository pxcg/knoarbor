from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


MaintenanceCandidateSource = Literal["structural", "provenance", "quality", "freshness", "graph"]
MaintenanceCandidateSeverity = Literal["high", "medium", "low"]
MaintenanceRiskHint = Literal["safe", "low", "medium", "high"]
MaintenanceExecutorHint = Literal[
    "deterministic_wiki_operation",
    "draft_write",
    "refresh_request",
    "report_only",
    "unsupported",
]
QualityDimension = Literal[
    "factuality",
    "completeness",
    "clarity",
    "relevance",
    "structure",
    "provenance",
    "freshness",
    "graph_integration",
]


class MaintenanceEvidence(BaseModel):
    kind: str = Field(..., min_length=1)
    ref: str = Field(..., min_length=1)
    quote: str = Field(..., min_length=1)


class MaintenanceRecommendedAction(BaseModel):
    action: str = Field(..., min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)


class MaintenanceCandidate(BaseModel):
    candidate_id: str = Field(..., min_length=1)
    source: MaintenanceCandidateSource
    target_page: str = Field(..., min_length=1)
    issue_type: str = Field(..., min_length=1)
    severity: MaintenanceCandidateSeverity
    confidence: float = Field(..., ge=0, le=1)
    risk_hint: MaintenanceRiskHint
    executor_hint: MaintenanceExecutorHint
    evidence: list[MaintenanceEvidence] = Field(default_factory=list)
    recommended_action: MaintenanceRecommendedAction
    related_pages: list[str] = Field(default_factory=list)
    expected_effect: str = Field(..., min_length=1)
    review_notes: str = Field(..., min_length=1)

    @field_validator("candidate_id", "target_page", "issue_type", "expected_effect", "review_notes")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("maintenance candidate text fields cannot be empty")
        return text


class PageQualityDimensionReview(BaseModel):
    dimension: QualityDimension
    score: float = Field(..., ge=0, le=1)
    severity: MaintenanceCandidateSeverity
    finding: str = Field(..., min_length=1)
    evidence: str = ""
    recommendation: str = ""


class PageQualityReview(BaseModel):
    path: str = Field(..., min_length=1)
    verdict: Literal["good", "needs_maintenance", "needs_refresh", "low_value"]
    overall_score: float = Field(..., ge=0, le=1)
    dimension_reviews: list[PageQualityDimensionReview] = Field(default_factory=list)


class MaintenanceCandidates(BaseModel):
    schema_version: Literal["maintenance_candidates.v1"] = "maintenance_candidates.v1"
    candidates: list[MaintenanceCandidate] = Field(default_factory=list)
    page_reviews: list[PageQualityReview] = Field(default_factory=list)
    summary: str = Field(..., min_length=1)
    warnings: list[str] = Field(default_factory=list)
