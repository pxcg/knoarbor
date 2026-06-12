from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


MemoryScope = Literal["global", "vault"]
MemoryCategory = Literal["preference", "constraint", "workflow", "decision", "fact", "style", "other"]
MemoryRisk = Literal["low", "medium", "high"]
MemoryCandidateStatus = Literal["pending", "written", "rejected", "discarded"]
MemoryCandidateDecision = Literal["auto_write", "candidate_review", "discard"]
MemoryEventType = Literal["recalled", "candidate_created", "written", "rejected", "discarded"]


class MemoryRecord(BaseModel):
    schema_version: Literal["memory_record.v1"] = "memory_record.v1"
    id: str
    scope: MemoryScope = "vault"
    vault_id: str | None = None
    category: MemoryCategory = "preference"
    content: str = Field(..., min_length=1)
    evidence: str = ""
    confidence: float = Field(default=0.8, ge=0, le=1)
    risk: MemoryRisk = "low"
    source_session: str | None = None
    source_chat_id: str | None = None
    created_at: str
    updated_at: str
    last_used_at: str | None = None
    use_count: int = Field(default=0, ge=0)


class MemoryCandidate(BaseModel):
    schema_version: Literal["memory_candidate.v1"] = "memory_candidate.v1"
    id: str
    status: MemoryCandidateStatus = "pending"
    decision: MemoryCandidateDecision = "candidate_review"
    record: MemoryRecord
    reason: str = ""
    created_at: str
    resolved_at: str | None = None


class MemoryEvent(BaseModel):
    schema_version: Literal["memory_event.v1"] = "memory_event.v1"
    event_type: MemoryEventType
    memory_id: str | None = None
    candidate_id: str | None = None
    chat_id: str | None = None
    vault_id: str | None = None
    created_at: str
    message: str = ""


class MemoryRecallResult(BaseModel):
    schema_version: Literal["memory_recall.v1"] = "memory_recall.v1"
    records: list[MemoryRecord] = Field(default_factory=list)
    context_block: str = ""
    warnings: list[str] = Field(default_factory=list)

