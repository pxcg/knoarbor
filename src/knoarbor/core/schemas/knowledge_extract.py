from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


KnowledgeSourceType = Literal["chat", "markdown", "html", "text_note", "document", "web", "manual"]
ContentUnitType = Literal["conversation_turn", "note", "section", "excerpt", "evidence"]
ContentUnitRole = Literal["user", "assistant", "note", "excerpt", "evidence"]


class KnowledgeSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: KnowledgeSourceType
    source_app: str = Field(..., min_length=1)
    source_id: str | None = None
    source_path: str | None = None
    title: str = Field(..., min_length=1)
    created_at: str | None = None
    updated_at: str | None = None

    @field_validator("source_app", "title")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("knowledge source text fields cannot be empty")
        return text


class ContentUnit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int = Field(..., ge=0)
    unit_type: ContentUnitType
    role: ContentUnitRole
    title: str | None = None
    content: str = ""
    timestamp: str | None = None
    is_primary: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class SupportingEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_tool: str | None = None
    tool_call_id: str | None = None
    content: str = ""
    truncated: bool = False
    original_content_length: int = Field(default=0, ge=0)


class CompileContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_content: str = ""
    supporting_evidence: list[SupportingEvidence] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    latest_unit_indexes: list[int] = Field(default_factory=list)

    @field_validator("links", mode="before")
    @classmethod
    def normalize_links(cls, value: object) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            return [str(value).strip()] if str(value).strip() else []
        links: list[str] = []
        for item in value:
            if isinstance(item, str):
                text = item.strip()
            elif isinstance(item, dict):
                url = str(item.get("url") or item.get("href") or "").strip()
                title = str(item.get("title") or item.get("label") or "").strip()
                text = url or title
            else:
                text = str(item).strip()
            if text:
                links.append(text)
        return links


class KnowledgeExtract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["knowledge_extract.v1"] = "knowledge_extract.v1"
    source: KnowledgeSource
    content_units: list[ContentUnit] = Field(default_factory=list)
    compile_context: CompileContext = Field(default_factory=CompileContext)
    confidence: float = Field(default=0.8, ge=0, le=1)
    warnings: list[str] = Field(default_factory=list)
