from __future__ import annotations

import json
import re
import shutil
from hashlib import sha256
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from knoarbor.core.markdown import compact_inline_text, extract_heading, extract_section, inline_text, parse_frontmatter, wikilink_display_text
from knoarbor.core.schemas.page_identity import PageIdentity
from knoarbor.core.wiki_schema import UNIFIED_KNOWLEDGE_PAGE_DIR, is_index_excluded_file
from knoarbor.runtime import vault_write_lock
from knoarbor.storage.index_snapshot import (
    IndexSnapshot,
    canonical_index_json,
    index_generation_id,
    open_index_generation,
    open_index_snapshot,
)
from knoarbor.storage.entity_registry import read_entity_registry
from knoarbor.storage.knowledge_atom_index import read_knowledge_atom_records
from knoarbor.storage.lexical_snapshot import build_lexical_snapshot
from knoarbor.storage.source_records import read_raw_evidence_records
from knoarbor.storage.vault_identity import ensure_vault_identity
from knoarbor.storage.vault_layout import runtime_index_root, wiki_root
from knoarbor.storage.wiki_paths import SOURCE_RECORD_ROOT_DIR, content_relative_path, content_root, source_record_root, vault_relative_path


def relative_wiki_path(vault_path: Path, path: Path) -> str:
    try:
        return content_relative_path(vault_path, path)
    except ValueError:
        return vault_relative_path(vault_path, path)


def wiki_link_for_path(vault_path: Path, md_path: Path, title: str | None = None) -> str:
    link_path = Path(relative_wiki_path(vault_path, md_path)).with_suffix("").as_posix()
    if title:
        return f"[[{link_path}|{title}]]"
    return f"[[{link_path}]]"


def index_entry(vault_path: Path, md_path: Path) -> str:
    link_path = Path(relative_wiki_path(vault_path, md_path)).with_suffix("").as_posix()
    fallback_title = md_path.stem

    try:
        content = md_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"- [[{link_path}|{fallback_title}]] — unreadable file"

    metadata = parse_frontmatter(content)
    title = extract_heading(content, fallback_title)
    role = metadata.get("role") or "knowledge_page"
    updated = metadata.get("updated") or metadata.get("created") or "unknown"
    summary = compact_inline_text(extract_section(content, "Summary") or "No summary yet.")

    return (
        f"- [[{link_path}|{title}]] — role: {role} | "
        f"updated: {updated} | summary: {summary}"
    )


def machine_index_dir(vault_path: Path) -> Path:
    snapshot = open_index_snapshot(vault_path)
    return snapshot.path if snapshot else runtime_index_root(vault_path) / "generations" / "missing"


def is_machine_index_stale(vault_path: Path) -> bool:
    snapshot = open_index_snapshot(vault_path)
    if snapshot is None:
        return True
    return str(snapshot.manifest.get("wiki_hash") or "") != wiki_tree_fingerprint(vault_path)


def ensure_machine_index(vault_path: Path) -> bool:
    """Report index freshness without mutating a read path.

    Readers may use an existing stale index as a locator, while raw-grounded
    retrieval reads committed revisions directly. Reconciliation is owned by
    the operation or the bounded startup scan, never by this read path.
    """

    return not is_machine_index_stale(vault_path.expanduser().resolve())


def page_record(vault_path: Path, md_path: Path) -> dict[str, Any]:
    content = md_path.read_text(encoding="utf-8")
    metadata = parse_frontmatter(content)
    title = extract_heading(content, md_path.stem)
    headings = _extract_headings(content)
    summary = inline_text(extract_section(content, "Summary") or "")
    raw_source_body = extract_section(content, "Raw Source")
    source = _extract_first_source_item(raw_source_body) if raw_source_body else None
    claims = extract_section(content, "Claims")
    relations = extract_section(content, "Relations")
    evidence = extract_section(content, "Evidence")
    evidence_rows = _extract_evidence_rows(evidence)
    if not source:
        source = _first_evidence_source(evidence_rows)
    entities = _extract_entities(content)
    directory = _page_directory(vault_path, md_path)
    identity = _page_identity(vault_path, md_path, metadata, title, headings)
    return {
        "schema_version": "machine_page.v2",
        "path": relative_wiki_path(vault_path, md_path),
        "canonical_path": identity.canonical_path,
        "directory": directory,
        "subject_kind": identity.subject_kind,
        "role": identity.role,
        "atom_ids": identity.atom_ids,
        "relation_ids": identity.relation_ids,
        "source_record_ids": identity.source_record_ids,
        "title": title,
        "created": _string_or_none(metadata.get("created")),
        "updated": _string_or_none(metadata.get("updated") or metadata.get("created")),
        "entities": entities,
        "summary": summary,
        "headings": headings,
        "claims": _extract_claim_ids(claims),
        "relations": _extract_relation_rows(relations),
        "evidence": evidence_rows,
        "outbound_links": _extract_wikilinks(content),
        "source": source,
        "search_text": inline_text(" ".join([title, summary, " ".join(entities), claims, relations, " ".join(headings)])),
        "body": _markdown_body(content),
    }


