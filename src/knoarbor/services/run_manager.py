from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from knoarbor.core.config import default_config_path, load_config
from knoarbor.core.errors import UserInputError
from knoarbor.core.vaults import select_config_vault
from knoarbor.core.schemas.ingest_run import (
    IngestDocumentRunRequest,
    IngestFileRunRequest,
    IngestFolderRunRequest,
    IngestRecoveryRunRequest,
    IngestRunRequest,
)
from knoarbor.core.schemas.run_monitor import RunEventsResponse, RunListResponse, RunRecord, RunStartResponse
from knoarbor.core.schemas.wiki_lint import LintRunRequest
from knoarbor.core.schemas.wiki_query import WikiSearchRequest
from knoarbor.runtime import LocalRunQueue, RunMonitor, configure_runtime_logging
from knoarbor.runtime.recovery import assess_run_recovery, with_recovery_assessment
from knoarbor.runtime.run_monitor import list_runs, read_run, read_run_events, request_cancel


class RunManager:
    """Starts long-running workflows in background threads and exposes run state."""

    def __init__(self) -> None:
        self._queue = LocalRunQueue()

    def start_ingest(self, request: IngestRunRequest, runner: Callable[[IngestRunRequest], Any]) -> RunStartResponse:
        config = _request_config(request.config_path, vault_path=request.obsidian_vault_path, vault_id=request.vault_id)
        return self._start(config.vault.path, "ingest", request.model_dump(), lambda: runner(request))

    def start_ingest_file(self, request: IngestFileRunRequest, runner: Callable[[IngestFileRunRequest], Any]) -> RunStartResponse:
        config = _request_config(request.config_path, vault_path=request.obsidian_vault_path, vault_id=request.vault_id)
        return self._start(config.vault.path, "ingest", request.model_dump(), lambda: runner(request))

    def start_ingest_folder(self, request: IngestFolderRunRequest, runner: Callable[[IngestFolderRunRequest], Any]) -> RunStartResponse:
        config = _request_config(request.config_path, vault_path=request.obsidian_vault_path, vault_id=request.vault_id)
        return self._start(config.vault.path, "ingest", request.model_dump(), lambda: runner(request))

    def start_ingest_document(
        self,
        request: IngestDocumentRunRequest,
        runner: Callable[[IngestDocumentRunRequest], Any],
    ) -> RunStartResponse:
        config = _request_config(request.config_path, vault_path=request.obsidian_vault_path, vault_id=request.vault_id)
        return self._start(config.vault.path, "ingest", request.model_dump(), lambda: runner(request))

    def start_ingest_recovery(
        self,
        vault_path: str,
        run_id: str,
        request: IngestRecoveryRunRequest,
        ingest_runner: Callable[[IngestRunRequest], Any],
        ingest_file_runner: Callable[[IngestFileRunRequest], Any],
        ingest_folder_runner: Callable[[IngestFolderRunRequest], Any] | None = None,
    ) -> RunStartResponse:
        previous = read_run(Path(vault_path), run_id)
        if previous.flow != "ingest":
            raise UserInputError(f"Only ingest runs can be recovered: {run_id}")
        recovery = assess_run_recovery(previous)
        if not recovery.available:
            raise UserInputError(f"Run cannot be recovered: {recovery.reason}")
        metadata = dict(previous.metadata)
        config_path = request.config_path if request.config_path is not None else _metadata_str(metadata.get("config_path"))
        provider = request.provider if request.provider is not None else _metadata_str(metadata.get("provider"))
        max_tokens = request.max_tokens if request.max_tokens is not None else _metadata_int(metadata.get("max_tokens"))
        write = request.write if request.write is not None else bool(metadata.get("write", False))
        write_report = request.write_report if request.write_report is not None else bool(metadata.get("write_report", True))
        append_ledger = request.append_ledger if request.append_ledger is not None else bool(metadata.get("append_ledger", True))
        if metadata.get("input_kind") == "folder":
            if ingest_folder_runner is None:
                raise UserInputError(f"Folder ingest recovery is not available for run: {run_id}")
            recovery_request = IngestFolderRunRequest(
                input_path=str(metadata["input_path"]),
                recursive=bool(metadata.get("recursive", True)),
                config_path=config_path,
                vault_path=str(vault_path),
                provider=provider,
                max_tokens=max_tokens,
                write=write,
                write_report=write_report,
                append_ledger=append_ledger,
                recovery_of_run_id=run_id,
            )
            config = _request_config(recovery_request.config_path, vault_path=str(vault_path))
            return self._start(config.vault.path, "ingest", recovery_request.model_dump(), lambda: ingest_folder_runner(recovery_request))
        if isinstance(metadata.get("input_path"), str):
            recovery_request = IngestFileRunRequest(
                input_path=str(metadata["input_path"]),
                config_path=config_path,
                vault_path=str(vault_path),
                provider=provider,
                max_tokens=max_tokens,
                write=write,
                write_report=write_report,
                append_ledger=append_ledger,
                recovery_of_run_id=run_id,
            )
            config = _request_config(recovery_request.config_path, vault_path=str(vault_path))
            return self._start(config.vault.path, "ingest", recovery_request.model_dump(), lambda: ingest_file_runner(recovery_request))

        recovery_request = IngestRunRequest(
            config_path=config_path,
            vault_path=str(vault_path),
            connector_names=_metadata_str_list(metadata.get("connector_names")),
            provider=provider,
            max_tokens=max_tokens,
            write=write,
            write_report=write_report,
            append_ledger=append_ledger,
            recovery_of_run_id=run_id,
        )
        config = _request_config(recovery_request.config_path, vault_path=str(vault_path))
        return self._start(config.vault.path, "ingest", recovery_request.model_dump(), lambda: ingest_runner(recovery_request))

    def start_lint(self, request: LintRunRequest, runner: Callable[[LintRunRequest], Any]) -> RunStartResponse:
        vault_path = _request_vault_path_for_start(request.config_path, vault_path=request.obsidian_vault_path, vault_id=request.vault_id)
        request = request.model_copy(update={"obsidian_vault_path": str(vault_path)})
        return self._start(vault_path, "lint", request.model_dump(), lambda: runner(request))

    def start_query(self, request: WikiSearchRequest, runner: Callable[[WikiSearchRequest], Any]) -> RunStartResponse:
        return self._start(Path(request.obsidian_vault_path).expanduser().resolve(), "query", request.model_dump(), lambda: runner(request))

    def list(self, vault_path: str, *, active_only: bool = False, limit: int = 50, vault_id: str | None = None, vault_name: str | None = None) -> RunListResponse:
        response = list_runs(Path(vault_path), active_only=active_only, limit=limit)
        return RunListResponse(runs=[_annotate_run(with_recovery_assessment(record), vault_path, vault_id=vault_id, vault_name=vault_name) for record in response.runs])

    def read(self, vault_path: str, run_id: str, *, vault_id: str | None = None, vault_name: str | None = None) -> RunRecord:
        return _annotate_run(with_recovery_assessment(read_run(Path(vault_path), run_id)), vault_path, vault_id=vault_id, vault_name=vault_name)

    def events(self, vault_path: str, run_id: str, *, after: int = 0, limit: int = 200) -> RunEventsResponse:
        return RunEventsResponse(events=read_run_events(Path(vault_path), run_id, after=after, limit=limit))

    def cancel(self, vault_path: str, run_id: str, *, vault_id: str | None = None, vault_name: str | None = None) -> RunRecord:
        return _annotate_run(request_cancel(Path(vault_path), run_id), vault_path, vault_id=vault_id, vault_name=vault_name)

    def _start(self, vault_path: Path, flow: str, metadata: dict[str, Any], target: Callable[[], Any]) -> RunStartResponse:
        configure_runtime_logging(vault_path)
        monitor = RunMonitor(vault_path=vault_path, flow=flow, metadata=_compact_metadata(metadata))
        record = monitor.queue(message=f"{flow} run queued.")
        self._queue.submit(monitor, target)
        return RunStartResponse(run_id=monitor.run_id, status=record.status, run=record)


def _compact_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key, value in metadata.items():
        if key in {"source_document"}:
            compact[key] = "<omitted>"
        else:
            compact[key] = value
    return compact


def _annotate_run(record: RunRecord, vault_path: str, *, vault_id: str | None = None, vault_name: str | None = None) -> RunRecord:
    return record.model_copy(update={"vault_id": vault_id, "vault_name": vault_name, "vault_path": str(Path(vault_path).expanduser().resolve())})


def _metadata_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _metadata_int(value: object) -> int | None:
    return value if isinstance(value, int) and value > 0 else None


def _metadata_str_list(value: object) -> list[str] | None:
    if not isinstance(value, list):
        return None
    items = [str(item) for item in value if isinstance(item, str) and item]
    return items or None


def _request_config(config_path: str | None, *, vault_path: str | None = None, vault_id: str | None = None):
    config = load_config(config_path or default_config_path())
    return select_config_vault(config, vault_path=vault_path, vault_id=vault_id)


def _request_vault_path_for_start(config_path: str | None, *, vault_path: str | None = None, vault_id: str | None = None) -> Path:
    if vault_path:
        return Path(vault_path).expanduser().resolve()
    return _request_config(config_path, vault_id=vault_id).vault.path
