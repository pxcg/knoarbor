from __future__ import annotations

from pathlib import Path

from knoarbor.core.config import default_config_path, load_config
from knoarbor.core.errors import UserInputError
from knoarbor.core.schemas.ingest_control import MaterializationRebuildResponse
from knoarbor.core.schemas.ingest_run import IngestRecoveryRunRequest, UnifiedIngestRequest
from knoarbor.core.schemas.run_monitor import RunStartResponse
from knoarbor.core.vaults import select_config_vault
from knoarbor.runtime.ingest_executor import IngestTaskExecutor
from knoarbor.runtime.local_operations import LocalOperationScheduler
from knoarbor.runtime.ingest_run_projection import project_ingest_attempt
from knoarbor.runtime.transactional_ingest import TransactionalIngestStore
from knoarbor.services.ingest import IngestService
from knoarbor.services.ingest_execution import build_execution_command, load_execution_config
from knoarbor.services.ingest_input_resolver import IngestInputResolver
from knoarbor.services.run_manager import RunManager
from knoarbor.storage.ingest_inputs import read_input_generation
from knoarbor.storage.materialization import VaultMaterializer


class IngestCoordinator:
    """The only public boundary that can create or recover an ingest attempt."""

    def __init__(
        self,
        *,
        ingest: IngestService | None = None,
        runs: RunManager | None = None,
        resolver: IngestInputResolver | None = None,
        scheduler: LocalOperationScheduler | None = None,
    ) -> None:
        self.ingest = ingest or IngestService()
        self.runs = runs or RunManager()
        self.resolver = resolver or IngestInputResolver()
        self.scheduler = scheduler or LocalOperationScheduler(max_workers=1)

    def start(self, request: UnifiedIngestRequest, *, foreground: bool = False) -> RunStartResponse:
        if request.kind == "recovery":
            run_id = request.recovery_of_run_id
            if not run_id:
                raise UserInputError("recovery_of_run_id is required for ingest recovery.")
            requested_vault = request.recovery_vault_path or request.vault_path
            if requested_vault:
                vault_path = Path(requested_vault).expanduser().resolve()
            else:
                vault_path = _load_selected_config(request.config_path, None, request.vault_id).vault.path
            attempt = TransactionalIngestStore(vault_path).attempt(run_id)
            return self._recover(
                vault_path,
                str(attempt["task_id"]),
                run_id,
                _recovery_request(request),
                foreground=foreground,
            )

        config = _load_selected_config(request.config_path, request.vault_path, request.vault_id)
        generation = self.resolver.resolve(request, config)
        resolved_config_path = Path(request.config_path or default_config_path()).expanduser().resolve()
        command = build_execution_command(request, config, generation, resolved_config_path=resolved_config_path)
        store = TransactionalIngestStore(config.vault.path)
        task, attempt = store.submit_command(command)
        attempt_id = str(attempt["attempt_id"])
        record = project_ingest_attempt(config.vault.path, attempt_id)
        record = record.model_copy(
            update={"vault_id": config.active_vault_id(), "vault_name": config.active_vault_name(), "vault_path": str(config.vault.path)}
        )
        self._execute(config.vault.path, str(task["task_id"]), foreground=foreground)
        return RunStartResponse(run_id=attempt_id, status=record.status, run=record)

    def recover_task(
        self,
        vault_path: str,
        task_id: str,
        request: IngestRecoveryRunRequest,
        *,
        vault_id: str | None = None,
    ) -> RunStartResponse:
        store = TransactionalIngestStore(Path(vault_path))
        task = store.task(task_id)
        return self._recover(store.vault_path, task_id, str(task["current_attempt_id"]), request, foreground=False)

    def _recover(
        self,
        vault_path: Path,
        task_id: str,
        attempt_id: str,
        request: IngestRecoveryRunRequest,
        *,
        foreground: bool,
    ) -> RunStartResponse:
        store = TransactionalIngestStore(vault_path)
        command = store.command_for_task(task_id)
        _validate_recovery_overrides(command, request)
        if not command.config_path:
            raise UserInputError("The persisted ingest command has no configuration path.")
        config = load_execution_config(command)
        if config.vault.path.expanduser().resolve() != store.vault_path.expanduser().resolve():
            raise UserInputError("The recovery store belongs to a different vault path.")
        read_input_generation(config.vault.path, command.generation_id)
        _, attempt = store.admit_recovery(task_id, expected_attempt_id=attempt_id)
        recovery_id = str(attempt["attempt_id"])
        record = project_ingest_attempt(config.vault.path, recovery_id)
        record = record.model_copy(
            update={"vault_id": config.active_vault_id(), "vault_name": config.active_vault_name(), "vault_path": str(config.vault.path)}
        )
        self._execute(config.vault.path, task_id, foreground=foreground)
        return RunStartResponse(run_id=recovery_id, status=record.status, run=record)

    def resume_queued(self, vault_path: str | Path) -> int:
        store = TransactionalIngestStore(Path(vault_path))
        tasks = store.dispatchable_tasks()
        for task in tasks:
            self._execute(store.vault_path, str(task["task_id"]), foreground=False)
        return len(tasks)

    def rebuild_materialization(self, vault_path: str | Path) -> MaterializationRebuildResponse:
        vault = Path(vault_path).expanduser().resolve()
        state = VaultMaterializer().reconcile(vault, force=True)
        return MaterializationRebuildResponse(
            phase=str(state["phase"]),
            requested_epoch=int(state["requested_epoch"]),
            published_epoch=int(state["published_epoch"]),
            fact_generation=str(state["published_fact_generation"] or state["requested_fact_generation"]),
            index_generation=str(state["published_index_generation"]) if state.get("published_index_generation") else None,
            error=str(state["error"]) if state.get("error") else None,
        )

    def _execute(self, vault_path: Path, task_id: str, *, foreground: bool) -> None:
        executor = IngestTaskExecutor(vault_path, service=self.ingest)
        if foreground:
            executor.execute(task_id)
            return
        self.scheduler.submit(
            task_id,
            lambda token: executor.execute(task_id, cancellation=token),
        )


def _load_selected_config(config_path: str | None, vault_path: str | None, vault_id: str | None):
    config = load_config(config_path or default_config_path())
    return select_config_vault(config, vault_path=vault_path, vault_id=vault_id)


def _validate_recovery_overrides(command, request: IngestRecoveryRunRequest) -> None:
    if request.config_path and Path(request.config_path).expanduser().resolve() != Path(str(command.config_path)).expanduser().resolve():
        raise UserInputError("Recovery cannot change the immutable ingest command config_path.")
    checks = {
        "provider": request.provider,
        "max_tokens": request.max_tokens,
        "write": request.write,
        "write_report": request.write_report,
        "append_ledger": request.append_ledger,
    }
    for field, override in checks.items():
        if override is not None and override != getattr(command, field):
            raise UserInputError(f"Recovery cannot change immutable ingest command field: {field}")


def _recovery_request(request: UnifiedIngestRequest) -> IngestRecoveryRunRequest:
    return IngestRecoveryRunRequest(
        config_path=request.config_path,
        provider=request.provider,
        max_tokens=request.max_tokens,
        write=request.write,
        write_report=request.write_report,
        append_ledger=request.append_ledger,
    )