def build_machine_index(vault_path: Path) -> dict[str, Any]:
    pages = read_wiki_page_records(vault_path)

    page_paths = {page["path"] for page in pages}
    page_targets: dict[str, set[str]] = {}
    for page in pages:
        for value in (page.get("path"), page.get("canonical_path"), page.get("title"), Path(str(page.get("path") or "")).stem):
            key = _link_key(str(value or ""))
            if key:
                page_targets.setdefault(key, set()).add(str(page["path"]))
    links: list[dict[str, object]] = []
    sources: dict[str, list[str]] = {}
    search: list[dict[str, object]] = []
    for page in pages:
        source = page.get("source")
        if isinstance(source, str) and source:
            sources.setdefault(source, []).append(page["path"])
        for target in page["outbound_links"]:
            target_path = _link_target_to_path(target, page_paths, page_targets)
            links.append({"source": page["path"], "target": target, "target_path": target_path, "resolved": target_path is not None})
        search.append(
            {
                "path": page["path"],
                "canonical_path": page["canonical_path"],
                "title": page["title"],
                "role": page["role"],
                "summary": page["summary"],
                "search_text": page["search_text"],
            }
        )

    return {
        "schema_version": "machine_index.v1",
        "pages": pages,
        "links": links,
        "sources": [{"source": key, "pages": value} for key, value in sorted(sources.items())],
        "search": search,
    }


def read_wiki_page_records(vault_path: Path) -> list[dict[str, Any]]:
    """Read current page identities from authoritative local Markdown files."""

    pages: list[dict[str, Any]] = []
    for md_path in _iter_indexable_page_paths(content_root(vault_path)):
        try:
            pages.append(page_record(vault_path, md_path))
        except UnicodeDecodeError:
            continue
    return pages


def build_graph_index(vault_path: Path, pages: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    records = pages if pages is not None else build_machine_index(vault_path)["pages"]
    node_map: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, str]] = []
    source_map: dict[str, dict[str, Any]] = {}

    indexed_paths = _add_atom_graph(vault_path, node_map, edges)

    for page in records:
        path = str(page.get("path") or "")
        title = str(page.get("title") or Path(path).stem)
        summary = str(page.get("summary") or "")
        role = str(page.get("role") or "")
        entities = [str(item).strip() for item in page.get("entities", []) if str(item).strip()] if isinstance(page.get("entities"), list) else []

        if path not in indexed_paths:
            for entity in entities:
                _upsert_node(node_map, entity, entity, path, summary)

        relations = page.get("relations") if isinstance(page.get("relations"), list) else []
        if path not in indexed_paths:
            for relation in relations:
                if not isinstance(relation, dict):
                    continue
                source = str(relation.get("subject") or "").strip()
                predicate = str(relation.get("predicate") or "").strip()
                target = str(relation.get("object") or "").strip()
                claim = str(relation.get("claim") or "").strip()
                if not source or not predicate or not target:
                    continue
                _upsert_node(node_map, source, source, path, summary)
                _upsert_node(node_map, target, target, path, "")
                edges.append({"source": source, "predicate": predicate, "target": target, "page": path, "claim": claim})

        evidence = page.get("evidence") if isinstance(page.get("evidence"), list) else []
        if role == "source_record":
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

        if path not in indexed_paths and not entities and title:
            _upsert_node(node_map, title, title, path, summary)

    return {
        "schema_version": "knoarbor_graph_index.v1",
        "nodes": sorted(node_map.values(), key=lambda item: str(item["id"]).lower()),
        "edges": sorted(edges, key=lambda item: (item["source"].lower(), item["predicate"].lower(), item["target"].lower(), item["page"])),
        "sources": sorted(source_map.values(), key=lambda item: str(item["source"]).lower()),
    }


