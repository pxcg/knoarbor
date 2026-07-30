from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from knoarbor.core.schemas.execution import WorkflowExecutionMode
from knoarbor.core.schemas.maintenance import MaintenanceScope


WikiLintCandidateSource = Literal["structural", "provenance", "quality", "freshness", "graph"]
WikiLintCandidateSeverity = Literal["high", "medium", "low"]
LintRunMode = Literal["deterministic", "semantic"]


class WikiLintRequest(BaseModel):
    vault_path: str = Field(..., min_length=1)
    write_report: bool = True
    report_path: str | None = None
    scope_pages: list[str] = Field(default_factory=list)
    include_related: bool = True


class WikiLintIssue(BaseModel):
    code: str
    severity: Literal["error", "warning", "info"]
    path: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class WikiLintFix(BaseModel):
    issue_code: str
    path: str
    action: str
    mode: Literal["auto_applied", "safe_auto", "manual"]
    description: str


class WikiLintResponse(BaseModel):
    issues: list[WikiLintIssue]
    stats: dict[str, Any]
    fixes: list[WikiLintFix] = Field(default_factory=list)
    report_path: str | None = None
    report_content: str | None = None


class LintPolicyDecision(BaseModel):
    triggered: bool
    mode: LintRunMode
    trigger_reasons: list[str] = Field(default_factory=list)
    recommended_mode: LintRunMode = "deterministic"
    deferred_issue_count: int = 0


class LintRunRequest(BaseModel):
    execution: WorkflowExecutionMode = "queued"
    vault_path: str | None = Field(default=None, min_length=1)
    vault_id: str | None = None
    config_path: str | None = None
    provider: str | None = None
    scope: MaintenanceScope
    mode: LintRunMode = "deterministic"
    include_related: bool = True
    write_report: bool = True
    report_path: str | None = None
    append_ledger: bool = True
    ledger_path: str = ".knoarbor/ledgers/lint_run.jsonl"
    max_candidates: int = Field(default=0, ge=0)
    max_chars_per_page: int = Field(default=0, ge=0)
    max_tokens: int | None = Field(default=None, ge=1)


class LintRunResult(BaseModel):
    schema_version: Literal["lint_run.v1"] = "lint_run.v1"
    scope: MaintenanceScope
    mode: LintRunMode
    deterministic_lint: WikiLintResponse
    policy_decision: LintPolicyDecision
    semantic_candidates: dict[str, Any] | None = None
    maintenance_review: dict[str, Any] | None = None
    repair_plan: list[dict[str, Any]] = Field(default_factory=list)
    repair_results: list[dict[str, Any]] = Field(default_factory=list)
    post_repair_lint: WikiLintResponse | None = None
    report_path: str | None = None
    ledger_path: str | None = None
    warnings: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


class WikiScanRequest(BaseModel):
    vault_path: str = Field(..., min_length=1)
    max_chars_per_page: int = Field(default=0, ge=0)
    scope_pages: list[str] = Field(default_factory=list)
    include_related: bool = True


class WikiScanPage(BaseModel):
    path: str
    directory: str
    title: str
    role: str | None = None
    updated: str | None = None
    content_hash: str | None = None
    entities: list[str] = Field(default_factory=list)
    summary: str = ""
    headings: list[str] = Field(default_factory=list)
    outgoing_links: list[str] = Field(default_factory=list)
    content_preview: str = ""
    content_truncated: bool = False
    original_content_length: int = 0


class WikiScanResponse(BaseModel):
    pages: list[WikiScanPage]
    issues: list[WikiLintIssue]
    fixes: list[WikiLintFix] = Field(default_factory=list)
    stats: dict[str, Any]


class WikiLintCandidateSelectRequest(BaseModel):
    vault_path: str = Field(..., min_length=1)
    mode: Literal["semantic"] = "semantic"
    max_candidates: int = Field(default=0, ge=0)
    max_chars_per_page: int = Field(default=0, ge=0)
    scope_pages: list[str] = Field(default_factory=list)
    include_related: bool = True


class WikiLintCandidateReason(BaseModel):
    source: WikiLintCandidateSource
    issue_type: str
    severity: WikiLintCandidateSeverity
    message: str
    score: float
    evidence: dict[str, Any] = Field(default_factory=dict)


class WikiLintCandidatePage(BaseModel):
    path: str
    directory: str
    title: str
    role: str | None = None
    updated: str | None = None
    summary: str = ""
    entities: list[str] = Field(default_factory=list)
    headings: list[str] = Field(default_factory=list)
    outgoing_links: list[str] = Field(default_factory=list)
    content_preview: str = ""
    content_truncated: bool = False
    original_content_length: int = 0
    score: float
    reasons: list[WikiLintCandidateReason] = Field(default_factory=list)


class WikiLintCandidateSelectResponse(BaseModel):
    mode: str
    candidates: list[WikiLintCandidatePage]
    stats: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)
