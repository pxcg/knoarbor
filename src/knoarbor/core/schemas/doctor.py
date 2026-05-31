from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


DoctorStatus = Literal["ok", "warning", "error"]


class DoctorCheck(BaseModel):
    name: str
    status: DoctorStatus
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class DoctorReport(BaseModel):
    schema_version: Literal["doctor_report.v1"] = "doctor_report.v1"
    status: DoctorStatus
    config_path: str | None = None
    checks: list[DoctorCheck] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)