def build_index_manifest(vault_path: Path, graph_index: dict[str, Any], pages: list[dict[str, Any]]) -> dict[str, Any]:
    graph_bytes = canonical_index_json(graph_index)
    return {
        "schema_version": "knoarbor_index.v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "vault_path": str(vault_path.expanduser().resolve()),
        "wiki_hash": wiki_tree_fingerprint(vault_path),
        "graph_index_hash": sha256(graph_bytes).hexdigest(),
        "page_count": len([page for page in pages if page.get("role") == "knowledge_page"]),
        "source_count": len(graph_index.get("sources", [])) if isinstance(graph_index.get("sources"), list) else 0,
        "node_count": len(graph_index.get("nodes", [])) if isinstance(graph_index.get("nodes"), list) else 0,
        "edge_count": len(graph_index.get("edges", [])) if isinstance(graph_index.get("edges"), list) else 0,
    }


def prepare_machine_index(vault_path: Path, *, target_generation: str | None = None) -> IndexSnapshot:
    ensure_vault_identity(vault_path)
    root = runtime_index_root(vault_path)
    payload = build_machine_index(vault_path)
    graph_index = build_graph_index(vault_path, payload["pages"])
    manifest = build_index_manifest(vault_path, graph_index, payload["pages"])
    staging = root / ".staging" / uuid4().hex
    staging.mkdir(parents=True, exist_ok=False)
    try:
        active_fact_generation = target_generation or "sha256:empty"
        artifacts = {
            "graph_index.json": graph_index,
            "pages.json": {"schema_version": "machine_pages.v2", "pages": payload["pages"]},
            "links.json": {"schema_version": "machine_links.v1", "links": payload["links"]},
            "sources.json": {"schema_version": "machine_sources.v1", "sources": payload["sources"]},
            "search.json": {"schema_version": "machine_search.v1", "entries": payload["search"]},
        }
        for name, artifact in artifacts.items():
            _write_json(staging / name, artifact)
        retrieval_metadata = build_lexical_snapshot(
            vault_path,
            staging / "retrieval.sqlite",
            fact_generation=active_fact_generation,
            atom_records=read_knowledge_atom_records(vault_path),
            raw_records=read_raw_evidence_records(vault_path),
        )
        files = {
            name: sha256((staging / name).read_bytes()).hexdigest()
            for name in sorted([*artifacts, "retrieval.sqlite"])
        }
        navigation_generation_id = sha256(
            canonical_index_json({name: files[name] for name in sorted(artifacts)})
        ).hexdigest()
        retrieval_generation_id = sha256(
            canonical_index_json(
                {
                    "artifact_hash": files["retrieval.sqlite"],
                    "active_fact_generation": active_fact_generation,
                    "schema_version": retrieval_metadata["schema_version"],
                }
            )
        ).hexdigest()
        identity_manifest = {
            **manifest,
            "identity_schema": "index_generation_identity.v4",
            "navigation_generation_id": navigation_generation_id,
            "retrieval_generation_id": retrieval_generation_id,
            "active_fact_generation": active_fact_generation,
            "files": files,
        }
        generation_id = index_generation_id(identity_manifest)
        complete_manifest = {**identity_manifest, "generation_id": generation_id}
        _write_json(staging / "manifest.json", complete_manifest)
        target = root / "generations" / generation_id
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            try:
                open_index_generation(vault_path, generation_id)
            except RuntimeError:
                shutil.rmtree(target)
                staging.replace(target)
            else:
                shutil.rmtree(staging, ignore_errors=True)
        else:
            staging.replace(target)
        return IndexSnapshot(generation_id=generation_id, path=target, manifest=complete_manifest)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _publish_machine_index(vault_path: Path, snapshot: IndexSnapshot) -> None:
    root = runtime_index_root(vault_path)
    if snapshot.path.parent != root / "generations":
        raise RuntimeError("Machine index snapshot belongs to a different vault.")
    verified = open_index_generation(vault_path, snapshot.generation_id)
    if verified.path != snapshot.path:
        raise RuntimeError("Machine index snapshot path does not match its verified generation.")
    _write_current(root, snapshot.generation_id)


