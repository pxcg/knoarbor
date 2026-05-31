from __future__ import annotations

import json
import queue
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from knoarbor.runtime.locks import vault_write_lock
from knoarbor.runtime.logging import runtime_logger
from knoarbor.runtime.reporter import RunReporter
from knoarbor.runtime.result_policy import completion_status_for_result
from knoarbor.runtime.run_monitor import RunCancelled, RunMonitor, run_monitor_context


logger = runtime_logger(__name__)


@dataclass(frozen=True)
class LocalRunTask:
    monitor: RunMonitor
    target: Callable[[], Any]


class LocalRunQueue:
    """Single-machine run queue backed by run records and lightweight task files.

    The queue owns scheduling only. It does not inspect workflow payloads, decide
    retries, call models directly, or write wiki pages.
    """

    def __init__(self) -> None:
        self._workers: dict[str, _VaultQueueWorker] = {}
        self._lock = threading.Lock()

    def submit(self, monitor: RunMonitor, target: Callable[[], Any]) -> None:
        vault_key = str(monitor.vault_path)
        with self._lock:
            worker = self._workers.get(vault_key)
            if worker is None:
                worker = _VaultQueueWorker(monitor.vault_path)
                self._workers[vault_key] = worker
            worker.submit(LocalRunTask(monitor=monitor, target=target))


class _VaultQueueWorker:
    def __init__(self, vault_path: Path) -> None:
        self.vault_path = vault_path.expanduser().resolve()
        self._queue: queue.Queue[LocalRunTask] = queue.Queue()
        self._thread = threading.Thread(target=self._run_loop, name=f"knoarbor-queue-{self.vault_path.name}", daemon=True)
        self._thread.start()

    def submit(self, task: LocalRunTask) -> None:
        _write_queue_task(task.monitor, "queued")
        self._queue.put(task)
        logger.info("run_queued run_id=%s flow=%s vault=%s", task.monitor.run_id, task.monitor.flow, task.monitor.vault_path)

    def _run_loop(self) -> None:
        while True:
            task = self._queue.get()
            try:
                _execute_task(task)
            finally:
                self._queue.task_done()


def _execute_task(task: LocalRunTask) -> None:
    monitor = task.monitor
    _write_queue_task(monitor, "running")
    with run_monitor_context(monitor):
        try:
            queued_record = monitor.read()
            if queued_record.cancel_requested:
                raise RunCancelled(f"Run {monitor.run_id} was cancelled before it started.")
            monitor.start(message=f"{monitor.flow} run started.")
            RunReporter.current().event("worker_started", stage="running", message=f"{monitor.flow} worker started.")
            result = task.target()
            completion_status = completion_status_for_result(monitor.flow, result)
            if completion_status == "partially_failed":
                monitor.partially_fail(
                    message=f"{monitor.flow} run partially failed.",
                    result_summary=_result_summary(result),
                    metrics=_result_metrics(result),
                )
            else:
                monitor.complete(
                    message=f"{monitor.flow} run completed.",
                    result_summary=_result_summary(result),
                    metrics=_result_metrics(result),
                )
            _write_queue_task(monitor, completion_status)
        except BaseException as exc:
            monitor.fail(exc)
            _write_queue_task(monitor, "failed" if not isinstance(exc, RunCancelled) else "cancelled", error=f"{type(exc).__name__}: {exc}")


def _write_queue_task(monitor: RunMonitor, queue_status: str, *, error: str | None = None) -> None:
    path = queue_dir(monitor.vault_path) / f"{monitor.run_id}.json"
    payload: dict[str, Any] = {
        "schema_version": "run_queue_task.v1",
        "run_id": monitor.run_id,
        "flow": monitor.flow,
        "queue_status": queue_status,
        "record_path": str(monitor.record_path.relative_to(monitor.vault_path)),
    }
    if error:
        payload["error"] = error
    with vault_write_lock(monitor.vault_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def queue_dir(vault_path: Path) -> Path:
    return vault_path.expanduser().resolve() / ".knoarbor" / "queue"


def _result_summary(result: Any) -> dict[str, Any]:
    if hasattr(result, "model_dump"):
        data = result.model_dump()
    elif isinstance(result, dict):
        data = result
    else:
        return {"result_type": type(result).__name__}
    summary: dict[str, Any] = {}
    for key in ("stats", "report_path", "ledger_path", "written_pages", "applied_operations", "warnings"):
        if key in data:
            summary[key] = data[key]
    if "results" in data and isinstance(data["results"], list):
        summary["result_count"] = len(data["results"])
    if "query" in data and "results" in data:
        summary["query"] = data["query"]
        summary["returned_count"] = len(data["results"] or [])
    return summary


def _result_metrics(result: Any) -> dict[str, Any]:
    if hasattr(result, "model_dump"):
        data = result.model_dump()
    elif isinstance(result, dict):
        data = result
    else:
        return {}
    metrics = data.get("metrics")
    return metrics if isinstance(metrics, dict) else {}
