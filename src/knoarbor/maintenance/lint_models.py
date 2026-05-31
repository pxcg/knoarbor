from __future__ import annotations

from dataclasses import dataclass
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
