from __future__ import annotations

import json
import re
from hashlib import sha256
from datetime import datetime
from pathlib import Path
from typing import Any

from knoarbor.core.markdown import compact_inline_text, extract_heading, extract_section, extract_tags, parse_frontmatter
from knoarbor.core.schemas.page_identity import PageIdentity, normalize_facet
from knoarbor.core.schemas.wiki_write import VaultWriteResult, WikiDraft
from knoarbor.core.wiki_schema import (
    FRONTMATTER_TYPES,
    GENERATED_VIEW_DIR,
    INDEX_PAGE_DIRS,
    UNIFIED_KNOWLEDGE_PAGE_DIR,
    is_index_excluded_file,
)
from knoarbor.runtime import vault_write_lock
from knoarbor.storage.wiki_paths import content_relative_path, content_root, vault_relative_path


ALLOWED_PAGE_KINDS = {
    "concept",
    "entity",
    "workflow",
    "comparison",
    "timeline",
    "query",
    "note",
    "source_digest",
    "generated_view",
    "unknown",
}


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
        index_dir / "manifest.json",
        index_dir / "graph_index.json",
        index_dir / "pages.json",
        index_dir / "links.json",
        index_dir / "sources.json",
        index_dir / "search.json",
    ]
    if any(not path.exists() for path in index_files):
        return True
    index_mtime = min(path.stat().st_mtime for path in index_files)
    root = content_root(vault_path)
    for md_path in _iter_indexable_page_paths(root):
        if md_path.stat().st_mtime > index_mtime:
            return True
    return False


def ensure_machine_index(vault_path: Path) -> None:
    if is_machine_index_stale(vault_path):
        update_machine_index(vault_path)


def page_record(vault_path: Path, md_path: Path) -> dict[str, Any]:
    content = md_path.read_text(encoding="utf-8")
    metadata = parse_frontmatter(content)
    title = extract_heading(content, md_path.stem)
    tags = extract_tags(content, metadata) or _extract_entities(content)
    headings = _extract_headings(content)
    summary = compact_inline_text(extract_section(content, "Summary") or "")
    claims = extract_section(content, "Claims")
    relations = extract_section(content, "Relations")
    evidence = extract_section(content, "Evidence")
    entities = _extract_entities(content)
    directory = _page_directory(vault_path, md_path)
    identity = _page_identity(vault_path, md_path, metadata, title, tags, headings)
    return {
        "schema_version": "machine_page.v2",
        "path": relative_wiki_path(vault_path, md_path),
        "canonical_path": identity.canonical_path,
        "legacy_paths": identity.legacy_paths,
        "directory": directory,
        "page_kind": identity.page_kind,
        "subject_kind": identity.subject_kind,
        "role": identity.role,
        "facets": identity.facets,
        "atom_ids": identity.atom_ids,
        "relation_ids": identity.relation_ids,
        "source_digest_ids": identity.source_digest_ids,
        "title": title,
        "type": str(metadata.get("type") or FRONTMATTER_TYPES.get(directory, "page")),
        "status": str(metadata.get("status") or "unknown"),
        "created": _string_or_none(metadata.get("created")),
        "updated": _string_or_none(metadata.get("updated") or metadata.get("created")),
        "source": _string_or_none(metadata.get("source")),
        "tags": tags,
        "entities": entities,
        "summary": summary,
        "headings": headings,
        "claims": _extract_claim_ids(claims),
        "relations": _extract_relation_rows(relations),
        "evidence": _extract_evidence_rows(evidence),
        "outbound_links": _extract_wikilinks(content),
        "search_text": compact_inline_text(" ".join([title, summary, " ".join(tags), " ".join(entities), claims, relations, " ".join(headings)])),
    }


def build_machine_index(vault_path: Path) -> dict[str, Any]:
    pages: list[dict[str, Any]] = []
    root = content_root(vault_path)
    for md_path in _iter_indexable_page_paths(root):
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
                "canonical_path": page["canonical_path"],
                "legacy_paths": page["legacy_paths"],
                "title": page["title"],
                "type": page["type"],
                "page_kind": page["page_kind"],
                "role": page["role"],
                "facets": page["facets"],
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


