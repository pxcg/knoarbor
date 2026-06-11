from __future__ import annotations

from typing import Any
from typing import Literal

from pydantic import BaseModel, Field

from knoarbor.core.schemas.lint_candidates import MaintenanceCandidate


class IngestSourceResult(BaseModel):
    connector: str
    source_id: str
    source_file: str
    should_process: bool
    mode: str
    reason: str
    status: Literal["processed", "skipped", "ignored", "failed", "written", "rejected"] = "processed"
    error_stage: str | None = None
    error_code: str | None = None
    error_category: str | None = None
    error_retryable: bool = False
    error_hint: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    semantic_result: Any | None = None
    approved_operation_indexes: list[int] = Field(default_factory=list)
    generated_pages: list[str] = Field(default_factory=list)
    redaction: dict[str, object] = Field(default_factory=dict)
    context: dict[str, object] = Field(default_factory=dict)
    quality_gate: dict[str, object] = Field(default_factory=dict)
    touched_pages: list[str] = Field(default_factory=list)
    scoped_lint: dict[str, object] = Field(default_factory=dict)
    scoped_lint_result: dict[str, object] = Field(default_factory=dict)
    report_path: str | None = None
    ledger_path: str | None = None
    wrote: bool = False
    metrics: dict[str, object] = Field(default_factory=dict)
    checkpoint: dict[str, object] = Field(default_factory=dict)
    semantic_skip_reason: str | None = None
    segmentation: dict[str, object] = Field(default_factory=dict)
    segments: list[dict[str, object]] = Field(default_factory=list)


class IngestPipelineResult(BaseModel):
    results: list[IngestSourceResult] = Field(default_factory=list)
    stats: dict[str, int] = Field(default_factory=dict)
    document_processing: Any = Field(default_factory=dict)
    lifecycle_candidates: list[MaintenanceCandidate] = Field(default_factory=list)
    report_path: str | None = None
    ledger_path: str | None = None
    metrics: dict[str, object] = Field(default_factory=dict)
