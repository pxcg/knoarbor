from __future__ import annotations

from knoarbor.core.config import load_config
from knoarbor.core.schemas.ingest_run import IngestFileRunRequest, UnifiedIngestRequest
from knoarbor.core.vaults import select_config_vault
from knoarbor.runtime.run_monitor import RunMonitor, run_monitor_context
from knoarbor.runtime.ingest_session import IngestExecutionSession
from knoarbor.runtime.transactional_ingest import TransactionalIngestStore
from knoarbor.services.ingest import IngestService
from knoarbor.services.ingest_execution import build_execution_command
from knoarbor.services.ingest_input_resolver import IngestInputResolver
from knoarbor.storage.materialization import VaultMaterializer


def execute_file_command(request: IngestFileRunRequest):
    unified = UnifiedIngestRequest(
        kind="file",
        execution="queued",
        input_path=request.input_path,
        config_path=request.config_path,
        vault_path=request.vault_path,
        vault_id=request.vault_id,
        provider=request.provider,
        max_tokens=request.max_tokens,
        write=request.write,
        write_report=request.write_report,
        append_ledger=request.append_ledger,
        force_reprocess=request.force_reprocess,
    )
    config = select_config_vault(
        load_config(str(request.config_path)),
        vault_path=request.vault_path,
        vault_id=request.vault_id,
    )
    generation = IngestInputResolver().resolve(unified, config)
    command = build_execution_command(unified, config, generation)
    store = TransactionalIngestStore(config.vault.path)
    task, attempt = store.submit_command(command)
    task_id = str(task["task_id"])
    attempt_id = str(attempt["attempt_id"])
    lease = store.claim(task_id, attempt_id, owner_id="test-executor", lease_seconds=300)
    monitor = RunMonitor(
        vault_path=config.vault.path,
        flow="ingest",
        run_id=attempt_id,
        metadata={
            "ingest_task_id": task_id,
            "ingest_lease_epoch": lease.epoch,
            "ingest_lease_expires_at": lease.expires_at,
            "ingest_lease_seconds": 300,
        },
    )
    with run_monitor_context(monitor):
        monitor.start()
        session = IngestExecutionSession(store, lease, monitor, lease_seconds=300)
        result = IngestService().run_generation_command(command, execution=session)
    session.renew()
    VaultMaterializer().reconcile(config.vault.path)
    store.finish(session.lease, state="completed", result=result.model_dump(mode="json"))
    return result
