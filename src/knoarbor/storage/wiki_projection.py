"""Deterministic Markdown projections derived from committed source facts."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from knoarbor.core.markdown import parse_frontmatter
from knoarbor.core.schemas.knowledge_atoms import KnowledgeAtomBatch, KnowledgeRelation
from knoarbor.core.schemas.raw_evidence import SourceProcessingRecord, SourceUnitRecord
from knoarbor.core.schemas.source_record import SourceRecordAttachment
from knoarbor.storage.vault_layout import wiki_pages_root
from knoarbor.storage.wiki_index import relative_wiki_path
from knoarbor.storage.wiki_paths import slugify_title


@dataclass(frozen=True)
class WikiProjectionResult:
    path: str
    absolute_path: Path
    written: bool
    deleted_stale_paths: list[str]


def write_source_projection_page(
    vault_path: Path,
    *,
    processing_record: SourceProcessingRecord,
    atom_batch: KnowledgeAtomBatch,
) -> WikiProjectionResult:
    """Write the deterministic readable projection for one raw source."""

    vault = vault_path.expanduser().resolve()
    pages_root = wiki_pages_root(vault)
    pages_root.mkdir(parents=True, exist_ok=True)
    target_path = _projection_path(vault, processing_record)
    _atomic_write(target_path, _render_projection(vault, target_path, processing_record, atom_batch))
    stale_paths = _delete_stale_projection_pages(vault, target_path, processing_record.raw_record_id)
    return WikiProjectionResult(
        path=relative_wiki_path(vault, target_path),
        absolute_path=target_path,
        written=True,
        deleted_stale_paths=stale_paths,
    )


def write_session_projection_page(
    vault_path: Path,
    *,
    windows: list[tuple[SourceProcessingRecord, KnowledgeAtomBatch]],
) -> WikiProjectionResult:
    """Write one readable projection that contains every committed session window."""

    if not windows:
        raise ValueError("Session projection requires at least one committed window.")
    vault = vault_path.expanduser().resolve()
    pages_root = wiki_pages_root(vault)
    pages_root.mkdir(parents=True, exist_ok=True)
    latest_record, _ = windows[-1]
    target_path = _projection_path(vault, latest_record)
    _atomic_write(target_path, _render_session_projection(vault, target_path, windows))
    stale_paths = _delete_stale_projection_pages(vault, target_path, latest_record.raw_record_id)
    return WikiProjectionResult(
        path=relative_wiki_path(vault, target_path),
        absolute_path=target_path,
        written=True,
        deleted_stale_paths=stale_paths,
    )


def source_projection_path(vault_path: Path, processing_record: SourceProcessingRecord) -> str:
    """Return the stable display path before the derived file is materialized."""

    return relative_wiki_path(vault_path, _projection_path(vault_path.expanduser().resolve(), processing_record))


def _projection_path(vault_path: Path, record: SourceProcessingRecord) -> Path:
    title = record.source.title or record.metadata.get("source_focus") or record.source.raw_path or record.raw_record_id
    raw_key = record.raw_record_id.split(":", 1)[-1][:12]
    return wiki_pages_root(vault_path) / f"{slugify_title(str(title), max_length=64)}--{raw_key}.md"


def _delete_stale_projection_pages(vault_path: Path, target_path: Path, raw_record_id: str) -> list[str]:
    deleted: list[str] = []
    for path in wiki_pages_root(vault_path).glob("*.md"):
        if path.resolve() == target_path.resolve():
            continue
        try:
            metadata = parse_frontmatter(path.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            continue
        if metadata.get("projection_kind") != "source_index" or metadata.get("raw_record_id") != raw_record_id:
            continue
        path.unlink()
        deleted.append(relative_wiki_path(vault_path, path))
    return deleted


def _atomic_write(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def _render_projection(vault: Path, target_path: Path, record: SourceProcessingRecord, atom_batch: KnowledgeAtomBatch) -> str:
    title = record.source.title or record.metadata.get("source_focus") or Path(record.source.raw_path or "Source").stem
    frontmatter = [
        "---",
        "schema_version: wiki_projection.v1",
        "role: knowledge_page",
        "projection_kind: source_index",
        "not_fact_material: true",
        f"raw_record_id: {record.raw_record_id}",
        f"raw_revision_id: {record.raw_revision_id}",
        f"source_record_id: {record.source_record_id}",
        f"processing_record_id: {record.processing_record_id}",
        "---",
    ]
    sections = [
        *frontmatter,
        "",
        f"# {title}",
        "",
        "## Source",
        "",
        _source_metadata(record),
        "",
        "## Synthesis",
        "",
        atom_batch.synthesis or "No synthesis available.",
        "",
        "## Claims",
        "",
        _render_claims(record, atom_batch),
        "",
        "## Entities",
        "",
        _list([_entity_line(entity.name, entity.aliases) for entity in atom_batch.entities], "No entities extracted."),
        "",
        "## Relations",
        "",
        _list(
            [_relation_line(index, relation, atom_batch) for index, relation in enumerate(atom_batch.relations, start=1)],
            "No relations extracted.",
        ),
        "",
        "## Attachments",
        "",
        _render_attachments(vault, target_path, record.attachments),
        "",
    ]
    return "\n".join(sections).rstrip() + "\n"


def _render_session_projection(vault: Path, target_path: Path, windows: list[tuple[SourceProcessingRecord, KnowledgeAtomBatch]]) -> str:
    latest_record, _ = windows[-1]
    title = (
        latest_record.source.title or latest_record.metadata.get("source_focus") or Path(latest_record.source.raw_path or "Session").stem
    )
    frontmatter = [
        "---",
        "schema_version: wiki_projection.v1",
        "role: knowledge_page",
        "projection_kind: session_index",
        "not_fact_material: true",
        f"raw_record_id: {latest_record.raw_record_id}",
        f"window_count: {len(windows)}",
        "---",
    ]
    sections = [*frontmatter, "", f"# {title}", "", "## Windows", ""]
    for index, (record, batch) in enumerate(windows, start=1):
        sections.extend(
            [
                f"### Window {index}",
                "",
                batch.synthesis or "No synthesis available.",
                "",
                "#### Claims",
                "",
                _render_claims(record, batch),
                "",
                "#### Entities",
                "",
                _list([_entity_line(entity.name, entity.aliases) for entity in batch.entities], "No entities extracted."),
                "",
                "#### Relations",
                "",
                _list(
                    [_relation_line(relation_index, relation, batch) for relation_index, relation in enumerate(batch.relations, start=1)],
                    "No relations extracted.",
                ),
                "",
                "#### Attachments",
                "",
                _render_attachments(vault, target_path, record.attachments),
                "",
            ]
        )
    return "\n".join(sections).rstrip() + "\n"


def _source_metadata(record: SourceProcessingRecord) -> str:
    values = [f"- Path: `{record.source.raw_path}`", f"- Type: {record.source.source_type or 'source'}"]
    if record.raw_revision_id:
        values.append(f"- Revision: `{record.raw_revision_id}`")
    return "\n".join(values)


def _render_claims(record: SourceProcessingRecord, batch: KnowledgeAtomBatch) -> str:
    if not batch.claims:
        return "- No claims extracted."
    units = {unit.source_unit_id: unit for unit in record.source_units}
    units_by_index = {unit.unit_index: unit for unit in record.source_units}
    sections: list[str] = []
    for index, claim in enumerate(batch.claims, start=1):
        sections.extend([f"### C{index}", "", claim.claim])
        for span in claim.evidence:
            excerpt = "\n".join(f"> {line}" for line in span.excerpt.splitlines() if line.strip())
            if excerpt:
                sections.extend(["", excerpt])
            unit_index = span.source_unit_index if span.source_unit_index is not None else -1
            unit = units.get(span.source_unit_id or "") or units_by_index.get(unit_index)
            location = _evidence_location(unit, span.source_path)
            if location:
                sections.extend(["", f"Source: {location}"])
        sections.append("")
    return "\n".join(sections).rstrip()


def _evidence_location(unit: SourceUnitRecord | None, source_path: str | None) -> str:
    parts: list[str] = []
    path = str(source_path or "").strip()
    if path:
        parts.append(f"`{path}`")
    if unit is not None:
        structural_path = getattr(unit, "structural_path", [])
        title = str(getattr(unit, "title", "") or "").strip()
        labels = [str(value).strip() for value in structural_path if str(value).strip()]
        if not labels and title:
            labels = [title]
        if labels:
            parts.append(" / ".join(labels))
        parts.append(f"unit {int(getattr(unit, 'unit_index', 0)) + 1}")
    return " · ".join(parts)


def _entity_line(name: str, aliases: list[str]) -> str:
    alias_text = ", ".join(alias for alias in aliases if alias.casefold() != name.casefold())
    return f"{name} (aliases: {alias_text})" if alias_text else name


def _relation_line(index: int, relation: KnowledgeRelation, batch: KnowledgeAtomBatch) -> str:
    claim_labels = {claim.id: f"C{claim_index}" for claim_index, claim in enumerate(batch.claims, start=1)}
    supporting = ", ".join(claim_labels[claim_id] for claim_id in relation.source_claim_ids if claim_id in claim_labels)
    suffix = f" (supporting claims: {supporting})" if supporting else ""
    return f"R{index}: {relation.subject.name} -> {relation.predicate} -> {relation.object.name}{suffix}"


def _render_attachments(vault: Path, target_path: Path, attachments: list[SourceRecordAttachment]) -> str:
    if not attachments:
        return "- No attachments."
    sections: list[str] = []
    for attachment in attachments:
        title = attachment.topic or attachment.name
        sections.append(f"### {title}")
        thumbnail = _attachment_thumbnail(vault, target_path, attachment)
        if thumbnail:
            sections.extend(["", f"![{_markdown_alt(title)}]({thumbnail})"])
        if attachment.description:
            sections.extend(["", attachment.description])
        sections.append("")
    return "\n".join(sections).rstrip()


def _attachment_thumbnail(vault: Path, target_path: Path, attachment: SourceRecordAttachment) -> str:
    if attachment.attachment_type != "image" and not str(attachment.mime_type or "").startswith("image/"):
        return ""
    candidate = Path(attachment.path).expanduser() if attachment.path else None
    if candidate is None and attachment.relative_path:
        candidate = vault / attachment.relative_path
    if candidate is None:
        return ""
    resolved = candidate.resolve()
    try:
        resolved.relative_to(vault)
    except ValueError:
        return ""
    if not resolved.is_file():
        return ""
    return Path(os.path.relpath(resolved, start=target_path.parent)).as_posix()


def _markdown_alt(value: str) -> str:
    return value.replace("[", "").replace("]", "").replace("\n", " ").strip()


def _list(items: list[str], empty: str) -> str:
    values = [item.strip() for item in items if item.strip()]
    if not values:
        return f"- {empty}"
    return "\n".join(f"- {item}" for item in values)
