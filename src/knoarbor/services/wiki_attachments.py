from __future__ import annotations

from pathlib import Path
import re
from typing import Any
from urllib.parse import quote

from knoarbor.core.attachments import read_attachment_sidecar
from knoarbor.core.markdown import compact_inline_text


_SOURCE_DIGEST_ID_RE = re.compile(r"\bsd_[A-Za-z0-9_-]+\b")
_RAW_SOURCE_RE = re.compile(r"^\s*-\s*Raw source:\s*(?P<path>.+?)\s*$", flags=re.MULTILINE)
_HASHY_NAME_RE = re.compile(r"^[A-Za-z0-9_-]*[a-f0-9]{16,}[A-Za-z0-9_.-]*$", flags=re.IGNORECASE)


def attachments_for_wiki_page(vault_path: str | Path | None, page_content: str, *, limit: int = 16) -> list[dict[str, Any]]:
    """Return renderable attachment evidence referenced by a maintained page."""

    if not vault_path or not page_content:
        return []
    vault = Path(vault_path).expanduser()
    sidecar_sources = _sidecar_sources_from_source_digests(vault, page_content)
    attachments = _attachments_from_raw_sources(vault, sidecar_sources)
    if not attachments:
        attachments = _attachments_from_matching_sidecars(vault, page_content)
    return _normalize_chat_attachments(attachments, vault=vault, page_content=page_content, limit=limit)


def _sidecar_sources_from_source_digests(vault: Path, page_content: str) -> list[Path]:
    source_ids = set(_SOURCE_DIGEST_ID_RE.findall(page_content))
    if not source_ids:
        return []
    sources_dir = vault / "wiki" / "sources"
    if not sources_dir.exists():
        return []
    raw_sources: list[Path] = []
    for source_page in sorted(sources_dir.glob("*.md")):
        try:
            text = source_page.read_text(encoding="utf-8")
        except OSError:
            continue
        if not source_ids.intersection(_SOURCE_DIGEST_ID_RE.findall(text)):
            continue
        raw_source = _raw_source_from_digest(vault, text)
        if raw_source:
            raw_sources.append(raw_source)
    return raw_sources


def _raw_source_from_digest(vault: Path, source_digest: str) -> Path | None:
    match = _RAW_SOURCE_RE.search(source_digest)
    if not match:
        return None
    raw_path = match.group("path").strip()
    if not raw_path:
        return None
    path = Path(raw_path)
    if not path.is_absolute():
        path = vault / path
    return path


def _attachments_from_raw_sources(vault: Path, raw_sources: list[Path]) -> list[dict[str, Any]]:
    attachments: list[dict[str, Any]] = []
    for raw_source in raw_sources:
        attachments.extend(read_attachment_sidecar(raw_source))
    return attachments


def _attachments_from_matching_sidecars(vault: Path, page_content: str) -> list[dict[str, Any]]:
    sidecars_dir = vault / "raw" / "derived" / "metadata" / "sources"
    if not sidecars_dir.exists():
        return []
    matched: list[dict[str, Any]] = []
    for sidecar in sorted(sidecars_dir.glob("*.attachments.json")):
        raw_source = vault / "raw" / "derived" / "markdown" / f"{sidecar.name.removesuffix('.attachments.json')}.md"
        attachments = read_attachment_sidecar(raw_source)
        selected = [item for item in attachments if _attachment_matches_page(item, page_content)]
        matched.extend(selected)
    return matched


def _attachment_matches_page(attachment: dict[str, Any], page_content: str) -> bool:
    haystack = page_content
    for value in _attachment_labels(attachment):
        if value and value in haystack:
            return True
    return False


def _normalize_chat_attachments(attachments: list[dict[str, Any]], *, vault: Path, page_content: str, limit: int) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    page_matched = [item for item in attachments if _attachment_matches_page(item, page_content)]
    candidates = page_matched or attachments
    for attachment in candidates:
        relative_path = str(attachment.get("relative_path") or "").strip()
        if not relative_path:
            continue
        key = str(attachment.get("content_hash") or relative_path)
        if key in seen:
            continue
        seen.add(key)
        topic = _attachment_topic(attachment)
        description = _attachment_description(attachment)
        normalized_path = _markdown_src(relative_path)
        markdown_src = _ui_asset_src(normalized_path, vault)
        if not topic and not description:
            topic = "Attachment image"
        normalized.append(
            {
                "type": str(attachment.get("attachment_type") or "image"),
                "topic": topic,
                "description": description,
                "markdown_src": markdown_src,
                "path": normalized_path,
                "mime_type": attachment.get("mime_type"),
                "source_range": attachment.get("source_range") or attachment.get("metadata", {}).get("source_range"),
            }
        )
        if len(normalized) >= limit:
            break
    return normalized


def _attachment_labels(attachment: dict[str, Any]) -> list[str]:
    metadata = attachment.get("metadata") if isinstance(attachment.get("metadata"), dict) else {}
    values = [
        metadata.get("topic"),
        metadata.get("caption"),
        metadata.get("image_caption"),
        metadata.get("table_caption"),
        attachment.get("topic"),
        attachment.get("description"),
        metadata.get("description"),
        metadata.get("mineru_description"),
        attachment.get("name"),
    ]
    return [str(value).strip() for value in values if str(value or "").strip()]


def _attachment_topic(attachment: dict[str, Any]) -> str:
    for value in _attachment_labels(attachment):
        if not _HASHY_NAME_RE.match(value):
            return compact_inline_text(value, 120)
    return ""


def _attachment_description(attachment: dict[str, Any]) -> str:
    metadata = attachment.get("metadata") if isinstance(attachment.get("metadata"), dict) else {}
    for value in (
        attachment.get("description"),
        metadata.get("description"),
        metadata.get("mineru_description"),
        metadata.get("caption"),
    ):
        text = str(value or "").strip()
        if text and not _HASHY_NAME_RE.match(text):
            return compact_inline_text(text, 240)
    return ""


def _markdown_src(relative_path: str) -> str:
    cleaned = relative_path.strip().replace("\\", "/").lstrip("/")
    if cleaned.startswith("raw/derived/assets/"):
        return cleaned
    if cleaned.startswith("assets/"):
        return f"raw/derived/{cleaned}"
    return f"raw/derived/assets/{cleaned}"


def _ui_asset_src(relative_path: str, vault: Path) -> str:
    cleaned = relative_path.strip().replace("\\", "/").lstrip("/")
    if cleaned.startswith("raw/derived/assets/"):
        cleaned = cleaned.removeprefix("raw/derived/assets/")
    elif cleaned.startswith("assets/"):
        cleaned = cleaned.removeprefix("assets/")
    return f"/ui/api/vault-assets/{quote(cleaned, safe='')}?vault_path={quote(str(vault.expanduser().resolve()), safe='')}"
