from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from knoarbor.core.schemas.ingest_execution import IngestExecutionCommand, execution_contract_hash
from knoarbor.core.schemas.ingest_pipeline import IngestPipelineResult, IngestSourceResult
from knoarbor.runtime.ingest_executor import IngestTaskExecutor
from knoarbor.runtime.local_operations import OperationCancellationToken
from knoarbor.runtime.transactional_ingest import TransactionalIngestStore
from knoarbor.services.startup_reconciler import StartupReconciler
from knoarbor.storage.ingest_inputs import write_input_generation
from knoarbor.storage.vault_identity import ensure_vault_identity


class IngestExecutorTests(unittest.TestCase):
    def test_executor_owns_one_task_from_claim_through_terminal_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            store, task = _queued_task(vault)
            service = _Service()

            finished = IngestTaskExecutor(vault, service=service).execute(str(task["task_id"]))

            self.assertEqual(finished["state"], "completed")
            self.assertEqual(service.calls, 1)
            attempt = store.attempt(str(finished["current_attempt_id"]))
            self.assertEqual(attempt["state"], "completed")

    def test_shutdown_before_claim_leaves_durable_task_queued(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            store, task = _queued_task(vault)
            token = OperationCancellationToken()
            token.stop()

            IngestTaskExecutor(vault, service=_Service()).execute(str(task["task_id"]), cancellation=token)

            self.assertEqual(store.task(str(task["task_id"]))["state"], "queued")

    def test_materialization_failure_is_reported_without_rolling_back_committed_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            store, task = _queued_task(vault)
            store.request_materialization()
            materializer = Mock()
            materializer.reconcile.side_effect = OSError("disk unavailable")

            finished = IngestTaskExecutor(vault, service=_Service(), materializer=materializer).execute(str(task["task_id"]))
            attempt = store.attempt(str(finished["current_attempt_id"]))

            self.assertEqual(finished["state"], "completed")
            self.assertTrue(attempt["result"]["materialization_pending"])
            self.assertIn("disk unavailable", attempt["result"]["materialization_error"])

    def test_terminal_summary_preserves_actionable_source_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            store, task = _queued_task(vault)
            service = _FailedService()

            finished = IngestTaskExecutor(vault, service=service).execute(str(task["task_id"]))
            attempt = store.attempt(str(finished["current_attempt_id"]))

            self.assertEqual(attempt["state"], "partially_failed")
            self.assertEqual(
                attempt["result"]["failures"],
                [
                    {
                        "source_id": "unit:test",
                        "source_file": "/tmp/test.md",
                        "error_stage": "auto_write",
                        "error_code": "KA-MODEL-001",
                        "error_category": "model_output",
                        "error_retryable": False,
                        "error_hint": "Review the model contract.",
                        "error_type": "ModelOutputError",
                        "error_message": "Invalid entity reference.",
                    }
                ],
            )

    def test_startup_reconciliation_is_finite_and_resubmits_only_queued_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            _, task = _queued_task(vault)
            coordinator = Mock()
            materializer = Mock()

            StartupReconciler(coordinator, materializer=materializer).reconcile(vault)

            materializer.reconcile.assert_called_once_with(vault.resolve())
            materializer.prune_unreachable_index_generations.assert_called_once_with(vault.resolve())
            coordinator.resume_queued.assert_called_once_with(vault.resolve())
            self.assertEqual(TransactionalIngestStore(vault).task(str(task["task_id"]))["state"], "queued")


class _Service:
    def __init__(self) -> None:
        self.calls = 0

    def run_generation_command(self, _command, *, execution) -> IngestPipelineResult:
        self.calls += 1
        return IngestPipelineResult(stats={"source_count": 0, "failed_count": 0, "partial_count": 0})


class _FailedService:
    def run_generation_command(self, _command, *, execution) -> IngestPipelineResult:
        return IngestPipelineResult(
            results=[
                IngestSourceResult(
                    connector="markdown",
                    source_id="unit:test",
                    source_file="/tmp/test.md",
                    should_process=True,
                    mode="new",
                    reason="New source.",
                    status="failed",
                    error_stage="auto_write",
                    error_code="KA-MODEL-001",
                    error_category="model_output",
                    error_hint="Review the model contract.",
                    error_type="ModelOutputError",
                    error_message="Invalid entity reference.",
                )
            ],
            stats={"source_count": 1, "failed_count": 1, "partial_count": 0},
        )


def _queued_task(vault: Path) -> tuple[TransactionalIngestStore, dict[str, object]]:
    generation = write_input_generation(vault, documents=[])
    contract = {
        "provider": {"name": "test", "model": "model", "base_url": "http://localhost"},
        "request_timeout_seconds": 10,
        "ingest": {"concurrency": {"max_concurrent_provider_requests": 1}},
    }
    command = IngestExecutionCommand(
        generation_id=generation.generation_id,
        request_kind="test",
        vault_id="test",
        vault_path=str(vault),
        vault_identity=ensure_vault_identity(vault),
        write=False,
        write_report=False,
        append_ledger=False,
        execution_contract=contract,
        execution_contract_hash=execution_contract_hash(contract),
    )
    store = TransactionalIngestStore(vault)
    task, _ = store.submit_command(command)
    return store, task


if __name__ == "__main__":
    unittest.main()
