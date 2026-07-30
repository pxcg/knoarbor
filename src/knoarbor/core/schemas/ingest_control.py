from __future__ import annotations

from pydantic import BaseModel, Field


class IngestControlResponse(BaseModel):
    paused: bool = False


class IngestQueueTask(BaseModel):
    task_id: str
    current_attempt_id: str | None = None
    queue_status: str
    attempt_ids: list[str] = Field(default_factory=list)
    error: str | None = None


class IngestQueueResponse(BaseModel):
    paused: bool = False
    tasks: list[IngestQueueTask] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)


class MaterializationRebuildRequest(BaseModel):
    pass


class MaterializationRebuildResponse(BaseModel):
    phase: str
    requested_epoch: int
    published_epoch: int
    fact_generation: str
    index_generation: str | None = None
    error: str | None = None
