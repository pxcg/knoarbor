from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


SourceType = Literal[
    "hermes_chat",
    "codex_chat",
    "openclaw_chat",
    "claude_code_chat",
    "knoarbor_chat",
    "generic_chat",
    "markdown",
    "document",
    "web",
    "text",
    "dataset",
]


class SourceRef(BaseModel):
    schema_version: Literal["source_ref.v1"] = "source_ref.v1"
    source_id: str = Field(..., min_length=1)
    connector: str = Field(..., min_length=1)
    source_type: SourceType
    uri: str = Field(..., min_length=1)
    display_name: str = Field(..., min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    discovered_at: str | None = None

    @field_validator("source_id", "connector", "uri", "display_name")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("source ref text fields cannot be empty")
        return text


class RawSource(BaseModel):
    schema_version: Literal["raw_source.v1"] = "raw_source.v1"
    source_id: str = Field(..., min_length=1)
    raw_path: str = Field(..., min_length=1)
    content_hash: str = Field(..., min_length=1)
    content_type: str = Field(..., min_length=1)
    bytes: int = Field(..., ge=0)
    created_at: str | None = None
    updated_at: str | None = None
    parser: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceOrigin(BaseModel):
    connector: str = Field(..., min_length=1)
    uri: str = Field(..., min_length=1)
    raw_path: str = Field(..., min_length=1)
    original_path: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class SourceContent(BaseModel):
    format: Literal["markdown", "text", "json", "html"]
    text: str = ""
    sections: list[dict[str, Any]] = Field(default_factory=list)
    attachments: list[dict[str, Any]] = Field(default_factory=list)


class SourceFingerprint(BaseModel):
    content_hash: str = Field(..., min_length=1)
    connector_version: str = Field(..., min_length=1)
    parser_version: str | None = None


class SourceCheckpointWindow(BaseModel):
    mode: Literal["full", "incremental"] = "full"
    from_index: int | None = Field(default=None, ge=0)
    to_index: int | None = Field(default=None, ge=0)


class SourceDocument(BaseModel):
    schema_version: Literal["source_document.v1"] = "source_document.v1"
    source_id: str = Field(..., min_length=1)
    source_type: SourceType
    origin: SourceOrigin
    content: SourceContent
    metadata: dict[str, Any] = Field(default_factory=dict)
    fingerprint: SourceFingerprint
    checkpoint: SourceCheckpointWindow = Field(default_factory=SourceCheckpointWindow)