def build_graph_index(vault_path: Path, pages: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    records = pages if pages is not None else build_machine_index(vault_path)["pages"]
    node_map: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, str]] = []
    source_map: dict[str, dict[str, Any]] = {}

    for page in records:
        path = str(page.get("path") or "")
        title = str(page.get("title") or Path(path).stem)
        summary = str(page.get("summary") or "")
        role = str(page.get("role") or "")
        entities = [str(item).strip() for item in page.get("entities", []) if str(item).strip()] if isinstance(page.get("entities"), list) else []

        for entity in entities:
            _upsert_node(node_map, entity, path, summary)

        relations = page.get("relations") if isinstance(page.get("relations"), list) else []
        for relation in relations:
            if not isinstance(relation, dict):
                continue
            source = str(relation.get("subject") or "").strip()
            predicate = str(relation.get("predicate") or "").strip()
            target = str(relation.get("object") or "").strip()
            claim = str(relation.get("claim") or "").strip()
            if not source or not predicate or not target:
                continue
            _upsert_node(node_map, source, path, summary)
            _upsert_node(node_map, target, path, "")
            edges.append({"source": source, "predicate": predicate, "target": target, "page": path, "claim": claim})

        evidence = page.get("evidence") if isinstance(page.get("evidence"), list) else []
        if role == "source_digest":
            raw = _first_evidence_source(evidence) or _string_or_none(page.get("source")) or ""
            source_entry = source_map.setdefault(path, {"source": path, "raw": raw, "pages": []})
            if raw and not source_entry.get("raw"):
                source_entry["raw"] = raw
            continue

        for row in evidence:
            if not isinstance(row, dict):
                continue
            source_path = str(row.get("source") or "").strip()
            if not source_path:
                continue
            entry = source_map.setdefault(source_path, {"source": source_path, "raw": "", "pages": []})
            if path and path not in entry["pages"]:
                entry["pages"].append(path)

        if not entities and title:
            _upsert_node(node_map, title, path, summary)

    return {
        "schema_version": "knoarbor_graph_index.v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "nodes": sorted(node_map.values(), key=lambda item: str(item["id"]).lower()),
        "edges": sorted(edges, key=lambda item: (item["source"].lower(), item["predicate"].lower(), item["target"].lower(), item["page"])),
        "sources": sorted(source_map.values(), key=lambda item: str(item["source"]).lower()),
    }


def build_index_manifest(vault_path: Path, graph_index: dict[str, Any], pages: list[dict[str, Any]]) -> dict[str, Any]:
    graph_bytes = _json_bytes(graph_index)
    return {
        "schema_version": "knoarbor_index.v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "vault_path": str(vault_path.expanduser().resolve()),
        "wiki_hash": _wiki_content_hash(vault_path),
        "graph_index_hash": sha256(graph_bytes).hexdigest(),
        "page_count": len([page for page in pages if page.get("role") == "knowledge_page"]),
        "source_count": len(graph_index.get("sources", [])) if isinstance(graph_index.get("sources"), list) else 0,
        "node_count": len(graph_index.get("nodes", [])) if isinstance(graph_index.get("nodes"), list) else 0,
        "edge_count": len(graph_index.get("edges", [])) if isinstance(graph_index.get("edges"), list) else 0,
    }


def update_machine_index(vault_path: Path) -> None:
    payload = build_machine_index(vault_path)
    graph_index = build_graph_index(vault_path, payload["pages"])
    manifest = build_index_manifest(vault_path, graph_index, payload["pages"])
    index_dir = machine_index_dir(vault_path)
    with vault_write_lock(vault_path):
        index_dir.mkdir(parents=True, exist_ok=True)
        _write_json(index_dir / "manifest.json", manifest)
        _write_json(index_dir / "graph_index.json", graph_index)
        _write_json(index_dir / "pages.json", {"schema_version": "machine_pages.v2", "pages": payload["pages"]})
        _write_json(index_dir / "links.json", {"schema_version": "machine_links.v1", "links": payload["links"]})
        _write_json(index_dir / "sources.json", {"schema_version": "machine_sources.v1", "sources": payload["sources"]})
        _write_json(index_dir / "search.json", {"schema_version": "machine_search.v1", "entries": payload["search"]})


