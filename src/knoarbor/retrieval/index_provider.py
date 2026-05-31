from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Protocol

from knoarbor.core.markdown import extract_list_items, extract_section
from knoarbor.core.wiki_schema import PAGE_TYPE_ORDER
from knoarbor.retrieval.markdown import SearchPage, collect_search_pages, strip_frontmatter
from knoarbor.retrieval.wiki_links import resolve_wikilink_target
from knoarbor.storage import ensure_machine_index, machine_index_dir


@dataclass(frozen=True)
class IndexRequest:
    vault_path: Path
    page_dirs: list[str] = field(default_factory=list)


class IndexProvider(Protocol):
    """Stable page index boundary for query and ingest retrieval."""

    name: str

    def collect(self, request: IndexRequest) -> list[SearchPage]:
        """Return queryable wiki pages without semantic ranking."""


class MarkdownIndexProvider:
    """Reads maintained Markdown wiki pages directly from the vault."""

    name = "markdown"

    def collect(self, request: IndexRequest) -> list[SearchPage]:
        pages = collect_search_pages(request.vault_path)
        allowed_dirs = {page_dir.strip() for page_dir in request.page_dirs if page_dir.strip()}
        if allowed_dirs:
            pages = [page for page in pages if page.directory in allowed_dirs]
        return pages


class MachineIndexProvider:
    """Reads program-readable machine index records and materializes page bodies on demand."""

    name = "machine"

    def collect(self, request: IndexRequest) -> list[SearchPage]:
        vault_path = request.vault_path.expanduser().resolve()
        pages_path = machine_index_dir(vault_path) / "pages.json"
        ensure_machine_index(vault_path)
        payload = json.loads(pages_path.read_text(encoding="utf-8"))
        records = payload.get("pages", [])
        if not isinstance(records, list):
            return []
        allowed_dirs = {page_dir.strip() for page_dir in request.page_dirs if page_dir.strip()}
        pages: list[SearchPage] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            directory = str(record.get("directory") or "")
            if allowed_dirs and directory not in allowed_dirs:
                continue
            page = _record_to_search_page(vault_path, record)
            if page:
                pages.append(page)
        return pages


def _record_to_search_page(vault_path: Path, record: dict[str, object]) -> SearchPage | None:
    relative_path = str(record.get("path") or "")
    if not relative_path:
        return None
    path = (vault_path / relative_path).resolve()
    try:
        path.relative_to(vault_path)
    except ValueError:
        return None
    if not path.exists() or not path.is_file():
        return None
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None
    return SearchPage(
        path=path,
        relative_path=relative_path,
        directory=str(record.get("directory") or path.parent.name),
        title=str(record.get("title") or path.stem),
        page_type=str(record.get("type") or _default_page_type(path.parent.name)),
        status=_optional_string(record.get("status")),
        source=_optional_string(record.get("source")),
        tags=[str(tag) for tag in record.get("tags", []) if isinstance(tag, str)],
        summary=str(record.get("summary") or extract_section(content, "Summary")),
        key_points=extract_list_items(extract_section(content, "Key Points")),
        related_pages=_resolve_related_paths(vault_path, record.get("outbound_links", [])),
        headings=[str(heading) for heading in record.get("headings", []) if isinstance(heading, str)],
        body=strip_frontmatter(content),
    )


def _resolve_related_paths(vault_path: Path, links: object) -> list[str]:
    if not isinstance(links, list):
        return []
    paths: list[str] = []
    seen: set[str] = set()
    for link in links:
        if not isinstance(link, str):
            continue
        resolved = resolve_wikilink_target(vault_path, link)
        if resolved and resolved not in seen:
            seen.add(resolved)
            paths.append(resolved)
    return paths


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text and text != "unknown" else None


def _default_page_type(directory: str) -> str:
    if directory in PAGE_TYPE_ORDER:
        return directory.rstrip("s")
    return "page"
