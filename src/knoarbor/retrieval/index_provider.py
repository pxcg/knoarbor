from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Protocol

from knoarbor.core.markdown import extract_list_items, extract_section
from knoarbor.retrieval.markdown import SearchPage, _extract_entities, collect_search_pages, strip_frontmatter
from knoarbor.retrieval.wiki_links import resolve_wikilink_target
from knoarbor.storage import ensure_machine_index, machine_index_dir
from knoarbor.storage.wiki_paths import content_path


@dataclass(frozen=True)
class IndexRequest:
    vault_path: Path
    page_dirs: list[str] = field(default_factory=list)
    page_roles: list[str] = field(default_factory=list)


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
    path = content_path(vault_path, relative_path).resolve()
    root = vault_path.expanduser().resolve()
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
        entities=[str(entity) for entity in record.get("entities", []) if isinstance(entity, str)] or _extract_entities(content),
        summary=str(record.get("summary") or extract_section(content, "Summary")),
        claim_points=extract_list_items(extract_section(content, "Claims")),
        outbound_links=_resolve_related_paths(vault_path, record.get("outbound_links", [])),
        headings=[str(heading) for heading in record.get("headings", []) if isinstance(heading, str)],
        body=strip_frontmatter(content),
        canonical_path=str(record.get("canonical_path") or relative_path),
        role=str(record.get("role") or "knowledge_page"),
        relations=_record_relations(record.get("relations", [])),
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


def _record_relations(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        subject = str(item.get("subject") or "").strip()
        predicate = str(item.get("predicate") or "").strip()
        obj = str(item.get("object") or "").strip()
        claim = str(item.get("claim") or "").strip().upper()
        if subject and predicate and obj:
            rows.append({"subject": subject, "predicate": predicate, "object": obj, "claim": claim})
    return rows


def _page_matches_request(page: SearchPage, request: IndexRequest) -> bool:
    allowed_dirs = _normalized_set(request.page_dirs)
    allowed_roles = _normalized_set(request.page_roles)
    page_directory = _normalize_value(page.directory)
    page_role = _normalize_value(page.role)

    if allowed_dirs and page_directory not in allowed_dirs:
        return False
    return not (allowed_roles and page_role not in allowed_roles)


def _normalized_set(values: list[str]) -> set[str]:
    return {_normalize_value(value) for value in values if str(value).strip()}


def _normalize_value(value: object) -> str:
    return str(value).strip().lower().replace(" ", "_").replace("-", "_")
