from __future__ import annotations

import hashlib
import json
from pathlib import Path

from knoarbor.connectors.base import ConnectorConfig
from knoarbor.connectors.jsonl import read_jsonl_records
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


class ClaudeCodeConnector:
    name = "claude_code"
    version = "claude-code@1"

    def discover(self, config: ConnectorConfig) -> list[SourceRef]:
        sessions_dir = config.settings.get("sessions_dir") or config.settings.get("root")
        explicit_files = _as_list(config.settings.get("session_files"))
        pattern = str(config.settings.get("pattern") or "*.jsonl")
        recursive = bool(config.settings.get("recursive", True))

        paths: list[Path] = []
        if sessions_dir:
            root = Path(str(sessions_dir)).expanduser().resolve()
            if not root.exists() or not root.is_dir():
                raise SourceNotFound(f"Claude Code sessions directory does not exist: {root}")
            iterator = root.rglob(pattern) if recursive else root.glob(pattern)
            paths.extend(sorted(path for path in iterator if path.is_file()))
        for value in explicit_files:
            path = Path(str(value)).expanduser().resolve()
            if not path.exists() or not path.is_file():
                raise SourceNotFound(f"Claude Code session file does not exist: {path}")
            paths.append(path)
        if not paths:
            raise ConnectorConfigError("ClaudeCodeConnector requires settings.sessions_dir or settings.session_files")

        refs: list[SourceRef] = []
        for path in _dedupe_paths(paths):
            metadata = _read_session_metadata(path)
            session_id = metadata["session_id"]
            refs.append(
                SourceRef(
                    source_id=f"claude_code:{session_id}",
                    connector=self.name,
                    source_type="claude_code_chat",
                    uri=f"claude-code://sessions/{path.name}",
                    display_name=path.name,
                    metadata={**metadata, "path": str(path), "file_uri": path.as_uri()},
                )
            )
        return sorted(refs, key=lambda ref: ref.uri)

    def fetch(self, ref: SourceRef, config: ConnectorConfig) -> RawSource:
        if ref.connector != self.name or ref.source_type != "claude_code_chat":
            raise ConnectorConfigError("ClaudeCodeConnector can only fetch claude_code_chat source refs")

        path = _path_from_ref(ref)
        data = path.read_bytes()
        metadata = _read_session_metadata(path)
        return RawSource(
            source_id=ref.source_id,
            raw_path=str(path),
            content_hash=hashlib.sha256(data).hexdigest(),
            content_type="application/x-jsonlines",
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
            source_type="claude_code_chat",
            origin=SourceOrigin(
                connector=self.name,
                uri=f"claude-code://sessions/{path.name}",
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
                "title": metadata.get("title") or f"Claude Code session {metadata['session_id']}",
                "session_id": metadata["session_id"],
                "source_app": "claude_code",
                "model": metadata.get("model"),
                "cwd": metadata.get("cwd"),
                "message_count": len(payload["turns"]),
            },
            fingerprint=SourceFingerprint(
                content_hash=raw.content_hash,
                connector_version=self.version,
                parser_version="claude-code-jsonl-normalizer@1",
            ),
        )


def _normalized_session_payload(path: Path) -> dict[str, object]:
    read_result = read_jsonl_records(path, source_name="Claude Code")
    records = read_result.records
    metadata = _session_metadata_from_records(path, records)
    turns: list[dict[str, object]] = []
    for raw_index, record in records:
        turn = _turn_from_record(raw_index, record)
        if turn:
            turn["index"] = len(turns)
            turns.append(turn)
    return {
        "schema_version": "claude_code_session_extract.v1",
        "source_app": "claude_code",
        "session_id": metadata["session_id"],
        "session_start": metadata.get("session_start"),
        "last_updated": metadata.get("last_updated"),
        "message_count": len(turns),
        "metadata": metadata,
        "turns": turns,
        "prefilter_warnings": [*read_result.warnings, *_prefilter_warnings(records, turns)],
    }


def _read_session_metadata(path: Path) -> dict[str, object]:
    read_result = read_jsonl_records(path, source_name="Claude Code")
    metadata = _session_metadata_from_records(path, read_result.records)
    if read_result.warnings:
        metadata["parse_warnings"] = read_result.warnings
    return metadata


