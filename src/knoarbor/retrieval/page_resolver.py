from __future__ import annotations

from dataclasses import dataclass, field
import re
from pathlib import Path

from knoarbor.core.markdown import wiki_target_key
from knoarbor.storage import ensure_machine_index, machine_index_dir
from knoarbor.storage.wiki_index import relative_wiki_path
from knoarbor.storage.wiki_paths import content_root, source_digest_root


@dataclass(frozen=True)
class PageResolution:
    query: str
    status: str
    resolved_path: str | None = None
    canonical_path: str | None = None
    title: str | None = None
    role: str | None = None
    matched_by: str | None = None
    conflicts: list[str] = field(default_factory=list)

    @property
    def resolved(self) -> bool:
        return self.status == "resolved" and self.resolved_path is not None


def resolve_page_reference(vault_path: Path, reference: str, *, directory: str | None = None) -> PageResolution:
    """Resolve paths, wikilinks, titles, and aliases."""

    query = _normalize_reference(reference)
    if not query:
        return PageResolution(query=reference, status="not_found")

    records = _page_records(vault_path)
    candidates = _candidate_records(records, query, directory=directory)
    if len(candidates) == 1:
        return _resolved(query, candidates[0])
    if len(candidates) > 1:
        return PageResolution(
            query=query,
            status="ambiguous",
            conflicts=sorted(str(record.get("path") or "") for record in candidates if record.get("path")),
        )
    return PageResolution(query=query, status="not_found")


def resolve_page_reference_path(vault_path: Path, reference: str, *, directory: str | None = None) -> str | None:
    resolution = resolve_page_reference(vault_path, reference, directory=directory)
    return resolution.resolved_path if resolution.resolved else None


def page_resolver_conflicts(vault_path: Path) -> list[dict[str, object]]:
    """Return deterministic alias/title/path collisions from the machine index."""

    records = _page_records(vault_path)
    buckets: dict[str, list[str]] = {}
    for record in records:
        path = str(record.get("path") or "")
        if not path:
            continue
        for key in _record_keys(record):
            buckets.setdefault(key, [])
            if path not in buckets[key]:
                buckets[key].append(path)
    conflicts: list[dict[str, object]] = []
    for key, paths in sorted(buckets.items()):
        if len(paths) > 1:
            conflicts.append({"key": key, "paths": sorted(paths)})
    return conflicts


def _page_records(vault_path: Path) -> list[dict[str, object]]:
    vault = vault_path.expanduser().resolve()
    try:
        ensure_machine_index(vault)
        import json

        payload = json.loads((machine_index_dir(vault) / "pages.json").read_text(encoding="utf-8"))
        records = payload.get("pages", [])
        return [record for record in records if isinstance(record, dict)]
    except (FileNotFoundError, OSError, ValueError):
        return _scan_page_records_from_markdown(vault)


def _scan_page_records_from_markdown(vault_path: Path) -> list[dict[str, object]]:
    """Build minimal page records when the machine index is unavailable."""

    root = content_root(vault_path)
    source_root = source_digest_root(vault_path)
    records: list[dict[str, object]] = []
    for md_path in [*sorted(root.rglob("*.md")), *sorted(source_root.rglob("*.md"))]:
        if not md_path.is_file():
            continue
        records.append({"path": relative_wiki_path(vault_path, md_path), "title": md_path.stem})
    return records


def _candidate_records(records: list[dict[str, object]], query: str, *, directory: str | None) -> list[dict[str, object]]:
    query_key = _key(query)
    query_path = _path_key(query)
    matches: list[dict[str, object]] = []
    for record in records:
        if directory and str(record.get("directory") or "") != directory:
            continue
        keys = _record_keys(record)
        if query_key in keys or query_path in keys:
            matches.append(record)
    return matches


def _record_keys(record: dict[str, object]) -> set[str]:
    keys: set[str] = set()
    path = str(record.get("path") or "")
    canonical_path = str(record.get("canonical_path") or "")
    title = str(record.get("title") or "")
    keys.update(_path_variants(path))
    keys.update(_path_variants(canonical_path))
    keys.add(_key(Path(path).stem))
    keys.add(_key(title))
    return {key for key in keys if key}


def _path_variants(path: str) -> set[str]:
    if not path:
        return set()
    normalized = _path_key(path)
    stem = _key(Path(normalized).stem)
    no_suffix = normalized.removesuffix(".md")
    return {normalized, no_suffix, stem}


def _resolved(query: str, record: dict[str, object]) -> PageResolution:
    path = str(record.get("path") or "")
    canonical_path = str(record.get("canonical_path") or path)
    matched_by = "path"
    if _key(query) == _key(str(record.get("title") or "")):
        matched_by = "title"
    elif _path_key(query) == _path_key(canonical_path):
        matched_by = "canonical_path"
    return PageResolution(
        query=query,
        status="resolved",
        resolved_path=path,
        canonical_path=canonical_path,
        title=str(record.get("title") or Path(path).stem),
        role=str(record.get("role") or ""),
        matched_by=matched_by,
    )


def _normalize_reference(reference: str) -> str:
    value = reference.strip()
    wiki_link = re.fullmatch(r"\[\[(.+?)(?:\|.*?)?\]\]", value)
    if wiki_link:
        value = wiki_link.group(1)
    value = wiki_target_key(value)
    value = re.sub(r"/+", "/", value.replace("\\", "/").strip("/"))
    return value


def _path_key(value: str) -> str:
    normalized = _normalize_reference(value)
    return normalized if normalized.endswith(".md") else f"{normalized}.md"


def _key(value: str) -> str:
    return re.sub(r"[\s_-]+", "-", _normalize_reference(value)).casefold()
