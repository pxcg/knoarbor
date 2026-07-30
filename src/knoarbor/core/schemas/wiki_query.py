from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


WIKI_QUERY_SCHEMA_VERSION = "wiki_query.v4"

WIKI_QUERY_RESPONSE_FIELDS = (
    "schema_version",
    "query",
    "status",
    "retrieval_mode",
    "results",
    "evidence_handles",
    "raw_evidence",
    "context_pack",
    "gaps",
    "warnings",
    "channel_statuses",
    "stats",
    "trace",
    "exhausted",
    "continuation_cursor",
    "continuation_cursors",
    "query_fingerprint",
    "snapshot_generation",
)


class WikiSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vault_path: str | None = Field(default=None, min_length=1)
    vault_id: str | None = None
    vault_ids: list[str] = Field(default_factory=list)
    all_vaults: bool = False
    config_path: str | None = None
    query: str = Field(..., min_length=1)
    record_query: bool = True
    write_report: bool = False
    caller: str | None = None
    continuation_cursor: str | None = None
    continuation_cursors: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_vault_selector(self) -> "WikiSearchRequest":
        if not self.vault_path and not self.vault_id and not self.vault_ids and not self.all_vaults:
            raise ValueError("vault_path, vault_id, vault_ids, or all_vaults is required")
        return self

    @field_validator("query")
    @classmethod
    def strip_query(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("query cannot be empty")
        return text


class WikiAtomTrace(BaseModel):
    atom_id: str
    atom_type: Literal["claim", "relation", "entity", "evidence"]
    text: str
    source_record_id: str
    raw_record_id: str | None = None
    raw_revision_id: str | None = None
    source_unit_ids: list[str] = Field(default_factory=list)
    processing_record_id: str | None = None


class WikiRawEvidence(BaseModel):
    evidence_id: str
    vault_id: str
    raw_record_id: str
    raw_revision_id: str
    revision_id: str
    source_unit_id: str
    source_record_id: str
    processing_record_id: str = ""
    source_path: str = ""
    unit_index: int = 0
    unit_type: str = ""
    title: str = ""
    excerpt: str
    content: str = ""
    excerpt_hash: str = ""
    char_start: int | None = None
    char_end: int | None = None
    structural_path: list[str] = Field(default_factory=list)
    locator_atom_ids: list[str] = Field(default_factory=list)
    locator_page_paths: list[str] = Field(default_factory=list)
    relevance: Literal["high", "medium", "low"] = "medium"
    reason: str = ""


class WikiRecallSignal(BaseModel):
    channel: Literal["atom_claim", "raw_lexical"]
    channel_rank: int
    channel_score: float
    matched_terms: list[str] = Field(default_factory=list)
    claim_refs: list[str] = Field(default_factory=list)
    locator_atom_refs: list[str] = Field(default_factory=list)
    matched_spans: list[tuple[int, int]] = Field(default_factory=list)


class WikiEvidenceHandle(BaseModel):
    evidence_id: str
    vault_id: str
    raw_record_id: str
    raw_revision_id: str
    revision_id: str
    source_unit_id: str
    source_record_id: str
    processing_record_id: str
    source_path: str = ""
    title: str = ""
    retrieval_generation_id: str
    active_fact_generation: str
    fused_score: float
    fused_rank: int
    signals: list[WikiRecallSignal] = Field(default_factory=list)


class WikiChannelStatus(BaseModel):
    channel: Literal["atom_claim", "raw_lexical"]
    status: Literal["completed", "no_candidates", "unavailable", "error", "cancelled", "resource_exhausted"]
    match_count: int = 0
    exhausted: bool = False
    fts_hit_count: int = 0
    ineligible_hit_count: int = 0
    continuation_offset: int | None = None
    detail: str | None = None


class WikiQueryFeedbackRequest(BaseModel):
    vault_path: str | None = Field(default=None, min_length=1)
    vault_id: str | None = None
    config_path: str | None = None
    query: str = Field(..., min_length=1)
    useful: bool | None = None
    selected_paths: list[str] = Field(default_factory=list)
    rejected_paths: list[str] = Field(default_factory=list)
    comment: str = ""
    caller: str | None = None

    @model_validator(mode="after")
    def require_feedback_vault_selector(self) -> "WikiQueryFeedbackRequest":
        if not self.vault_path and not self.vault_id:
            raise ValueError("vault_path or vault_id is required")
        return self

    @field_validator("query")
    @classmethod
    def strip_feedback_query(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("query cannot be empty")
        return text


class WikiQueryFeedbackResponse(BaseModel):
    recorded: bool
    ledger_path: str


class WikiQueryTrendResponse(BaseModel):
    sample_size: int = 0
    no_result_count: int = 0
    low_confidence_count: int = 0
    repeated_gap_queries: list[dict[str, object]] = Field(default_factory=list)


class WikiSearchResult(BaseModel):
    path: str
    vault_id: str | None = None
    vault_name: str | None = None
    vault_path: str | None = None
    title: str
    score: float
    relevance: Literal["high", "medium", "low"]
    matched_fields: list[str] = Field(default_factory=list)
    matched_terms: dict[str, list[str]] = Field(default_factory=dict)
    reason: str = ""
    atom_traces: list[WikiAtomTrace] = Field(default_factory=list)


class WikiSearchResponse(BaseModel):
    schema_version: Literal["wiki_query.v4"] = WIKI_QUERY_SCHEMA_VERSION
    query: str
    status: Literal[
        "candidates",
        "no_match",
        "index_unavailable",
        "integrity_error",
        "invalid_query",
        "invalid_scope",
        "resource_exhausted",
        "cancelled",
    ]
    retrieval_mode: str
    results: list[WikiSearchResult]
    evidence_handles: list[WikiEvidenceHandle] = Field(default_factory=list)
    raw_evidence: list[WikiRawEvidence] = Field(default_factory=list)
    context_pack: str
    gaps: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    channel_statuses: list[WikiChannelStatus] = Field(default_factory=list)
    stats: dict[str, object] = Field(default_factory=dict)
    trace: dict[str, object] = Field(default_factory=dict)
    exhausted: bool = True
    continuation_cursor: str | None = None
    continuation_cursors: dict[str, str] = Field(default_factory=dict)
    query_fingerprint: str = ""
    snapshot_generation: str = ""
