from __future__ import annotations

import re
from pathlib import Path

from knoarbor.core.markdown import parse_frontmatter
from knoarbor.core.schemas.source_digest import SourceDigest
from knoarbor.core.schemas.wiki_draft_batch import WikiDraftBatchItem
from knoarbor.core.schemas.wiki_write import WikiDraftBatchWriteItem, WikiDraftInput
from knoarbor.storage.wiki_paths import (
    content_relative_path,
    normalize_source_digest_title,
    resolve_existing_by_hash,
    slugify_title,
    source_digest_root,
)


def build_source_digest_write_item(
    *,
    vault_path: Path,
    source_digest: SourceDigest,
    source_file: str,
    display_source_file: str,
) -> WikiDraftBatchWriteItem:
    """Build the deterministic source digest write item for one raw source."""

    target_page = resolve_source_digest_target_page(vault_path, source_digest)
    draft = build_source_digest_draft(
        source_digest,
        write_action="update" if target_page else "create",
        target_page=target_page,
    )
    return WikiDraftBatchWriteItem(
        wiki_draft=WikiDraftInput.model_validate(draft.model_dump()),
        write_action=draft.write_action,
        target_page=draft.target_page,
        source_file=source_file,
        display_source_file=display_source_file,
        operation_index=None,
    )


def build_source_digest_draft(
    source_digest: SourceDigest,
    *,
    write_action: str,
    target_page: str | None = None,
) -> WikiDraftBatchItem:
    title = source_digest_title(source_digest)
    source_file = source_digest.raw_source or source_digest.source.source_path or source_digest.source.source_id
    summary = source_digest.summary or _source_digest_audit_summary(source_digest)
    question = source_digest.source_focus or source_digest.source.title or title
    return WikiDraftBatchItem(
        operation_index=0,
        write_action=write_action,  # type: ignore[arg-type]
        target_page=target_page,
        source_file=source_file,
        title=title,
        page_dir="sources",
        canonical_path=target_page or f"sources/{slugify_title(title)}.md",
        question=question,
        summary=summary,
        synthesis=summary,
        claims=_source_digest_contribution_rows(source_digest),
        evidence=_source_digest_evidence_rows(source_digest),
        attachments=[attachment.model_dump() for attachment in source_digest.attachments],
        unresolved_items=[f"{item.item_id}: {item.reason}" for item in source_digest.unresolved_items],
        source_digest_ids=[source_digest.digest_id],
        confidence=source_digest.confidence,
        model_provider="knoarbor",
        model_name="deterministic-source-digest",
    )


def resolve_source_digest_target_page(vault_path: Path, source_digest: SourceDigest) -> str | None:
    """Resolve an existing source digest page before creating a new one."""

    if source_digest.content_hash:
        hash_match = resolve_existing_by_hash(vault_path, "sources", source_digest.content_hash)
        if hash_match is not None:
            return content_relative_path(vault_path, hash_match)

    text_match = _resolve_existing_by_source_pointer(vault_path, source_digest)
    if text_match is not None:
        return content_relative_path(vault_path, text_match)

    title_path = source_digest_root(vault_path) / f"{slugify_title(source_digest_title(source_digest))}.md"
    if title_path.exists() and title_path.is_file():
        return content_relative_path(vault_path, title_path)
    return None


def source_digest_title(source_digest: SourceDigest) -> str:
    title = source_digest.source.title or source_digest.source_focus or source_digest.source.source_id or "Source Digest"
    normalized = normalize_source_digest_title(title)
    if normalized.lower().endswith(" source"):
        return f"{normalized} Digest"
    return normalized


def _resolve_existing_by_source_pointer(vault_path: Path, source_digest: SourceDigest) -> Path | None:
    root = source_digest_root(vault_path)
    if not root.exists():
        return None
    pointers = _source_pointers(source_digest)
    if not pointers:
        return None
    for md_path in sorted(root.glob("*.md")):
        try:
            content = md_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        frontmatter = parse_frontmatter(content)
        searchable = "\n".join(
            [
                str(frontmatter.get("source") or ""),
                str(frontmatter.get("source_file") or ""),
                str(frontmatter.get("raw_source") or ""),
                content,
            ]
        )
        if _matches_source_pointer(searchable, pointers):
            return md_path
    return None


def _source_pointers(source_digest: SourceDigest) -> list[str]:
    values = [
        source_digest.raw_source,
        source_digest.source.source_path,
        source_digest.source.source_id,
        source_digest.source.title,
    ]
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
        name = Path(text.replace("\\", "/")).name if text else ""
        if name and name not in result:
            result.append(name)
        stem = Path(name).stem if name else ""
        if stem and len(stem) >= 4 and stem not in result:
            result.append(stem)
    return result


def _matches_source_pointer(content: str, pointers: list[str]) -> bool:
    lowered = content.lower()
    for pointer in pointers:
        normalized = pointer.strip()
        if not normalized:
            continue
        if normalized.lower() in lowered:
            return True
        if _slug_like(normalized).lower() in _slug_like(content).lower():
            return True
    return False


def _slug_like(value: str) -> str:
    return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "-", value).strip("-")


def _source_digest_audit_summary(source_digest: SourceDigest) -> str:
    raw_pointer = source_digest.raw_source or source_digest.source.source_path or source_digest.source.source_id or "not recorded"
    return (
        f"Audit record for {source_digest.source.title or source_digest.digest_id}. "
        f"Source units: {len(source_digest.units)}. "
        f"Contributions: {len(source_digest.contribution_map)}. "
        f"Unresolved items: {len(source_digest.unresolved_items)}. "
        f"Raw pointer: {raw_pointer}."
    )


def _source_digest_evidence_rows(source_digest: SourceDigest) -> list[str]:
    source_path = source_digest.raw_source or source_digest.source.source_path or source_digest.source.source_id or source_digest.digest_id
    rows: list[str] = []
    for index, unit in enumerate(source_digest.units, start=1):
        basis = " ".join((unit.summary or unit.evidence.excerpt or "source unit").replace("|", "/").split())
        rows.append(f"U{index} | {source_path} | unit:{unit.index} | {basis[:220]} | high")
    if rows:
        return rows
    return [f"U1 | {source_path} | source-level | source digest compiled from this raw source | medium"]


def _source_digest_contribution_rows(source_digest: SourceDigest) -> list[str]:
    return [
        f"{item.item_id}: {item.contribution}"
        for item in source_digest.contribution_map
        if item.contribution.strip()
    ]
