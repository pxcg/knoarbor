from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


KnowledgeEventType = Literal[
    "source.discovered",
    "source.synced",
    "source.normalized",
    "source.deleted",
    "ingest.extracted",
    "ingest.planned",
    "ingest.compiled",
    "ingest.reviewed",
    "wiki.written",
    "maintenance.scope_created",
    "lint.scanned",
    "lint.diagnosed",
    "lint.reviewed",
    "operation.applied",
    "query.retrieved",
]


class KnowledgeEvent(BaseModel):
    schema_version: Literal["knowledge_event.v1"] = "knowledge_event.v1"
    event_id: str = Field(..., min_length=1)
    run_id: str = Field(..., min_length=1)
    event_type: KnowledgeEventType
    created_at: str = Field(..., min_length=1)
    source_id: str | None = None
    page_path: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
