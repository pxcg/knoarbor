from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from knoarbor.core.config import default_config_path, load_config
from knoarbor.core.errors import UserInputError
from knoarbor.core.schemas.ingest_control import IngestQueueResponse, IngestQueueTask
from knoarbor.core.schemas.run_monitor import ACTIVE_RUN_STATUSES, RunEventsResponse, RunListResponse, RunRecord, RunStartResponse
from knoarbor.core.schemas.wiki_lint import LintRunRequest
from knoarbor.core.schemas.wiki_query import WikiSearchRequest
from knoarbor.core.vaults import select_config_vault
from knoarbor.runtime import LocalRunQueue, RunMonitor, configure_runtime_logging, vault_write_lock
from knoarbor.runtime.ingest_control import read_ingest_control
from knoarbor.runtime.ingest_run_projection import project_ingest_attempt, project_ingest_attempts
from knoarbor.runtime.recovery import with_recovery_assessment
from knoarbor.runtime.run_monitor import list_runs, read_run, read_run_events, request_cancel
from knoarbor.runtime.transactional_ingest import TransactionalIngestStore


class RunManager:
    """Project local run state without owning ingest execution."""

    def __init__(self) -> None:
        self._queue = LocalRunQueue()

    def start_lint(self, request: LintRunRequest, runner: Callable[[LintRunRequest], Any]) -> RunStartResponse:
        if request.vault_path:
            vault_path = Path(request.vault_path).expanduser().resolve()
            vault_id = request.vault_id
            vault_name = _configured_vault_name(request.config_path, vault_id)
        else:
            config = _request_config(request.config_path, vault_id=request.vault_id)
            vault_path = config.vault.path
            vault_id = config.active_vault_id()
            vault_name = config.active_vault_name()
        admitted = request.model_copy(update={"vault_path": str(vault_path), "vault_id": request.vault_id or vault_id})
        return self._start(vault_path, "lint", admitted.model_dump(), lambda: runner(admitted), vault_id=vault_id, vault_name=vault_name)

    def start_query(self, request: WikiSearchRequest, runner: Callable[[WikiSearchRequest], Any]) -> RunStartResponse:
        vault = Path(request.vault_path).expanduser().resolve()
        return self._start(vault, "query", request.model_dump(), lambda: runner(request))

    def list(
        self,
        vault_path: str,
        *,
        active_only: bool = False,
        limit: int = 50,
        vault_id: str | None = None,
        vault_name: str | None = None,
    ) -> RunListResponse:
        vault = Path(vault_path)
        response = list_runs(vault, active_only=False, limit=limit)
        records = list(response.runs)
        if (vault / ".knoarbor" / "ingest.sqlite").is_file():
            ingest = project_ingest_attempts(vault, limit=limit)
            ingest_ids = {record.run_id for record in ingest}
            records = ingest + [record for record in records if record.run_id not in ingest_ids]
        if active_only:
            records = [record for record in records if record.status in ACTIVE_RUN_STATUSES]
        records = sorted(records, key=lambda record: record.updated_at, reverse=True)[:limit]
        return RunListResponse(
            runs=[
                _annotate_run(
                    with_recovery_assessment(record, vault_path=Path(vault_path)),
                    vault_path,
                    vault_id=vault_id,
                    vault_name=vault_name,
                )
                for record in records
            ]
        )

    def read(self, vault_path: str, run_id: str, *, vault_id: str | None = None, vault_name: str | None = None) -> RunRecord:
        vault = Path(vault_path)
        if (vault / ".knoarbor" / "ingest.sqlite").is_file():
            try:
                record = project_ingest_attempt(vault, run_id)
            except UserInputError:
                record = read_run(vault, run_id)
        else:
            record = read_run(vault, run_id)
        return _annotate_run(
            with_recovery_assessment(record, vault_path=vault),
            vault_path,
            vault_id=vault_id,
            vault_name=vault_name,
        )

    def events(self, vault_path: str, run_id: str, *, after: int = 0, limit: int = 200) -> RunEventsResponse:
        return RunEventsResponse(events=read_run_events(Path(vault_path), run_id, after=after, limit=limit))

    def ingest_queue(self, vault_path: str) -> IngestQueueResponse:
        path = Path(vault_path)
        store = TransactionalIngestStore(path)
        tasks = [
            IngestQueueTask(
                task_id=str(task["task_id"]),
                current_attempt_id=str(task["current_attempt_id"]),
                queue_status=str(task["state"]),
                attempt_ids=[str(item["attempt_id"]) for item in store.attempts_for_task(str(task["task_id"]))],
                error=None,
            )
            for task in store.tasks()
        ]
        counts: dict[str, int] = {}
        for task in tasks:
            counts[task.queue_status] = counts.get(task.queue_status, 0) + 1
        return IngestQueueResponse(paused=bool(read_ingest_control(path)["paused"]), tasks=tasks, counts=counts)

    def cancel(self, vault_path: str, run_id: str, *, vault_id: str | None = None, vault_name: str | None = None) -> RunRecord:
        vault = Path(vault_path)
        try:
            if not (vault / ".knoarbor" / "ingest.sqlite").is_file():
                raise UserInputError("No transactional ingest store exists.")
            store = TransactionalIngestStore(vault)
            attempt = store.attempt(run_id)
            store.request_cancel(str(attempt["task_id"]), expected_attempt_id=run_id)
            try:
                request_cancel(vault, run_id)
            except Exception:
                pass
            record = project_ingest_attempt(vault, run_id)
        except UserInputError:
            record = request_cancel(vault, run_id)
        return _annotate_run(record, vault_path, vault_id=vault_id, vault_name=vault_name)

    def cancel_ingest_task(self, vault_path: str, task_id: str) -> IngestQueueTask:
        store = TransactionalIngestStore(Path(vault_path))
        task = store.task(task_id)
        attempt_id = str(task["current_attempt_id"])
        task = store.request_cancel(task_id, expected_attempt_id=attempt_id)
        try:
            request_cancel(Path(vault_path), attempt_id)
        except Exception:
            pass
        return IngestQueueTask(
            task_id=task_id,
            current_attempt_id=attempt_id,
            queue_status=str(task["state"]),
            attempt_ids=[str(item["attempt_id"]) for item in store.attempts_for_task(task_id)],
            error=None,
        )

    def _start(
        self,
        vault_path: Path,
        flow: str,
        metadata: dict[str, Any],
        target: Callable[[], Any],
        *,
        vault_id: str | None = None,
        vault_name: str | None = None,
    ) -> RunStartResponse:
        configure_runtime_logging(vault_path)
        with vault_write_lock(vault_path):
            monitor = RunMonitor(vault_path=vault_path, flow=flow, metadata=_compact_metadata(metadata))
            record = monitor.queue(message=f"{flow} run queued.")
            self._queue.submit(monitor, target)
        return RunStartResponse(
            run_id=monitor.run_id,
            status=record.status,
            run=_annotate_run(record, str(vault_path), vault_id=vault_id, vault_name=vault_name),
        )


def _compact_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {key: "<omitted>" if key == "source_document" else value for key, value in metadata.items()}


def _annotate_run(record: RunRecord, vault_path: str, *, vault_id: str | None = None, vault_name: str | None = None) -> RunRecord:
    return record.model_copy(update={"vault_id": vault_id, "vault_name": vault_name, "vault_path": str(Path(vault_path).resolve())})


def _request_config(config_path: str | None, *, vault_path: str | None = None, vault_id: str | None = None):
    config = load_config(config_path or default_config_path())
    return select_config_vault(config, vault_path=vault_path, vault_id=vault_id)


def _configured_vault_name(config_path: str | None, vault_id: str | None) -> str | None:
    try:
        return _request_config(config_path, vault_id=vault_id).active_vault_name()
    except Exception:
        return None
