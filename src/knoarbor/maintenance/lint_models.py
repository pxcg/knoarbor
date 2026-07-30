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
    entities: list[str] = field(default_factory=list)
    relation_nodes: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    canonical_path: str = ""
    role: str = "knowledge_page"

    @property
    def is_knowledge_page(self) -> bool:
        return self.role == "knowledge_page"

    @property
    def is_source_record(self) -> bool:
        return self.role == "source_record"
