from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from knoarbor.core.markdown import compact_inline_text, extract_heading, extract_section, extract_tags, parse_frontmatter
from knoarbor.core.schemas.wiki_write import VaultWriteResult, WikiDraft
from knoarbor.core.wiki_schema import FRONTMATTER_TYPES, PAGE_TYPE_ORDER, is_index_excluded_file
from knoarbor.runtime import vault_write_lock
from knoarbor.storage.wiki_paths import content_relative_path, content_root, vault_relative_path


def relative_wiki_path(vault_path: Path, path: Path) -> str:
    try:
        return content_relative_path(vault_path, path)
    except ValueError:
        return vault_relative_path(vault_path, path)


def wiki_link_for_path(vault_path: Path, md_path: Path, title: str | None = None) -> str:
    link_path = md_path.resolve().relative_to(content_root(vault_path).resolve()).with_suffix("").as_posix()
    if title:
        return f"[[{link_path}|{title}]]"
    return f"[[{link_path}]]"


def index_entry(vault_path: Path, md_path: Path) -> str:
    relative = md_path.resolve().relative_to(content_root(vault_path).resolve()).with_suffix("")
    link_path = relative.as_posix()
    fallback_title = md_path.stem

    try:
        content = md_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"- [[{link_path}|{fallback_title}]] — unreadable file"

    metadata = parse_frontmatter(content)
    title = extract_heading(content, fallback_title)
    page_type = metadata.get("type") or FRONTMATTER_TYPES.get(md_path.parent.name, "page")
    status = metadata.get("status", "unknown")
    updated = metadata.get("updated") or metadata.get("created") or "unknown"
    tags = extract_tags(content, metadata)
    tags_text = ", ".join(tags) if tags else "none"
    summary = compact_inline_text(extract_section(content, "Summary") or "No summary yet.")

    return (
        f"- [[{link_path}|{title}]] — type: {page_type} | status: {status} | "
        f"updated: {updated} | tags: {tags_text} | summary: {summary}"
    )


def machine_index_dir(vault_path: Path) -> Path:
    return vault_path.expanduser().resolve() / ".knoarbor" / "index"


def is_machine_index_stale(vault_path: Path) -> bool:
    index_dir = machine_index_dir(vault_path)
    index_files = [
        index_dir / "pages.json",
        index_dir / "links.json",
        index_dir / "sources.json",
        index_dir / "search.json",
    ]
    if any(not path.exists() for path in index_files):
        return True
    index_mtime = min(path.stat().st_mtime for path in index_files)
    root = content_root(vault_path)
    for page_type in PAGE_TYPE_ORDER:
        page_dir = root / page_type
        if not page_dir.exists():
            continue
        for md_path in page_dir.glob("*.md"):
            if not is_index_excluded_file(md_path.name) and md_path.stat().st_mtime > index_mtime:
                return True
    return False


def ensure_machine_index(vault_path: Path) -> None:
    if is_machine_index_stale(vault_path):
        update_machine_index(vault_path)


def page_record(vault_path: Path, md_path: Path) -> dict[str, Any]:
    content = md_path.read_text(encoding="utf-8")
    metadata = parse_frontmatter(content)
    title = extract_heading(content, md_path.stem)
    tags = extract_tags(content, metadata)
    headings = _extract_headings(content)
    summary = compact_inline_text(extract_section(content, "Summary") or "")
    return {
        "schema_version": "machine_page.v1",
        "path": relative_wiki_path(vault_path, md_path),
        "directory": md_path.parent.name,
        "title": title,
        "type": str(metadata.get("type") or FRONTMATTER_TYPES.get(md_path.parent.name, "page")),
        "status": str(metadata.get("status") or "unknown"),
        "created": _string_or_none(metadata.get("created")),
        "updated": _string_or_none(metadata.get("updated") or metadata.get("created")),
        "source": _string_or_none(metadata.get("source")),
        "tags": tags,
        "summary": summary,
        "headings": headings,
        "outbound_links": _extract_wikilinks(content),
        "search_text": compact_inline_text(" ".join([title, summary, " ".join(tags), " ".join(headings)])),
    }


def build_machine_index(vault_path: Path) -> dict[str, Any]:
    pages: list[dict[str, Any]] = []
    root = content_root(vault_path)
    for page_type in PAGE_TYPE_ORDER:
        page_dir = root / page_type
        if not page_dir.exists():
            continue
        for md_path in sorted(page_dir.glob("*.md")):
            if is_index_excluded_file(md_path.name):
                continue
            try:
                pages.append(page_record(vault_path, md_path))
            except UnicodeDecodeError:
                continue

    page_paths = {page["path"] for page in pages}
    links: list[dict[str, object]] = []
    sources: dict[str, list[str]] = {}
    search: list[dict[str, object]] = []
    for page in pages:
        source = page.get("source")
        if isinstance(source, str) and source:
            sources.setdefault(source, []).append(page["path"])
        for target in page["outbound_links"]:
            target_path = _link_target_to_path(target, page_paths)
            links.append({"source": page["path"], "target": target, "target_path": target_path, "resolved": target_path is not None})
        search.append(
            {
                "path": page["path"],
                "title": page["title"],
                "type": page["type"],
                "tags": page["tags"],
                "summary": page["summary"],
                "search_text": page["search_text"],
            }
        )

    return {
        "schema_version": "machine_index.v1",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "pages": pages,
        "links": links,
        "sources": [{"source": key, "pages": value} for key, value in sorted(sources.items())],
        "search": search,
    }


