from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import unquote, urlparse

from knoarbor.connectors.base import ConnectorConfig
from knoarbor.core.errors import ConnectorConfigError, SourceNotFound
from knoarbor.core.schemas.sources import (
    RawSource,
    SourceContent,
    SourceDocument,
    SourceFingerprint,
    SourceOrigin,
    SourceRef,
)


class HermesConnector:
    name = "hermes"
    version = "hermes@1"

    def discover(self, config: ConnectorConfig) -> list[SourceRef]:
        sessions_dir = config.settings.get("sessions_dir") or config.settings.get("root")
        explicit_files = _as_list(config.settings.get("session_files"))
        pattern = str(config.settings.get("pattern") or "session_*.json")
        recursive = bool(config.settings.get("recursive", False))

        paths: list[Path] = []
        if sessions_dir:
            root = Path(str(sessions_dir)).expanduser().resolve()
            if not root.exists() or not root.is_dir():
                raise SourceNotFound(f"Hermes sessions directory does not exist: {root}")
            iterator = root.rglob(pattern) if recursive else root.glob(pattern)
            paths.extend(sorted(path for path in iterator if path.is_file()))
        for value in explicit_files:
            path = Path(str(value)).expanduser().resolve()
            if not path.exists() or not path.is_file():
                raise SourceNotFound(f"Hermes session file does not exist: {path}")
            paths.append(path)
        if not paths:
            raise ConnectorConfigError("HermesConnector requires settings.sessions_dir or settings.session_files")

        refs: list[SourceRef] = []
        for path in _dedupe_paths(paths):
            metadata = _read_session_metadata(path)
            session_id = metadata["session_id"]
            refs.append(
                SourceRef(
                    source_id=f"hermes:{session_id}",
                    connector=self.name,
                    source_type="hermes_chat",
                    uri=f"hermes://sessions/{path.name}",
                    display_name=path.name,
                    metadata={**metadata, "path": str(path), "file_uri": path.as_uri()},
                )
            )
        return sorted(refs, key=lambda ref: ref.uri)

    def fetch(self, ref: SourceRef, config: ConnectorConfig) -> RawSource:
        if ref.connector != self.name or ref.source_type != "hermes_chat":
            raise ConnectorConfigError("HermesConnector can only fetch hermes_chat source refs")

        path = _path_from_ref(ref)
        data = path.read_bytes()
        metadata = _read_session_metadata(path)
        return RawSource(
            source_id=ref.source_id,
            raw_path=str(path),
            content_hash=hashlib.sha256(data).hexdigest(),
            content_type="application/json",
            bytes=len(data),
            created_at=metadata.get("session_start"),
            updated_at=metadata.get("last_updated"),
            metadata={**ref.metadata, **metadata},
        )

    def to_document(self, raw: RawSource, config: ConnectorConfig) -> SourceDocument:
        path = Path(raw.raw_path).expanduser().resolve()
        text = path.read_text(encoding="utf-8")
        metadata = _read_session_metadata(path)
        return SourceDocument(
            source_id=raw.source_id,
            source_type="hermes_chat",
            origin=SourceOrigin(
                connector=self.name,
                uri=f"hermes://sessions/{path.name}",
                raw_path=raw.raw_path,
                original_path=str(raw.metadata.get("file_uri") or path.as_uri()),
                created_at=raw.created_at,
                updated_at=raw.updated_at,
            ),
            content=SourceContent(format="json", text=text),
            metadata={
                "title": f"Hermes session {metadata['session_id']}",
                "session_id": metadata["session_id"],
                "source_app": metadata.get("platform") or "hermes",
                "model": metadata.get("model"),
                "message_count": metadata.get("message_count", 0),
            },
            fingerprint=SourceFingerprint(
                content_hash=raw.content_hash,
                connector_version=self.version,
            ),
        )


def _read_session_metadata(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ConnectorConfigError(f"Hermes session must be a JSON object: {path}")
    session_id = str(payload.get("session_id") or payload.get("id") or path.stem.replace("session_", ""))
    messages = payload.get("messages")
    return {
        "session_id": session_id,
        "platform": payload.get("platform"),
        "model": payload.get("model"),
        "session_start": payload.get("session_start"),
        "last_updated": payload.get("last_updated"),
        "message_count": len(messages) if isinstance(messages, list) else 0,
    }


def _path_from_ref(ref: SourceRef) -> Path:
    path_value = ref.metadata.get("path")
    if isinstance(path_value, str) and path_value:
        path = Path(path_value).expanduser().resolve()
    else:
        file_uri = ref.metadata.get("file_uri")
        if not isinstance(file_uri, str):
            raise ConnectorConfigError("Hermes source ref must include metadata.path or metadata.file_uri")
        parsed = urlparse(file_uri)
        if parsed.scheme != "file":
            raise ConnectorConfigError(f"Expected file URI in Hermes source ref, got: {file_uri}")
        path = Path(unquote(parsed.path)).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise SourceNotFound(f"Hermes session file does not exist: {path}")
    return path


def _as_list(value: object) -> list[object]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    deduped: list[Path] = []
    for path in paths:
        resolved = path.expanduser().resolve()
        if resolved not in seen:
            seen.add(resolved)
            deduped.append(resolved)
    return deduped