def _session_metadata_from_records(path: Path, records: list[tuple[int, dict[str, object]]]) -> dict[str, object]:
    timestamps: list[str] = []
    session_id: str | None = None
    cwd = None
    model = None
    version = None
    for _, record in records:
        timestamp = record.get("timestamp")
        if isinstance(timestamp, str) and timestamp:
            timestamps.append(timestamp)
        if session_id is None and isinstance(record.get("sessionId"), str):
            session_id = str(record["sessionId"])
        if cwd is None and isinstance(record.get("cwd"), str):
            cwd = str(record["cwd"])
        if version is None and isinstance(record.get("version"), str):
            version = str(record["version"])
        message = record.get("message")
        if isinstance(message, dict) and model is None and isinstance(message.get("model"), str):
            model = str(message["model"])

    session_id = session_id or path.stem
    title = _title_from_records(records) or _title_from_ai_title(records) or f"Claude Code session {session_id}"
    return {
        "session_id": session_id,
        "session_start": timestamps[0] if timestamps else None,
        "last_updated": timestamps[-1] if timestamps else None,
        "message_count": len([1 for raw_index, record in records if _turn_from_record(raw_index, record)]),
        "cwd": cwd,
        "model": model,
        "version": version,
        "title": title,
    }


def _turn_from_record(raw_index: int, record: dict[str, object]) -> dict[str, object] | None:
    if record.get("isSidechain") is True:
        return None
    if record.get("type") not in {"user", "assistant"}:
        return None
    message = record.get("message")
    if not isinstance(message, dict):
        return None

    role = message.get("role")
    if role not in {"user", "assistant"}:
        return None

    text = _message_text(message.get("content"))
    if not text or _is_process_only_text(text):
        return None
    return {
        "raw_index": raw_index,
        "role": role,
        "content": text,
        "timestamp": record.get("timestamp"),
        "title": _compact_title(text),
    }


def _message_text(content: object) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "text":
            continue
        text = item.get("text")
        if isinstance(text, str) and text.strip():
            parts.append(text.strip())
    return "\n\n".join(parts).strip()


def _is_process_only_text(text: str) -> bool:
    stripped = text.strip()
    process_prefixes = (
        "<environment_context>",
        "<turn_context>",
        "<permissions instructions>",
        "<collaboration_mode>",
        "<apps_instructions>",
        "<skills_instructions>",
    )
    return any(stripped.startswith(prefix) for prefix in process_prefixes)


def _compact_title(text: str) -> str:
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if len(first_line) <= 80:
        return first_line
    return f"{first_line[:77]}..."


def _title_from_records(records: list[tuple[int, dict[str, object]]]) -> str | None:
    for raw_index, record in records:
        turn = _turn_from_record(raw_index, record)
        if turn and turn.get("role") == "user":
            title = str(turn.get("title") or "").strip()
            if title:
                return title
    return None


def _title_from_ai_title(records: list[tuple[int, dict[str, object]]]) -> str | None:
    for _, record in records:
        title = record.get("aiTitle")
        if record.get("type") == "ai-title" and isinstance(title, str) and title.strip():
            return title.strip()
    return None


def _prefilter_warnings(records: list[tuple[int, dict[str, object]]], turns: list[dict[str, object]]) -> list[str]:
    dropped = max(0, len(records) - len(turns))
    if dropped == 0:
        return []
    return [
        "Dropped "
        f"{dropped} non-substantive Claude Code records such as permission mode changes, snapshots, attachments, "
        "thinking blocks, tool calls, tool results, or timing metadata."
    ]

def _path_from_ref(ref: SourceRef) -> Path:
    path_value = ref.metadata.get("path")
    if isinstance(path_value, str) and path_value:
        path = Path(path_value).expanduser().resolve()
    else:
        file_uri = ref.metadata.get("file_uri")
        if not isinstance(file_uri, str):
            raise ConnectorConfigError("Claude Code source ref must include metadata.path or metadata.file_uri")
        try:
            path = path_from_file_uri(file_uri)
        except ValueError as exc:
            raise ConnectorConfigError(f"Expected file URI in Claude Code source ref, got: {file_uri}") from exc
    if not path.exists() or not path.is_file():
        raise SourceNotFound(f"Claude Code session file does not exist: {path}")
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
