from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from knoarbor.core.errors import InvalidConfig, SourceNotFound, VaultPathError
from knoarbor.runtime import vault_write_lock


class SessionCheckpointPlan(BaseModel):
    session_id: str
    source_file: str
    source_path: str
    should_process: bool
    mode: str
    from_raw_index: int | None = None
    to_raw_index: int | None = None
    last_processed_raw_index: int | None = None
    content_hash: str | None = None
    reason: str


class SourceCheckpointPlan(BaseModel):
    source_id: str
    source_file: str
    source_path: str
    should_process: bool
    mode: str
    content_hash: str | None = None
    last_processed_content_hash: str | None = None
    reason: str


class CheckpointStore:
    """Deterministic checkpoint state machine for source ingest windows."""

    def checkpoint_path(self, vault_path: Path, raw_path: str) -> Path:
        path = Path(raw_path)
        resolved = path.expanduser().resolve() if path.is_absolute() else (vault_path / path).resolve()
        try:
            resolved.relative_to(vault_path)
        except ValueError as exc:
            raise VaultPathError("checkpoint_path must be inside obsidian_vault_path") from exc
        return resolved

    def read_state(self, checkpoint_path: Path) -> dict[str, Any]:
        if not checkpoint_path.exists():
            return {"sessions": {}, "sources": {}}
        state = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            raise InvalidConfig("checkpoint state must be a JSON object")
        state.setdefault("sessions", {})
        state.setdefault("sources", {})
        return state

    def write_state(self, vault_path: Path, checkpoint_path: Path, state: dict[str, Any]) -> None:
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        with vault_write_lock(vault_path):
            checkpoint_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def prepare_session_file(self, vault_path: Path, state: dict[str, Any], source_path: Path) -> SessionCheckpointPlan:
        if not source_path.exists() or not source_path.is_file():
            raise SourceNotFound(f"Session file does not exist: {source_path}")

        payload = json.loads(source_path.read_text(encoding="utf-8"))
        return self.prepare_session_payload(vault_path, state, source_path, payload)

    def prepare_session_payload(
        self,
        vault_path: Path,
        state: dict[str, Any],
        source_path: Path,
        payload: dict[str, Any],
    ) -> SessionCheckpointPlan:
        if not isinstance(payload, dict):
            raise InvalidConfig(f"Session payload must be a JSON object: {source_path}")
        session_id = str(payload.get("session_id") or payload.get("id") or source_path.stem.replace("session_", ""))
        messages = session_message_units(payload)
        source_file = relative_to_vault(vault_path, source_path)

        if not messages:
            return SessionCheckpointPlan(
                session_id=session_id,
                source_file=source_file,
                source_path=str(source_path),
                should_process=False,
                mode="empty",
                reason="Session has no messages.",
            )

        latest_raw_index = max(session_unit_raw_index(message, index) for index, message in enumerate(messages))
        content_hash = message_window_hash(messages, 0, latest_raw_index)
        checkpoint = state.get("sessions", {}).get(session_id)
        last_processed = checkpoint.get("last_processed_raw_index") if checkpoint else None

        if last_processed is None:
            return SessionCheckpointPlan(
                session_id=session_id,
                source_file=source_file,
                source_path=str(source_path),
                should_process=True,
                mode="new_session",
                from_raw_index=None,
                to_raw_index=latest_raw_index,
                content_hash=content_hash,
                reason="No checkpoint exists.",
            )

        if latest_raw_index <= int(last_processed):
            return SessionCheckpointPlan(
                session_id=session_id,
                source_file=source_file,
                source_path=str(source_path),
                should_process=False,
                mode="unchanged",
                from_raw_index=int(last_processed) + 1,
                to_raw_index=latest_raw_index,
                last_processed_raw_index=int(last_processed),
                content_hash=content_hash,
                reason="No new messages after checkpoint.",
            )

        from_raw_index = int(last_processed) + 1
        incremental_hash = message_window_hash(messages, from_raw_index, latest_raw_index)
        return SessionCheckpointPlan(
            session_id=session_id,
            source_file=source_file,
            source_path=str(source_path),
            should_process=True,
            mode="incremental",
            from_raw_index=from_raw_index,
            to_raw_index=latest_raw_index,
            last_processed_raw_index=int(last_processed),
            content_hash=incremental_hash,
            reason="New messages found after checkpoint.",
        )

    def commit_session(
        self,
        vault_path: Path,
        state: dict[str, Any],
        *,
        session_id: str,
        source_file: str,
        last_processed_raw_index: int,
        last_processed_content_hash: str | None,
        generated_pages: list[str],
    ) -> list[str]:
        sessions = state.setdefault("sessions", {})
        existing = sessions.get(session_id, {})
        merged_pages = merge_pages(existing.get("generated_pages", []), generated_pages, vault_path)
        sessions[session_id] = {
            "source_file": relative_to_vault(vault_path, Path(source_file)),
            "last_processed_raw_index": last_processed_raw_index,
            "last_processed_content_hash": last_processed_content_hash,
            "last_processed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "generated_pages": merged_pages,
        }
        return merged_pages

    def prepare_source_file(self, vault_path: Path, state: dict[str, Any], source_path: Path) -> SourceCheckpointPlan:
        if not source_path.exists() or not source_path.is_file():
            raise SourceNotFound(f"Source file does not exist: {source_path}")

        source_file = relative_to_vault(vault_path, source_path)
        source_id = source_file
        if source_path.stat().st_size == 0:
            return SourceCheckpointPlan(
                source_id=source_id,
                source_file=source_file,
                source_path=str(source_path),
                should_process=False,
                mode="empty",
                reason="Source file is empty.",
            )

        content_hash = file_hash(source_path)
        checkpoint = state.get("sources", {}).get(source_id)
        last_hash = checkpoint.get("last_processed_content_hash") if checkpoint else None

        if last_hash is None:
            return SourceCheckpointPlan(
                source_id=source_id,
                source_file=source_file,
                source_path=str(source_path),
                should_process=True,
                mode="new_source",
                content_hash=content_hash,
                reason="No source checkpoint exists.",
            )

        if str(last_hash) == content_hash:
            return SourceCheckpointPlan(
                source_id=source_id,
                source_file=source_file,
                source_path=str(source_path),
                should_process=False,
                mode="unchanged",
                content_hash=content_hash,
                last_processed_content_hash=str(last_hash),
                reason="Source content hash matches checkpoint.",
            )

        return SourceCheckpointPlan(
            source_id=source_id,
            source_file=source_file,
            source_path=str(source_path),
            should_process=True,
            mode="changed",
            content_hash=content_hash,
            last_processed_content_hash=str(last_hash),
            reason="Source content hash changed after checkpoint.",
        )

    def commit_source(
        self,
        vault_path: Path,
        state: dict[str, Any],
        *,
        source_id: str,
        source_file: str,
        content_hash: str,
        generated_pages: list[str],
    ) -> list[str]:
        sources = state.setdefault("sources", {})
        existing = sources.get(source_id, {})
        merged_pages = merge_pages(existing.get("generated_pages", []), generated_pages, vault_path)
        sources[source_id] = {
            "source_file": relative_to_vault(vault_path, Path(source_file)),
            "last_processed_content_hash": content_hash,
            "last_processed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "generated_pages": merged_pages,
        }
        return merged_pages


def relative_to_vault(vault_path: Path, path: Path) -> str:
    resolved = path.expanduser().resolve() if path.is_absolute() else (vault_path / path).resolve()
    try:
        return resolved.relative_to(vault_path).as_posix()
    except ValueError:
        return str(path)


def merge_pages(existing: Any, new_pages: list[str], vault_path: Path) -> list[str]:
    pages = [str(page) for page in existing if str(page).strip()] if isinstance(existing, list) else []
    for page in new_pages:
        normalized = relative_to_vault(vault_path, Path(page))
        if normalized not in pages:
            pages.append(normalized)
    return pages


def message_window_hash(messages: list[Any], start: int, end: int) -> str:
    window = [
        message
        for index, message in enumerate(messages)
        if start <= session_unit_raw_index(message, index) <= end
    ]
    encoded = json.dumps(window, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:12]


def session_message_units(payload: dict[str, Any]) -> list[Any]:
    """Return connector-normalized conversation units for append-only checkpoints."""

    for key in ("messages", "turns"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def session_unit_raw_index(unit: Any, fallback: int) -> int:
    if isinstance(unit, dict):
        value = unit.get("raw_index")
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return fallback


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:12]
