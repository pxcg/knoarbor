from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from knoarbor.core.config import default_config_path, load_config
from knoarbor.core.errors import UserInputError
from knoarbor.core.schemas.ingest_run import IngestDocumentRunRequest, IngestFileRunRequest, IngestRecoveryRunRequest, IngestRunRequest
from knoarbor.core.schemas.run_monitor import RunEventsResponse, RunListResponse, RunRecord, RunStartResponse
from knoarbor.core.schemas.run_start import RunStartRequest
from knoarbor.core.schemas.wiki_lint import LintRunRequest
from knoarbor.core.schemas.wiki_query import WikiSearchRequest
from knoarbor.runtime import LocalRunQueue, RunMonitor, configure_runtime_logging
from knoarbor.runtime.run_monitor import list_runs, read_run, read_run_events, request_cancel


class RunManager:
    """Starts long-running workflows in background threads and exposes run state."""

    def __init__(self) -> None:
        self._queue = LocalRunQueue()

    def start(
        self,
        request: RunStartRequest,
        *,
        ingest_runner: Callable[[IngestRunRequest], Any],
        ingest_file_runner: Callable[[IngestFileRunRequest], Any],
        ingest_document_runner: Callable[[IngestDocumentRunRequest], Any],
        lint_runner: Callable[[LintRunRequest], Any],
        query_runner: Callable[[WikiSearchRequest], Any],
    ) -> RunStartResponse:
        if request.flow == "ingest":
            if request.recovery_of_run_id:
                return self.start_ingest_recovery(
                    request.vault_path or "",
                    request.recovery_of_run_id,
                    request.recovery or IngestRecoveryRunRequest(),
                    ingest_runner,
                    ingest_file_runner,
                )
            ingest = request.ingest
            if ingest is None:
                raise ValueError("ingest payload is required when flow='ingest'.")
            if ingest.kind == "document":
                return self.start_ingest_document(ingest.to_document_request(), ingest_document_runner)
            if ingest.kind == "file":
                return self.start_ingest_file(ingest.to_file_request(), ingest_file_runner)
            return self.start_ingest(ingest.to_connectors_request(), ingest_runner)
        if request.flow == "lint":
            if request.lint is None:
                raise ValueError("lint payload is required when flow='lint'.")
            return self.start_lint(request.lint, lint_runner)
        if request.query is None:
            raise ValueError("query payload is required when flow='query'.")
        effective_request = request.query if request.query.caller is not None else request.query.model_copy(update={"caller": "api"})
        return self.start_query(effective_request, query_runner)

    def start_ingest(self, request: IngestRunRequest, runner: Callable[[IngestRunRequest], Any]) -> RunStartResponse:
        config = load_config(request.config_path or default_config_path())
        return self._start(config.vault.path, "ingest", request.model_dump(), lambda: runner(request))

    def start_ingest_file(self, request: IngestFileRunRequest, runner: Callable[[IngestFileRunRequest], Any]) -> RunStartResponse:
        config = load_config(request.config_path or default_config_path())
        return self._start(config.vault.path, "ingest", request.model_dump(), lambda: runner(request))

    def start_ingest_document(
        self,
        request: IngestDocumentRunRequest,
        runner: Callable[[IngestDocumentRunRequest], Any],
    ) -> RunStartResponse:
        config = load_config(request.config_path or default_config_path())
        vault_path = Path(request.obsidian_vault_path).expanduser().resolve() if request.obsidian_vault_path else config.vault.path
        return self._start(vault_path, "ingest", request.model_dump(), lambda: runner(request))

    def start_ingest_recovery(
        self,
        vault_path: str,
        run_id: str,
        request: IngestRecoveryRunRequest,
        ingest_runner: Callable[[IngestRunRequest], Any],
        ingest_file_runner: Callable[[IngestFileRunRequest], Any],
    ) -> RunStartResponse:
        previous = read_run(Path(vault_path), run_id)
        if previous.flow != "ingest":
            raise UserInputError(f"Only ingest runs can be recovered: {run_id}")
        metadata = dict(previous.metadata)
        config_path = request.config_path if request.config_path is not None else _metadata_str(metadata.get("config_path"))
        provider = request.provider if request.provider is not None else _metadata_str(metadata.get("provider"))
        max_tokens = request.max_tokens if request.max_tokens is not None else _metadata_int(metadata.get("max_tokens"))
        write = request.write if request.write is not None else bool(metadata.get("write", False))
        write_report = request.write_report if request.write_report is not None else bool(metadata.get("write_report", True))
        append_ledger = request.append_ledger if request.append_ledger is not None else bool(metadata.get("append_ledger", True))
        if isinstance(metadata.get("input_path"), str):
            recovery_request = IngestFileRunRequest(
                input_path=str(metadata["input_path"]),
                config_path=config_path,
                provider=provider,
                max_tokens=max_tokens,
                write=write,
                write_report=write_report,
                append_ledger=append_ledger,
                recovery_of_run_id=run_id,
            )
            config = load_config(recovery_request.config_path or default_config_path())
            return self._start(config.vault.path, "ingest", recovery_request.model_dump(), lambda: ingest_file_runner(recovery_request))

        recovery_request = IngestRunRequest(
            config_path=config_path,
            connector_names=_metadata_str_list(metadata.get("connector_names")),
            provider=provider,
            max_tokens=max_tokens,
            write=write,
            write_report=write_report,
            append_ledger=append_ledger,
            recovery_of_run_id=run_id,
        )
        config = load_config(recovery_request.config_path or default_config_path())
        return self._start(config.vault.path, "ingest", recovery_request.model_dump(), lambda: ingest_runner(recovery_request))

    def start_lint(self, request: LintRunRequest, runner: Callable[[LintRunRequest], Any]) -> RunStartResponse:
        return self._start(Path(request.obsidian_vault_path).expanduser().resolve(), "lint", request.model_dump(), lambda: runner(request))

    def start_query(self, request: WikiSearchRequest, runner: Callable[[WikiSearchRequest], Any]) -> RunStartResponse:
        return self._start(Path(request.obsidian_vault_path).expanduser().resolve(), "query", request.model_dump(), lambda: runner(request))

    def list(self, vault_path: str, *, active_only: bool = False, limit: int = 50) -> RunListResponse:
        return list_runs(Path(vault_path), active_only=active_only, limit=limit)

    def read(self, vault_path: str, run_id: str) -> RunRecord:
        return read_run(Path(vault_path), run_id)

    def events(self, vault_path: str, run_id: str, *, after: int = 0, limit: int = 200) -> RunEventsResponse:
        return RunEventsResponse(events=read_run_events(Path(vault_path), run_id, after=after, limit=limit))

    def cancel(self, vault_path: str, run_id: str) -> RunRecord:
        return request_cancel(Path(vault_path), run_id)

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


def _metadata_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _metadata_int(value: object) -> int | None:
    return value if isinstance(value, int) and value > 0 else None


def _metadata_str_list(value: object) -> list[str] | None:
    if not isinstance(value, list):
        return None
    items = [str(item) for item in value if isinstance(item, str) and item]
    return items or None
