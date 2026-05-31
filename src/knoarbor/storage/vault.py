from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from knoarbor.core.errors import VaultPathError


@dataclass
class VaultPage:
    path: str
    exists: bool
    content: str = ""
    truncated: bool = False
    original_content_length: int = 0
    error: str | None = None


class VaultStore:
    """Safe local Markdown vault reader.

    Storage owns path normalization and traversal protection. API/agent layers
    should only adapt the returned data to their response contracts.
    """

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()
        if not self.root.exists() or not self.root.is_dir():
            raise VaultPathError(f"vault_path does not exist or is not a directory: {self.root}")

    def read_pages(self, page_paths: list[str], max_pages: int, max_chars_per_page: int) -> list[VaultPage]:
        return [
            self.read_page(raw_path, max_chars_per_page)
            for raw_path in self.unique_paths(page_paths)[:max_pages]
        ]

    def read_page(self, raw_path: str, max_chars: int) -> VaultPage:
        normalized = self.normalize_page_path(raw_path)
        if not normalized:
            return VaultPage(path=raw_path, exists=False, error="empty page path")

        try:
            page_path = (self.root / normalized).resolve()
            page_path.relative_to(self.root)
        except ValueError:
            return VaultPage(path=normalized, exists=False, error="page path escapes vault")

        if not page_path.exists() or not page_path.is_file():
            return VaultPage(path=normalized, exists=False, error="page not found")

        content = page_path.read_text(encoding="utf-8")
        truncated = len(content) > max_chars
        return VaultPage(
            path=page_path.relative_to(self.root).as_posix(),
            exists=True,
            content=content[:max_chars],
            truncated=truncated,
            original_content_length=len(content),
        )

    def unique_paths(self, page_paths: list[str]) -> list[str]:
        seen: set[str] = set()
        unique: list[str] = []
        for page_path in page_paths:
            normalized = self.normalize_page_path(page_path)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            unique.append(page_path)
        return unique

    @staticmethod
    def normalize_page_path(raw_path: str) -> str:
        value = raw_path.strip()
        if not value:
            return ""

        wiki_link = re.fullmatch(r"\[\[(.+?)(?:\|.*?)?\]\]", value)
        if wiki_link:
            value = wiki_link.group(1)

        value = value.strip().lstrip("/")
        if value.endswith(".md"):
            return value
        return f"{value}.md"
