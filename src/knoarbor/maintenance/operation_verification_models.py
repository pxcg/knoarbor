from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

VerificationStatus = Literal["verified", "failed", "skipped"]


class LintPostFixVerification(BaseModel):
    """Result of verifying one reviewed lint maintenance effect."""

    action: str
    status: VerificationStatus
    target_page: str | None = None
    operation_id: str | None = None
    reason: str
    evidence: dict[str, Any] = Field(default_factory=dict)

