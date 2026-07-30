from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator


Position = Annotated[StrictInt, Field(ge=0)]


class IndexMetadataExtractResult(BaseModel):
    """Transient semantic candidates using request-local array positions."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["index_metadata_extract.v7"] = "index_metadata_extract.v7"
    entities: list[ExtractedEntity] = Field(default_factory=list)
    claims: list[ExtractedClaim] = Field(default_factory=list)
    synthesis_topics: list[str] = Field(default_factory=list)
    ambiguities: list[ExtractedAmbiguity] = Field(default_factory=list)

    @field_validator("synthesis_topics")
    @classmethod
    def normalize_topics(cls, value: list[str]) -> list[str]:
        topics: list[str] = []
        seen: set[str] = set()
        for item in value:
            text = item.strip()
            key = text.casefold()
            if text and key not in seen:
                seen.add(key)
                topics.append(text)
        return topics


class ExtractedEvidenceMixin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unit_positions: list[Position] = Field(..., min_length=1)

    @field_validator("unit_positions")
    @classmethod
    def dedupe_unit_positions(cls, value: list[int]) -> list[int]:
        return list(dict.fromkeys(value))


class ExtractedEntity(ExtractedEvidenceMixin):
    name: str = Field(..., min_length=1)
    aliases: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("entity name cannot be empty")
        return text

    @field_validator("aliases")
    @classmethod
    def normalize_aliases(cls, value: list[str]) -> list[str]:
        aliases: list[str] = []
        seen: set[str] = set()
        for item in value:
            text = item.strip()
            key = text.casefold()
            if text and key not in seen:
                seen.add(key)
                aliases.append(text)
        return aliases


class ExtractedEvidenceQuote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    unit_position: Position
    quote: str = Field(..., min_length=1)

    @field_validator("quote")
    @classmethod
    def validate_quote(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("evidence quote cannot be empty")
        if value != value.strip():
            raise ValueError("evidence quote must not contain leading or trailing whitespace")
        return value


class ExtractedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=1)
    entity_positions: list[Position] = Field(default_factory=list)
    evidence: list[ExtractedEvidenceQuote] = Field(..., min_length=1)
    relations: list[ExtractedRelation] = Field(default_factory=list)

    @field_validator("text")
    @classmethod
    def strip_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("claim text cannot be empty")
        return text

    @field_validator("entity_positions")
    @classmethod
    def dedupe_entity_positions(cls, value: list[int]) -> list[int]:
        return list(dict.fromkeys(value))

    @field_validator("evidence")
    @classmethod
    def dedupe_evidence(cls, value: list[ExtractedEvidenceQuote]) -> list[ExtractedEvidenceQuote]:
        output: list[ExtractedEvidenceQuote] = []
        seen: set[tuple[int, str]] = set()
        for item in value:
            key = (item.unit_position, item.quote)
            if key not in seen:
                seen.add(key)
                output.append(item)
        return output


class ExtractedRelation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_entity_position: Position
    predicate: str = Field(..., min_length=1)
    object_entity_position: Position

    @field_validator("predicate")
    @classmethod
    def strip_predicate(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("relation predicate cannot be empty")
        return text


class ExtractedAmbiguity(ExtractedEvidenceMixin):
    kind: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)

    @field_validator("kind", "description")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("ambiguity fields cannot be empty")
        return text
