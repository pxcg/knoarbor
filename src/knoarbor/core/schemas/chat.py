from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from knoarbor.core.schemas.memory import MemoryCandidate, MemoryRecord


ChatRole = Literal["user", "assistant", "tool"]
ChatAnswerMode = Literal[
    "knowledge_grounded",
    "knowledge_grounded_with_gap",
    "general_knowledge",
    "knowledge_gap",
    "clarification",
    "direct_capability",
]
ChatQueryOutcome = Literal[
    "candidates",
    "no_match",
    "index_unavailable",
    "integrity_error",
    "invalid_query",
    "invalid_scope",
    "resource_exhausted",
    "cancelled",
    "not_applicable",
]
ChatSemanticOutcome = Literal[
    "sufficient",
    "partial",
    "no_match",
    "needs_clarification",
    "planning_exhausted",
    "resource_exhausted",
    "tool_error",
    "integrity_error",
    "cancelled",
    "direct",
]
ChatToolStatus = Literal["ok", "error", "skipped"]
ChatToolName = Literal[
    "retrieve_knowledge_batch",
    "list_vaults",
    "generate_image",
]
ChatCitationKind = Literal["raw_evidence", "page", "report", "run"]
ChatSessionStatus = Literal["active", "closed"]
ChatEventType = Literal[
    "chat_started",
    "answer_source_selected",
    "model_call_started",
    "model_call_finished",
    "answer_delta",
    "tool_call_started",
    "tool_call_finished",
    "tool_call_failed",
    "final_answer_ready",
    "chat_stopped",
]
ChatStreamEventType = Literal["stage", "tool", "source", "answer_delta", "final", "error"]


