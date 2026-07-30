from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from knoarbor.runtime.logging import runtime_logger
from knoarbor.runtime.reporter import RunReporter
from knoarbor.runtime.result_policy import completion_status_for_result
from knoarbor.runtime.run_monitor import RunMonitor, run_monitor_context


logger = runtime_logger(__name__)


@dataclass(frozen=True)
class LocalRunTask:
    monitor: RunMonitor
    target: Callable[[], Any]


class LocalRunQueue:
    """Process-local executor for non-ingest workflows."""

    _workers: dict[str, _VaultQueueWorker] = {}
    _lock = threading.Lock()

    def submit(self, monitor: RunMonitor, target: Callable[[], Any]) -> None:
        if monitor.flow == "ingest":
            raise RuntimeError("Ingest commands must be executed by the local operation scheduler.")
        key = str(monitor.vault_path)
        with type(self)._lock:
            worker = type(self)._workers.get(key)
            if worker is None:
                worker = _VaultQueueWorker(monitor.vault_path)
                type(self)._workers[key] = worker
            worker.submit(LocalRunTask(monitor=monitor, target=target))


class _VaultQueueWorker:
    def __init__(self, vault_path: Path) -> None:
        self.vault_path = vault_path.expanduser().resolve()
        self._queue: queue.Queue[LocalRunTask] = queue.Queue()
        self._thread = threading.Thread(target=self._run_loop, name=f"knoarbor-queue-{self.vault_path.name}", daemon=True)
        self._thread.start()

    def submit(self, task: LocalRunTask) -> None:
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
    with run_monitor_context(monitor):
        try:
            if monitor.read().cancel_requested:
                monitor.raise_if_cancelled()
            monitor.start(message=f"{monitor.flow} run started.")
            RunReporter.current().event("worker_started", stage="running", message=f"{monitor.flow} worker started.")
            result = task.target()
            status = completion_status_for_result(monitor.flow, result)
            if status == "partially_failed":
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
        except BaseException as exc:
            monitor.fail(exc)


def _result_summary(result: Any) -> dict[str, Any]:
    if hasattr(result, "model_dump"):
        data = result.model_dump()
    elif isinstance(result, dict):
        data = result
    else:
        return {"result_type": type(result).__name__}
    summary = {
        key: data[key]
        for key in ("stats", "report_path", "ledger_path", "written_pages", "applied_operations", "warnings")
        if key in data
    }
    if "results" in data and isinstance(data["results"], list):
        summary["result_count"] = len(data["results"])
    if "query" in data and "results" in data:
        summary["query"] = data["query"]
        summary["returned_count"] = len(data["results"] or [])
    return summary


def _result_metrics(result: Any) -> dict[str, Any]:
    metrics = getattr(result, "metrics", None)
    return dict(metrics) if isinstance(metrics, dict) else {}
