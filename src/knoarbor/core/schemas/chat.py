from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from knoarbor.core.schemas.memory import MemoryCandidate, MemoryRecord


ChatRole = Literal["user", "assistant", "tool"]
ChatRetrievalMode = Literal["quick", "balanced", "deep"]
ChatToolStatus = Literal["ok", "error", "skipped"]
ChatCitationKind = Literal["page", "report", "run", "source"]
ChatEventType = Literal[
    "chat_started",
    "model_call_started",
    "model_call_finished",
    "tool_call_started",
    "tool_call_finished",
    "tool_call_failed",
    "final_answer_ready",
    "chat_stopped",
]


class ChatMessageItem(BaseModel):
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
    schema_version: Literal["chat_request.v1"] = "chat_request.v1"
    session_id: str | None = Field(default=None, min_length=1)
    config_path: str | None = None
    vault_path: str | None = Field(default=None, min_length=1)
    vault_id: str | None = None
    vault_ids: list[str] = Field(default_factory=list)
    all_vaults: bool = False
    messages: list[ChatMessageItem] = Field(..., min_length=1)
    mode: ChatRetrievalMode = "balanced"
    max_turns: int = Field(default=6, ge=1, le=12)
    include_trace: bool = True
    append_ledger: bool = True
    provider: str | None = None
    max_tokens: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def require_user_message(self) -> "ChatRequest":
        if not any(message.role == "user" for message in self.messages):
            raise ValueError("chat request must include at least one user message")
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
    reason: str = ""


class ChatToolTraceItem(BaseModel):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    status: ChatToolStatus = "ok"
    summary: str = ""
    citations: list[ChatCitation] = Field(default_factory=list)
    result: dict[str, Any] = Field(default_factory=dict)


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
    schema_version: Literal["chat_response.v1"] = "chat_response.v1"
    session_id: str | None = None
    answer: str
    messages: list[ChatMessageItem] = Field(default_factory=list)
    citations: list[ChatCitation] = Field(default_factory=list)
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
    title: str
    created_at: str
    updated_at: str
    vault_id: str | None = None
    vault_name: str | None = None
    vault_path: str | None = None
    message_count: int = 0
    last_message: str = ""


class ChatSessionRecord(BaseModel):
    schema_version: Literal["chat_session.v1"] = "chat_session.v1"
    session_id: str
    title: str
    created_at: str
    updated_at: str
    vault_id: str | None = None
    vault_name: str | None = None
    vault_path: str | None = None
    messages: list[ChatMessageItem] = Field(default_factory=list)
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
            title=self.title,
            created_at=self.created_at,
            updated_at=self.updated_at,
            vault_id=self.vault_id,
            vault_name=self.vault_name,
            vault_path=self.vault_path,
            message_count=len(self.messages),
            last_message=last_message[:240],
        )


class ChatSessionListResponse(BaseModel):
    sessions: list[ChatSessionSummary] = Field(default_factory=list)


class ChatSessionDeleteResponse(BaseModel):
    deleted: bool
    session_id: str


class ChatAgentDecision(BaseModel):
    type: Literal["tool_call", "final"]
    tool: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    answer: str | None = None
    citations: list[ChatCitation] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_decision(self) -> "ChatAgentDecision":
        if self.type == "tool_call" and not self.tool:
            raise ValueError("tool_call decision requires tool")
        if self.type == "final" and not (self.answer or "").strip():
            raise ValueError("final decision requires answer")
        return self