def update_index(vault_path: Path) -> None:
    root = content_root(vault_path)
    root.mkdir(parents=True, exist_ok=True)
    entries: dict[str, list[str]] = {UNIFIED_KNOWLEDGE_PAGE_DIR: []}
    entries.update({name: [] for name in INDEX_PAGE_DIRS})
    indexable_paths = _iter_indexable_page_paths(root)
    page_records = _page_records_for_views(vault_path, indexable_paths)

    for md_path in indexable_paths:
        entries[_page_directory(vault_path, md_path)].append(index_entry(vault_path, md_path))

    with vault_write_lock(vault_path):
        _write_generated_views(root, page_records)
    update_machine_index(vault_path)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _extract_entities(content: str) -> list[str]:
    entities: list[str] = []
    for line in extract_section(content, "Entities").splitlines():
        if not line.startswith("- "):
            continue
        text = line[2:].strip()
        if not text or text.startswith("暂无"):
            continue
        text = text.removeprefix("[[").removesuffix("]]")
        if "|" in text:
            text = text.split("|", 1)[-1]
        if text and text not in entities:
            entities.append(text)
    return entities[:24]


def _extract_claim_ids(section: str) -> list[str]:
    claims: list[str] = []
    for line in section.splitlines():
        match = re.match(r"\s*-\s*(C\d+)\s*[:：.]\s+", line.strip(), flags=re.IGNORECASE)
        if match:
            claim_id = match.group(1).upper()
            if claim_id not in claims:
                claims.append(claim_id)
    return claims


