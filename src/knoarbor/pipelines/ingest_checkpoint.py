from __future__ import annotations

import json
from pathlib import Path

from knoarbor.core.checkpoints import CheckpointStore, session_unit_raw_index
from knoarbor.core.errors import PolicyRejection
from knoarbor.core.schemas.sources import SourceCheckpointWindow, SourceContent, SourceDocument, SourceFingerprint
from knoarbor.pipelines.source import SourcePipelineItem


def _prepare_checkpoint_plan(
    checkpoint_store: CheckpointStore,
    *,
    connector_name: str,
    item: SourcePipelineItem,
    vault_path: Path,
    state: dict[str, object],
) -> dict[str, object]:
    source_path = Path(item.raw.raw_path)
    fingerprint = item.document.fingerprint
    if _uses_session_checkpoint(connector_name, item.document):
        payload = json.loads(item.document.content.text)
        if not isinstance(payload, dict):
            raise PolicyRejection("Session source document content must be a JSON object")
        plan = checkpoint_store.prepare_session_payload(
            vault_path,
            state,
            source_path,
            payload,
            connector_version=fingerprint.connector_version,
            parser_version=fingerprint.parser_version,
        )
        return {
            "checkpoint_type": "session",
            "source_id": item.document.source_id,
            "source_file": plan.source_file,
            "should_process": plan.should_process,
            "mode": plan.mode,
            "reason": plan.reason,
            "content_hash": plan.content_hash,
            "session_id": plan.session_id,
            "from_raw_index": plan.from_raw_index,
            "to_raw_index": plan.to_raw_index,
            "last_processed_raw_index": plan.last_processed_raw_index,
            "connector_version": plan.connector_version,
            "parser_version": plan.parser_version,
        }
    plan = checkpoint_store.prepare_source_file(
        vault_path,
        state,
        source_path,
        content_hash=fingerprint.content_hash,
        connector_version=fingerprint.connector_version,
        parser_version=fingerprint.parser_version,
    )
    return {
        "checkpoint_type": "source",
        "source_id": plan.source_id,
        "source_file": plan.source_file,
        "should_process": plan.should_process,
        "mode": plan.mode,
        "reason": plan.reason,
        "content_hash": plan.content_hash,
        "last_processed_content_hash": plan.last_processed_content_hash,
        "connector_version": plan.connector_version,
        "parser_version": plan.parser_version,
    }


def _uses_session_checkpoint(connector_name: str, document: SourceDocument) -> bool:
    return connector_name in {"hermes", "codex", "openclaw", "claude_code", "knoarbor_chat", "generic_chat"} or document.source_type in {
        "hermes_chat",
        "codex_chat",
        "openclaw_chat",
        "claude_code_chat",
        "knoarbor_chat",
        "generic_chat",
    }


def _document_for_checkpoint(document: SourceDocument, checkpoint_plan: dict[str, object]) -> SourceDocument:
    if checkpoint_plan.get("checkpoint_type") != "session":
        return document
    from_raw_index = checkpoint_plan.get("from_raw_index")
    to_raw_index = checkpoint_plan.get("to_raw_index")
    if not isinstance(to_raw_index, int):
        return document
    start = from_raw_index if isinstance(from_raw_index, int) else 0
    payload = json.loads(document.content.text)
    units_key, units = _session_units_for_document(payload if isinstance(payload, dict) else {})
    if not units_key or not isinstance(units, list):
        return document
    payload[units_key] = [
        unit
        for index, unit in enumerate(units)
        if start <= session_unit_raw_index(unit, index) <= to_raw_index
    ]
    sections = [
        section
        for index, section in enumerate(document.content.sections)
        if start <= session_unit_raw_index(section, index) <= to_raw_index
    ]
    metadata = {
        **document.metadata,
        "checkpoint_type": "session",
        "checkpoint_mode": checkpoint_plan.get("mode"),
        "from_raw_index": start,
        "to_raw_index": to_raw_index,
        "total_message_count": len(units),
    }
    return document.model_copy(
        update={
            "content": SourceContent(format="json", text=json.dumps(payload, ensure_ascii=False, indent=2), sections=sections),
            "metadata": metadata,
            "fingerprint": SourceFingerprint(
                content_hash=str(checkpoint_plan.get("content_hash") or document.fingerprint.content_hash),
                connector_version=document.fingerprint.connector_version,
                parser_version=document.fingerprint.parser_version,
            ),
            "checkpoint": SourceCheckpointWindow(
                mode="incremental" if checkpoint_plan.get("mode") == "incremental" else "full",
                from_index=start,
                to_index=to_raw_index,
            ),
        }
    )


def _session_units_for_document(payload: dict[str, object]) -> tuple[str | None, list[object] | None]:
    for key in ("messages", "turns"):
        value = payload.get(key)
        if isinstance(value, list):
            return key, value
    return None, None


def _commit_checkpoint_plan(
    checkpoint_store: CheckpointStore,
    *,
    vault_path: Path,
    state: dict[str, object],
    checkpoint_plan: dict[str, object],
    generated_pages: list[str],
    fallback_content_hash: str,
) -> None:
    if checkpoint_plan.get("checkpoint_type") == "session":
        session_id = str(checkpoint_plan.get("session_id") or checkpoint_plan["source_id"])
        to_raw_index = checkpoint_plan.get("to_raw_index")
        if isinstance(to_raw_index, int):
            checkpoint_store.commit_session(
                vault_path,
                state,
                session_id=session_id,
                source_file=str(checkpoint_plan["source_file"]),
                last_processed_raw_index=to_raw_index,
                last_processed_content_hash=str(checkpoint_plan.get("content_hash") or fallback_content_hash),
                generated_pages=generated_pages,
                connector_version=_optional_str(checkpoint_plan.get("connector_version")),
                parser_version=_optional_str(checkpoint_plan.get("parser_version")),
            )
        return
    checkpoint_store.commit_source(
        vault_path,
        state,
        source_id=str(checkpoint_plan["source_id"]),
        source_file=str(checkpoint_plan["source_file"]),
        content_hash=str(checkpoint_plan.get("content_hash") or fallback_content_hash),
        generated_pages=generated_pages,
        connector_version=_optional_str(checkpoint_plan.get("connector_version")),
        parser_version=_optional_str(checkpoint_plan.get("parser_version")),
    )


def _should_commit_checkpoint_result(result: object, *, write: bool) -> bool:
    """Return whether a completed source result may advance its source checkpoint."""

    if not write:
        return False
    generated_pages = getattr(result, "generated_pages", None)
    if isinstance(generated_pages, list) and generated_pages:
        return True
    return (
        getattr(result, "status", None) == "skipped"
        and bool(getattr(result, "should_process", False))
        and getattr(result, "semantic_result", None) is not None
        and bool(getattr(result, "semantic_skip_reason", None))
        and not getattr(result, "error_stage", None)
    )


def _checkpoint_payload(checkpoint_plan: dict[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in checkpoint_plan.items()
        if key
        in {
            "checkpoint_type",
            "mode",
            "content_hash",
            "session_id",
            "from_raw_index",
            "to_raw_index",
            "last_processed_raw_index",
            "last_processed_content_hash",
            "connector_version",
            "parser_version",
        }
        and value is not None
    }


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