def update_machine_index(vault_path: Path) -> None:
    payload = build_machine_index(vault_path)
    index_dir = machine_index_dir(vault_path)
    with vault_write_lock(vault_path):
        index_dir.mkdir(parents=True, exist_ok=True)
        _write_json(index_dir / "pages.json", {"schema_version": "machine_pages.v1", "pages": payload["pages"]})
        _write_json(index_dir / "links.json", {"schema_version": "machine_links.v1", "links": payload["links"]})
        _write_json(index_dir / "sources.json", {"schema_version": "machine_sources.v1", "sources": payload["sources"]})
        _write_json(index_dir / "search.json", {"schema_version": "machine_search.v1", "entries": payload["search"]})


def update_index(vault_path: Path) -> None:
    root = content_root(vault_path)
    root.mkdir(parents=True, exist_ok=True)
    index_path = root / "index.md"
    entries: dict[str, list[str]] = {name: [] for name in PAGE_TYPE_ORDER}

    for page_type in entries:
        page_dir = root / page_type
        if not page_dir.exists():
            continue
        for md_path in sorted(page_dir.glob("*.md")):
            if is_index_excluded_file(md_path.name):
                continue
            entries[page_type].append(index_entry(vault_path, md_path))

    index_lines = [
        "# Index",
        "",
        "Catalog of LLM-maintained wiki pages. Raw sources are excluded.",
        "Each entry is a compact routing record: link, type, status, updated time, tags, and one-line summary.",
        "",
    ]
    for page_type, links in entries.items():
        index_lines.extend([f"## {page_type}", ""])
        index_lines.extend(links or ["- No pages yet."])
        index_lines.append("")
    with vault_write_lock(vault_path):
        index_path.write_text("\n".join(index_lines).rstrip() + "\n", encoding="utf-8")
    update_machine_index(vault_path)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _extract_wikilinks(content: str) -> list[str]:
    links: list[str] = []
    for match in re.finditer(r"\[\[([^\]]+)\]\]", content):
        target = match.group(1).split("|", 1)[0].strip()
        if target:
            links.append(target)
    return sorted(set(links))


def _extract_headings(content: str) -> list[str]:
    headings: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        marker, _, title = stripped.partition(" ")
        if marker.startswith("#") and 1 <= len(marker) <= 6 and set(marker) == {"#"} and title.strip():
            headings.append(title.strip())
    return headings


def _link_target_to_path(target: str, page_paths: set[str]) -> str | None:
    normalized = target.strip().removesuffix(".md")
    candidates = {normalized, f"{normalized}.md"}
    if "/" not in normalized:
        candidates.update(path for path in page_paths if Path(path).stem == normalized)
    for candidate in candidates:
        if candidate in page_paths:
            return candidate
    return None


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def ensure_log(vault_path: Path) -> None:
    root = content_root(vault_path)
    root.mkdir(parents=True, exist_ok=True)
    log_path = root / "log.md"
    with vault_write_lock(vault_path):
        if not log_path.exists():
            log_path.write_text("# Log\n\nAppend-only operation log for ingest, query, and lint passes.\n", encoding="utf-8")


def append_ingest_log(
    vault_path: Path,
    draft: WikiDraft,
    result: VaultWriteResult,
    source_file: str | None,
    action: str = "create",
) -> None:
    ensure_log(vault_path)
    log_path = content_root(vault_path) / "log.md"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    source = source_file if source_file else "null"
    entry = (
        f"\n## {now}\n\n"
        f"- operation: ingest_source\n"
        f"- action: {action}\n"
        f"- source: {source}\n"
        f"- output: {wiki_link_for_path(vault_path, result.path, draft.title)}\n"
        f"- directory: {draft.page_dir}\n"
        f"- type: {draft.page_type}\n"
        f"- created: {str(result.created).lower()}\n"
        f"- content_hash: {result.content_hash}\n"
    )
    with vault_write_lock(vault_path):
        with log_path.open("a", encoding="utf-8") as file:
            file.write(entry)


def append_operation_log(vault_path: Path, message: str) -> None:
    ensure_log(vault_path)
    log_path = content_root(vault_path) / "log.md"
    with vault_write_lock(vault_path):
        with log_path.open("a", encoding="utf-8") as file:
            file.write(message.rstrip() + "\n")
