from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
from collections.abc import Callable, Iterable

from pydantic import BaseModel, Field

from knoarbor.core.errors import MaterializationPending, UserInputError, VaultPathError, WikiPageNotFound
from knoarbor.core.markdown import compact_inline_text, extract_heading, extract_section, parse_frontmatter
from knoarbor.core.schemas.sources import SourceDocument
from knoarbor.core.schemas.projection_edit import ProjectionEdit, ProjectionEditorState
from knoarbor.core.schemas.raw_revision_edit import RawRevisionEditorState
from knoarbor.retrieval.page_resolver import resolve_page_reference
from knoarbor.runtime import vault_write_lock
from knoarbor.runtime.transactional_ingest import TransactionalIngestStore
from knoarbor.storage.ingest_inputs import read_input_generation
from knoarbor.storage.materialization import VaultMaterializer
from knoarbor.storage.source_records import read_source_processing_records
from knoarbor.storage.source_revisions import (
    read_active_processing_records,
    release_unreferenced_image_assets,
    source_revision_image_asset_paths,
)
from knoarbor.storage.wiki_index import ensure_machine_index, machine_index_dir, relative_wiki_path
from knoarbor.storage.wiki_paths import content_path
from knoarbor.services.projection_edits import commit_projection_edit, read_projection_edit
from knoarbor.services.raw_revision_edits import read_raw_revision_editor


class WikiPageSummary(BaseModel):
    path: str
    canonical_path: str | None = None
    directory: str
    title: str
    role: str | None = None
    updated: str | None = None
    entities: list[str] = Field(default_factory=list)
    summary: str = ""
    headings: list[str] = Field(default_factory=list)
    raw_record_id: str | None = None
    raw_revision_id: str | None = None
    source_record_id: str | None = None
    processing_record_id: str | None = None
    original_source_path: str | None = None
    source_unit_count: int = 0


class WikiPagesResponse(BaseModel):
    vault_path: str
    vault_id: str | None = None
    vault_name: str | None = None
    pages: list[WikiPageSummary] = Field(default_factory=list)


class WikiPageRelation(BaseModel):
    source: str
    target: str
    target_path: str | None = None
    resolved: bool = False


class WikiPageRelationsResponse(BaseModel):
    path: str
    canonical_path: str | None = None
    vault_path: str | None = None
    vault_id: str | None = None
    vault_name: str | None = None
    outgoing_pages: list[WikiPageRelation] = Field(default_factory=list)
    incoming_pages: list[WikiPageRelation] = Field(default_factory=list)


class WikiPageDetail(BaseModel):
    path: str
    canonical_path: str | None = None
    vault_path: str | None = None
    vault_id: str | None = None
    vault_name: str | None = None
    content: str
    metadata: dict[str, str] = Field(default_factory=dict)
    summary: WikiPageSummary
    default_view: str = "wiki"
    raw_content: str | None = None
    wiki_content: str | None = None
    raw_record_id: str | None = None
    raw_revision_id: str | None = None
    source_record_id: str | None = None
    processing_record_id: str | None = None
    original_source_path: str | None = None
    source_unit_count: int = 0
    outgoing_pages: list[WikiPageRelation] = Field(default_factory=list)
    incoming_pages: list[WikiPageRelation] = Field(default_factory=list)
    editable_projection: ProjectionEditorState | None = None
    editable_raw: RawRevisionEditorState | None = None


class WikiPageDeleteResponse(BaseModel):
    deleted: bool
    path: str