class ChatMessageItem(BaseModel):
    message_id: str = Field(default_factory=lambda: _chat_id("msg"))
    role: ChatRole
    content: str = Field(..., min_length=1)
    tool_name: str | None = None

    @field_validator("content")
    @classmethod
    def strip_content(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("chat message content cannot be empty")
        return text


class ChatRequest(BaseModel):
    model_config = {"extra": "forbid"}

    schema_version: Literal["chat_request.v4"] = "chat_request.v4"
    request_id: str = Field(default_factory=lambda: _chat_id("req"))
    execution_id: str = Field(default_factory=lambda: _chat_id("exec"))
    session_id: str | None = Field(default=None, min_length=1)
    expected_session_revision: int | None = Field(default=None, ge=1)
    config_path: str | None = None
    vault_path: str | None = Field(default=None, min_length=1)
    vault_id: str | None = None
    vault_ids: list[str] = Field(default_factory=list)
    all_vaults: bool = False
    message: ChatMessageItem
    include_trace: bool = True
    append_ledger: bool = True
    provider: str | None = None
    max_tokens: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def require_user_message(self) -> "ChatRequest":
        if self.message.role != "user":
            raise ValueError("chat request message must have role=user")
        if self.session_id is not None and self.expected_session_revision is None:
            raise ValueError("continued chat requests require expected_session_revision")
        if self.session_id is None and self.expected_session_revision is not None:
            raise ValueError("expected_session_revision requires session_id")
        return self


class ChatAnswerProvenance(BaseModel):
    model_config = {"extra": "forbid"}

    mode: ChatAnswerMode
    query_outcome: ChatQueryOutcome
    chat_outcome: ChatSemanticOutcome


class ChatCitationSpan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_range(self) -> "ChatCitationSpan":
        if self.char_end <= self.char_start:
            raise ValueError("Citation span end must be greater than start.")
        return self


class ChatCitation(BaseModel):
    kind: ChatCitationKind
    role: Literal["primary", "supporting", "source", "further_reading"] | None = None
    path: str | None = None
    title: str | None = None
    vault_id: str | None = None
    vault_name: str | None = None
    vault_path: str | None = None
    run_id: str | None = None
    evidence_id: str | None = None
    raw_revision_id: str | None = None
    source_unit_id: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    spans: list[ChatCitationSpan] = Field(default_factory=list)
    reason: str = ""


class ChatCitationResolveRequest(BaseModel):
    """Resolve persisted citation locators without persisting Raw excerpts."""

    model_config = {"extra": "forbid"}

    schema_version: Literal["chat_citation_resolve_request.v1"] = "chat_citation_resolve_request.v1"
    config_path: str | None = None
    vault_path: str | None = Field(default=None, min_length=1)
    vault_id: str | None = None
    citations: list[ChatCitation] = Field(..., min_length=1, max_length=100)


class ChatCitationResolution(BaseModel):
    index: int = Field(..., ge=0)
    status: Literal["resolved", "unavailable"]
    text: str | None = None
    texts: list[str] = Field(default_factory=list)


class ChatCitationResolveResponse(BaseModel):
    schema_version: Literal["chat_citation_resolve_response.v1"] = "chat_citation_resolve_response.v1"
    resolutions: list[ChatCitationResolution] = Field(default_factory=list)


class ChatToolTraceItem(BaseModel):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    status: ChatToolStatus = "ok"
    summary: str = ""
    citations: list[ChatCitation] = Field(default_factory=list)
    result: dict[str, Any] = Field(default_factory=dict)


class ChatToolCall(BaseModel):
    name: ChatToolName
    arguments: dict[str, Any] = Field(default_factory=dict)


class ChatToolPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_calls: list[ChatToolCall] = Field(default_factory=list)
    reason: str = Field(default="", max_length=1000)
    confidence: float = Field(default=0.0, ge=0, le=1)


class ChatRegionSearch(BaseModel):
    """One model-authored search expression bound to a visible corpus region."""

    model_config = ConfigDict(extra="forbid")

    region_id: str = Field(min_length=1)
    search_query: str = Field(min_length=1, max_length=2000)

    @field_validator("region_id", "search_query")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class ChatRetrievalPlan(BaseModel):
    """Dialogue-aware region selection and region-targeted query expression."""

    model_config = ConfigDict(extra="forbid")

    searches: list[ChatRegionSearch] = Field(default_factory=list)

    @field_validator("searches")
    @classmethod
    def deduplicate_regions(
        cls,
        values: list[ChatRegionSearch],
    ) -> list[ChatRegionSearch]:
        output: list[ChatRegionSearch] = []
        seen: set[str] = set()
        for value in values:
            if value.region_id not in seen:
                seen.add(value.region_id)
                output.append(value)
        return output


class ChatRunLink(BaseModel):
    flow: Literal["ingest", "lint", "query"]
    run_id: str
    status: str
    vault_id: str | None = None
    vault_name: str | None = None
    vault_path: str | None = None


class ChatEvent(BaseModel):
    event_type: ChatEventType
    created_at: str
    message: str = ""
    tool: str | None = None
    turn: int | None = None
    status: ChatToolStatus | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    schema_version: Literal["chat_response.v4"] = "chat_response.v4"
    request_id: str
    execution_id: str
    session_id: str
    session_revision: int = Field(..., ge=1)
    turn_id: str
    answer: str
    answer_provenance: ChatAnswerProvenance
    citations: list[ChatCitation] = Field(default_factory=list)
    hidden_evidence_count: int = Field(default=0, ge=0)
    citation_warnings: list[str] = Field(default_factory=list)
    tool_trace: list[ChatToolTraceItem] = Field(default_factory=list)
    events: list[ChatEvent] = Field(default_factory=list)
    run_links: list[ChatRunLink] = Field(default_factory=list)
    memory_used: list[MemoryRecord] = Field(default_factory=list)
    memory_candidates: list[MemoryCandidate] = Field(default_factory=list)
    memory_writes: list[MemoryRecord] = Field(default_factory=list)
    stats: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class ChatStreamEvent(BaseModel):
    schema_version: Literal["chat_stream_event.v1"] = "chat_stream_event.v1"
    event: ChatStreamEventType
    message: str = ""
    stage: str | None = None
    tool: str | None = None
    status: str | None = None
    response: ChatResponse | None = None
    error: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)


