from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from knoarbor.core.errors import InvalidConfig, SourceNotFound, VaultPathError


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
    connector_version: str | None = None
    parser_version: str | None = None
    reason: str


class SourceCheckpointPlan(BaseModel):
    source_id: str
    source_file: str
    source_path: str
    should_process: bool
    mode: str
    content_hash: str | None = None
    last_processed_content_hash: str | None = None
    connector_version: str | None = None
    parser_version: str | None = None
    reason: str


class CheckpointStore:
    """Deterministic checkpoint state machine for source ingest windows."""

    def checkpoint_path(self, vault_path: Path, raw_path: str) -> Path:
        path = Path(raw_path)
        resolved = path.expanduser().resolve() if path.is_absolute() else (vault_path / path).resolve()
        try:
            resolved.relative_to(vault_path)
        except ValueError as exc:
            raise VaultPathError("checkpoint_path must be inside vault_path") from exc
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
        *,
        connector_version: str | None = None,
        parser_version: str | None = None,
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
        version_changed = checkpoint_versions_changed(checkpoint, connector_version, parser_version)
        missing_output = checkpoint_missing_output(vault_path, checkpoint)

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
                connector_version=connector_version,
                parser_version=parser_version,
                reason="No checkpoint exists.",
            )

        if version_changed:
            return SessionCheckpointPlan(
                session_id=session_id,
                source_file=source_file,
                source_path=str(source_path),
                should_process=True,
                mode="changed_parser",
                from_raw_index=None,
                to_raw_index=latest_raw_index,
                last_processed_raw_index=int(last_processed),
                content_hash=content_hash,
                connector_version=connector_version,
                parser_version=parser_version,
                reason="Connector or parser version changed after checkpoint.",
            )

        if missing_output:
            return SessionCheckpointPlan(
                session_id=session_id,
                source_file=source_file,
                source_path=str(source_path),
                should_process=True,
                mode="output_missing",
                from_raw_index=None,
                to_raw_index=latest_raw_index,
                last_processed_raw_index=int(last_processed),
                content_hash=content_hash,
                connector_version=connector_version,
                parser_version=parser_version,
                reason=f"Generated output recorded in checkpoint is missing: {missing_output}",
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
                connector_version=connector_version,
                parser_version=parser_version,
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
            connector_version=connector_version,
            parser_version=parser_version,
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
        connector_version: str | None = None,
        parser_version: str | None = None,
    ) -> list[str]:
        sessions = state.setdefault("sessions", {})
        existing = sessions.get(session_id, {})
        merged_pages = merge_pages(existing.get("generated_pages", []), generated_pages, vault_path)
        sessions[session_id] = {
            "source_file": relative_to_vault(vault_path, Path(source_file)),
            "last_processed_raw_index": last_processed_raw_index,
            "last_processed_content_hash": last_processed_content_hash,
            "connector_version": connector_version,
            "parser_version": parser_version,
            "last_processed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "generated_pages": merged_pages,
            "generated_outputs": generated_outputs_manifest(vault_path, merged_pages),
        }
        return merged_pages

    def prepare_source_file(
        self,
        vault_path: Path,
        state: dict[str, Any],
        source_path: Path,
        *,
        content_hash: str | None = None,
        connector_version: str | None = None,
        parser_version: str | None = None,
    ) -> SourceCheckpointPlan:
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

        content_hash = content_hash or file_hash(source_path)
        checkpoint = state.get("sources", {}).get(source_id)
        last_hash = checkpoint.get("last_processed_content_hash") if checkpoint else None
        version_changed = checkpoint_versions_changed(checkpoint, connector_version, parser_version)
        missing_output = checkpoint_missing_output(vault_path, checkpoint)

        if last_hash is None:
            return SourceCheckpointPlan(
                source_id=source_id,
                source_file=source_file,
                source_path=str(source_path),
                should_process=True,
                mode="new_source",
                content_hash=content_hash,
                connector_version=connector_version,
                parser_version=parser_version,
                reason="No source checkpoint exists.",
            )

        if version_changed:
            return SourceCheckpointPlan(
                source_id=source_id,
                source_file=source_file,
                source_path=str(source_path),
                should_process=True,
                mode="changed_parser",
                content_hash=content_hash,
                last_processed_content_hash=str(last_hash),
                connector_version=connector_version,
                parser_version=parser_version,
                reason="Connector or parser version changed after checkpoint.",
            )

        if str(last_hash) == content_hash:
            if missing_output:
                return SourceCheckpointPlan(
                    source_id=source_id,
                    source_file=source_file,
                    source_path=str(source_path),
                    should_process=True,
                    mode="output_missing",
                    content_hash=content_hash,
                    last_processed_content_hash=str(last_hash),
                    connector_version=connector_version,
                    parser_version=parser_version,
                    reason=f"Generated output recorded in checkpoint is missing: {missing_output}",
                )
            return SourceCheckpointPlan(
                source_id=source_id,
                source_file=source_file,
                source_path=str(source_path),
                should_process=False,
                mode="unchanged",
                content_hash=content_hash,
                last_processed_content_hash=str(last_hash),
                connector_version=connector_version,
                parser_version=parser_version,
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
            connector_version=connector_version,
            parser_version=parser_version,
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
        connector_version: str | None = None,
        parser_version: str | None = None,
    ) -> list[str]:
        sources = state.setdefault("sources", {})
        existing = sources.get(source_id, {})
        merged_pages = merge_pages(existing.get("generated_pages", []), generated_pages, vault_path)
        sources[source_id] = {
            "source_file": relative_to_vault(vault_path, Path(source_file)),
            "last_processed_content_hash": content_hash,
            "connector_version": connector_version,
            "parser_version": parser_version,
            "last_processed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "generated_pages": merged_pages,
            "generated_outputs": generated_outputs_manifest(vault_path, merged_pages),
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


def checkpoint_missing_output(vault_path: Path, checkpoint: Any) -> str | None:
    if not isinstance(checkpoint, dict):
        return None
    records = checkpoint_output_records(checkpoint)
    if not records:
        records = [{"path": page} for page in checkpoint.get("generated_pages", []) if str(page).strip()] if "generated_outputs" not in checkpoint else []
    for record in records:
        path = str(record.get("path") or "").strip()
        if not path:
            continue
        if not checkpoint_output_path(vault_path, path).is_file():
            return path
    return None


def generated_outputs_manifest(vault_path: Path, pages: list[str]) -> dict[str, list[dict[str, str]]]:
    manifest: dict[str, list[dict[str, str]]] = {"wiki_pages": [], "source_digests": []}
    for page in pages:
        page_path = checkpoint_output_path(vault_path, page)
        if not page_path.is_file():
            continue
        normalized = normalize_checkpoint_page_path(page)
        entry = {"path": normalized, "content_hash": file_hash(page_path)}
        if is_source_digest_output(normalized):
            manifest["source_digests"].append(entry)
        else:
            manifest["wiki_pages"].append(entry)
    return manifest


def checkpoint_output_records(checkpoint: dict[str, Any]) -> list[dict[str, Any]]:
    outputs = checkpoint.get("generated_outputs")
    if not isinstance(outputs, dict):
        return []
    records: list[dict[str, Any]] = []
    for key in ("source_digest", "source_digests", "wiki_pages", "attachments"):
        value = outputs.get(key)
        if isinstance(value, dict):
            records.append(value)
        elif isinstance(value, list):
            records.extend(item for item in value if isinstance(item, dict))
    return records


def checkpoint_output_path(vault_path: Path, page: str | Path) -> Path:
    normalized = normalize_checkpoint_page_path(page)
    relative = Path(normalized)
    if is_source_digest_output(normalized):
        return vault_path / "wiki" / "sources" / Path(*relative.parts[1:])
    return vault_path / "wiki" / "pages" / relative


def normalize_checkpoint_page_path(page: str | Path) -> str:
    text = str(page).replace("\\", "/").strip().lstrip("/")
    for prefix in ("wiki/pages/", "pages/"):
        if text.startswith(prefix):
            return text.removeprefix(prefix)
    if text.startswith("wiki/sources/"):
        return f"sources/{text.removeprefix('wiki/sources/')}"
    return text


def is_source_digest_output(page: str) -> bool:
    return page.replace("\\", "/").lstrip("/").startswith("sources/")


def checkpoint_versions_changed(checkpoint: Any, connector_version: str | None, parser_version: str | None) -> bool:
    if not isinstance(checkpoint, dict):
        return False
    if connector_version and checkpoint.get("connector_version") not in {None, connector_version}:
        return True
    if parser_version and checkpoint.get("parser_version") not in {None, parser_version}:
        return True
    return False


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