class WikiPageService:
    def resolve_page_path(self, vault_path: Path, relative_path: str) -> Path:
        return _resolve_vault_file(vault_path, relative_path)

    """Read maintained wiki pages through the machine index boundary."""

    def list_pages(self, vault_path: Path, *, vault_id: str | None = None, vault_name: str | None = None) -> WikiPagesResponse:
        vault = _resolve_vault(vault_path)
        if not vault.exists():
            return WikiPagesResponse(vault_path=str(vault), vault_id=vault_id, vault_name=vault_name, pages=[])
        records = _page_records(vault)
        knowledge = [record for record in records if record.get("role") == "knowledge_page"]
        processing_by_page = _processing_records_by_page(vault)
        return WikiPagesResponse(
            vault_path=str(vault),
            vault_id=vault_id,
            vault_name=vault_name,
            pages=[_summary_from_record(record, processing_by_page.get(str(record.get("path") or ""))) for record in knowledge],
        )

    def read_page(self, vault_path: Path, relative_path: str, *, vault_id: str | None = None, vault_name: str | None = None) -> WikiPageDetail:
        vault = _resolve_vault(vault_path)
        try:
            page_path = _resolve_vault_file(vault, relative_path)
        except WikiPageNotFound:
            state = TransactionalIngestStore(vault).materialization_state()
            if state["phase"] != "clean" and read_active_processing_records(vault):
                raise MaterializationPending(
                    "Knowledge view materialization is pending; rebuild the knowledge view before deciding that the page was deleted."
                ) from None
            raise
        content = page_path.read_text(encoding="utf-8")
        metadata = parse_frontmatter(content)
        page_relative = relative_wiki_path(vault, page_path)
        processing_record = _processing_record_for_page(vault, page_relative, metadata)
        source_document = _source_document_from_processing_record(vault, processing_record)
        raw_content = _raw_markdown_from_source_document(source_document)
        relations = self.page_relations(vault, page_relative, vault_id=vault_id, vault_name=vault_name)
        return WikiPageDetail(
            path=page_relative,
            canonical_path=relations.canonical_path,
            vault_path=str(vault),
            vault_id=vault_id,
            vault_name=vault_name,
            content=content,
            metadata=metadata,
            summary=_summary_from_content(vault, page_path, content, processing_record),
            default_view="raw" if raw_content else "wiki",
            raw_content=raw_content,
            wiki_content=content,
            raw_record_id=processing_record.raw_record_id if processing_record else _optional_text(metadata.get("raw_record_id")),
            raw_revision_id=processing_record.raw_revision_id if processing_record else _optional_text(metadata.get("raw_revision_id")),
            source_record_id=processing_record.source_record_id if processing_record else _optional_text(metadata.get("source_record_id")),
            processing_record_id=processing_record.processing_record_id if processing_record else _optional_text(metadata.get("processing_record_id")),
            original_source_path=source_document.origin.raw_path if source_document else None,
            source_unit_count=len(processing_record.source_units) if processing_record else 0,
            outgoing_pages=relations.outgoing_pages,
            incoming_pages=relations.incoming_pages,
            editable_projection=read_projection_edit(vault, page_path),
            editable_raw=read_raw_revision_editor(vault, page_path),
        )

    def page_relations(self, vault_path: Path, relative_path: str, *, vault_id: str | None = None, vault_name: str | None = None) -> WikiPageRelationsResponse:
        vault = _resolve_vault(vault_path)
        resolution = resolve_page_reference(vault, relative_path)
        resolved_path = resolution.resolved_path or relative_path
        links = _link_records(vault)
        outgoing = _unique_links(
            (link for link in links if link.source == resolved_path and link.target_path != resolved_path),
            key=lambda link: link.target_path or link.target,
        )
        incoming = _unique_links(
            (link for link in links if link.target_path == resolved_path and link.source != resolved_path),
            key=lambda link: link.source,
        )
        return WikiPageRelationsResponse(
            path=resolved_path,
            canonical_path=resolution.canonical_path,
            vault_path=str(vault),
            vault_id=vault_id,
            vault_name=vault_name,
            outgoing_pages=outgoing,
            incoming_pages=incoming,
        )

    def edit_page(self, vault_path: Path, relative_path: str, edit: ProjectionEdit, *, vault_id: str | None = None, vault_name: str | None = None) -> WikiPageDetail:
        page_path = _resolve_vault_file(vault_path, relative_path)
        commit_projection_edit(vault_path, page_path, edit)
        return self.read_page(vault_path, relative_path, vault_id=vault_id, vault_name=vault_name)

    def delete_page(self, vault_path: Path, relative_path: str) -> WikiPageDeleteResponse:
        with vault_write_lock(vault_path):
            page_path = _resolve_vault_file(vault_path, relative_path)
            metadata = parse_frontmatter(page_path.read_text(encoding="utf-8"))
            page_relative = relative_wiki_path(vault_path, page_path)
            processing_record = _processing_record_for_page(vault_path, page_relative, metadata)
            fact_paths: list[str] = []
            obsolete_image_candidates: set[Path] = set()
            if processing_record is not None:
                store = TransactionalIngestStore(vault_path)
                obsolete_image_candidates = source_revision_image_asset_paths(
                    vault_path,
                    processing_record.raw_record_id,
                    store=store,
                )
                fact_paths = store.purge_source(processing_record.raw_record_id)
            page_path.unlink()
            for fact_path in fact_paths:
                shutil.rmtree((vault_path / fact_path).resolve(), ignore_errors=True)
            if processing_record is not None:
                release_unreferenced_image_assets(vault_path, obsolete_image_candidates, store=store)
            VaultMaterializer().reconcile(vault_path, force=True)
        return WikiPageDeleteResponse(
            deleted=True,
            path=relative_path,
        )


