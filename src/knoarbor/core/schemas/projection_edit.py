from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProjectionEvidenceView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    excerpt: str = ""
    source_path: str | None = None
    source_unit_id: str | None = None
    source_unit_index: int | None = None


class ProjectionClaimEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    claim: str = Field(..., min_length=1)

    @field_validator("id", "claim")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("projection claim fields cannot be empty")
        return text


class ProjectionClaimView(ProjectionClaimEdit):
    evidence: list[ProjectionEvidenceView] = Field(default_factory=list)


class ProjectionEntityEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    atom_id: str | None = None
    name: str = Field(..., min_length=1)
    aliases: list[str] = Field(default_factory=list)

    @field_validator("atom_id", mode="before")
    @classmethod
    def normalize_optional_id(cls, value: object) -> str | None:
        text = str(value or "").strip()
        return text or None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("projection entity names cannot be empty")
        return text

    @field_validator("aliases", mode="before")
    @classmethod
    def normalize_aliases(cls, value: object) -> list[str]:
        items = value if isinstance(value, list) else []
        aliases: list[str] = []
        for item in items:
            text = str(item).strip()
            if text and text not in aliases:
                aliases.append(text)
        return aliases


class ProjectionRelationObjectEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    atom_id: str | None = None
    name: str = Field(..., min_length=1)

    @field_validator("atom_id", mode="before")
    @classmethod
    def normalize_optional_id(cls, value: object) -> str | None:
        text = str(value or "").strip()
        return text or None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("relation object names cannot be empty")
        return text


class ProjectionRelationEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    subject: ProjectionRelationObjectEdit
    predicate: str = Field(..., min_length=1)
    object: ProjectionRelationObjectEdit
    source_claim_ids: list[str] = Field(..., min_length=1)

    @field_validator("id", mode="before")
    @classmethod
    def normalize_optional_id(cls, value: object) -> str | None:
        text = str(value or "").strip()
        return text or None

    @field_validator("predicate")
    @classmethod
    def strip_predicate(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("relation predicates cannot be empty")
        return text

    @field_validator("source_claim_ids", mode="before")
    @classmethod
    def normalize_claim_ids(cls, value: object) -> list[str]:
        items = value if isinstance(value, list) else []
        claim_ids: list[str] = []
        for item in items:
            text = str(item).strip()
            if text and text not in claim_ids:
                claim_ids.append(text)
        return claim_ids


class ProjectionEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["projection_edit.v1"] = "projection_edit.v1"
    base_revision_id: str = Field(..., min_length=1)
    synthesis: str = ""
    claims: list[ProjectionClaimEdit] = Field(default_factory=list)
    entities: list[ProjectionEntityEdit] = Field(default_factory=list)
    relations: list[ProjectionRelationEdit] = Field(default_factory=list)

    @field_validator("base_revision_id")
    @classmethod
    def strip_revision_id(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("base_revision_id cannot be empty")
        return text

    @field_validator("synthesis", mode="before")
    @classmethod
    def normalize_synthesis(cls, value: object) -> str:
        return str(value or "").strip()


class ProjectionEditorState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["projection_editor.v1"] = "projection_editor.v1"
    base_revision_id: str = Field(..., min_length=1)
    synthesis: str = ""
    claims: list[ProjectionClaimView] = Field(default_factory=list)
    entities: list[ProjectionEntityEdit] = Field(default_factory=list)
    relations: list[ProjectionRelationEdit] = Field(default_factory=list)
