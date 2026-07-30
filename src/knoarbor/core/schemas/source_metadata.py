from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


KnowledgeSourceType = Literal["chat", "markdown", "html", "text_note", "document", "web", "manual"]


class KnowledgeSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: KnowledgeSourceType
    source_app: str = Field(..., min_length=1)
    source_id: str | None = None
    source_path: str | None = None
    title: str = Field(..., min_length=1)
    created_at: str | None = None
    updated_at: str | None = None

    @field_validator("source_app", "title")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("knowledge source text fields cannot be empty")
        return text