def _resolve_vault(vault_path: Path) -> Path:
    return vault_path.expanduser().resolve()


def _resolve_vault_file(vault_path: Path, relative_path: str) -> Path:
    resolution = resolve_page_reference(vault_path, relative_path)
    resolved_relative_path = resolution.resolved_path or relative_path
    page_path = content_path(vault_path, resolved_relative_path).resolve()
    vault = vault_path.expanduser().resolve()
    try:
        page_path.relative_to(vault)
    except ValueError as exc:
        raise VaultPathError("Path must stay inside the configured vault") from exc
    if not page_path.exists() or not page_path.is_file():
        raise WikiPageNotFound(f"Vault file not found: {relative_path}")
    if page_path.suffix.lower() != ".md":
        raise UserInputError("Only Markdown wiki pages can be previewed")
    return page_path


def _page_records(vault_path: Path) -> list[dict[str, object]]:
    ensure_machine_index(vault_path)
    payload = _read_json(machine_index_dir(vault_path) / "pages.json")
    return [item for item in payload.get("pages", []) if isinstance(item, dict)]


def _link_records(vault_path: Path) -> list[WikiPageRelation]:
    ensure_machine_index(vault_path)
    payload = _read_json(machine_index_dir(vault_path) / "links.json")
    links: list[WikiPageRelation] = []
    for item in payload.get("links", []):
        if not isinstance(item, dict):
            continue
        links.append(
            WikiPageRelation(
                source=str(item.get("source") or ""),
                target=str(item.get("target") or ""),
                target_path=_optional_text(item.get("target_path")),
                resolved=bool(item.get("resolved")),
            )
        )
    return links


def _unique_links(links: Iterable[WikiPageRelation], *, key: Callable[[WikiPageRelation], str | None]) -> list[WikiPageRelation]:
    seen: set[str] = set()
    unique: list[WikiPageRelation] = []
    for link in links:
        identity = key(link) or ""
        if not identity or identity in seen:
            continue
        seen.add(identity)
        unique.append(link)
    return unique


def _summary_from_record(record: dict[str, object], processing_record: object | None = None) -> WikiPageSummary:
    path = str(record.get("path") or "")
    source = getattr(processing_record, "source", None)
    return WikiPageSummary(
        path=path,
        canonical_path=_optional_text(record.get("canonical_path")),
        directory=str(record.get("directory") or Path(path).parent.name or "root"),
        title=str(record.get("title") or Path(path).stem),
        role=_optional_text(record.get("role")),
        updated=_optional_text(record.get("updated") or record.get("created")),
        entities=[str(entity) for entity in record.get("entities", []) if isinstance(entity, str)],
        summary=compact_inline_text(str(record.get("summary") or ""), 280),
        headings=[str(heading) for heading in record.get("headings", []) if isinstance(heading, str)][:12],
        raw_record_id=getattr(processing_record, "raw_record_id", None) or _optional_text(record.get("raw_record_id")),
        raw_revision_id=getattr(processing_record, "raw_revision_id", None) or _optional_text(record.get("raw_revision_id")),
        source_record_id=getattr(processing_record, "source_record_id", None) or _first_optional_text(record.get("source_record_ids")),
        processing_record_id=getattr(processing_record, "processing_record_id", None) or _optional_text(record.get("processing_record_id")),
        original_source_path=getattr(source, "raw_path", None),
        source_unit_count=len(getattr(processing_record, "source_units", []) or []),
    )


def _summary_from_content(vault_path: Path, path: Path, content: str, processing_record: object | None = None) -> WikiPageSummary:
    metadata = parse_frontmatter(content)
    relative = relative_wiki_path(vault_path, path)
    directory = relative.split("/", 1)[0] if "/" in relative else "root"
    source = getattr(processing_record, "source", None)
    return WikiPageSummary(
        path=relative,
        canonical_path=metadata.get("canonical_path") or relative,
        directory=directory,
        title=metadata.get("title") or extract_heading(content, path.stem),
        role=None,
        updated=metadata.get("updated") or metadata.get("created"),
        entities=_extract_entities(content),
        summary=compact_inline_text(extract_section(content, "Summary") or extract_section(content, "摘要"), 280),
        headings=_extract_headings(content)[:12],
        raw_record_id=getattr(processing_record, "raw_record_id", None) or _optional_text(metadata.get("raw_record_id")),
        raw_revision_id=getattr(processing_record, "raw_revision_id", None) or _optional_text(metadata.get("raw_revision_id")),
        source_record_id=getattr(processing_record, "source_record_id", None) or _optional_text(metadata.get("source_record_id")),
        processing_record_id=getattr(processing_record, "processing_record_id", None) or _optional_text(metadata.get("processing_record_id")),
        original_source_path=getattr(source, "raw_path", None),
        source_unit_count=len(getattr(processing_record, "source_units", []) or []),
    )


