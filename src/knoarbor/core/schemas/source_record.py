from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from knoarbor.core.schemas.knowledge_atoms import KnowledgeEvidenceSpan
from knoarbor.core.schemas.source_metadata import KnowledgeSource


SourceRecordUnitType = Literal["conversation_turn", "note", "section", "excerpt", "evidence"]


class SourceRecordUnit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int = Field(..., ge=0)
    unit_type: SourceRecordUnitType
    title: str | None = None
    summary: str = ""
    evidence: KnowledgeEvidenceSpan
    metadata: dict[str, object] = Field(default_factory=dict)


class SourceRecordContribution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str = Field(..., min_length=1)
    contribution: str = Field(..., min_length=1)
    evidence_unit_ids: list[str] = Field(default_factory=list)
    target_page: str | None = None
    status: Literal["pending", "accepted", "rejected", "unresolved"] = "pending"

    @field_validator("item_id", "contribution")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("source record contribution fields cannot be empty")
        return text


class SourceRecordUnresolvedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str = Field(..., min_length=1)
    item_type: Literal["warning", "rejected", "unresolved"] = "unresolved"
    reason: str = Field(..., min_length=1)
    evidence_unit_ids: list[str] = Field(default_factory=list)

    @field_validator("item_id", "reason")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("source record unresolved fields cannot be empty")
        return text


class SourceRecordAttachment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attachment_id: str = ""
    attachment_type: Literal["image", "file", "table", "other"] = "file"
    name: str = Field(..., min_length=1)
    topic: str = ""
    description: str = ""
    source_range: str = ""
    status: Literal["candidate", "used", "skipped"] = "candidate"
    path: str | None = None
    relative_path: str | None = None
    mime_type: str | None = None
    content_hash: str | None = None
    source: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("source record attachment name cannot be empty")
        return text


class SourceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["source_record.v1"] = "source_record.v1"
    record_id: str = Field(..., min_length=1)
    source: KnowledgeSource
    raw_source: str | None = None
    content_hash: str | None = None
    source_focus: str = ""
    summary: str = ""
    units: list[SourceRecordUnit] = Field(default_factory=list)
    evidence_spans: list[KnowledgeEvidenceSpan] = Field(default_factory=list)
    attachments: list[SourceRecordAttachment] = Field(default_factory=list)
    contribution_map: list[SourceRecordContribution] = Field(default_factory=list)
    unresolved_items: list[SourceRecordUnresolvedItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("record_id")
    @classmethod
    def strip_record_id(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("record_id cannot be empty")
        return text

    @field_validator("warnings", mode="before")
    @classmethod
    def normalize_string_list(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        items: list[str] = []
        for item in value if isinstance(value, list) else []:
            text = str(item).strip()
            if text and text not in items:
                items.append(text)
        return items

    @model_validator(mode="after")
    def collect_unit_evidence(self) -> "SourceRecord":
        evidence = list(self.evidence_spans)
        seen = {
            (span.source_record_id, span.source_unit_index, span.excerpt_hash or span.excerpt)
            for span in evidence
        }
        for unit in self.units:
            key = (unit.evidence.source_record_id, unit.evidence.source_unit_index, unit.evidence.excerpt_hash or unit.evidence.excerpt)
            if key not in seen:
                seen.add(key)
                evidence.append(unit.evidence)
        self.evidence_spans = evidence
        return self

    def summary_counts(self) -> dict[str, int]:
        return {
            "units": len(self.units),
            "evidence_spans": len(self.evidence_spans),
            "attachments": len(self.attachments),
            "contributions": len(self.contribution_map),
            "unresolved": len(self.unresolved_items),
        }
