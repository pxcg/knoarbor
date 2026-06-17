from __future__ import annotations

import contextlib
import contextvars
import json
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from knoarbor.core.errors import RunNotFound, error_info
from knoarbor.core.schemas.run_monitor import ACTIVE_RUN_STATUSES, TERMINAL_RUN_STATUSES, RunEvent, RunFlow, RunListResponse, RunProgress, RunRecord, RunStatus
from knoarbor.runtime.events import KNOWN_RUN_EVENT_TYPES
from .logging import runtime_logger


_CURRENT_MONITOR: contextvars.ContextVar[RunMonitor | None] = contextvars.ContextVar("knoarbor_run_monitor", default=None)
logger = runtime_logger(__name__)

STALE_CANCELLING_SECONDS = 30
STALE_ACTIVE_SECONDS = 600


class RunCancelled(RuntimeError):
    """Raised when a cooperative pipeline observes a cancellation request."""


class RunMonitor:
    """Filesystem-backed run state, event log, and heartbeat boundary.

    The monitor is intentionally small and local-first: pipelines emit stage
    events, semantic calls emit model wait events, and API/UI/CLI read the same
    JSON files. It does not own workflow decisions or retry policy.
    """

    def __init__(self, *, vault_path: Path, flow: RunFlow, run_id: str | None = None, metadata: dict[str, Any] | None = None) -> None:
        self.vault_path = vault_path.expanduser().resolve()
        self.flow = flow
        self.run_id = run_id or _new_run_id()
        self.metadata = metadata or {}
        self.run_dir = runs_dir(self.vault_path)
        self.record_path = self.run_dir / f"{self.run_id}.json"
        self.events_path = self.run_dir / f"{self.run_id}.events.jsonl"
        self._lock = threading.Lock()
        self._sequence = self._last_event_sequence()
        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None

    def start(self, *, message: str = "Run started.") -> RunRecord:
        now = _now()
        record = RunRecord(
            run_id=self.run_id,
            flow=self.flow,
            status="running",
            stage="started",
            message=message,
            started_at=now,
            updated_at=now,
            last_heartbeat_at=now,
            metadata=self.metadata,
        )
        self._write_record(record)
        self.event("run_started", message=message, status="running", stage="started")
        logger.info(
            "run_started run_id=%s flow=%s vault=%s metadata=%s",
            self.run_id,
            self.flow,
            self.vault_path,
            _compact_mapping(self.metadata),
        )
        self._start_heartbeat_loop()
        return record

    def queue(self, *, message: str = "Run queued.") -> RunRecord:
        now = _now()
        record = RunRecord(
            run_id=self.run_id,
            flow=self.flow,
            status="queued",
            stage="queued",
            message=message,
            started_at=now,
            updated_at=now,
            last_heartbeat_at=now,
            metadata=self.metadata,
        )
        self._write_record(record)
        self.event("run_queued", message=message, status="queued", stage="queued")
        logger.info("run_queued run_id=%s flow=%s vault=%s metadata=%s", self.run_id, self.flow, self.vault_path, _compact_mapping(self.metadata))
        return record

    def heartbeat(
        self,
        *,
        status: RunStatus | None = None,
        stage: str | None = None,
        current_item: str | None = None,
        message: str | None = None,
        progress: dict[str, Any] | RunProgress | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> RunRecord:
        with self._lock:
            record = self._read_record_unlocked()
            if record.cancel_requested and record.status not in TERMINAL_RUN_STATUSES:
                record.status = "cancelling"
            elif status:
                record.status = status
            if stage is not None:
                record.stage = stage
            if current_item is not None:
                record.current_item = _compact_display_text(current_item)
            if message is not None:
                record.message = message
            if progress is not None:
                record.progress = _progress(progress)
            if metrics:
                record.metrics = {**record.metrics, **metrics}
            now = _now()
            record.updated_at = now
            record.last_heartbeat_at = now
            record.elapsed_seconds = _elapsed(record.started_at)
            self._write_record_unlocked(record)
            return record

    def event(
        self,
        event_type: str,
        *,
        message: str = "",
        status: RunStatus | None = None,
        stage: str | None = None,
        current_item: str | None = None,
        progress: dict[str, Any] | RunProgress | None = None,
        metrics: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> RunEvent:
        if event_type not in KNOWN_RUN_EVENT_TYPES:
            logger.warning("unknown_run_event_type run_id=%s flow=%s event=%s", self.run_id, self.flow, event_type)
        record = self.heartbeat(
            status=status,
            stage=stage,
            current_item=current_item,
            message=message or None,
            progress=progress,
            metrics=metrics,
        )
        with self._lock:
            self._sequence += 1
            event = RunEvent(
                run_id=self.run_id,
                sequence=self._sequence,
                created_at=_now(),
                event_type=event_type,
                status=record.status,
                stage=record.stage,
                message=message,
                current_item=record.current_item,
                progress=record.progress,
                metrics=metrics or {},
                payload=payload or {},
            )
            self.run_dir.mkdir(parents=True, exist_ok=True)
            with self.events_path.open("a", encoding="utf-8") as handle:
                handle.write(event.model_dump_json() + "\n")
            logger.info("run_event run_id=%s flow=%s event=%s stage=%s status=%s message=%s", self.run_id, self.flow, event_type, record.stage, record.status, message)
            return event

    def _append_event_for_record(
        self,
        record: RunRecord,
        event_type: str,
        *,
        message: str = "",
        payload: dict[str, Any] | None = None,
    ) -> RunEvent:
        if event_type not in KNOWN_RUN_EVENT_TYPES:
            logger.warning("unknown_run_event_type run_id=%s flow=%s event=%s", self.run_id, self.flow, event_type)
        with self._lock:
            self._sequence += 1
            event = RunEvent(
                run_id=self.run_id,
                sequence=self._sequence,
                created_at=_now(),
                event_type=event_type,
                status=record.status,
                stage=record.stage,
                message=message,
                current_item=record.current_item,
                progress=record.progress,
                metrics={},
                payload=payload or {},
            )
            self.run_dir.mkdir(parents=True, exist_ok=True)
            with self.events_path.open("a", encoding="utf-8") as handle:
                handle.write(event.model_dump_json() + "\n")
            logger.info("run_event run_id=%s flow=%s event=%s stage=%s status=%s message=%s", self.run_id, self.flow, event_type, record.stage, record.status, message)
            return event

    def complete(self, *, message: str = "Run completed.", result_summary: dict[str, Any] | None = None, metrics: dict[str, Any] | None = None) -> RunRecord:
        return self._finish(
            status="completed",
            stage="completed",
            event_type="run_completed",
            message=message,
            result_summary=result_summary,
            metrics=metrics,
        )

    def partially_fail(
        self,
        *,
        message: str = "Run partially failed.",
        result_summary: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> RunRecord:
        """Finish a run that produced usable output but had source-level failures."""
        return self._finish(
            status="partially_failed",
            stage="partially_failed",
            event_type="run_partially_failed",
            message=message,
            result_summary=result_summary,
            metrics=metrics,
        )

    def fail(self, exc: BaseException, *, stage: str = "failed") -> RunRecord:
        self._stop_heartbeat_loop()
        status: RunStatus = "cancelled" if isinstance(exc, RunCancelled) else "failed"
        info = error_info(exc)
        public_info = _public_error_info(info)
        with self._lock:
            record = self._read_record_unlocked()
            now = _now()
            record.status = status
            record.stage = stage if status == "failed" else "cancelled"
            record.message = str(public_info.get("message") or exc)
            record.error = _format_error(public_info)
            record.error_info = public_info
            record.updated_at = now
            record.last_heartbeat_at = now
            record.finished_at = now
            record.elapsed_seconds = _elapsed(record.started_at)
            self._write_record_unlocked(record)
        self.event(
            "run_failed" if status == "failed" else "run_cancelled",
            message=str(public_info.get("message") or exc),
            status=status,
            stage=record.stage,
            payload={"error": public_info},
        )
        logger.error(
            "run_finished run_id=%s flow=%s status=%s stage=%s elapsed_seconds=%.2f error_code=%s retryable=%s message=%s action=%s",
            self.run_id,
            self.flow,
            status,
            record.stage,
            record.elapsed_seconds,
            public_info.get("code", "-"),
            public_info.get("retryable", "-"),
            public_info.get("message") or str(exc),
            public_info.get("action") or "-",
        )
        self._stop_heartbeat_loop()
        return self.read()

    def request_cancel(self) -> RunRecord:
        with self._lock:
            record = self._read_record_unlocked()
            if record.status in TERMINAL_RUN_STATUSES:
                return record
            if record.cancel_requested and record.status == "cancelling":
                return record
            if record.status not in TERMINAL_RUN_STATUSES:
                record.cancel_requested = True
                record.status = "cancelling"
                record.message = "Cancellation requested."
                record.updated_at = _now()
                self._write_record_unlocked(record)
        self._append_event_for_record(record, "cancel_requested", message="Cancellation requested.")
        return self.read()

    def raise_if_cancelled(self) -> None:
        record = self.read()
        if record.cancel_requested or record.status == "cancelling":
            raise RunCancelled(f"Run {self.run_id} was cancelled.")

    def read(self) -> RunRecord:
        with self._lock:
            return self._read_record_unlocked()

    def _read_record_unlocked(self) -> RunRecord:
        if not self.record_path.exists():
            now = _now()
            return RunRecord(
                run_id=self.run_id,
                flow=self.flow,
                status="queued",
                stage="queued",
                started_at=now,
                updated_at=now,
                last_heartbeat_at=now,
                metadata=self.metadata,
            )
        return RunRecord.model_validate(json.loads(self.record_path.read_text(encoding="utf-8")))

    def _write_record(self, record: RunRecord) -> None:
        with self._lock:
            self._write_record_unlocked(record)

    def _write_record_unlocked(self, record: RunRecord) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        tmp = self.record_path.with_suffix(".json.tmp")
        tmp.write_text(record.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(self.record_path)

    def _start_heartbeat_loop(self) -> None:
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            return
        self._heartbeat_stop.clear()
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, name=f"knoarbor-heartbeat-{self.run_id}", daemon=True)
        self._heartbeat_thread.start()

    def _stop_heartbeat_loop(self) -> None:
        self._heartbeat_stop.set()

    def _heartbeat_loop(self) -> None:
        while not self._heartbeat_stop.wait(5):
            try:
                record = self.read()
                if record.status in TERMINAL_RUN_STATUSES:
                    return
                self.heartbeat()
            except Exception as exc:
                logger.exception("run_heartbeat_failed run_id=%s flow=%s error=%s", self.run_id, self.flow, exc)
                return

    def _finish(
        self,
        *,
        status: RunStatus,
        stage: str,
        event_type: str,
        message: str,
        result_summary: dict[str, Any] | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> RunRecord:
        self._stop_heartbeat_loop()
        with self._lock:
            record = self._read_record_unlocked()
            now = _now()
            record.status = status
            record.stage = stage
            record.message = message
            record.updated_at = now
            record.last_heartbeat_at = now
            record.finished_at = now
            record.elapsed_seconds = _elapsed(record.started_at)
            record.result_summary = result_summary or {}
            if metrics:
                record.metrics = {**record.metrics, **metrics}
            self._write_record_unlocked(record)
        self.event(event_type, message=message, status=status, stage=stage, payload=result_summary or {})
        logger.info(
            "run_finished run_id=%s flow=%s status=%s stage=%s elapsed_seconds=%.2f summary=%s metrics=%s report=%s",
            self.run_id,
            self.flow,
            status,
            stage,
            record.elapsed_seconds,
            _compact_mapping(record.result_summary),
            _compact_mapping(record.metrics),
            _report_path(record.result_summary),
        )
        self._stop_heartbeat_loop()
        return self.read()

    def _last_event_sequence(self) -> int:
        if not self.events_path.exists():
            return 0
        last = 0
        for line in self.events_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                sequence = item.get("sequence")
                if isinstance(sequence, int):
                    last = max(last, sequence)
            except json.JSONDecodeError as exc:
                logger.warning("run_event_sequence_skipped run_id=%s path=%s error=%s", self.run_id, self.events_path, exc)
                continue
        return last


@contextlib.contextmanager
def run_monitor_context(monitor: RunMonitor | None) -> Iterator[None]:
    token = _CURRENT_MONITOR.set(monitor)
    try:
        yield
    finally:
        _CURRENT_MONITOR.reset(token)


def current_run_monitor() -> RunMonitor | None:
    return _CURRENT_MONITOR.get()


def runs_dir(vault_path: Path) -> Path:
    return vault_path.expanduser().resolve() / ".knoarbor" / "runs"


def list_runs(vault_path: Path, *, limit: int = 50, active_only: bool = False) -> RunListResponse:
    records = []
    for path in sorted(runs_dir(vault_path).glob("*.json"), reverse=True):
        try:
            record = _reconcile_stale_record(path, RunRecord.model_validate(json.loads(path.read_text(encoding="utf-8"))))
        except Exception as exc:
            logger.warning("run_record_skipped path=%s error=%s", path, exc)
            continue
        if active_only and record.status not in ACTIVE_RUN_STATUSES:
            continue
        records.append(record)
        if len(records) >= limit:
            break
    return RunListResponse(runs=records)


def read_run(vault_path: Path, run_id: str) -> RunRecord:
    path = runs_dir(vault_path) / f"{run_id}.json"
    if not path.exists():
        raise RunNotFound(f"Run does not exist: {run_id}")
    return _reconcile_stale_record(path, RunRecord.model_validate(json.loads(path.read_text(encoding="utf-8"))))


def read_run_events(vault_path: Path, run_id: str, *, after: int = 0, limit: int = 200) -> list[RunEvent]:
    path = runs_dir(vault_path) / f"{run_id}.events.jsonl"
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = RunEvent.model_validate(json.loads(line))
        if event.sequence > after:
            events.append(event)
        if len(events) >= limit:
            break
    return events


def request_cancel(vault_path: Path, run_id: str) -> RunRecord:
    record = read_run(vault_path, run_id)
    monitor = RunMonitor(vault_path=vault_path, flow=record.flow, run_id=run_id, metadata=record.metadata)
    return monitor.request_cancel()


def _reconcile_stale_record(path: Path, record: RunRecord) -> RunRecord:
    if record.status in TERMINAL_RUN_STATUSES:
        _write_reconciled_queue_state(path.parents[2], record.run_id, record.status)
        return record
    stale_seconds = _seconds_since(record.last_heartbeat_at)
    if record.cancel_requested or record.status == "cancelling":
        if stale_seconds < STALE_CANCELLING_SECONDS:
            return record
        return _finish_orphaned_record(
            path,
            record,
            status="cancelled",
            stage="cancelled",
            message="Cancellation finalized after stale heartbeat.",
            event_type="run_cancelled",
        )
    if stale_seconds < STALE_ACTIVE_SECONDS:
        return record
    return _finish_orphaned_record(
        path,
        record,
        status="failed",
        stage="orphaned",
        message="Run marked failed because its heartbeat is stale and no local worker owns it.",
        event_type="run_failed",
        error_info={
            "code": "KA-RUNTIME-001",
            "category": "internal_error",
            "message": "Run heartbeat is stale; the local worker likely stopped before writing a terminal state.",
            "retryable": True,
            "hint": "Refresh the run list. If the operation did not finish, start a new run.",
            "error_type": "StaleRunRecord",
        },
    )


def _finish_orphaned_record(
    path: Path,
    record: RunRecord,
    *,
    status: RunStatus,
    stage: str,
    message: str,
    event_type: str,
    error_info: dict[str, Any] | None = None,
) -> RunRecord:
    now = _now()
    record.status = status
    record.stage = stage
    record.message = message
    record.updated_at = now
    record.finished_at = now
    record.elapsed_seconds = _elapsed(record.started_at)
    if error_info:
        record.error_info = error_info
        record.error = _format_error(error_info)
    path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
    vault_path = path.parents[2]
    _write_reconciled_queue_state(vault_path, record.run_id, status)
    monitor = RunMonitor(vault_path=vault_path, flow=record.flow, run_id=record.run_id, metadata=record.metadata)
    monitor._append_event_for_record(record, event_type, message=message, payload={"reconciled": True, "error": error_info or {}})
    return record


def _compact_mapping(value: dict[str, Any] | None, *, max_items: int = 8) -> str:
    if not value:
        return "-"
    parts = []
    for index, (key, item) in enumerate(value.items()):
        if index >= max_items:
            parts.append("...")
            break
        parts.append(f"{key}={_compact_value(item)}")
    return ",".join(parts)


def _compact_value(value: Any) -> str:
    if isinstance(value, dict):
        return f"dict({len(value)})"
    if isinstance(value, list):
        return f"list({len(value)})"
    text = str(value).replace("\n", " ")
    return text if len(text) <= 120 else text[:117] + "..."


def _report_path(summary: dict[str, Any]) -> str:
    report = summary.get("report_path")
    return str(report) if report else "-"


def _write_reconciled_queue_state(vault_path: Path, run_id: str, status: str) -> None:
    path = vault_path / ".knoarbor" / "queue" / f"{run_id}.json"
    if not path.exists():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        payload = {
            "schema_version": "run_queue_task.v1",
            "run_id": run_id,
            "record_path": f".knoarbor/runs/{run_id}.json",
        }
    payload["queue_status"] = status
    payload["reconciled"] = True
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _seconds_since(timestamp: str) -> float:
    try:
        value = datetime.fromisoformat(timestamp)
    except ValueError:
        return float("inf")
    return max(0.0, (datetime.now() - value).total_seconds())


def _new_run_id() -> str:
    return f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _elapsed(started_at: str) -> float:
    try:
        started = datetime.fromisoformat(started_at)
    except ValueError:
        return 0.0
    return max(0.0, (datetime.now() - started).total_seconds())


def _progress(value: dict[str, Any] | RunProgress) -> RunProgress:
    if isinstance(value, RunProgress):
        return value.model_copy(update={"current": _compact_display_text(value.current) if value.current else None})
    data = dict(value)
    if isinstance(data.get("current"), str):
        data["current"] = _compact_display_text(data["current"])
    return RunProgress.model_validate(data)


def _public_error_info(info: dict[str, Any]) -> dict[str, Any]:
    public = dict(info)
    public.pop("http_status", None)
    return public


def _format_error(info: dict[str, Any]) -> str:
    code = info.get("code") or "KA-INTERNAL-001"
    category = info.get("category") or "internal_error"
    message = info.get("message") or ""
    return f"[{code}] {category}: {message}"


def _compact_display_text(text: str, *, max_chars: int = 180) -> str:
    normalized = " ".join(str(text).split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 1].rstrip() + "…"
