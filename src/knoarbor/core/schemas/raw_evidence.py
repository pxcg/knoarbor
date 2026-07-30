from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from knoarbor.core.schemas.source_record import SourceRecordAttachment


class OriginalSourceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["original_source_record.v1"] = "original_source_record.v1"
    raw_record_id: str = Field(..., min_length=1)
    raw_revision_id: str = Field(..., min_length=1)
    source_id: str = Field(..., min_length=1)
    source_type: str = ""
    connector: str = ""
    raw_path: str = ""
    title: str = ""
    content_hash: str = ""
    normalized_content_hash: str = ""
    parser_version: str = "source_document.v1"
    privacy: dict[str, object] = Field(default_factory=dict)
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("raw_record_id", "raw_revision_id", "source_id")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("source record identity fields cannot be empty")
        return text


class SourceUnitRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["source_unit_record.v1"] = "source_unit_record.v1"
    source_unit_id: str = Field(..., min_length=1)
    raw_record_id: str = Field(..., min_length=1)
    raw_revision_id: str = Field(..., min_length=1)
    revision_id: str | None = None
    window_id: str | None = None
    unit_index: int = Field(..., ge=0)
    unit_type: str = ""
    role: str = ""
    title: str = ""
    content: str = Field(..., min_length=1)
    excerpt: str = ""
    excerpt_hash: str = ""
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    structural_path: list[str] = Field(default_factory=list)
    raw_indexes: list[int] = Field(default_factory=list)
    source_range: dict[str, object] = Field(default_factory=dict)
    unitization_rule: str = ""
    source_path: str = ""
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("source_unit_id", "raw_record_id", "raw_revision_id", "content")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("source unit record fields cannot be empty")
        return text

    @model_validator(mode="after")
    def validate_char_range(self) -> "SourceUnitRecord":
        if self.char_start is not None and self.char_end is not None and self.char_end < self.char_start:
            raise ValueError("char_end must be greater than or equal to char_start")
        return self


class SourceProcessingRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["source_processing_record.v2"] = "source_processing_record.v2"
    processing_record_id: str = Field(..., min_length=1)
    raw_record_id: str = Field(..., min_length=1)
    raw_revision_id: str = Field(..., min_length=1)
    revision_id: str | None = None
    window_id: str | None = None
    source_record_id: str = Field(..., min_length=1)
    run_id: str = ""
    ingest_profile: str = ""
    scope_type: Literal["full_source", "segment", "excerpt"] = "full_source"
    source: OriginalSourceRecord
    source_units: list[SourceUnitRecord] = Field(default_factory=list)
    attachments: list[SourceRecordAttachment] = Field(default_factory=list)
    atom_ids: list[str] = Field(default_factory=list)
    page_paths: list[str] = Field(default_factory=list)
    decisions: dict[str, object] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("processing_record_id", "raw_record_id", "raw_revision_id", "source_record_id")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("source processing identity fields cannot be empty")
        return text


class RawEvidenceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["raw_evidence_record.v1"] = "raw_evidence_record.v1"
    evidence_id: str = Field(..., min_length=1)
    raw_record_id: str = Field(..., min_length=1)
    raw_revision_id: str = Field(..., min_length=1)
    revision_id: str | None = None
    window_id: str | None = None
    source_unit_id: str = Field(..., min_length=1)
    source_record_id: str = Field(..., min_length=1)
    processing_record_id: str = ""
    source_path: str = ""
    unit_index: int = Field(..., ge=0)
    unit_type: str = ""
    title: str = ""
    excerpt: str = Field(..., min_length=1)
    content: str = ""
    excerpt_hash: str = ""
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    structural_path: list[str] = Field(default_factory=list)
    raw_indexes: list[int] = Field(default_factory=list)
    locator_atom_ids: list[str] = Field(default_factory=list)
    locator_page_paths: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("evidence_id", "raw_record_id", "raw_revision_id", "source_unit_id", "source_record_id", "excerpt")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("raw evidence record fields cannot be empty")
        return text
