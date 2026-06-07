from __future__ import annotations

import json
from pathlib import Path
from collections.abc import Callable, Iterable

from pydantic import BaseModel, Field

from knoarbor.core.errors import UserInputError, VaultPathError, WikiPageNotFound
from knoarbor.core.markdown import compact_inline_text, extract_heading, extract_section, extract_tags, parse_frontmatter
from knoarbor.storage import ensure_machine_index, machine_index_dir


class WikiPageSummary(BaseModel):
    path: str
    directory: str
    title: str
    page_type: str | None = None
    status: str | None = None
    updated: str | None = None
    source: str | None = None
    tags: list[str] = Field(default_factory=list)
    summary: str = ""
    headings: list[str] = Field(default_factory=list)


class WikiPagesResponse(BaseModel):
    vault_path: str
    vault_id: str | None = None
    vault_name: str | None = None
    pages: list[WikiPageSummary] = Field(default_factory=list)


class WikiPageLink(BaseModel):
    source: str
    target: str
    target_path: str | None = None
    resolved: bool = False


class WikiPageBacklinksResponse(BaseModel):
    path: str
    vault_path: str | None = None
    vault_id: str | None = None
    vault_name: str | None = None
    outbound_links: list[WikiPageLink] = Field(default_factory=list)
    backlinks: list[WikiPageLink] = Field(default_factory=list)


class WikiPageDetail(BaseModel):
    path: str
    vault_path: str | None = None
    vault_id: str | None = None
    vault_name: str | None = None
    content: str
    metadata: dict[str, str] = Field(default_factory=dict)
    summary: WikiPageSummary
    outbound_links: list[WikiPageLink] = Field(default_factory=list)
    backlinks: list[WikiPageLink] = Field(default_factory=list)


class WikiPageService:
    """Read maintained wiki pages through the machine index boundary."""

    def list_pages(self, vault_path: Path, *, vault_id: str | None = None, vault_name: str | None = None) -> WikiPagesResponse:
        vault = _resolve_vault(vault_path)
        if not vault.exists():
            return WikiPagesResponse(vault_path=str(vault), vault_id=vault_id, vault_name=vault_name, pages=[])
        records = _page_records(vault)
        return WikiPagesResponse(vault_path=str(vault), vault_id=vault_id, vault_name=vault_name, pages=[_summary_from_record(record) for record in records])

    def read_page(self, vault_path: Path, relative_path: str, *, vault_id: str | None = None, vault_name: str | None = None) -> WikiPageDetail:
        vault = _resolve_vault(vault_path)
        page_path = _resolve_vault_file(vault, relative_path)
        content = page_path.read_text(encoding="utf-8")
        links = self.page_links(vault, page_path.relative_to(vault).as_posix(), vault_id=vault_id, vault_name=vault_name)
        return WikiPageDetail(
            path=page_path.relative_to(vault).as_posix(),
            vault_path=str(vault),
            vault_id=vault_id,
            vault_name=vault_name,
            content=content,
            metadata=parse_frontmatter(content),
            summary=_summary_from_content(vault, page_path, content),
            outbound_links=links.outbound_links,
            backlinks=links.backlinks,
        )

    def page_links(self, vault_path: Path, relative_path: str, *, vault_id: str | None = None, vault_name: str | None = None) -> WikiPageBacklinksResponse:
        vault = _resolve_vault(vault_path)
        links = _link_records(vault)
        outbound = _unique_links(
            (link for link in links if link.source == relative_path and link.target_path != relative_path),
            key=lambda link: link.target_path or link.target,
        )
        backlinks = _unique_links(
            (link for link in links if link.target_path == relative_path and link.source != relative_path),
            key=lambda link: link.source,
        )
        return WikiPageBacklinksResponse(path=relative_path, vault_path=str(vault), vault_id=vault_id, vault_name=vault_name, outbound_links=outbound, backlinks=backlinks)


def _resolve_vault(vault_path: Path) -> Path:
    return vault_path.expanduser().resolve()


def _resolve_vault_file(vault_path: Path, relative_path: str) -> Path:
    page_path = (vault_path / relative_path).resolve()
    try:
        page_path.relative_to(vault_path)
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


def _link_records(vault_path: Path) -> list[WikiPageLink]:
    ensure_machine_index(vault_path)
    payload = _read_json(machine_index_dir(vault_path) / "links.json")
    links: list[WikiPageLink] = []
    for item in payload.get("links", []):
        if not isinstance(item, dict):
            continue
        links.append(
            WikiPageLink(
                source=str(item.get("source") or ""),
                target=str(item.get("target") or ""),
                target_path=_optional_text(item.get("target_path")),
                resolved=bool(item.get("resolved")),
            )
        )
    return links


def _unique_links(links: Iterable[WikiPageLink], *, key: Callable[[WikiPageLink], str | None]) -> list[WikiPageLink]:
    seen: set[str] = set()
    unique: list[WikiPageLink] = []
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
        directory=str(record.get("directory") or Path(path).parent.name or "root"),
        title=str(record.get("title") or Path(path).stem),
        page_type=_optional_text(record.get("type")),
        status=_optional_text(record.get("status")),
        updated=_optional_text(record.get("updated") or record.get("created")),
        source=_optional_text(record.get("source")),
        tags=[str(tag) for tag in record.get("tags", []) if isinstance(tag, str)],
        summary=compact_inline_text(str(record.get("summary") or ""), 280),
        headings=[str(heading) for heading in record.get("headings", []) if isinstance(heading, str)][:12],
    )


def _summary_from_content(vault_path: Path, path: Path, content: str) -> WikiPageSummary:
    metadata = parse_frontmatter(content)
    relative = path.relative_to(vault_path).as_posix()
    directory = relative.split("/", 1)[0] if "/" in relative else "root"
    return WikiPageSummary(
        path=relative,
        directory=directory,
        title=metadata.get("title") or extract_heading(content, path.stem),
        page_type=metadata.get("type"),
        status=metadata.get("status"),
        updated=metadata.get("updated") or metadata.get("created"),
        source=metadata.get("source"),
        tags=extract_tags(content, metadata),
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
