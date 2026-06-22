from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from knoarbor.core.schemas.knowledge_atoms import KnowledgeAtomObject, KnowledgeEvidenceSpan
from knoarbor.core.schemas.knowledge_extract import KnowledgeSource


SourceDigestUnitType = Literal["conversation_turn", "note", "section", "excerpt", "evidence"]
SourceObservationType = Literal["fact_candidate", "claim_candidate", "decision", "workflow_step", "limitation", "open_question"]


class SourceDigestUnit(BaseModel):
    index: int = Field(..., ge=0)
    unit_type: SourceDigestUnitType
    title: str | None = None
    summary: str = ""
    evidence: KnowledgeEvidenceSpan
    metadata: dict[str, object] = Field(default_factory=dict)


class SourceObservation(BaseModel):
    id: str = Field(..., min_length=1)
    observation_type: SourceObservationType = "fact_candidate"
    statement: str = Field(..., min_length=1)
    evidence: list[KnowledgeEvidenceSpan] = Field(..., min_length=1)
    confidence: float = Field(default=0.8, ge=0, le=1)

    @field_validator("id", "statement")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("source observation fields cannot be empty")
        return text


class SourceDigest(BaseModel):
    schema_version: Literal["source_digest.v1"] = "source_digest.v1"
    digest_id: str = Field(..., min_length=1)
    source: KnowledgeSource
    source_focus: str = ""
    summary: str = ""
    units: list[SourceDigestUnit] = Field(default_factory=list)
    observations: list[SourceObservation] = Field(default_factory=list)
    mentioned_objects: list[KnowledgeAtomObject] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    evidence_spans: list[KnowledgeEvidenceSpan] = Field(default_factory=list)
    confidence: float = Field(default=0.8, ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("digest_id")
    @classmethod
    def strip_digest_id(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("digest_id cannot be empty")
        return text

    @field_validator("limitations", "warnings", mode="before")
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
    def collect_unit_evidence(self) -> "SourceDigest":
        evidence = list(self.evidence_spans)
        seen = {
            (span.source_digest_id, span.source_unit_index, span.excerpt_hash or span.excerpt)
            for span in evidence
        }
        for unit in self.units:
            key = (unit.evidence.source_digest_id, unit.evidence.source_unit_index, unit.evidence.excerpt_hash or unit.evidence.excerpt)
            if key not in seen:
                seen.add(key)
                evidence.append(unit.evidence)
        self.evidence_spans = evidence
        return self

    def summary_counts(self) -> dict[str, int]:
        return {
            "units": len(self.units),
            "observations": len(self.observations),
            "mentioned_objects": len(self.mentioned_objects),
            "limitations": len(self.limitations),
            "evidence_spans": len(self.evidence_spans),
        }
