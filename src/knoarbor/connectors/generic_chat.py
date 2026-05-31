from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from urllib.parse import unquote, urlparse

from knoarbor.connectors.base import ConnectorCapabilities, ConnectorConfig
from knoarbor.connectors.jsonl import read_jsonl_records
from knoarbor.core.errors import ConnectorConfigError, SourceNotFound
from knoarbor.core.schemas.sources import RawSource, SourceContent, SourceDocument, SourceFingerprint, SourceOrigin, SourceRef


class GenericChatConnector:
    name = "generic_chat"
    version = "generic-chat@1"

    def capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            name=self.name,
            version=self.version,
            source_types=["generic_chat"],
            supports_segmentation_hint=True,
        )

    def discover(self, config: ConnectorConfig) -> list[SourceRef]:
        roots = _as_list(config.settings.get("roots") or config.settings.get("sessions_dir") or config.settings.get("root"))
        explicit_files = _as_list(config.settings.get("session_files"))
        patterns = [str(item) for item in _as_list(config.settings.get("patterns"))] or ["*.jsonl", "*.sqlite", "*.db"]
        recursive = bool(config.settings.get("recursive", True))

        paths: list[Path] = []
        for value in roots:
            root = Path(str(value)).expanduser().resolve()
            if not root.exists() or not root.is_dir():
                raise SourceNotFound(f"Generic chat root does not exist: {root}")
            for pattern in patterns:
                iterator = root.rglob(pattern) if recursive else root.glob(pattern)
                paths.extend(sorted(path for path in iterator if path.is_file() and _is_supported_chat_file(path)))
        for value in explicit_files:
            path = Path(str(value)).expanduser().resolve()
            if not path.exists() or not path.is_file():
                raise SourceNotFound(f"Generic chat session file does not exist: {path}")
            if not _is_supported_chat_file(path):
                raise ConnectorConfigError(f"Generic chat connector only accepts JSONL or SQLite files: {path}")
            paths.append(path)
        if not paths:
            raise ConnectorConfigError("GenericChatConnector requires settings.roots or settings.session_files")

        refs: list[SourceRef] = []
        for path in _dedupe_paths(paths):
            metadata = _read_session_metadata(path)
            session_id = metadata["session_id"]
            refs.append(
                SourceRef(
                    source_id=f"generic_chat:{session_id}",
                    connector=self.name,
                    source_type="generic_chat",
                    uri=f"generic-chat://sessions/{path.name}",
                    display_name=path.name,
                    metadata={**metadata, "path": str(path), "file_uri": path.as_uri()},
                )
            )
        return sorted(refs, key=lambda ref: ref.uri)

    def fetch(self, ref: SourceRef, config: ConnectorConfig) -> RawSource:
        if ref.connector != self.name or ref.source_type != "generic_chat":
            raise ConnectorConfigError("GenericChatConnector can only fetch generic_chat source refs")
        path = _path_from_ref(ref)
        data = path.read_bytes()
        metadata = _read_session_metadata(path)
        return RawSource(
            source_id=ref.source_id,
            raw_path=str(path),
            content_hash=hashlib.sha256(data).hexdigest(),
            content_type=_content_type(path),
            bytes=len(data),
            created_at=metadata.get("session_start"),
            updated_at=metadata.get("last_updated"),
            metadata={**ref.metadata, **metadata},
        )

    def to_document(self, raw: RawSource, config: ConnectorConfig) -> SourceDocument:
        path = Path(raw.raw_path).expanduser().resolve()
        payload = _normalized_session_payload(path)
        metadata = payload["metadata"]
        return SourceDocument(
            source_id=raw.source_id,
            source_type="generic_chat",
            origin=SourceOrigin(
                connector=self.name,
                uri=f"generic-chat://sessions/{path.name}",
                raw_path=raw.raw_path,
                original_path=str(raw.metadata.get("file_uri") or path.as_uri()),
                created_at=raw.created_at,
                updated_at=raw.updated_at,
            ),
            content=SourceContent(
                format="json",
                text=json.dumps(payload, ensure_ascii=False, indent=2),
                sections=[
                    {
                        "index": turn["index"],
                        "role": turn["role"],
                        "title": turn.get("title"),
                        "content": turn["content"],
                        "timestamp": turn.get("timestamp"),
                        "raw_index": turn["raw_index"],
                    }
                    for turn in payload["turns"]
                ],
            ),
            metadata={
                "title": metadata.get("title") or f"Generic chat {metadata['session_id']}",
                "session_id": metadata["session_id"],
                "source_app": metadata.get("source_app") or "generic_chat",
                "message_count": len(payload["turns"]),
            },
            fingerprint=SourceFingerprint(
                content_hash=raw.content_hash,
                connector_version=self.version,
                parser_version="generic-chat-normalizer@1",
            ),
        )


def _normalized_session_payload(path: Path) -> dict[str, object]:
    if path.suffix.lower() == ".jsonl":
        turns, warnings = _jsonl_turns(path)
    else:
        turns, warnings = _sqlite_turns(path)
    if not turns:
        raise ConnectorConfigError(f"Generic chat file contains no recognizable chat turns: {path}")
    metadata = _session_metadata(path, turns)
    return {
        "schema_version": "generic_chat_extract.v1",
        "source_app": "generic_chat",
        "session_id": metadata["session_id"],
        "session_start": metadata.get("session_start"),
        "last_updated": metadata.get("last_updated"),
        "message_count": len(turns),
        "metadata": metadata,
        "turns": turns,
        "prefilter_warnings": warnings,
    }


