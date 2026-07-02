from __future__ import annotations

import hashlib
import json
import mimetypes
from pathlib import Path
import re
from typing import Any


ATTACHMENT_SIDECAR_SCHEMA = "knoarbor.attachments.v1"
IMAGE_SUFFIXES = {".apng", ".avif", ".bmp", ".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"}

_MARKDOWN_IMAGE_RE = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<target>[^)\s]+)(?:\s+\"[^\"]*\")?\)")
_DETAILS_RE = re.compile(
    r"^\s*<details>\s*<summary>(?P<summary>[^<]*)</summary>\s*(?P<body>.*?)</details>",
    flags=re.DOTALL | re.IGNORECASE,
)
_CAPTION_RE = re.compile(r"^(?:图|表|Figure|Fig\.?|Table)\s*[\dA-Za-z一二三四五六七八九十.-]*\s*[:：.]?\s*\S+")


def attachment_sidecar_path(markdown_path: Path) -> Path:
    return _canonical_sidecar_path(markdown_path) or markdown_path.with_name(f"{markdown_path.stem}.attachments.json")


def read_attachment_sidecar(markdown_path: Path) -> list[dict[str, Any]]:
    sidecar = next((path for path in _sidecar_candidates(markdown_path) if path.exists() and path.is_file()), None)
    if sidecar is None:
        return []
    try:
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, dict) or payload.get("schema_version") != ATTACHMENT_SIDECAR_SCHEMA:
        return []
    attachments = payload.get("attachments")
    if not isinstance(attachments, list):
        return []
    return [item for item in attachments if isinstance(item, dict)]


def write_attachment_sidecar(markdown_path: Path, attachments: list[dict[str, Any]], *, source: str) -> None:
    sidecar = attachment_sidecar_path(markdown_path)
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text(
        json.dumps(
            {
                "schema_version": ATTACHMENT_SIDECAR_SCHEMA,
                "source": source,
                "attachments": attachments,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def discover_markdown_image_attachments(markdown_path: Path, markdown: str | None = None, *, base_dir: Path | None = None) -> list[dict[str, Any]]:
    text = markdown if markdown is not None else markdown_path.read_text(encoding="utf-8")
    attachments: list[dict[str, Any]] = []
    for match in _MARKDOWN_IMAGE_RE.finditer(text):
        target = match.group("target").strip()
        if _is_remote_or_embedded(target):
            continue
        target_path = _resolve_markdown_target(markdown_path, target)
        if target_path is None or not _is_image_path(target_path):
            continue
        context = _markdown_image_context(text, match.start(), match.end())
        metadata = {key: value for key, value in context.items() if value}
        alt = match.group("alt").strip()
        description = alt or str(metadata.get("mineru_description") or metadata.get("caption") or "")
        attachments.append(
            normalize_attachment(
                target_path,
                base_dir=base_dir or markdown_path.parent,
                name=target_path.name,
                description=description,
                source="markdown_image_link",
                metadata=metadata,
            )
        )
    return dedupe_attachments(attachments)


def normalize_attachment(
    path: Path,
    *,
    base_dir: Path,
    name: str | None = None,
    description: str = "",
    source: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    relative_path = _relative_path(resolved, base_dir)
    mime_type, _ = mimetypes.guess_type(resolved.name)
    return {
        "attachment_type": "image" if _is_image_path(resolved) else "file",
        "name": name or resolved.name,
        "description": description,
        "path": str(resolved),
        "relative_path": relative_path,
        "mime_type": mime_type,
        "content_hash": _file_hash(resolved),
        "source": source,
        "metadata": metadata or {},
    }


def dedupe_attachments(attachments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for attachment in attachments:
        key = _attachment_identity(attachment)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(attachment)
    return deduped


def _attachment_identity(attachment: dict[str, Any]) -> str:
    for field in ("content_hash", "relative_path", "path", "name"):
        value = str(attachment.get(field) or "").strip()
        if value:
            return f"{field}:{value}"
    return ""


def _markdown_image_context(text: str, start: int, end: int) -> dict[str, str]:
    after = text[end:]
    before = text[:start]
    metadata: dict[str, str] = {}
    details_match = _DETAILS_RE.match(after)
    after_details = after
    if details_match:
        summary = _compact_attachment_text(details_match.group("summary"), limit=80)
        body = _compact_attachment_text(details_match.group("body"), limit=300)
        if summary:
            metadata["sub_type"] = summary
        if body:
            metadata["mineru_description"] = body
            metadata["description"] = body
        after_details = after[details_match.end():]

    caption = _first_caption_after(after_details) or _nearest_caption_before(before)
    if caption:
        metadata["caption"] = caption
        metadata["topic"] = caption
        metadata.setdefault("description", caption)
    return metadata


def _first_caption_after(value: str) -> str:
    for line in value.splitlines()[:6]:
        cleaned = _compact_attachment_text(line, limit=180)
        if not cleaned:
            continue
        if _CAPTION_RE.match(cleaned):
            return cleaned
        if cleaned.startswith("<"):
            continue
        break
    return ""


def _nearest_caption_before(value: str) -> str:
    lines = value.splitlines()
    for line in reversed(lines[-6:]):
        cleaned = _compact_attachment_text(line, limit=180)
        if cleaned and _CAPTION_RE.match(cleaned):
            return cleaned
    return ""


def _compact_attachment_text(value: str, *, limit: int) -> str:
    text = re.sub(r"<[^>]+>", " ", value or "")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _resolve_markdown_target(markdown_path: Path, target: str) -> Path | None:
    cleaned = target.split("#", 1)[0].split("?", 1)[0].strip()
    if not cleaned:
        return None
    path = Path(cleaned)
    if not path.is_absolute():
        path = markdown_path.parent / path
    return path.expanduser().resolve() if path.exists() and path.is_file() else None


def _is_remote_or_embedded(target: str) -> bool:
    lowered = target.lower()
    return lowered.startswith(("http://", "https://", "data:", "file:"))


def _is_image_path(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_SUFFIXES


def _relative_path(path: Path, base_dir: Path) -> str:
    try:
        return str(path.relative_to(base_dir.expanduser().resolve()))
    except ValueError:
        return path.name


def _file_hash(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _sidecar_candidates(markdown_path: Path) -> list[Path]:
    adjacent = markdown_path.with_name(f"{markdown_path.stem}.attachments.json")
    canonical = _canonical_sidecar_path(markdown_path)
    if canonical and canonical != adjacent:
        return [canonical, adjacent]
    return [adjacent]


def _canonical_sidecar_path(markdown_path: Path) -> Path | None:
    try:
        resolved = markdown_path.expanduser().resolve()
    except OSError:
        resolved = markdown_path.expanduser()
    raw_root = _raw_root_for_normalized_path(resolved)
    if raw_root is None:
        return None
    return raw_root / "derived" / "metadata" / "sources" / f"{resolved.stem}.attachments.json"


def _raw_root_for_normalized_path(path: Path) -> Path | None:
    parts = path.parts
    for index, part in enumerate(parts):
        if part != "raw":
            continue
        if index + 1 < len(parts) and parts[index + 1] == "derived":
            return Path(*parts[: index + 1])
    return None
