from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from knoarbor.storage.ledger import append_jsonl_ledger, read_jsonl_ledger
from knoarbor.storage.wiki_index import relative_wiki_path


def write_ingest_execution_ledger(vault_path: Path, result: Any, *, run_id: str, ledger_path: str) -> str:
    """Append one source-level execution record per source.

    The execution ledger is not a checkpoint. It records what happened during a
    run so UI/API/CLI can explain failures and start recovery runs without
    interpreting Markdown reports.
    """

    path: Path | None = None
    created_at = datetime.now().isoformat(timespec="seconds")
    for source_result in getattr(result, "results", []) or []:
        path = append_jsonl_ledger(
            vault_path,
            ledger_path,
            build_ingest_execution_record(source_result, run_id=run_id, created_at=created_at),
        )
    if path is None:
        path = append_jsonl_ledger(
            vault_path,
            ledger_path,
            {
                "schema_version": "ingest_execution.v1",
                "run_id": run_id,
                "created_at": created_at,
                "status": "empty",
                "can_rerun": False,
            },
        )
    return relative_wiki_path(vault_path, path)


def build_ingest_execution_record(source_result: Any, *, run_id: str, created_at: str) -> dict[str, object]:
    segments = [_compact_segment(segment) for segment in getattr(source_result, "segments", []) or []]
    status = str(getattr(source_result, "status", "unknown"))
    can_rerun = _can_rerun_source(source_result, segments)
    return {
        "schema_version": "ingest_execution.v1",
        "run_id": run_id,
        "created_at": created_at,
        "connector": getattr(source_result, "connector", ""),
        "source_id": getattr(source_result, "source_id", ""),
        "source_file": getattr(source_result, "source_file", ""),
        "status": status,
        "mode": getattr(source_result, "mode", ""),
        "should_process": bool(getattr(source_result, "should_process", False)),
        "wrote": bool(getattr(source_result, "wrote", False)),
        "generated_pages": list(getattr(source_result, "generated_pages", []) or []),
        "touched_pages": list(getattr(source_result, "touched_pages", []) or []),
        "error_stage": getattr(source_result, "error_stage", None),
        "error_code": getattr(source_result, "error_code", None),
        "error_category": getattr(source_result, "error_category", None),
        "error_retryable": bool(getattr(source_result, "error_retryable", False)),
        "error_hint": getattr(source_result, "error_hint", None),
        "error_type": getattr(source_result, "error_type", None),
        "error_message": getattr(source_result, "error_message", None),
        "segments": segments,
        "segment_count": len(segments),
        "failed_segment_count": sum(1 for segment in segments if segment.get("status") == "failed"),
        "can_rerun": can_rerun,
        "recovery_action": _recovery_action(source_result, can_rerun),
    }


def failed_execution_records(vault_path: Path, ledger_path: str, *, run_id: str) -> list[dict[str, object]]:
    return [
        record
        for record in read_jsonl_ledger(vault_path, ledger_path)
        if record.get("run_id") == run_id and record.get("status") == "failed"
    ]


def _compact_segment(segment: object) -> dict[str, object]:
    data = segment if isinstance(segment, dict) else {}
    return {
        "segment_id": data.get("segment_id"),
        "index": data.get("index"),
        "title": data.get("title"),
        "status": data.get("status"),
        "chars": data.get("chars"),
        "error_stage": data.get("error_stage"),
        "error_code": data.get("error_code"),
        "error_category": data.get("error_category"),
        "error_retryable": data.get("error_retryable"),
        "error_hint": data.get("error_hint"),
        "error_type": data.get("error_type"),
        "error_message": data.get("error_message"),
        "generated_pages": data.get("generated_pages") or [],
    }


def _can_rerun_source(source_result: Any, segments: list[dict[str, object]]) -> bool:
    if getattr(source_result, "status", None) != "failed":
        return False
    if bool(getattr(source_result, "error_retryable", False)):
        return True
    return any(bool(segment.get("error_retryable")) for segment in segments)


def _recovery_action(source_result: Any, can_rerun: bool) -> str:
    if can_rerun:
        return "rerun_source"
    if getattr(source_result, "status", None) != "failed":
        return "none"
    stage = str(getattr(source_result, "error_stage", "") or "")
    if stage in {"connector", "document_processing"}:
        return "fix_input_or_config"
    return "inspect_error"
