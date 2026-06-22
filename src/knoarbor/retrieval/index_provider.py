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
from knoarbor.storage.wiki_paths import content_root


@dataclass(frozen=True)
class IndexRequest:
    vault_path: Path
    page_dirs: list[str] = field(default_factory=list)
    page_kinds: list[str] = field(default_factory=list)
    page_roles: list[str] = field(default_factory=list)
    facets: list[str] = field(default_factory=list)


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
        return [page for page in pages if _page_matches_request(page, request)]


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
        pages: list[SearchPage] = []
        for record in records:
            if not isinstance(record, dict):
                continue
            page = _record_to_search_page(vault_path, record)
            if page and _page_matches_request(page, request):
                pages.append(page)
        return pages


def _record_to_search_page(vault_path: Path, record: dict[str, object]) -> SearchPage | None:
    relative_path = str(record.get("path") or "")
    if not relative_path:
        return None
    root = content_root(vault_path)
    path = (root / relative_path).resolve()
    try:
        path.relative_to(root)
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
        canonical_path=str(record.get("canonical_path") or relative_path),
        legacy_paths=[str(path) for path in record.get("legacy_paths", []) if isinstance(path, str)],
        page_kind=str(record.get("page_kind") or _default_page_type(path.parent.name)),
        role=str(record.get("role") or "knowledge_page"),
        facets=[str(facet) for facet in record.get("facets", []) if isinstance(facet, str)],
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


def _page_matches_request(page: SearchPage, request: IndexRequest) -> bool:
    allowed_dirs_or_facets = _normalized_set(request.page_dirs)
    allowed_kinds = _normalized_set(request.page_kinds)
    allowed_roles = _normalized_set(request.page_roles)
    allowed_facets = _normalized_set(request.facets)
    page_directory = _normalize_value(page.directory)
    page_kind = _normalize_value(page.page_kind)
    page_role = _normalize_value(page.role)
    page_facets = {_normalize_value(item) for item in page.facets if item.strip()}

    if allowed_dirs_or_facets and not (
        page_directory in allowed_dirs_or_facets
        or page_kind in allowed_dirs_or_facets
        or bool(page_facets.intersection(allowed_dirs_or_facets))
    ):
        return False
    if allowed_kinds and page_kind not in allowed_kinds:
        return False
    if allowed_roles and page_role not in allowed_roles:
        return False
    return not (allowed_facets and not page_facets.intersection(allowed_facets))


def _normalized_set(values: list[str]) -> set[str]:
    return {_normalize_value(value) for value in values if str(value).strip()}


def _normalize_value(value: object) -> str:
    return str(value).strip().lower().replace(" ", "_").replace("-", "_")
