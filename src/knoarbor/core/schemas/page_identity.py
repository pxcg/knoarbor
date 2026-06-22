from __future__ import annotations

import re
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


PageKind = Literal[
    "concept",
    "entity",
    "workflow",
    "comparison",
    "timeline",
    "query",
    "note",
    "source_digest",
    "generated_view",
    "unknown",
]
PageRole = Literal["knowledge_page", "source_digest", "generated_view", "report"]
PageFacet = str


class PageIdentity(BaseModel):
    """Stable page identity independent of physical type directories."""

    canonical_path: str = Field(..., min_length=1)
    legacy_paths: list[str] = Field(default_factory=list)
    title: str = Field(..., min_length=1)
    page_kind: PageKind = "unknown"
    subject_kind: str = ""
    role: PageRole = "knowledge_page"
    facets: list[str] = Field(default_factory=list)
    atom_ids: list[str] = Field(default_factory=list)
    relation_ids: list[str] = Field(default_factory=list)
    source_digest_ids: list[str] = Field(default_factory=list)

    @field_validator("canonical_path")
    @classmethod
    def normalize_canonical_path(cls, value: str) -> str:
        return normalize_identity_path(value)

    @field_validator("legacy_paths", mode="before")
    @classmethod
    def normalize_legacy_paths(cls, value: object) -> list[str]:
        return _normalize_path_list(value)

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("page identity title cannot be empty")
        return text

    @field_validator("subject_kind")
    @classmethod
    def normalize_subject_kind(cls, value: str) -> str:
        return normalize_facet(value)

    @field_validator("facets", mode="before")
    @classmethod
    def normalize_facets(cls, value: object) -> list[str]:
        return _normalize_string_list(value, normalizer=normalize_facet)

    @field_validator("atom_ids", "relation_ids", "source_digest_ids", mode="before")
    @classmethod
    def normalize_id_list(cls, value: object) -> list[str]:
        return _normalize_string_list(value, normalizer=lambda item: str(item).strip())

    @model_validator(mode="after")
    def validate_identity_consistency(self) -> "PageIdentity":
        if self.canonical_path in self.legacy_paths:
            self.legacy_paths = [path for path in self.legacy_paths if path != self.canonical_path]
        if self.role == "source_digest" and self.page_kind not in {"source_digest", "unknown"}:
            raise ValueError("source_digest role must use page_kind source_digest or unknown")
        if self.page_kind == "source_digest":
            self.role = "source_digest"
        if self.role == "generated_view":
            self.page_kind = "generated_view"
        return self


def normalize_identity_path(value: str) -> str:
    text = str(value).strip().replace("\\", "/").lstrip("/")
    text = re.sub(r"/+", "/", text)
    if not text:
        raise ValueError("page path cannot be empty")
    parts = text.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError(f"invalid page path: {value}")
    if not text.lower().endswith(".md"):
        text = f"{text}.md"
    return text


def normalize_facet(value: str) -> str:
    text = str(value).strip().lower()
    text = re.sub(r"[\s-]+", "_", text)
    text = re.sub(r"[^a-z0-9_\u4e00-\u9fff]+", "", text)
    return text.strip("_")


def _normalize_path_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    paths: list[str] = []
    seen: set[str] = set()
    for item in value if isinstance(value, list) else []:
        path = normalize_identity_path(str(item))
        if path not in seen:
            paths.append(path)
            seen.add(path)
    return paths


def _normalize_string_list(value: object, *, normalizer: Callable[[object], str]) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    items: list[str] = []
    seen: set[str] = set()
    for item in value if isinstance(value, list) else []:
        text = normalizer(item)
        if text and text not in seen:
            items.append(text)
            seen.add(text)
    return items