def _processing_records_by_page(vault_path: Path) -> dict[str, object]:
    records: dict[str, object] = {}
    for record in read_source_processing_records(vault_path):
        for page_path in record.page_paths:
            if page_path:
                records[page_path] = record
    return records


def _processing_record_for_page(vault_path: Path, page_relative: str, metadata: dict[str, str]) -> object | None:
    processing_record_id = metadata.get("processing_record_id", "").strip()
    raw_record_id = metadata.get("raw_record_id", "").strip()
    source_record_id = metadata.get("source_record_id", "").strip()
    for record in read_source_processing_records(vault_path):
        if processing_record_id and record.processing_record_id == processing_record_id:
            return record
        if page_relative in record.page_paths:
            return record
        if raw_record_id and record.raw_record_id == raw_record_id:
            return record
        if source_record_id and record.source_record_id == source_record_id:
            return record
    return None


def _source_document_from_processing_record(vault_path: Path, record: object | None) -> SourceDocument | None:
    revision_id = _optional_text(getattr(record, "revision_id", None))
    source = getattr(record, "source", None)
    source_id = _optional_text(getattr(source, "source_id", None))
    if not revision_id or not source_id:
        return None
    generation_id = TransactionalIngestStore(vault_path).input_generation_id_for_revision(revision_id)
    generation = read_input_generation(vault_path, generation_id)
    return next((item for item in generation.documents if item.source_id == source_id), None)


_OBSIDIAN_IMAGE_EMBED_RE = re.compile(r"!\[\[(?P<target>[^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
_MARKDOWN_IMAGE_RE = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<target>[^)\s]+)(?:\s+\"[^\"]*\")?\)")


def _raw_markdown_from_source_document(document: SourceDocument | None) -> str | None:
    if document is None:
        return None
    content = document.content.text.strip()
    if not content:
        return None
    return f"{_raw_display_markdown(content, document.content.attachments)}\n"


def _raw_display_markdown(content: str, attachments: list[dict[str, object]]) -> str:
    references: dict[str, set[str]] = {}
    for attachment in attachments:
        if not isinstance(attachment, dict) or str(attachment.get("attachment_type") or "") != "image":
            continue
        relative_path = str(attachment.get("relative_path") or "").replace("\\", "/").strip()
        if not relative_path.startswith("raw/derived/assets/"):
            continue
        metadata = attachment.get("metadata") if isinstance(attachment.get("metadata"), dict) else {}
        for reference in (metadata.get("obsidian_target"), metadata.get("markdown_target")):
            key = _attachment_reference_key(reference)
            if key:
                references.setdefault(key, set()).add(relative_path)

    def retained_path(target: str) -> str | None:
        paths = references.get(_attachment_reference_key(target), set())
        return next(iter(paths)) if len(paths) == 1 else None

    def replace_markdown_image(match: re.Match[str]) -> str:
        path = retained_path(match.group("target"))
        if path is None:
            return match.group(0)
        return f"![{match.group('alt')}]({path})"

    def replace_obsidian_image(match: re.Match[str]) -> str:
        target = match.group("target").strip()
        path = retained_path(target)
        if path is None:
            return match.group(0)
        alt = Path(target.replace("\\", "/")).name.replace("[", "").replace("]", "")
        return f"![{alt}]({path})"

    return _OBSIDIAN_IMAGE_EMBED_RE.sub(replace_obsidian_image, _MARKDOWN_IMAGE_RE.sub(replace_markdown_image, content))


def _attachment_reference_key(value: object) -> str:
    return str(value or "").replace("\\", "/").strip().casefold()


def _extract_headings(content: str) -> list[str]:
    headings: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        marker, _, title = stripped.partition(" ")
        if marker.startswith("#") and 1 <= len(marker) <= 6 and set(marker) == {"#"} and title.strip():
            headings.append(title.strip())
    return headings


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


def _read_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _first_optional_text(value: object) -> str | None:
    if isinstance(value, list):
        for item in value:
            text = _optional_text(item)
            if text:
                return text
        return None
    return _optional_text(value)
