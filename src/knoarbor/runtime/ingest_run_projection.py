from __future__ import annotations

from datetime import datetime
from pathlib import Path
from knoarbor.core.schemas.run_monitor import RunRecord
from knoarbor.runtime.run_monitor import read_run
from knoarbor.runtime.transactional_ingest import TransactionalIngestStore


_STATUS = {
    "queued": "queued",
    "running": "running",
    "completed": "completed",
    "partially_failed": "partially_failed",
    "failed": "failed",
    "paused_rate_limited": "failed",
    "recovery_needed": "failed",
    "cancelled": "cancelled",
}


def project_ingest_attempt(vault_path: Path, attempt_id: str) -> RunRecord:
    """Build an ingest run read model from the transactional authority."""

    vault = vault_path.expanduser().resolve()
    store = TransactionalIngestStore(vault)
    store.reap_expired_attempts()
    attempt, task = store.attempt_projection(attempt_id)
    try:
        observed = read_run(vault, attempt_id)
    except Exception:
        observed = None

    return _project_attempt(attempt, task, observed)


def project_ingest_attempts(vault_path: Path, *, limit: int = 50) -> list[RunRecord]:
    store = TransactionalIngestStore(vault_path)
    store.reap_expired_attempts()
    return [_project_attempt(attempt, task, None) for attempt, task in store.attempt_projections(limit=limit)]


def _project_attempt(attempt: dict[str, object], task: dict[str, object], observed: RunRecord | None) -> RunRecord:
    attempt_id = str(attempt["attempt_id"])
    state = str(attempt["state"])
    status = _STATUS.get(state, "failed")
    created = _timestamp(float(attempt["created_at"]))
    updated = _timestamp(float(attempt["updated_at"]))
    finished = _timestamp(float(attempt["finished_at"])) if attempt.get("finished_at") is not None else None
    result = attempt.get("result") if isinstance(attempt.get("result"), dict) else {}
    metadata = dict(observed.metadata) if observed else {}
    metadata.update(
        {
            "ingest_task_id": str(task["task_id"]),
            "input_generation_id": str(task.get("input_generation_id") or ""),
        }
    )
    error_info = dict(observed.error_info) if observed else {}
    if state in {"paused_rate_limited", "recovery_needed"}:
        error_info = {
            "code": "KA-INGEST-RECOVERY-REQUIRED",
            "retryable": True,
            "message": str(attempt.get("error") or _message(state)),
        }
    return RunRecord(
        run_id=attempt_id,
        flow="ingest",
        status=status,  # type: ignore[arg-type]
        stage=state,
        message=_message(state),
        started_at=observed.started_at if observed and state == "running" else created,
        updated_at=updated,
        last_heartbeat_at=observed.last_heartbeat_at if observed and state == "running" else updated,
        finished_at=finished,
        elapsed_seconds=max(0.0, (float(attempt.get("finished_at") or attempt["updated_at"]) - float(attempt["created_at"]))),
        progress=observed.progress if observed else {},
        metrics=dict(observed.metrics) if observed else {},
        metadata=metadata,
        result_summary=dict(result),
        error=str(attempt.get("error") or "") or None,
        error_info=error_info,
        cancel_requested=bool(task.get("cancel_requested")) and str(task["current_attempt_id"]) == attempt_id,
    )


def _timestamp(value: float) -> str:
    return datetime.fromtimestamp(value).isoformat(timespec="seconds")


def _message(state: str) -> str:
    return {
        "queued": "ingest run queued.",
        "running": "ingest run started.",
        "completed": "ingest run completed.",
        "partially_failed": "ingest run partially failed.",
        "cancelled": "ingest run cancelled.",
        "paused_rate_limited": "ingest run paused after provider rate limiting.",
        "recovery_needed": "ingest run requires recovery.",
        "failed": "ingest run failed.",
    }.get(state, "ingest run state is unavailable.")
