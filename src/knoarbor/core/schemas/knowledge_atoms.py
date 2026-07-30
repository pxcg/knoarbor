from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


KnowledgeAtomObjectType = Literal["knowledge_object", "page", "source", "claim", "unknown"]


class KnowledgeEvidenceSpan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_record_id: str = Field(..., min_length=1)
    raw_record_id: str | None = None
    raw_revision_id: str | None = None
    revision_id: str | None = None
    window_id: str | None = None
    source_unit_id: str | None = None
    processing_record_id: str | None = None
    source_path: str | None = None
    source_unit_index: int | None = Field(default=None, ge=0)
    excerpt: str = ""
    excerpt_hash: str | None = None
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)

    @field_validator("source_record_id")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("evidence span fields cannot be empty")
        return text

    @model_validator(mode="after")
    def validate_char_range(self) -> "KnowledgeEvidenceSpan":
        if self.char_start is not None and self.char_end is not None and self.char_end < self.char_start:
            raise ValueError("char_end must be greater than or equal to char_start")
        if not self.excerpt.strip() and not self.source_unit_id:
            raise ValueError("evidence span requires excerpt or source_unit_id")
        return self


class KnowledgeAtomObject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    object_type: KnowledgeAtomObjectType = "knowledge_object"
    name: str = Field(..., min_length=1)
    page_path: str | None = None
    atom_id: str | None = None
    aliases: list[str] = Field(default_factory=list)
    evidence: list[KnowledgeEvidenceSpan] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("knowledge atom object name cannot be empty")
        return text

    @field_validator("aliases", mode="before")
    @classmethod
    def normalize_aliases(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        aliases: list[str] = []
        for item in value if isinstance(value, list) else []:
            text = str(item).strip()
            if text and text not in aliases:
                aliases.append(text)
        return aliases


class KnowledgeClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    claim: str = Field(..., min_length=1)
    evidence: list[KnowledgeEvidenceSpan] = Field(default_factory=list)
    entity_names: list[str] = Field(default_factory=list)
    entity_ids: list[str] = Field(default_factory=list)

    @field_validator("id", "claim")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("claim fields cannot be empty")
        return text

    @field_validator("entity_names", "entity_ids", mode="before")
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
    def require_support(self) -> "KnowledgeClaim":
        if not self.evidence:
            raise ValueError("claim requires evidence")
        return self


class KnowledgeRelation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    subject: KnowledgeAtomObject
    predicate: str = Field(..., min_length=1)
    object: KnowledgeAtomObject
    source_claim_ids: list[str] = Field(default_factory=list)
    evidence: list[KnowledgeEvidenceSpan] = Field(default_factory=list)

    @field_validator("id", "predicate")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("relation fields cannot be empty")
        return text

    @field_validator("source_claim_ids", mode="before")
    @classmethod
    def normalize_ids(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        ids: list[str] = []
        for item in value if isinstance(value, list) else []:
            text = str(item).strip()
            if text and text not in ids:
                ids.append(text)
        return ids

    @model_validator(mode="after")
    def require_support(self) -> "KnowledgeRelation":
        if not self.source_claim_ids:
            raise ValueError("relation requires source_claim_ids")
        return self


class KnowledgeAtomBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["knowledge_atoms.v3"] = "knowledge_atoms.v3"
    source_record_id: str = Field(..., min_length=1)
    revision_id: str | None = None
    window_id: str | None = None
    entities: list[KnowledgeAtomObject] = Field(default_factory=list)
    claims: list[KnowledgeClaim] = Field(default_factory=list)
    relations: list[KnowledgeRelation] = Field(default_factory=list)
    synthesis: str = ""

    @field_validator("source_record_id")
    @classmethod
    def strip_source_record_id(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("source_record_id cannot be empty")
        return text

    @field_validator("synthesis", mode="before")
    @classmethod
    def normalize_synthesis(cls, value: object) -> str:
        return str(value or "").strip()

    def summary(self) -> dict[str, int]:
        evidence_ids = {
            (span.source_record_id, span.source_unit_index, span.excerpt_hash or span.excerpt)
            for entity in self.entities
            for span in entity.evidence
        }
        evidence_ids.update(
            (span.source_record_id, span.source_unit_index, span.excerpt_hash or span.excerpt)
            for claim in self.claims
            for span in claim.evidence
        )
        evidence_ids.update(
            (span.source_record_id, span.source_unit_index, span.excerpt_hash or span.excerpt)
            for relation in self.relations
            for span in relation.evidence
        )
        return {
            "entities": len(self.entities),
            "claims": len(self.claims),
            "relations": len(self.relations),
            "evidence_spans": len(evidence_ids),
        }
