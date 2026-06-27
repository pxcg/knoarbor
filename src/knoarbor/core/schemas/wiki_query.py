from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


WIKI_QUERY_SCHEMA_VERSION = "wiki_query.v1"

WIKI_QUERY_RESPONSE_FIELDS = (
    "query",
    "retrieval_mode",
    "results",
    "primary_pages",
    "supporting_pages",
    "source_pages",
    "answer_scope",
    "answer_set",
    "evidence_coverage",
    "context_pack",
)

WIKI_ANSWER_PAGE_ROLES = ("primary", "supporting", "source")


class WikiPageReadRequest(BaseModel):
    vault_path: str = Field(..., min_length=1)
    page_paths: list[str] = Field(default_factory=list)
    max_pages: int = Field(default=5, ge=0, le=20)
    max_chars_per_page: int = Field(default=6000, ge=500, le=50000)


class WikiPageReadItem(BaseModel):
    path: str
    exists: bool
    content: str = ""
    truncated: bool = False
    original_content_length: int = 0
    error: str | None = None


class WikiPageReadResponse(BaseModel):
    pages: list[WikiPageReadItem]


class WikiSearchRequest(BaseModel):
    vault_path: str | None = Field(default=None, min_length=1)
    vault_id: str | None = None
    vault_ids: list[str] = Field(default_factory=list)
    all_vaults: bool = False
    config_path: str | None = None
    query: str = Field(..., min_length=1)
    mode: Literal["quick", "balanced", "deep"] = "balanced"
    page_dirs: list[str] = Field(default_factory=list)
    page_roles: list[str] = Field(default_factory=list)
    max_results: int = Field(default=6, ge=1, le=20)
    max_pages_to_read: int = Field(default=10, ge=1, le=30)
    max_excerpts_per_page: int = Field(default=3, ge=0, le=8)
    max_chars_per_excerpt: int = Field(default=800, ge=120, le=3000)
    max_context_chars: int = Field(default=8000, ge=1000, le=30000)
    include_related: bool = True
    record_query: bool = True
    write_report: bool = False
    caller: str | None = None

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


class WikiSearchExcerpt(BaseModel):
    path: str
    page_title: str
    heading: str
    section: str
    content: str
    score: float


class WikiAtomTrace(BaseModel):
    atom_id: str
    atom_type: Literal["claim", "relation", "entity", "evidence"]
    text: str
    source_digest_id: str


class WikiQueryGapSuggestion(BaseModel):
    kind: Literal["no_result", "low_confidence"]
    query: str
    reason: str
    recommended_action: Literal["ingest_more_sources", "review_query_terms", "ask_followup"]


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
    canonical_path: str | None = None
    vault_id: str | None = None
    vault_name: str | None = None
    vault_path: str | None = None
    title: str
    page_role: str | None = None
    score: float
    relevance: Literal["high", "medium", "low"]
    match_kind: Literal["direct", "related"]
    role: Literal["primary", "supporting", "source"] = "supporting"
    matched_fields: list[str] = Field(default_factory=list)
    matched_terms: dict[str, list[str]] = Field(default_factory=dict)
    reason: str = ""
    summary: str = ""
    claims: list[str] = Field(default_factory=list)
    excerpts: list[WikiSearchExcerpt] = Field(default_factory=list)
    content: str | None = None
    source: str | None = None
    entities: list[str] = Field(default_factory=list)
    outbound_links: list[str] = Field(default_factory=list)
    content_truncated: bool = False
    atom_traces: list[WikiAtomTrace] = Field(default_factory=list)


class WikiAnswerScope(BaseModel):
    kind: Literal["narrow", "broad", "exploratory"] = "narrow"
    vault_ids: list[str] = Field(default_factory=list)
    initial_page_dirs: list[str] = Field(default_factory=list)
    expanded_page_dirs: list[str] = Field(default_factory=list)
    include_related: bool = True
    reason: str = ""


class WikiRejectedCandidate(BaseModel):
    path: str
    title: str = ""
    reason: str
    score: float | None = None
    role_hint: Literal["primary", "supporting", "source", "further_reading"] | None = None


class WikiAnswerSet(BaseModel):
    kind: Literal["single_page", "multi_page"] = "single_page"
    primary_paths: list[str] = Field(default_factory=list)
    supporting_paths: list[str] = Field(default_factory=list)
    source_paths: list[str] = Field(default_factory=list)
    further_reading_paths: list[str] = Field(default_factory=list)
    rejected_candidates: list[WikiRejectedCandidate] = Field(default_factory=list)
    reason: str = ""
    stop_reason: str = ""


class WikiEvidenceCoverage(BaseModel):
    status: Literal["strong", "adequate", "weak"] = "weak"
    primary_count: int = 0
    supporting_count: int = 0
    source_count: int = 0
    gap_count: int = 0
    covered_terms: list[str] = Field(default_factory=list)
    covered_dimensions: list[str] = Field(default_factory=list)
    missing_dimensions: list[str] = Field(default_factory=list)


class WikiSearchResponse(BaseModel):
    schema_version: Literal["wiki_query.v1"] = WIKI_QUERY_SCHEMA_VERSION
    query: str
    retrieval_mode: str
    results: list[WikiSearchResult]
    primary_pages: list[WikiSearchResult] = Field(default_factory=list)
    supporting_pages: list[WikiSearchResult] = Field(default_factory=list)
    source_pages: list[WikiSearchResult] = Field(default_factory=list)
    answer_scope: WikiAnswerScope = Field(default_factory=WikiAnswerScope)
    answer_set: WikiAnswerSet = Field(default_factory=WikiAnswerSet)
    evidence_coverage: WikiEvidenceCoverage = Field(default_factory=WikiEvidenceCoverage)
    rejected_candidates: list[WikiRejectedCandidate] = Field(default_factory=list)
    context_pack: str
    response_guidance: list[str] = Field(default_factory=list)
    gap_suggestions: list[WikiQueryGapSuggestion] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    stats: dict[str, object] = Field(default_factory=dict)
    trace: dict[str, object] = Field(default_factory=dict)


class WikiContextRequest(BaseModel):
    vault_path: str = Field(..., min_length=1)
    query: str = Field(..., min_length=1)
    purpose: Literal["ingest_relation", "lint_quality", "lint_freshness", "query", "manual"] = "manual"
    page_dirs: list[str] = Field(default_factory=list)
    page_roles: list[str] = Field(default_factory=list)
    limit: int = Field(default=8, ge=1, le=30)
    include_content: bool = False
    max_chars_per_page: int = Field(default=2500, ge=500, le=12000)
    include_related: bool = True

    @field_validator("query")
    @classmethod
    def strip_context_query(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("query cannot be empty")
        return text


class WikiContextMatch(BaseModel):
    path: str
    canonical_path: str | None = None
    title: str
    page_dir: str
    page_role: str | None = None
    summary: str = ""
    entities: list[str] = Field(default_factory=list)
    claims: list[str] = Field(default_factory=list)
    outbound_links: list[str] = Field(default_factory=list)
    score: float
    relevance: Literal["high", "medium", "low"]
    matched_fields: list[str] = Field(default_factory=list)
    reason: str = ""
    content: str | None = None
    content_truncated: bool = False


class WikiContextResponse(BaseModel):
    query: str
    purpose: str
    matches: list[WikiContextMatch]
    context_pack: str
    warnings: list[str] = Field(default_factory=list)
    stats: dict[str, object] = Field(default_factory=dict)