def _extract_relation_rows(section: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for cells in _markdown_table_rows(section):
        if len(cells) < 4:
            continue
        subject, predicate, obj, claim = cells[:4]
        if subject.lower() == "subject" or not subject or not predicate or not obj:
            continue
        rows.append(
            {
                "subject": _clean_graph_object(subject),
                "predicate": predicate.strip(),
                "object": _clean_graph_object(obj),
                "claim": claim.strip().upper(),
            }
        )
    return rows


def _extract_evidence_rows(section: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for cells in _markdown_table_rows(section):
        if len(cells) < 5:
            continue
        claim, source, source_range, basis, confidence = cells[:5]
        if claim.lower() == "claim" or not claim:
            continue
        rows.append(
            {
                "claim": claim.strip().upper(),
                "source": source.strip(),
                "range": source_range.strip(),
                "basis": basis.strip(),
                "confidence": confidence.strip().lower(),
            }
        )
    return rows


def _markdown_table_rows(section: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if cells and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        rows.append(cells)
    return rows


def _clean_graph_object(value: str) -> str:
    text = value.strip()
    if text.startswith("[[") and text.endswith("]]"):
        text = text[2:-2]
    if "|" in text:
        text = text.split("|", 1)[-1]
    return text.strip()


def _upsert_node(node_map: dict[str, dict[str, Any]], node_id: str, page: str, summary: str) -> None:
    clean_id = _clean_graph_object(node_id)
    if not clean_id:
        return
    node = node_map.setdefault(clean_id, {"id": clean_id, "pages": [], "aliases": [], "summary": ""})
    if page and page not in node["pages"]:
        node["pages"].append(page)
    if summary and not node["summary"]:
        node["summary"] = compact_inline_text(summary, 180)


def _first_evidence_source(evidence: object) -> str:
    if not isinstance(evidence, list):
        return ""
    for row in evidence:
        if isinstance(row, dict) and row.get("source"):
            return str(row["source"]).strip()
    return ""


def _wiki_content_hash(vault_path: Path) -> str:
    root = content_root(vault_path)
    digest = sha256()
    for md_path in _iter_indexable_page_paths(root):
        relative = md_path.resolve().relative_to(root.resolve()).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(md_path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _page_records_for_views(vault_path: Path, paths: list[Path]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for md_path in paths:
        try:
            records.append(page_record(vault_path, md_path))
        except UnicodeDecodeError:
            continue
    return records


def _write_generated_views(root: Path, records: list[dict[str, Any]]) -> None:
    views = {
        "Home.md": _render_home_view(records),
        "Concepts.md": _render_kind_view("Concepts", records, {"concept"}),
        "Entities.md": _render_kind_view("Entities", records, {"entity"}),
        "Workflows.md": _render_kind_view("Workflows", records, {"workflow"}),
        "Comparisons.md": _render_kind_view("Comparisons", records, {"comparison"}),
        "Open-Questions.md": _render_open_questions_view(records),
        "Source-Audit.md": _render_source_audit_view(records),
    }
    views_dir = root / GENERATED_VIEW_DIR
    views_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in views.items():
        (views_dir / filename).write_text(content.rstrip() + "\n", encoding="utf-8")


def _render_home_view(records: list[dict[str, Any]]) -> str:
    counts = {
        "knowledge pages": sum(1 for record in records if record.get("role") == "knowledge_page"),
        "source digests": sum(1 for record in records if record.get("role") == "source_digest"),
        "concepts": sum(1 for record in records if record.get("page_kind") == "concept"),
        "entities": sum(1 for record in records if record.get("page_kind") == "entity"),
        "workflows": sum(1 for record in records if record.get("page_kind") == "workflow"),
        "comparisons": sum(1 for record in records if record.get("page_kind") == "comparison"),
    }
    lines = [
        "# Home",
        "",
        *_view_frontmatter("Home", ["generated_view", "home"]),
        "## Overview",
        "",
        "Generated navigation view for this KnoArbor vault. It is rebuilt from maintained wiki pages.",
        "",
        "## Views",
        "",
        "- [[_views/Concepts|Concepts]]",
        "- [[_views/Entities|Entities]]",
        "- [[_views/Workflows|Workflows]]",
        "- [[_views/Comparisons|Comparisons]]",
        "- [[_views/Open-Questions|Open Questions]]",
        "- [[_views/Source-Audit|Source Audit]]",
        "",
        "## Counts",
        "",
    ]
    lines.extend(f"- {name}: {count}" for name, count in counts.items())
    lines.extend(["", "## Recent Pages", "", *_record_links(records[:20])])
    return "\n".join(lines)


def _render_kind_view(title: str, records: list[dict[str, Any]], page_kinds: set[str]) -> str:
    selected = [record for record in records if str(record.get("page_kind") or "") in page_kinds and record.get("role") == "knowledge_page"]
    lines = [
        f"# {title}",
        "",
        *_view_frontmatter(title, ["generated_view", *sorted(page_kinds)]),
        "## Pages",
        "",
        *_record_links(selected),
    ]
    return "\n".join(lines)


def _render_open_questions_view(records: list[dict[str, Any]]) -> str:
    selected = [
        record
        for record in records
        if record.get("page_kind") == "query" or "open_questions" in set(record.get("facets", []))
    ]
    lines = [
        "# Open Questions",
        "",
        *_view_frontmatter("Open Questions", ["generated_view", "open_questions"]),
        "## Pages",
        "",
        *_record_links(selected),
    ]
    return "\n".join(lines)


def _render_source_audit_view(records: list[dict[str, Any]]) -> str:
    selected = [record for record in records if record.get("role") == "source_digest" or record.get("page_kind") == "source_digest"]
    lines = [
        "# Source Audit",
        "",
        *_view_frontmatter("Source Audit", ["generated_view", "source_audit"]),
        "## Source Digests",
        "",
        *_record_links(selected),
    ]
    return "\n".join(lines)


def _view_frontmatter(title: str, facets: list[str]) -> list[str]:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return [
        "---",
        f"created: {now}",
        f"updated: {now}",
        "type: view",
        "status: generated",
        f"canonical_path: {GENERATED_VIEW_DIR}/{title.replace(' ', '-')}.md",
        "page_kind: generated_view",
        "role: generated_view",
        f"facets: {_yaml_list(facets)}",
        "---",
        "",
    ]


def _record_links(records: list[dict[str, Any]]) -> list[str]:
    if not records:
        return ["- No pages yet."]
    lines: list[str] = []
    for record in sorted(records, key=lambda item: (str(item.get("page_kind") or ""), str(item.get("title") or ""))):
        path = str(record.get("path") or "")
        title = str(record.get("title") or Path(path).stem)
        summary = compact_inline_text(str(record.get("summary") or "No summary."), 160)
        link_path = path.removesuffix(".md")
        lines.append(f"- [[{link_path}|{title}]] — {summary}")
    return lines


def _yaml_list(values: list[str]) -> str:
    normalized: list[str] = []
    for value in values:
        text = normalize_facet(value)
        if text and text not in normalized:
            normalized.append(text)
    return "[" + ", ".join(f'"{value}"' for value in normalized) + "]"


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


def _iter_indexable_page_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    for md_path in sorted(root.glob("*.md")):
        if not is_index_excluded_file(md_path.name):
            paths.append(md_path)
    for page_type in INDEX_PAGE_DIRS:
        page_dir = root / page_type
        if not page_dir.exists():
            continue
        for md_path in sorted(page_dir.glob("*.md")):
            if not is_index_excluded_file(md_path.name):
                paths.append(md_path)
    return paths


def _page_directory(vault_path: Path, md_path: Path) -> str:
    root = content_root(vault_path)
    if md_path.parent.resolve() == root.resolve():
        return UNIFIED_KNOWLEDGE_PAGE_DIR
    return md_path.parent.name


def _page_identity(
    vault_path: Path,
    md_path: Path,
    metadata: dict[str, str],
    title: str,
    tags: list[str],
    headings: list[str],
) -> PageIdentity:
    relative_path = relative_wiki_path(vault_path, md_path)
    directory = _page_directory(vault_path, md_path)
    page_kind = _infer_page_kind(metadata, directory)
    role = _infer_page_role(directory, page_kind)
    canonical_path = metadata.get("canonical_path") or relative_path
    legacy_paths = _metadata_list(metadata.get("legacy_paths"))
    if canonical_path != relative_path:
        legacy_paths.append(relative_path)
    facets = _identity_facets(metadata, directory, page_kind, tags, headings)
    return PageIdentity(
        canonical_path=canonical_path,
        legacy_paths=legacy_paths,
        title=title,
        page_kind=page_kind,
        subject_kind=metadata.get("subject_kind", ""),
        role=role,
        facets=facets,
        atom_ids=_metadata_list(metadata.get("atom_ids")) + _metadata_list(metadata.get("claim_ids")),
        relation_ids=_metadata_list(metadata.get("relation_ids")),
        source_digest_ids=_metadata_list(metadata.get("source_digest_ids")),
    )


def _infer_page_role(directory: str, page_kind: str) -> str:
    if directory == "sources" or page_kind == "source_digest":
        return "source_digest"
    if directory == GENERATED_VIEW_DIR or page_kind == "generated_view":
        return "generated_view"
    return "knowledge_page"


def _infer_page_kind(metadata: dict[str, str], directory: str) -> str:
    explicit = metadata.get("page_kind") or metadata.get("kind")
    if explicit:
        return _normalize_page_kind(explicit)
    legacy_type = metadata.get("type") or FRONTMATTER_TYPES.get(directory, "unknown")
    if directory == "sources" or legacy_type == "source":
        return "source_digest"
    if directory == UNIFIED_KNOWLEDGE_PAGE_DIR and legacy_type == "page":
        return "unknown"
    return _normalize_page_kind(legacy_type)


def _normalize_page_kind(value: str) -> str:
    normalized = normalize_facet(value)
    aliases = {
        "source": "source_digest",
        "digest": "source_digest",
        "view": "generated_view",
        "question": "query",
        "qa": "query",
        "q_a": "query",
        "page": "unknown",
    }
    normalized = aliases.get(normalized, normalized or "unknown")
    return normalized if normalized in ALLOWED_PAGE_KINDS else "unknown"


def _identity_facets(metadata: dict[str, str], directory: str, page_kind: str, tags: list[str], headings: list[str]) -> list[str]:
    section_facets = {
        "Claims": "claims",
        "Relations": "relations",
        "Synthesis": "synthesis",
        "Definition": "definition",
        "Key Points": "key_points",
        "Source Focus": "source_focus",
    }
    values: list[str] = []
    values.extend(_metadata_list(metadata.get("facets")))
    values.extend(_metadata_list(metadata.get("entities")))
    values.extend(_metadata_list(metadata.get("concepts")))
    values.extend(tags)
    values.extend([directory, page_kind])
    values.extend(facet for heading, facet in section_facets.items() if heading in headings)
    return values


def _metadata_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("[") and text.endswith("]"):
            text = text[1:-1]
        return [item.strip().strip("'\"") for item in text.split(",") if item.strip().strip("'\"")]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


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
