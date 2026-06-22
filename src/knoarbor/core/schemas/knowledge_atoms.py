from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


KnowledgeAtomObjectType = Literal["page", "source", "entity", "concept", "claim", "workflow", "comparison", "timeline", "unknown"]
KnowledgeClaimType = Literal["definition", "recommendation", "assessment", "causal", "decision", "comparison", "open_question"]
KnowledgeClaimStance = Literal["asserted", "tentative", "disputed"]
KnowledgeRelationPredicate = Literal[
    "supports",
    "contradicts",
    "relates_to",
    "contrasts",
    "derived_from",
    "depends_on",
    "part_of",
    "mentions",
]
KnowledgeAtomIssueSeverity = Literal["error", "warning", "info"]
KnowledgeAtomIssueType = Literal[
    "duplicate_atom_id",
    "unsupported_fact",
    "unsupported_claim",
    "unsupported_relation",
    "conflicting_relation",
]


class KnowledgeEvidenceSpan(BaseModel):
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
    object_type: KnowledgeAtomObjectType = "unknown"
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


class KnowledgeFact(BaseModel):
    id: str = Field(..., min_length=1)
    statement: str = Field(..., min_length=1)
    subject: KnowledgeAtomObject | None = None
    predicate: str | None = None
    object: KnowledgeAtomObject | None = None
    qualifiers: dict[str, Any] = Field(default_factory=dict)
    evidence: list[KnowledgeEvidenceSpan] = Field(..., min_length=1)
    confidence: float = Field(default=0.8, ge=0, le=1)

    @field_validator("id", "statement")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("fact fields cannot be empty")
        return text


class KnowledgeClaim(BaseModel):
    id: str = Field(..., min_length=1)
    claim: str = Field(..., min_length=1)
    claim_type: KnowledgeClaimType
    stance: KnowledgeClaimStance = "asserted"
    supporting_fact_ids: list[str] = Field(default_factory=list)
    evidence: list[KnowledgeEvidenceSpan] = Field(default_factory=list)
    scope: str = ""
    limitations: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.8, ge=0, le=1)

    @field_validator("id", "claim")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("claim fields cannot be empty")
        return text

    @field_validator("supporting_fact_ids", "limitations", mode="before")
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
        if not self.supporting_fact_ids and not self.evidence:
            raise ValueError("claim requires supporting_fact_ids or evidence")
        return self


class KnowledgeRelation(BaseModel):
    id: str = Field(..., min_length=1)
    subject: KnowledgeAtomObject
    predicate: KnowledgeRelationPredicate
    object: KnowledgeAtomObject
    source_fact_ids: list[str] = Field(default_factory=list)
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

    @field_validator("source_fact_ids", "source_claim_ids", mode="before")
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
        if not self.source_fact_ids and not self.source_claim_ids and not self.evidence:
            raise ValueError("relation requires source_fact_ids, source_claim_ids, or evidence")
        return self


class KnowledgeAtomBatch(BaseModel):
    schema_version: Literal["knowledge_atoms.v1"] = "knowledge_atoms.v1"
    source_digest_id: str = Field(..., min_length=1)
    facts: list[KnowledgeFact] = Field(default_factory=list)
    claims: list[KnowledgeClaim] = Field(default_factory=list)
    relations: list[KnowledgeRelation] = Field(default_factory=list)
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
            for fact in self.facts
            for span in fact.evidence
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
            "facts": len(self.facts),
            "claims": len(self.claims),
            "relations": len(self.relations),
            "evidence_spans": len(evidence_ids),
        }


class KnowledgeAtomQualityIssue(BaseModel):
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
            "facts": int(self.extracted.get("facts", 0)),
            "claims": int(self.extracted.get("claims", 0)),
            "relations": int(self.extracted.get("relations", 0)),
            "evidence_spans": int(self.extracted.get("evidence_spans", 0)),
            "unsupported": unsupported,
            "conflicting": conflicting,
            "rejected": rejected,
        }
