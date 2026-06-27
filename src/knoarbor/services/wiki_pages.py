from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from collections.abc import Callable, Iterable

from pydantic import BaseModel, Field

from knoarbor.core.errors import PolicyRejection, UserInputError, VaultPathError, WikiPageNotFound
from knoarbor.core.markdown import compact_inline_text, extract_heading, extract_section, parse_frontmatter
from knoarbor.retrieval.page_resolver import resolve_page_reference
from knoarbor.storage import ensure_machine_index, machine_index_dir, update_index
from knoarbor.storage.vault_layout import maintenance_archives_root
from knoarbor.storage.wiki_index import relative_wiki_path
from knoarbor.storage.wiki_paths import content_path


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
    outgoing_pages: list[WikiPageRelation] = Field(default_factory=list)
    incoming_pages: list[WikiPageRelation] = Field(default_factory=list)


class WikiPageDeleteResponse(BaseModel):
    deleted: bool
    path: str
    archived_path: str


class WikiPageService:
    """Read maintained wiki pages through the machine index boundary."""

    def list_pages(self, vault_path: Path, *, vault_id: str | None = None, vault_name: str | None = None) -> WikiPagesResponse:
        vault = _resolve_vault(vault_path)
        if not vault.exists():
            return WikiPagesResponse(vault_path=str(vault), vault_id=vault_id, vault_name=vault_name, pages=[])
        records = _page_records(vault)
        knowledge = [record for record in records if record.get("role") == "knowledge_page"]
        return WikiPagesResponse(vault_path=str(vault), vault_id=vault_id, vault_name=vault_name, pages=[_summary_from_record(record) for record in knowledge])

    def read_page(self, vault_path: Path, relative_path: str, *, vault_id: str | None = None, vault_name: str | None = None) -> WikiPageDetail:
        vault = _resolve_vault(vault_path)
        page_path = _resolve_vault_file(vault, relative_path)
        content = page_path.read_text(encoding="utf-8")
        page_relative = relative_wiki_path(vault, page_path)
        relations = self.page_relations(vault, page_relative, vault_id=vault_id, vault_name=vault_name)
        return WikiPageDetail(
            path=page_relative,
            canonical_path=relations.canonical_path,
            vault_path=str(vault),
            vault_id=vault_id,
            vault_name=vault_name,
            content=content,
            metadata=parse_frontmatter(content),
            summary=_summary_from_content(vault, page_path, content),
            outgoing_pages=relations.outgoing_pages,
            incoming_pages=relations.incoming_pages,
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

    def edit_page(self, vault_path: Path, relative_path: str, content: str, *, vault_id: str | None = None, vault_name: str | None = None) -> WikiPageDetail:
        if not content.strip():
            raise PolicyRejection("Page content cannot be empty")
        page_path = _resolve_vault_file(vault_path, relative_path)
        page_path.write_text(content, encoding="utf-8")
        update_index(vault_path)
        return self.read_page(vault_path, relative_path, vault_id=vault_id, vault_name=vault_name)

    def delete_page(self, vault_path: Path, relative_path: str) -> WikiPageDeleteResponse:
        page_path = _resolve_vault_file(vault_path, relative_path)
        archive_dir = maintenance_archives_root(vault_path) / "deleted_pages"
        archive_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_path = archive_dir / f"{timestamp}_{page_path.name}"
        page_path.rename(archive_path)
        update_index(vault_path)
        return WikiPageDeleteResponse(
            deleted=True,
            path=relative_path,
            archived_path=str(archive_path),
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


def _summary_from_record(record: dict[str, object]) -> WikiPageSummary:
    path = str(record.get("path") or "")
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
    )


def _summary_from_content(vault_path: Path, path: Path, content: str) -> WikiPageSummary:
    metadata = parse_frontmatter(content)
    relative = relative_wiki_path(vault_path, path)
    directory = relative.split("/", 1)[0] if "/" in relative else "root"
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
    )


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