def _jsonl_turns(path: Path) -> tuple[list[dict[str, object]], list[str]]:
    read_result = read_jsonl_records(path, source_name="Generic chat")
    turns: list[dict[str, object]] = []
    for raw_index, record in read_result.records:
        turn = _turn_from_mapping(raw_index, record)
        if turn:
            turn["index"] = len(turns)
            turns.append(turn)
    return turns, read_result.warnings


def _sqlite_turns(path: Path) -> tuple[list[dict[str, object]], list[str]]:
    turns: list[dict[str, object]] = []
    warnings: list[str] = []
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        tables = [row[0] for row in connection.execute("select name from sqlite_master where type = 'table' order by name")]
        for table in tables:
            columns = [row["name"] for row in connection.execute(f"pragma table_info({_quote_identifier(table)})")]
            content_column = _first_matching_column(columns, ["content", "text", "message", "body", "prompt", "response"])
            if not content_column:
                continue
            role_column = _first_matching_column(columns, ["role", "sender", "author", "speaker", "source"])
            timestamp_column = _first_matching_column(columns, ["timestamp", "created_at", "updated_at", "time", "created"])
            order_column = _first_matching_column(columns, ["timestamp", "created_at", "time", "id", "rowid"])
            selected = [content_column]
            if role_column:
                selected.append(role_column)
            if timestamp_column and timestamp_column not in selected:
                selected.append(timestamp_column)
            query = f"select rowid as __rowid, {', '.join(_quote_identifier(column) for column in selected)} from {_quote_identifier(table)}"
            if order_column:
                query += f" order by {_quote_identifier(order_column)}"
            for row in connection.execute(query):
                raw_index = len(turns)
                content = str(row[content_column] or "").strip()
                if not content:
                    continue
                role = _normalize_role(str(row[role_column])) if role_column else "user"
                turn = {
                    "raw_index": raw_index,
                    "role": role,
                    "content": content,
                    "timestamp": str(row[timestamp_column]) if timestamp_column and row[timestamp_column] is not None else None,
                    "title": _compact_title(content),
                    "table": table,
                    "rowid": row["__rowid"],
                    "index": len(turns),
                }
                turns.append(turn)
    finally:
        connection.close()
    if not turns:
        warnings.append("No SQLite table with a recognizable chat text column was found.")
    return turns, warnings


def _turn_from_mapping(raw_index: int, record: dict[str, object]) -> dict[str, object] | None:
    candidate = record
    for key in ("message", "payload", "data"):
        nested = candidate.get(key)
        if isinstance(nested, dict):
            candidate = nested
            break
    role = _normalize_role(str(candidate.get("role") or candidate.get("sender") or candidate.get("author") or candidate.get("speaker") or "user"))
    content = _message_text(candidate.get("content") or candidate.get("text") or candidate.get("message") or candidate.get("body"))
    if not content:
        return None
    return {
        "raw_index": raw_index,
        "role": role,
        "content": content,
        "timestamp": candidate.get("timestamp") or candidate.get("created_at") or candidate.get("time"),
        "title": _compact_title(content),
    }


def _read_session_metadata(path: Path) -> dict[str, object]:
    try:
        payload = _normalized_session_payload(path)
        return dict(payload["metadata"])  # type: ignore[arg-type]
    except ConnectorConfigError:
        return _session_metadata(path, [])


def _session_metadata(path: Path, turns: list[dict[str, object]]) -> dict[str, object]:
    timestamps = [str(turn.get("timestamp")) for turn in turns if turn.get("timestamp")]
    path_hash = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:10]
    return {
        "session_id": f"{path.stem}-{path_hash}",
        "session_start": timestamps[0] if timestamps else None,
        "last_updated": timestamps[-1] if timestamps else None,
        "title": path.stem,
        "source_app": "generic_chat",
    }


def _message_text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(part.strip() for part in parts if part and part.strip()).strip()
    return ""


def _normalize_role(value: str) -> str:
    role = value.lower().strip()
    if role in {"assistant", "ai", "bot", "model"}:
        return "assistant"
    if role in {"system", "tool"}:
        return "assistant"
    return "user"


def _compact_title(text: str) -> str:
    cleaned = " ".join(text.strip().split())
    return cleaned[:80] or "turn"


def _first_matching_column(columns: list[str], candidates: list[str]) -> str | None:
    lowered = {column.lower(): column for column in columns}
    for candidate in candidates:
        if candidate in lowered:
            return lowered[candidate]
    for candidate in candidates:
        for column in columns:
            if candidate in column.lower():
                return column
    return None


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _content_type(path: Path) -> str:
    if path.suffix.lower() == ".jsonl":
        return "application/x-jsonlines"
    return "application/vnd.sqlite3"


def _is_supported_chat_file(path: Path) -> bool:
    return path.suffix.lower() in {".jsonl", ".sqlite", ".db"}


def _path_from_ref(ref: SourceRef) -> Path:
    file_uri = ref.metadata.get("file_uri")
    if isinstance(file_uri, str) and file_uri:
        parsed = urlparse(file_uri)
        if parsed.scheme != "file":
            raise ConnectorConfigError(f"Expected file URI in generic chat source ref, got: {file_uri}")
        return Path(unquote(parsed.path)).expanduser().resolve()
    path = ref.metadata.get("path")
    if isinstance(path, str) and path:
        return Path(path).expanduser().resolve()
    raise ConnectorConfigError("Generic chat source ref must include metadata.path or metadata.file_uri")


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    result: list[Path] = []
    for path in paths:
        resolved = path.expanduser().resolve()
        if resolved not in seen:
            seen.add(resolved)
            result.append(resolved)
    return result


def _as_list(value: object) -> list[object]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]
