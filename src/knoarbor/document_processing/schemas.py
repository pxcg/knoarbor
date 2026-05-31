from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DocumentProcessingItem(BaseModel):
    adapter: str
    input_path: str
    output_path: str | None = None
    status: Literal["processed", "skipped", "failed"]
    reason: str
    error_type: str | None = None
    error_message: str | None = None


class DocumentProcessingResult(BaseModel):
    items: list[DocumentProcessingItem] = Field(default_factory=list)
    stats: dict[str, int] = Field(default_factory=dict)
