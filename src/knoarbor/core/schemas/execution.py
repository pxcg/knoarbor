from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from knoarbor.core.schemas.run_monitor import RunRecord, RunStatus

WorkflowExecutionMode = Literal["queued", "direct"]
WorkflowFlow = Literal["ingest", "lint"]


class WorkflowResponse(BaseModel):
    """Stable response envelope for direct and queued workflow APIs."""

    schema_version: Literal["workflow_response.v1"] = "workflow_response.v1"
    flow: WorkflowFlow
    execution: WorkflowExecutionMode
    status: RunStatus
    run_id: str | None = None
    run: RunRecord | None = None
    result: dict[str, Any] | None = None
