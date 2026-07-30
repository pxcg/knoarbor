from __future__ import annotations

import hashlib
from pathlib import Path

from knoarbor.connectors.base import ConnectorConfig
from knoarbor.core.attachments import dedupe_attachments, discover_markdown_image_attachments, read_attachment_sidecar
from knoarbor.core.errors import ConnectorConfigError, SourceNotFound
from knoarbor.core.path_utils import path_from_file_uri
from knoarbor.core.schemas.sources import (
    RawSource,
    SourceContent,
    SourceDocument,
    SourceFingerprint,
    SourceOrigin,
    SourceRef,
)


class MarkdownConnector:
    name = "markdown"
    version = "markdown@1"

    def discover(self, config: ConnectorConfig) -> list[SourceRef]:
        roots = _as_list(config.settings.get("roots"))
        if not roots:
            raise ConnectorConfigError("MarkdownConnector requires settings.roots")

        pattern = str(config.settings.get("pattern") or "*.md")
        recursive = bool(config.settings.get("recursive", True))

        refs: list[SourceRef] = []
        for root_value in roots:
            root = Path(str(root_value)).expanduser().resolve()
            if not root.exists():
                raise SourceNotFound(f"Markdown root does not exist: {root}")
            paths = [root] if root.is_file() else _iter_markdown_files(root, pattern, recursive)
            for path in paths:
                if path.is_file() and path.match(pattern):
                    uri = path.as_uri()
                    refs.append(
                        SourceRef(
                            source_id=_source_id(uri),
                            connector=self.name,
                            source_type="markdown",
                            uri=uri,
                            display_name=path.name,
                            metadata={"root": str(root), "path": str(path)},
                        )
                    )
        return sorted(refs, key=lambda ref: ref.uri)

    def fetch(self, ref: SourceRef, config: ConnectorConfig) -> RawSource:
        if ref.connector != self.name or ref.source_type != "markdown":
            raise ConnectorConfigError("MarkdownConnector can only fetch markdown source refs")

        path = _path_from_file_uri(ref.uri)
        if not path.exists() or not path.is_file():
            raise SourceNotFound(f"Markdown source does not exist: {path}")
        data = path.read_bytes()
        return RawSource(
            source_id=ref.source_id,
            raw_path=str(path),
            content_hash=hashlib.sha256(data).hexdigest(),
            content_type="text/markdown",
            bytes=len(data),
            updated_at=None,
            metadata={"uri": ref.uri, "display_name": ref.display_name, **ref.metadata},
        )

    def to_document(self, raw: RawSource, config: ConnectorConfig) -> SourceDocument:
        path = Path(raw.raw_path).expanduser().resolve()
        text = path.read_text(encoding="utf-8")
        uri = str(raw.metadata.get("uri") or path.as_uri())
        source_root = _source_root(raw, config, path)
        attachments = dedupe_attachments(
            [
                *read_attachment_sidecar(path),
                *discover_markdown_image_attachments(path, text, source_root=source_root),
            ]
        )
        return SourceDocument(
            source_id=raw.source_id,
            source_type="markdown",
            origin=SourceOrigin(
                connector=self.name,
                uri=uri,
                raw_path=raw.raw_path,
                updated_at=raw.updated_at,
            ),
            content=SourceContent(format="markdown", text=text, attachments=attachments),
            metadata={
                "title": _extract_markdown_title(text) or raw.metadata.get("display_name") or path.name,
                "display_name": raw.metadata.get("display_name") or path.name,
                "attachment_count": len(attachments),
            },
            fingerprint=SourceFingerprint(
                content_hash=raw.content_hash,
                connector_version=self.version,
            ),
        )


def _iter_markdown_files(root: Path, pattern: str, recursive: bool) -> list[Path]:
    iterator = root.rglob(pattern) if recursive else root.glob(pattern)
    return sorted(path for path in iterator if path.is_file())


def _as_list(value: object) -> list[object]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _source_root(raw: RawSource, config: ConnectorConfig, path: Path) -> Path:
    configured = config.settings.get("source_root") or raw.metadata.get("root")
    root = Path(str(configured)).expanduser().resolve() if configured else path.parent
    return root.parent if root.is_file() else root


def _source_id(uri: str) -> str:
    digest = hashlib.sha256(uri.encode("utf-8")).hexdigest()[:16]
    return f"markdown:{digest}"


def _path_from_file_uri(uri: str) -> Path:
    try:
        return path_from_file_uri(uri)
    except ValueError as exc:
        raise ConnectorConfigError(f"MarkdownConnector expects file:// URI, got: {uri}") from exc


def _extract_markdown_title(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip() or None
    return None
