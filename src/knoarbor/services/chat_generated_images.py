from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import re
import shutil
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from knoarbor.core.schemas.image_generation import GeneratedImage
from knoarbor.storage.vault_layout import (
    chat_session_artifact_manifest_path,
    chat_session_image_artifacts_root,
)


MAX_CHAT_GENERATED_IMAGE_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True)
class StoredChatGeneratedImage:
    src: str
    path: str
    mime_type: str
    size_bytes: int
    manifest_path: str | None = None


def store_chat_generated_image(
    image: GeneratedImage,
    *,
    vault_path: str | Path | None,
    session_id: str | None,
    request_id: str,
    index: int,
    provider: str | None = None,
    model: str | None = None,
    prompt: str | None = None,
    revised_prompt: str | None = None,
    timeout_seconds: float = 60.0,
) -> StoredChatGeneratedImage | None:
    """Persist a generated image inside the chat storage root and return a Markdown-safe path."""

    if not vault_path:
        return None
    payload = _image_bytes(image, timeout_seconds=timeout_seconds)
    if payload is None:
        return None
    data, mime_type = payload
    if not data or len(data) > MAX_CHAT_GENERATED_IMAGE_BYTES:
        return None
    ext = _extension_for_image(image, mime_type)
    full_digest = hashlib.sha256(data).hexdigest()
    digest = full_digest[:20]
    vault = Path(vault_path).expanduser().resolve()
    session_key = session_id or "ad-hoc"
    created_at = _created_at()
    filename = f"{created_at}-{_prompt_slug(prompt)}-{index}-{digest}{ext}"
    full_path = chat_session_image_artifacts_root(vault, session_key) / _safe_path_part(request_id) / filename
    rel_path = full_path.relative_to(vault)
    full_path.parent.mkdir(parents=True, exist_ok=True)
    if not full_path.exists():
        full_path.write_bytes(data)
    manifest_path = _write_manifest(
        vault,
        session_id=session_key,
        item={
            "schema_version": "knoarbor.chat_artifact.image.v1",
            "type": "image",
            "src": rel_path.as_posix(),
            "filename": filename,
            "mime_type": mime_type,
            "size_bytes": len(data),
            "sha256": full_digest,
            "created_at": created_at,
            "request_id": request_id,
            "provider": provider,
            "model": model,
            "prompt": prompt,
            "revised_prompt": revised_prompt or image.revised_prompt,
        },
    )
    return StoredChatGeneratedImage(
        src=rel_path.as_posix(),
        path=str(full_path),
        mime_type=mime_type,
        size_bytes=len(data),
        manifest_path=str(manifest_path) if manifest_path else None,
    )


def delete_chat_session_artifacts(vault_path: str | Path, session_id: str) -> None:
    root = chat_session_image_artifacts_root(Path(vault_path).expanduser().resolve(), session_id).parent
    if root.exists():
        shutil.rmtree(root)


def delete_chat_request_artifacts(
    vault_path: str | Path,
    session_id: str,
    request_id: str,
    *,
    stored_paths: set[str] | None = None,
) -> None:
    vault = Path(vault_path).expanduser().resolve()
    manifest_path = chat_session_artifact_manifest_path(vault, session_id)
    request_root = chat_session_image_artifacts_root(vault, session_id) / _safe_path_part(request_id)
    if request_root.exists():
        shutil.rmtree(request_root)
    if not manifest_path.exists():
        _prune_empty_session_artifact_dirs(vault, session_id)
        return
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _prune_empty_session_artifact_dirs(vault, session_id)
        return
    images = payload.get("images") if isinstance(payload, dict) else None
    if not isinstance(images, list):
        _prune_empty_session_artifact_dirs(vault, session_id)
        return
    session_root = manifest_path.parent.resolve()
    legacy_paths = {str(Path(path).expanduser().resolve()) for path in (stored_paths or set())}
    retained: list[dict[str, Any]] = []
    for entry in (item for item in images if isinstance(item, dict)):
        src = str(entry.get("src") or "")
        artifact_path = (vault / src).resolve() if src else None
        owned = entry.get("request_id") == request_id or (
            artifact_path is not None and str(artifact_path) in legacy_paths
        )
        if not owned:
            retained.append(entry)
            continue
        if artifact_path is not None and artifact_path.is_relative_to(session_root):
            artifact_path.unlink(missing_ok=True)
    if retained:
        payload["images"] = retained
        manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return
    manifest_path.unlink(missing_ok=True)
    _prune_empty_session_artifact_dirs(vault, session_id)


def _prune_empty_session_artifact_dirs(vault: Path, session_id: str) -> None:
    images_root = chat_session_image_artifacts_root(vault, session_id)
    session_root = images_root.parent
    if images_root.exists() and not any(images_root.iterdir()):
        images_root.rmdir()
    if session_root.exists() and not any(session_root.iterdir()):
        session_root.rmdir()


def _image_bytes(image: GeneratedImage, *, timeout_seconds: float) -> tuple[bytes, str] | None:
    if image.b64_json:
        return base64.b64decode(image.b64_json), image.mime_type or "image/png"
    if not image.url:
        return None
    if image.url.startswith("data:"):
        header, _, encoded = image.url.partition(",")
        mime_type = header.removeprefix("data:").split(";", 1)[0] or image.mime_type or "image/png"
        return base64.b64decode(encoded), mime_type
    if not image.url.startswith(("http://", "https://")):
        return None
    try:
        with urllib.request.urlopen(image.url, timeout=timeout_seconds) as response:
            content_type = response.headers.get_content_type() or image.mime_type or "image/png"
            data = response.read(MAX_CHAT_GENERATED_IMAGE_BYTES + 1)
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return data, content_type


def _extension_for_image(image: GeneratedImage, mime_type: str) -> str:
    from_mime = mimetypes.guess_extension(mime_type.split(";", 1)[0].strip())
    if from_mime in {".jpg", ".jpeg", ".png", ".webp"}:
        return ".jpg" if from_mime == ".jpeg" else from_mime
    if image.url:
        parsed = urllib.parse.urlparse(image.url)
        suffix = Path(parsed.path).suffix.lower()
        if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
            return ".jpg" if suffix == ".jpeg" else suffix
    return ".png"


def _safe_path_part(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip())
    clean = clean.strip(".-")
    return clean[:80] or "ad-hoc"


def _created_at() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _prompt_slug(value: str | None) -> str:
    clean = re.sub(r"[^A-Za-z0-9]+", "-", (value or "generated-image").strip().lower())
    clean = clean.strip("-")
    return clean[:48].strip("-") or "generated-image"


def _write_manifest(vault_path: Path, *, session_id: str, item: dict[str, Any]) -> Path | None:
    manifest_path = chat_session_artifact_manifest_path(vault_path, session_id)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    images: list[dict[str, Any]] = []
    if manifest_path.exists():
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        existing = payload.get("images") if isinstance(payload, dict) else None
        if isinstance(existing, list):
            images = [entry for entry in existing if isinstance(entry, dict)]
    key = str(item.get("src") or "")
    images = [entry for entry in images if str(entry.get("src") or "") != key]
    images.append({key: value for key, value in item.items() if value is not None})
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "knoarbor.chat_artifacts.v1",
                "session_id": session_id,
                "images": images,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest_path