class ChatTurnRecord(BaseModel):
    index: int = Field(..., ge=0)
    turn_id: str
    request_id: str
    execution_id: str
    created_at: str
    user_message: ChatMessageItem
    assistant_message: ChatMessageItem
    answer_provenance: ChatAnswerProvenance
    citations: list[ChatCitation] = Field(default_factory=list)
    hidden_evidence_count: int = Field(default=0, ge=0)
    citation_warnings: list[str] = Field(default_factory=list)
    tool_trace: list[ChatToolTraceItem] = Field(default_factory=list)
    events: list[ChatEvent] = Field(default_factory=list)
    run_links: list[ChatRunLink] = Field(default_factory=list)
    memory_used: list[MemoryRecord] = Field(default_factory=list)
    memory_candidates: list[MemoryCandidate] = Field(default_factory=list)
    memory_writes: list[MemoryRecord] = Field(default_factory=list)
    stats: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class ChatSessionSummary(BaseModel):
    session_id: str
    session_revision: int = Field(..., ge=1)
    title: str
    created_at: str
    updated_at: str
    vault_id: str | None = None
    vault_name: str | None = None
    vault_path: str | None = None
    message_count: int = 0
    last_message: str = ""
    last_ingest_run_id: str | None = None
    last_ingested_at: str | None = None
    ingest_candidate: "ChatIngestCandidate | None" = None


class ChatIngestCandidate(BaseModel):
    should_ingest: bool
    reason: str
    user_turns: int = 0
    assistant_turns: int = 0
    citation_count: int = 0
    signal_count: int = 0
    signals: list[str] = Field(default_factory=list)


class ChatSessionRecord(BaseModel):
    schema_version: Literal["chat_session.v4"] = "chat_session.v4"
    session_id: str
    session_revision: int = Field(..., ge=1)
    title: str
    created_at: str
    updated_at: str
    vault_id: str | None = None
    vault_name: str | None = None
    vault_path: str | None = None
    status: ChatSessionStatus = "active"
    closed_at: str | None = None
    last_ingest_run_id: str | None = None
    last_ingested_at: str | None = None
    ingest_candidate: ChatIngestCandidate | None = None
    messages: list[ChatMessageItem] = Field(default_factory=list)
    turns: list[ChatTurnRecord] = Field(default_factory=list)
    citations: list[ChatCitation] = Field(default_factory=list)
    tool_trace: list[ChatToolTraceItem] = Field(default_factory=list)
    events: list[ChatEvent] = Field(default_factory=list)
    run_links: list[ChatRunLink] = Field(default_factory=list)
    memory_used: list[MemoryRecord] = Field(default_factory=list)
    memory_candidates: list[MemoryCandidate] = Field(default_factory=list)
    memory_writes: list[MemoryRecord] = Field(default_factory=list)
    stats: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    def summary(self) -> ChatSessionSummary:
        last_message = self.messages[-1].content if self.messages else ""
        return ChatSessionSummary(
            session_id=self.session_id,
            session_revision=self.session_revision,
            title=self.title,
            created_at=self.created_at,
            updated_at=self.updated_at,
            vault_id=self.vault_id,
            vault_name=self.vault_name,
            vault_path=self.vault_path,
            message_count=len(self.messages),
            last_message=last_message[:240],
            last_ingest_run_id=self.last_ingest_run_id,
            last_ingested_at=self.last_ingested_at,
            ingest_candidate=self.ingest_candidate,
        )


class ChatSessionListResponse(BaseModel):
    sessions: list[ChatSessionSummary] = Field(default_factory=list)
    total_count: int = Field(default=0, ge=0)
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=50, ge=1)
    has_more: bool = False


class ChatSessionDeleteResponse(BaseModel):
    deleted: bool
    session_id: str


class ChatSessionMutationRequest(BaseModel):
    config_path: str | None = None
    vault_path: str | None = Field(default=None, min_length=1)
    vault_id: str | None = None
    expected_session_revision: int = Field(..., ge=1)


class ChatSessionUpdateRequest(ChatSessionMutationRequest):
    title: str = Field(..., min_length=1, max_length=160)

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("chat session title cannot be empty")
        return text


class ChatSessionIngestRequest(ChatSessionMutationRequest):
    target_vault_path: str | None = None
    target_vault_id: str | None = None
    source_title: str | None = Field(default=None, max_length=160)
    provider: str | None = None
    max_tokens: int | None = Field(default=None, ge=1)
    write: bool = True
    write_report: bool = True
    append_ledger: bool = True
    auto_scoped_lint: bool | None = None
    scoped_lint_include_related: bool | None = None
    turn_ids: list[str] | None = Field(
        default=None, description="Selected stable turn identities to ingest. When null, all turns are ingested."
    )

    @field_validator("source_title", "target_vault_path", "target_vault_id")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None


