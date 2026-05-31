from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class MaintenanceScopeSource(BaseModel):
    kind: str = Field(..., min_length=1)
    run_id: str | None = None
    source_id: str | None = None


class MaintenanceScope(BaseModel):
    schema_version: Literal["maintenance_scope.v1"] = "maintenance_scope.v1"
    scope_id: str = Field(..., min_length=1)
    trigger: Literal["ingest", "manual", "query_gap", "scheduled"]
    source: MaintenanceScopeSource
    changed_pages: list[str] = Field(default_factory=list)
    neighbor_pages: list[str] = Field(default_factory=list)
    global_checks: list[str] = Field(default_factory=list)
    quality_candidates: list[dict[str, Any]] = Field(default_factory=list)
    recommended_lint_modes: list[str] = Field(default_factory=list)
    priority: Literal["low", "normal", "high"] = "normal"
    reason: str = ""