def _discard_machine_index(vault_path: Path, snapshot: IndexSnapshot) -> None:
    root = runtime_index_root(vault_path)
    if snapshot.path.parent != root / "generations":
        raise RuntimeError("Machine index snapshot belongs to a different vault.")
    current = open_index_snapshot(vault_path)
    if current is None or current.generation_id != snapshot.generation_id:
        shutil.rmtree(snapshot.path, ignore_errors=True)


def _prune_index_generations(vault_path: Path, *, protected: set[str]) -> list[str]:
    generations = runtime_index_root(vault_path) / "generations"
    if not generations.is_dir():
        return []
    removed: list[str] = []
    for path in sorted(generations.iterdir(), key=lambda item: item.name):
        if path.name in protected or not path.is_dir() or path.is_symlink():
            continue
        shutil.rmtree(path)
        removed.append(path.name)
    return removed


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _write_current(root: Path, generation_id: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    temporary = root / f".CURRENT.{uuid4().hex}.tmp"
    temporary.write_text(generation_id + "\n", encoding="utf-8")
    temporary.replace(root / "CURRENT")


def _markdown_body(content: str) -> str:
    if not content.startswith("---\n"):
        return content
    boundary = content.find("\n---\n", 4)
    return content[boundary + 5 :] if boundary >= 0 else content


def _extract_entities(content: str) -> list[str]:
    entities: list[str] = []
    for line in extract_section(content, "Entities").splitlines():
        if not line.startswith("- "):
            continue
        text = line[2:].strip()
        if not text or text.startswith("暂无"):
            continue
        text = wikilink_display_text(text)
        if text and text not in entities:
            entities.append(text)
    return entities


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
    return wikilink_display_text(value)


def _add_atom_graph(vault_path: Path, node_map: dict[str, dict[str, Any]], edges: list[dict[str, str]]) -> set[str]:
    """Populate ingest-backed graph records from resolved entity ids."""

    registry = {entry.entity_id: entry for entry in read_entity_registry(vault_path).entries}
    records = read_knowledge_atom_records(vault_path)
    indexed_paths: set[str] = set()
    labels: dict[str, str] = {}
    for record in records:
        if record.atom_type != "entity" or not record.atom_id.startswith("ent:"):
            continue
        entry = registry.get(record.atom_id)
        label = entry.canonical_name if entry else record.text
        aliases = entry.aliases if entry else []
        labels[record.atom_id] = label
        for path in record.page_paths:
            indexed_paths.add(path)
            _upsert_node(node_map, record.atom_id, label, path, "", aliases=aliases)
    for record in records:
        if record.atom_type != "relation":
            continue
        payload = record.payload
        subject = payload.get("subject") if isinstance(payload, dict) else None
        obj = payload.get("object") if isinstance(payload, dict) else None
        if not isinstance(subject, dict) or not isinstance(obj, dict):
            continue
        source = str(subject.get("atom_id") or "").strip()
        target = str(obj.get("atom_id") or "").strip()
        predicate = str(payload.get("predicate") or "").strip()
        if not source.startswith("ent:") or not target.startswith("ent:") or not predicate:
            continue
        source_label = labels.get(source, str(subject.get("name") or source))
        target_label = labels.get(target, str(obj.get("name") or target))
        for path in record.page_paths:
            indexed_paths.add(path)
            _upsert_node(node_map, source, source_label, path, "")
            _upsert_node(node_map, target, target_label, path, "")
            edges.append(
                {
                    "source": source,
                    "predicate": predicate,
                    "target": target,
                    "page": path,
                    "claim": str(payload.get("source_claim_ids", [""])[0] if isinstance(payload.get("source_claim_ids"), list) else ""),
                    "source_label": source_label,
                    "target_label": target_label,
                }
            )
    return indexed_paths


def _upsert_node(
    node_map: dict[str, dict[str, Any]],
    node_id: str,
    label: str,
    page: str,
    summary: str,
    *,
    aliases: list[str] | None = None,
) -> None:
    clean_id = _clean_graph_object(node_id)
    if not clean_id:
        return
    node = node_map.setdefault(clean_id, {"id": clean_id, "label": label, "pages": [], "aliases": [], "summary": ""})
    if label and not node.get("label"):
        node["label"] = label
    for alias in aliases or []:
        if alias and alias not in node["aliases"]:
            node["aliases"].append(alias)
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


def wiki_tree_fingerprint(vault_path: Path) -> str:
    root = content_root(vault_path)
    digest = sha256()
    for md_path in _iter_indexable_page_paths(root):
        relative = relative_wiki_path(vault_path, md_path)
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(md_path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


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


def _extract_first_source_item(source_text: str) -> str | None:
    """Extract the first raw source reference from a raw source trace section."""
    for line in source_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            value = stripped[2:].strip()
            if value.lower().startswith("raw source:"):
                value = value.split(":", 1)[1].strip()
            return value
    first_line = source_text.strip().split("\n")[0].strip()
    if first_line.lower().startswith("raw source:"):
        first_line = first_line.split(":", 1)[1].strip()
    return first_line if first_line else None


def _iter_indexable_page_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    seen: set[Path] = set()
    if root.name == "pages" and root.parent.name == "wiki":
        vault = root.parent.parent
    elif root.name == "pages":
        vault = root.parent
    else:
        vault = root
    source_root = source_record_root(vault)
    def add_path(md_path: Path) -> None:
        if not is_index_excluded_file(md_path.name):
            resolved = md_path.resolve()
            if resolved in seen:
                return
            seen.add(resolved)
            paths.append(md_path)

    for md_path in sorted(root.glob("*.md")):
        add_path(md_path)
    if source_root.exists():
        for md_path in sorted(source_root.glob("*.md")):
            add_path(md_path)
    return paths


def _page_directory(vault_path: Path, md_path: Path) -> str:
    root = content_root(vault_path)
    try:
        md_path.resolve().relative_to(source_record_root(vault_path).resolve())
        return SOURCE_RECORD_ROOT_DIR
    except ValueError:
        pass
    if md_path.parent.resolve() == root.resolve():
        return UNIFIED_KNOWLEDGE_PAGE_DIR
    return md_path.parent.name


def _page_identity(
    vault_path: Path,
    md_path: Path,
    metadata: dict[str, str],
    title: str,
    headings: list[str],
) -> PageIdentity:
    relative_path = relative_wiki_path(vault_path, md_path)
    directory = _page_directory(vault_path, md_path)
    role = _infer_page_role(directory)
    canonical_path = relative_path
    return PageIdentity(
        canonical_path=canonical_path,
        title=title,
        subject_kind=metadata.get("subject_kind", ""),
        role=role,
        atom_ids=_metadata_list(metadata.get("atom_ids")) + _metadata_list(metadata.get("claim_ids")),
        relation_ids=_metadata_list(metadata.get("relation_ids")),
        source_record_ids=_metadata_list(metadata.get("source_record_ids")),
    )


def _infer_page_role(directory: str) -> str:
    if directory == "sources":
        return "source_record"
    return "knowledge_page"


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


def _link_target_to_path(target: str, page_paths: set[str], page_targets: dict[str, set[str]]) -> str | None:
    normalized = target.strip().removesuffix(".md")
    candidates = {normalized, f"{normalized}.md"}
    if "/" not in normalized:
        candidates.update(path for path in page_paths if Path(path).stem == normalized)
    for candidate in candidates:
        if candidate in page_paths:
            return candidate
    matches = page_targets.get(_link_key(normalized), set())
    if len(matches) == 1:
        return next(iter(matches))
    return None


def _link_key(value: str) -> str:
    return re.sub(r"[\W_]+", "", value.casefold().removesuffix(".md"), flags=re.UNICODE)


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def ensure_log(vault_path: Path) -> None:
    root = wiki_root(vault_path)
    root.mkdir(parents=True, exist_ok=True)
    log_path = root / "log.md"
    with vault_write_lock(vault_path):
        if not log_path.exists():
            log_path.write_text("# Log\n\nAppend-only operation log for ingest, query, and lint passes.\n", encoding="utf-8")
