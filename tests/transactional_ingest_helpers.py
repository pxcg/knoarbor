from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from knoarbor.core.schemas.ingest_execution import IngestExecutionCommand, execution_contract_hash
from knoarbor.runtime.transactional_ingest import TransactionalIngestStore


def admit_test_task(vault: Path, label: str = "test"):
    store = TransactionalIngestStore(vault)
    contract = {"test": label}
    generation_id = f"sha256:{sha256(label.encode('utf-8')).hexdigest()}"
    command = IngestExecutionCommand(
        generation_id=generation_id,
        request_kind="test",
        vault_id="test",
        vault_path=str(vault),
        vault_identity="test-vault",
        write=True,
        write_report=False,
        append_ledger=False,
        execution_contract=contract,
        execution_contract_hash=execution_contract_hash(contract),
    )
    task, attempt = store.submit_command(command)
    return store, task, attempt
