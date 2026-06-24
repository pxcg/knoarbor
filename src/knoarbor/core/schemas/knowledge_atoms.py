from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


KnowledgeAtomObjectType = Literal["knowledge_object", "page", "source", "claim", "unknown"]
KnowledgeClaimType = Literal["definition", "recommendation", "assessment", "causal", "decision", "comparison", "open_question"]
KnowledgeClaimStance = Literal["asserted", "tentative", "disputed"]
KnowledgeRelationPredicate = Literal[
    "supports",
    "contradicts",
    "contrasts_with",
    "derived_from",
    "depends_on",
    "requires",
    "uses",
    "implements",
    "constrains",
    "part_of",
    "coordinates",
    "includes",
    "can_mask",
    "preferred_over",
]
KnowledgeAtomIssueSeverity = Literal["error", "warning", "info"]
KnowledgeAtomIssueType = Literal[
    "duplicate_atom_id",
    "unsupported_claim",
    "unsupported_relation",
    "conflicting_relation",
    "undefined_entity_reference",
    "unused_entity",
]


class KnowledgeEvidenceSpan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_digest_id: str = Field(..., min_length=1)
    source_path: str | None = None
    source_unit_index: int | None = Field(default=None, ge=0)
    excerpt: str = Field(..., min_length=1)
    excerpt_hash: str | None = None
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)

    @field_validator("source_digest_id", "excerpt")
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
        return self


class KnowledgeAtomObject(BaseModel):
    model_config = ConfigDict(extra="forbid")

    object_type: KnowledgeAtomObjectType = "knowledge_object"
    name: str = Field(..., min_length=1)
    page_path: str | None = None
    atom_id: str | None = None
    aliases: list[str] = Field(default_factory=list)

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
    claim_type: KnowledgeClaimType
    stance: KnowledgeClaimStance = "asserted"
    evidence: list[KnowledgeEvidenceSpan] = Field(default_factory=list)
    entity_names: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.8, ge=0, le=1)

    @field_validator("id", "claim")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("claim fields cannot be empty")
        return text

    @field_validator("entity_names", mode="before")
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
    predicate: KnowledgeRelationPredicate
    object: KnowledgeAtomObject
    source_claim_ids: list[str] = Field(default_factory=list)
    evidence: list[KnowledgeEvidenceSpan] = Field(default_factory=list)
    reason: str = ""
    confidence: float = Field(default=0.8, ge=0, le=1)

    @field_validator("id")
    @classmethod
    def strip_id(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("relation id cannot be empty")
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

    schema_version: Literal["knowledge_atoms.v2"] = "knowledge_atoms.v2"
    source_digest_id: str = Field(..., min_length=1)
    entities: list[KnowledgeAtomObject] = Field(default_factory=list)
    claims: list[KnowledgeClaim] = Field(default_factory=list)
    relations: list[KnowledgeRelation] = Field(default_factory=list)
    evidence: list[KnowledgeEvidenceSpan] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("source_digest_id")
    @classmethod
    def strip_source_digest_id(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("source_digest_id cannot be empty")
        return text

    def summary(self) -> dict[str, int]:
        evidence_ids = {
            (span.source_digest_id, span.source_unit_index, span.excerpt_hash or span.excerpt)
            for span in self.evidence
        }
        evidence_ids.update(
            (span.source_digest_id, span.source_unit_index, span.excerpt_hash or span.excerpt)
            for claim in self.claims
            for span in claim.evidence
        )
        evidence_ids.update(
            (span.source_digest_id, span.source_unit_index, span.excerpt_hash or span.excerpt)
            for relation in self.relations
            for span in relation.evidence
        )
        return {
            "entities": len(self.entities),
            "claims": len(self.claims),
            "relations": len(self.relations),
            "evidence_spans": len(evidence_ids),
        }


class KnowledgeAtomQualityIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issue_type: KnowledgeAtomIssueType
    severity: KnowledgeAtomIssueSeverity = "warning"
    atom_id: str | None = None
    message: str = Field(..., min_length=1)

    @field_validator("message")
    @classmethod
    def strip_message(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("quality issue message cannot be empty")
        return text


class KnowledgeAtomQualityReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["knowledge_atom_quality.v1"] = "knowledge_atom_quality.v1"
    source_digest_id: str = Field(..., min_length=1)
    extracted: dict[str, int] = Field(default_factory=dict)
    issues: list[KnowledgeAtomQualityIssue] = Field(default_factory=list)

    @field_validator("source_digest_id")
    @classmethod
    def strip_source_digest_id(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("source_digest_id cannot be empty")
        return text

    def summary(self) -> dict[str, int]:
        unsupported = sum(1 for issue in self.issues if issue.issue_type.startswith("unsupported_"))
        conflicting = sum(1 for issue in self.issues if issue.issue_type == "conflicting_relation")
        rejected = sum(1 for issue in self.issues if issue.severity == "error")
        return {
            "entities": int(self.extracted.get("entities", 0)),
            "claims": int(self.extracted.get("claims", 0)),
            "relations": int(self.extracted.get("relations", 0)),
            "evidence_spans": int(self.extracted.get("evidence_spans", 0)),
            "unsupported": unsupported,
            "conflicting": conflicting,
            "rejected": rejected,
        }
