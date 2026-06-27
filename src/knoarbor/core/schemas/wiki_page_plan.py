from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from knoarbor.core.schemas.knowledge_atoms import KnowledgeRelationPredicate


WikiPagePlanAction = Literal["create", "update", "skip"]
WikiPageDir = Literal["sources", "pages"]
WikiCrossPageRelationDirection = Literal["outgoing", "incoming", "bidirectional"]


class WikiCandidatePage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(..., min_length=1)
    title: str = ""
    match_reason: str = Field(..., min_length=1)


class WikiEntityMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_name: str = Field(..., min_length=1)
    canonical_name: str = Field(..., min_length=1)
    aliases: list[str] = Field(default_factory=list)
    target_page: str | None = None
    atom_id: str | None = None
    reason: str = Field(..., min_length=1)

    @field_validator("source_name", "canonical_name", "target_page", "atom_id", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("aliases", mode="before")
    @classmethod
    def normalize_aliases(cls, value: object) -> list[str]:
        return _normalize_string_list(value)


class WikiRelationMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relation_id: str = Field(..., min_length=1)
    canonical_subject: str = Field(..., min_length=1)
    predicate: KnowledgeRelationPredicate
    canonical_object: str = Field(..., min_length=1)
    subject_page: str | None = None
    object_page: str | None = None
    supporting_claim_ids: list[str] = Field(default_factory=list)
    reason: str = Field(..., min_length=1)

    @field_validator("relation_id", "canonical_subject", "canonical_object", "subject_page", "object_page", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("supporting_claim_ids", mode="before")
    @classmethod
    def normalize_ids(cls, value: object) -> list[str]:
        return _normalize_string_list(value)


class WikiCrossPageRelation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relation_id: str = Field(..., min_length=1)
    target_page: str = Field(..., min_length=1)
    direction: WikiCrossPageRelationDirection = "outgoing"
    supporting_claim_ids: list[str] = Field(default_factory=list)
    reason: str = Field(..., min_length=1)

    @field_validator("relation_id", "target_page", mode="before")
    @classmethod
    def normalize_required_text(cls, value: object) -> str:
        text = str(value or "").strip().lstrip("/")
        if not text:
            raise ValueError("cross-page relation fields cannot be empty")
        return text

    @field_validator("supporting_claim_ids", mode="before")
    @classmethod
    def normalize_ids(cls, value: object) -> list[str]:
        return _normalize_string_list(value)


class WikiPageOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: WikiPagePlanAction
    target_page: str | None = None
    page_dir: WikiPageDir | None = None
    canonical_path: str | None = None
    title: str | None = None
    knowledge_object: str | None = None
    selected_claim_ids: list[str] = Field(default_factory=list)
    selected_relation_ids: list[str] = Field(default_factory=list)
    source_digest_ids: list[str] = Field(default_factory=list)
    candidate_pages: list[WikiCandidatePage] = Field(default_factory=list)
    entity_mappings: list[WikiEntityMapping] = Field(default_factory=list)
    relation_mappings: list[WikiRelationMapping] = Field(default_factory=list)
    cross_page_relations: list[WikiCrossPageRelation] = Field(default_factory=list)
    decision_reason: str = Field(..., min_length=1)

    @field_validator("target_page")
    @classmethod
    def blank_target_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None

    @field_validator("canonical_path")
    @classmethod
    def blank_canonical_path_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip().lstrip("/")
        return text or None

    @field_validator("selected_claim_ids", "selected_relation_ids", "source_digest_ids", mode="before")
    @classmethod
    def normalize_id_list(cls, value: object) -> list[str]:
        return _normalize_string_list(value)

    @model_validator(mode="after")
    def validate_target_page(self) -> WikiPageOperation:
        if self.action == "update" and not self.target_page:
            raise ValueError(f"{self.action} operation requires target_page")
        if self.action in {"create", "skip"} and self.target_page:
            raise ValueError(f"{self.action} operation must not set target_page")
        if self.action in {"create", "update"}:
            if not self.page_dir:
                raise ValueError(f"{self.action} operation requires page_dir")
            if not self.title or not self.title.strip():
                raise ValueError(f"{self.action} operation requires title")
            if not self.knowledge_object or not self.knowledge_object.strip():
                raise ValueError(f"{self.action} operation requires knowledge_object")
            if not self.source_digest_ids:
                raise ValueError(f"{self.action} operation requires source_digest_ids")
            if self.page_dir != "sources" and not self.selected_claim_ids:
                raise ValueError(f"{self.action} non-source operation requires selected_claim_ids")
            _validate_mapping_support(self)
        if self.action == "skip":
            self.title = (self.title or "Skipped source").strip()
            self.knowledge_object = (self.knowledge_object or "No durable wiki object").strip()
            if self.entity_mappings or self.relation_mappings or self.cross_page_relations:
                raise ValueError("skip operation cannot carry graph alignment metadata")
        return self


class WikiPagePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operations: list[WikiPageOperation] = Field(..., min_length=1)
    overall_summary: str = Field(..., min_length=1)
    confidence: float = Field(default=0.8, ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def canonicalize_skip_operations(self) -> WikiPagePlan:
        actionable = [operation for operation in self.operations if operation.action != "skip"]
        if actionable and len(actionable) != len(self.operations):
            self.operations = actionable
            self.warnings.append("Dropped redundant skip operation because actionable page operations were present.")
        return self


def _normalize_string_list(value: object) -> list[str]:
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


def _validate_mapping_support(operation: WikiPageOperation) -> None:
    selected_claims = set(operation.selected_claim_ids)
    selected_relations = set(operation.selected_relation_ids)
    for mapping in operation.relation_mappings:
        if mapping.relation_id not in selected_relations:
            raise ValueError(f"relation mapping references unselected relation: {mapping.relation_id}")
        missing_claims = sorted(set(mapping.supporting_claim_ids).difference(selected_claims))
        if missing_claims:
            raise ValueError(f"relation mapping references unselected claim ids: {', '.join(missing_claims)}")
    for relation in operation.cross_page_relations:
        if relation.relation_id not in selected_relations:
            raise ValueError(f"cross-page relation references unselected relation: {relation.relation_id}")
        missing_claims = sorted(set(relation.supporting_claim_ids).difference(selected_claims))
        if missing_claims:
            raise ValueError(f"cross-page relation references unselected claim ids: {', '.join(missing_claims)}")
