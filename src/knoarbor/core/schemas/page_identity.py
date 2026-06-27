from __future__ import annotations

import re
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


PageRole = Literal["knowledge_page", "source_digest", "report"]


class PageIdentity(BaseModel):
    """Stable page identity independent of physical type directories."""

    canonical_path: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    subject_kind: str = ""
    role: PageRole = "knowledge_page"
    atom_ids: list[str] = Field(default_factory=list)
    relation_ids: list[str] = Field(default_factory=list)
    source_digest_ids: list[str] = Field(default_factory=list)

    @field_validator("canonical_path")
    @classmethod
    def normalize_canonical_path(cls, value: str) -> str:
        return normalize_identity_path(value)

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
        return normalize_identity_label(value)

    @field_validator("atom_ids", "relation_ids", "source_digest_ids", mode="before")
    @classmethod
    def normalize_id_list(cls, value: object) -> list[str]:
        return _normalize_string_list(value, normalizer=lambda item: str(item).strip())

    @model_validator(mode="after")
    def validate_identity_consistency(self) -> "PageIdentity":
        if self.canonical_path.startswith("sources/"):
            self.role = "source_digest"
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


def normalize_identity_label(value: str) -> str:
    text = str(value).strip().lower()
    text = re.sub(r"[\s-]+", "_", text)
    text = re.sub(r"[^a-z0-9_\u4e00-\u9fff]+", "", text)
    return text.strip("_")


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
