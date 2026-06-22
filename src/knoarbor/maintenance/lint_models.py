from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class LintPage:
    path: Path
    relative_path: str
    directory: str
    stem: str
    title: str
    content: str
    metadata: dict[str, str]
    links: list[str]
    canonical_path: str = ""
    legacy_paths: list[str] = field(default_factory=list)
    page_kind: str = "unknown"
    role: str = "knowledge_page"
    facets: list[str] = field(default_factory=list)

    @property
    def is_knowledge_page(self) -> bool:
        return self.role == "knowledge_page"

    @property
    def is_source_digest(self) -> bool:
        return self.role == "source_digest"