class ChatSessionRetryRequest(BaseModel):
    model_config = {"extra": "forbid"}

    schema_version: Literal["chat_session_retry_request.v4"] = "chat_session_retry_request.v4"
    request_id: str = Field(default_factory=lambda: _chat_id("req"))
    execution_id: str = Field(default_factory=lambda: _chat_id("exec"))
    target_turn_id: str = Field(..., min_length=1)
    expected_session_revision: int = Field(..., ge=1)
    config_path: str | None = None
    vault_path: str | None = Field(default=None, min_length=1)
    vault_id: str | None = None
    vault_ids: list[str] = Field(default_factory=list)
    all_vaults: bool = False
    include_trace: bool = True
    append_ledger: bool = True
    provider: str | None = None
    max_tokens: int | None = Field(default=None, ge=1)


class ChatSessionCloseRequest(ChatSessionIngestRequest):
    auto_ingest: bool | None = None


class ChatSessionWorkflowResponse(BaseModel):
    session: ChatSessionRecord
    ingest_started: bool = False
    run_id: str | None = None
    status: str | None = None
    reason: str = ""


class ChatAnswerDraft(BaseModel):
    answer: str = Field(..., min_length=1)
    citations: list[ChatCitation] = Field(default_factory=list)


class ChatAnswerDecision(BaseModel):
    """Minimal semantic handoff from evidence judgment to composition."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["raw", "general", "gap"]
    spans: list[str] = Field(default_factory=list)
    visuals: list[str] = Field(default_factory=list)
    gap: str | None = Field(default=None, min_length=1)
    generated_image_prompt: str | None = Field(default=None, max_length=4000)

    @field_validator("spans", "visuals")
    @classmethod
    def require_unique_references(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("decision references cannot be empty")
        if len(normalized) != len(set(normalized)):
            raise ValueError("decision references must be unique")
        return normalized

    @field_validator("gap", "generated_image_prompt", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value

    @model_validator(mode="after")
    def validate_mode(self) -> "ChatAnswerDecision":
        if self.mode == "raw":
            if not self.spans:
                raise ValueError("raw mode requires selected support spans")
        elif self.spans or self.visuals:
            raise ValueError(f"{self.mode} mode cannot select Raw references")
        if self.mode == "gap":
            if self.gap is None:
                raise ValueError("gap mode requires a gap")
        return self


class ChatComposerTextItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["text"]
    markdown: str = Field(..., min_length=1)
    materials: list[str] = Field(default_factory=list)

    @field_validator("markdown")
    @classmethod
    def strip_markdown(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("composer Markdown cannot be empty")
        return normalized

    @field_validator("materials")
    @classmethod
    def require_unique_materials(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("composer material references cannot be empty")
        if len(normalized) != len(set(normalized)):
            raise ValueError("composer material references must be unique")
        return normalized


class ChatComposerSourceVisualItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["source_visual"]
    visual: str = Field(..., min_length=1)

    @field_validator("visual")
    @classmethod
    def strip_visual(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("composer visual reference cannot be empty")
        return normalized


class ChatComposerGeneratedVisualItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["generated_visual"]
    visual: str = Field(..., min_length=1)

    @field_validator("visual")
    @classmethod
    def strip_visual(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("composer visual reference cannot be empty")
        return normalized


ChatResponseComposerItem = Annotated[
    ChatComposerTextItem | ChatComposerSourceVisualItem | ChatComposerGeneratedVisualItem,
    Field(discriminator="type"),
]


class ChatResponseComposerDraft(BaseModel):
    """Ordered reader-facing composition over validated selected materials."""

    model_config = ConfigDict(extra="forbid")

    items: list[ChatResponseComposerItem] = Field(default_factory=list)
    gap_markdown: str | None = Field(default=None, min_length=1)

    @field_validator("gap_markdown", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value


def _chat_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"
