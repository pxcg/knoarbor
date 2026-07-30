from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RawRevisionEditorState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["raw_revision_editor.v1"] = "raw_revision_editor.v1"
    base_revision_id: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    source_unit_count: int = Field(..., ge=0)
    evidence_span_count: int = Field(..., ge=0)


class RawRevisionEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["raw_revision_edit.v1"] = "raw_revision_edit.v1"
    base_revision_id: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)

    @field_validator("base_revision_id")
    @classmethod
    def strip_revision_id(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("raw revision edit fields cannot be empty")
        return text

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        content = value.replace("\r\n", "\n").replace("\r", "\n")
        if not content.strip():
            raise ValueError("raw revision content cannot be empty")
        return content
