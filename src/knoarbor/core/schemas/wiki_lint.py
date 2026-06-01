from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from knoarbor.core.schemas.execution import WorkflowExecutionMode
from knoarbor.core.schemas.maintenance import MaintenanceScope


WikiLintCandidateSource = Literal["structural", "provenance", "quality", "freshness", "graph"]
WikiLintCandidateSeverity = Literal["high", "medium", "low"]
LintRunMode = Literal[
    "deterministic",
    "structural",
    "quality",
    "full",
    "semantic_structural",
    "semantic_quality",
    "semantic_full",
]
LintRunProfile = Literal["standard", "deep"]


class WikiLintRequest(BaseModel):
    obsidian_vault_path: str = Field(..., min_length=1)
    write_report: bool = True
    report_path: str | None = None
    apply_safe_fixes: bool = False
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
    model_config = ConfigDict(populate_by_name=True)

    execution: WorkflowExecutionMode = "queued"
    obsidian_vault_path: str = Field(..., alias="vault_path", min_length=1)
    config_path: str | None = None
    provider: str | None = None
    scope: MaintenanceScope
    mode: LintRunMode = "deterministic"
    profile: LintRunProfile = "standard"
    apply_safe_fixes: bool = True
    include_related: bool = True
    write_report: bool = True
    report_path: str | None = None
    append_ledger: bool = True
    ledger_path: str = "maintenance/lint_run_ledger.jsonl"
    max_candidates: int = Field(default=8, ge=1, le=30)
    max_chars_per_page: int = Field(default=2500, ge=0, le=30000)
    max_tokens: int | None = Field(default=None, ge=1)
    auto_apply_reviewed_changes: bool = False


class LintRunResult(BaseModel):
    schema_version: Literal["lint_run.v1"] = "lint_run.v1"
    scope: MaintenanceScope
    mode: LintRunMode
    profile: LintRunProfile = "standard"
    deterministic_lint: WikiLintResponse
    policy_decision: LintPolicyDecision
    semantic_candidates: dict[str, Any] | None = None
    maintenance_review: dict[str, Any] | None = None
    draft_batch: dict[str, Any] | None = None
    queued_actions: list[dict[str, Any]] = Field(default_factory=list)
    written_pages: list[str] = Field(default_factory=list)
    written_page_details: list[dict[str, Any]] = Field(default_factory=list)
    applied_operations: list[dict[str, Any]] = Field(default_factory=list)
    verifications: list[dict[str, Any]] = Field(default_factory=list)
    rescan: WikiLintResponse | None = None
    report_path: str | None = None
    ledger_path: str | None = None
    warnings: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


class WikiScanRequest(BaseModel):
    obsidian_vault_path: str = Field(..., min_length=1)
    max_chars_per_page: int = Field(default=2500, ge=0, le=30000)
    scope_pages: list[str] = Field(default_factory=list)
    include_related: bool = True


class WikiScanPage(BaseModel):
    path: str
    directory: str
    title: str
    page_type: str | None = None
    status: str | None = None
    updated: str | None = None
    source: str | None = None
    content_hash: str | None = None
    tags: list[str] = Field(default_factory=list)
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
    obsidian_vault_path: str = Field(..., min_length=1)
    mode: Literal["quality", "freshness", "full"] = "quality"
    max_candidates: int = Field(default=8, ge=1, le=30)
    max_chars_per_page: int = Field(default=3000, ge=500, le=30000)


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
    page_type: str | None = None
    updated: str | None = None
    source: str | None = None
    summary: str = ""
    tags: list[str] = Field(default_factory=list)
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
