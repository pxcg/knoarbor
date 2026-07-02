from __future__ import annotations

import base64
import hashlib
import mimetypes
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from knoarbor.core.schemas.image_generation import GeneratedImage


MAX_CHAT_GENERATED_IMAGE_BYTES = 32 * 1024 * 1024


@dataclass(frozen=True)
class StoredChatGeneratedImage:
    src: str
    path: str
    mime_type: str
    size_bytes: int
    original_src: str | None = None


def store_chat_generated_image(
    image: GeneratedImage,
    *,
    vault_path: str | Path | None,
    session_id: str | None,
    index: int,
    timeout_seconds: float = 60.0,
) -> StoredChatGeneratedImage | None:
    """Persist a generated image inside the current vault and return a Markdown-safe path."""

    if not vault_path:
        return None
    original_src = image.markdown_src()
    payload = _image_bytes(image, timeout_seconds=timeout_seconds)
    if payload is None:
        return None
    data, mime_type = payload
    if not data or len(data) > MAX_CHAT_GENERATED_IMAGE_BYTES:
        return None
    ext = _extension_for_image(image, mime_type)
    digest = hashlib.sha256(data).hexdigest()[:20]
    safe_session = _safe_path_part(session_id or "ad-hoc")
    rel_path = Path("raw/derived/assets/images/generated/chat") / safe_session / f"image-{index}-{digest}{ext}"
    full_path = Path(vault_path).expanduser() / rel_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    if not full_path.exists():
        full_path.write_bytes(data)
    return StoredChatGeneratedImage(
        src=rel_path.as_posix(),
        path=str(full_path),
        mime_type=mime_type,
        size_bytes=len(data),
        original_src=original_src,
    )


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
