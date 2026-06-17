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


class OpenClawConnector:
    name = "openclaw"
    version = "openclaw@1"

    def discover(self, config: ConnectorConfig) -> list[SourceRef]:
        sessions_dir = config.settings.get("sessions_dir") or config.settings.get("root")
        explicit_files = _as_list(config.settings.get("session_files"))
        pattern = str(config.settings.get("pattern") or "*.jsonl")
        recursive = bool(config.settings.get("recursive", False))

        paths: list[Path] = []
        if sessions_dir:
            root = Path(str(sessions_dir)).expanduser().resolve()
            if not root.exists() or not root.is_dir():
                raise SourceNotFound(f"OpenClaw sessions directory does not exist: {root}")
            iterator = root.rglob(pattern) if recursive else root.glob(pattern)
            paths.extend(sorted(path for path in iterator if _is_session_file(path)))
        for value in explicit_files:
            path = Path(str(value)).expanduser().resolve()
            if not path.exists() or not path.is_file():
                raise SourceNotFound(f"OpenClaw session file does not exist: {path}")
            if not _is_session_file(path):
                raise ConnectorConfigError(f"OpenClaw connector only accepts main session jsonl files: {path}")
            paths.append(path)
        if not paths:
            raise ConnectorConfigError("OpenClawConnector requires settings.sessions_dir or settings.session_files")

        refs: list[SourceRef] = []
        for path in _dedupe_paths(paths):
            metadata = _read_session_metadata(path)
            session_id = metadata["session_id"]
            refs.append(
                SourceRef(
                    source_id=f"openclaw:{session_id}",
                    connector=self.name,
                    source_type="openclaw_chat",
                    uri=f"openclaw://sessions/{path.name}",
                    display_name=path.name,
                    metadata={**metadata, "path": str(path), "file_uri": path.as_uri()},
                )
            )
        return sorted(refs, key=lambda ref: ref.uri)

    def fetch(self, ref: SourceRef, config: ConnectorConfig) -> RawSource:
        if ref.connector != self.name or ref.source_type != "openclaw_chat":
            raise ConnectorConfigError("OpenClawConnector can only fetch openclaw_chat source refs")

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
            source_type="openclaw_chat",
            origin=SourceOrigin(
                connector=self.name,
                uri=f"openclaw://sessions/{path.name}",
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
                "title": metadata.get("title") or f"OpenClaw session {metadata['session_id']}",
                "session_id": metadata["session_id"],
                "source_app": "openclaw",
                "model": metadata.get("model"),
                "provider": metadata.get("provider"),
                "cwd": metadata.get("cwd"),
                "message_count": len(payload["turns"]),
            },
            fingerprint=SourceFingerprint(
                content_hash=raw.content_hash,
                connector_version=self.version,
                parser_version="openclaw-jsonl-normalizer@1",
            ),
        )


def _normalized_session_payload(path: Path) -> dict[str, object]:
    read_result = read_jsonl_records(path, source_name="OpenClaw")
    records = read_result.records
    metadata = _session_metadata_from_records(path, records)
    turns: list[dict[str, object]] = []
    for raw_index, record in records:
        turn = _turn_from_record(raw_index, record)
        if turn:
            turn["index"] = len(turns)
            turns.append(turn)
    return {
        "schema_version": "openclaw_session_extract.v1",
        "source_app": "openclaw",
        "session_id": metadata["session_id"],
        "session_start": metadata.get("session_start"),
        "last_updated": metadata.get("last_updated"),
        "message_count": len(turns),
        "metadata": metadata,
        "turns": turns,
        "prefilter_warnings": [*read_result.warnings, *_prefilter_warnings(records, turns)],
    }


def _read_session_metadata(path: Path) -> dict[str, object]:
    read_result = read_jsonl_records(path, source_name="OpenClaw")
    metadata = _session_metadata_from_records(path, read_result.records)
    if read_result.warnings:
        metadata["parse_warnings"] = read_result.warnings
    return metadata


def _session_metadata_from_records(path: Path, records: list[tuple[int, dict[str, object]]]) -> dict[str, object]:
    session_payload: dict[str, object] = {}
    timestamps: list[str] = []
    provider = None
    model = None
    cwd = None
    for _, record in records:
        timestamp = record.get("timestamp")
        if isinstance(timestamp, str) and timestamp:
            timestamps.append(timestamp)
        if record.get("type") == "session":
            session_payload = dict(record)
            if isinstance(record.get("cwd"), str):
                cwd = str(record["cwd"])
        if record.get("type") == "model_change":
            if provider is None and isinstance(record.get("provider"), str):
                provider = str(record["provider"])
            if model is None and isinstance(record.get("modelId"), str):
                model = str(record["modelId"])
        message = record.get("message")
        if isinstance(message, dict):
            if provider is None and isinstance(message.get("provider"), str):
                provider = str(message["provider"])
            if model is None and isinstance(message.get("model"), str):
                model = str(message["model"])

    session_id = str(session_payload.get("id") or path.stem)
    title = _title_from_records(records) or f"OpenClaw session {session_id}"
    return {
        "session_id": session_id,
        "session_start": session_payload.get("timestamp") or (timestamps[0] if timestamps else None),
        "last_updated": timestamps[-1] if timestamps else session_payload.get("timestamp"),
        "message_count": len([1 for raw_index, record in records if _turn_from_record(raw_index, record)]),
        "cwd": cwd,
        "provider": provider,
        "model": model,
        "title": title,
    }


def _turn_from_record(raw_index: int, record: dict[str, object]) -> dict[str, object] | None:
    if record.get("type") != "message":
        return None
    payload = record.get("message")
    if not isinstance(payload, dict):
        return None

    role = payload.get("role")
    if role not in {"user", "assistant"}:
        return None

    text = _message_text(payload.get("content"))
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


def _prefilter_warnings(records: list[tuple[int, dict[str, object]]], turns: list[dict[str, object]]) -> list[str]:
    dropped = max(0, len(records) - len(turns))
    if dropped == 0:
        return []
    return [f"Dropped {dropped} non-substantive OpenClaw records such as session metadata, model changes, tool calls, tool results, or traces."]

def _path_from_ref(ref: SourceRef) -> Path:
    path_value = ref.metadata.get("path")
    if isinstance(path_value, str) and path_value:
        path = Path(path_value).expanduser().resolve()
    else:
        file_uri = ref.metadata.get("file_uri")
        if not isinstance(file_uri, str):
            raise ConnectorConfigError("OpenClaw source ref must include metadata.path or metadata.file_uri")
        try:
            path = path_from_file_uri(file_uri)
        except ValueError as exc:
            raise ConnectorConfigError(f"Expected file URI in OpenClaw source ref, got: {file_uri}") from exc
    if not path.exists() or not path.is_file():
        raise SourceNotFound(f"OpenClaw session file does not exist: {path}")
    if not _is_session_file(path):
        raise ConnectorConfigError(f"OpenClaw connector only accepts main session jsonl files: {path}")
    return path


def _is_session_file(path: Path) -> bool:
    return path.is_file() and path.suffix == ".jsonl" and ".trajectory" not in path.name


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
