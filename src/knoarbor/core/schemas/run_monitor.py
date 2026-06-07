from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


RunFlow = Literal["ingest", "lint", "query"]
RunStatus = Literal[
    "created",
    "queued",
    "running",
    "waiting_external_service",
    "waiting_model",
    "writing",
    "linting",
    "completed",
    "failed",
    "cancelling",
    "cancelled",
    "partially_failed",
]

ACTIVE_RUN_STATUSES: set[str] = {
    "created",
    "queued",
    "running",
    "waiting_external_service",
    "waiting_model",
    "writing",
    "linting",
    "cancelling",
}

TERMINAL_RUN_STATUSES: set[str] = {"completed", "failed", "cancelled", "partially_failed"}


class RunProgress(BaseModel):
    total: int | None = None
    completed: int = 0
    current: str | None = None


class RunRecord(BaseModel):
    schema_version: Literal["run_record.v1"] = "run_record.v1"
    run_id: str
    vault_id: str | None = None
    vault_name: str | None = None
    vault_path: str | None = None
    flow: RunFlow
    status: RunStatus
    stage: str = "queued"
    current_item: str | None = None
    message: str = ""
    started_at: str
    updated_at: str
    last_heartbeat_at: str
    finished_at: str | None = None
    elapsed_seconds: float = 0.0
    progress: RunProgress = Field(default_factory=RunProgress)
    metrics: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    result_summary: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    error_info: dict[str, Any] = Field(default_factory=dict)
    cancel_requested: bool = False


class RunEvent(BaseModel):
    schema_version: Literal["run_event.v1"] = "run_event.v1"
    run_id: str
    sequence: int
    created_at: str
    event_type: str
    status: RunStatus
    stage: str
    message: str = ""
    current_item: str | None = None
    progress: RunProgress = Field(default_factory=RunProgress)
    metrics: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)


class RunStartResponse(BaseModel):
    run_id: str
    status: RunStatus
    run: RunRecord


class RunListResponse(BaseModel):
    runs: list[RunRecord]


class RunEventsResponse(BaseModel):
    events: list[RunEvent]
