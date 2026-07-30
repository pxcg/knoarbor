from __future__ import annotations

import tempfile
import threading
import time
import unittest
import multiprocessing
import inspect
import queue
from pathlib import Path
from unittest.mock import patch

from knoarbor.core.errors import StorageConflict
from knoarbor.core.schemas.ingest_execution import IngestExecutionCommand, execution_contract_hash
from knoarbor.runtime.local_operations import LocalOperationScheduler
from knoarbor.runtime.locks import vault_write_lock
from knoarbor.runtime.transactional_ingest import FORMAT_VERSION, TransactionalIngestStore
from knoarbor.storage.ingest_inputs import write_input_generation
from knoarbor.storage.materialization import VaultMaterializer
from knoarbor.storage.vault_identity import ensure_vault_identity
from knoarbor.storage.index_snapshot import open_index_snapshot
from knoarbor.storage.wiki_index import prepare_machine_index
from knoarbor.storage.wiki_init import init_wiki_vault
from knoarbor.pipelines import ingest_auto
from knoarbor.storage import materialization, wiki_index
from tests.transactional_ingest_helpers import admit_test_task


class IngestV5ArchitectureTests(unittest.TestCase):
    def test_execution_and_materialization_boundaries_have_one_owner_each(self) -> None:
        pipeline_source = inspect.getsource(ingest_auto)
        materializer_source = inspect.getsource(materialization.VaultMaterializer.reconcile)

        self.assertNotIn("TransactionalIngestStore", pipeline_source)
        self.assertNotIn("AttemptLease", pipeline_source)
        self.assertNotIn("while True", materializer_source)
        self.assertNotIn("knoarbor.pipelines", inspect.getsource(materialization))
        self.assertFalse(hasattr(wiki_index, "update_index"))
        self.assertFalse(hasattr(wiki_index, "update_machine_index"))

    def test_fresh_store_has_one_materialization_state_and_no_removed_runtime_tables(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = TransactionalIngestStore(Path(tmp_dir))
            with store._read_connection() as connection:
                version = connection.execute("select version from ingest_format").fetchone()[0]
                tables = {row[0] for row in connection.execute("select name from sqlite_master where type='table'")}

            self.assertEqual(version, FORMAT_VERSION)
            self.assertIn("materialization_state", tables)
            self.assertNotIn("derived_jobs", tables)
            self.assertNotIn("segment_results", tables)
            self.assertNotIn("task_commands", tables)
            self.assertEqual(store.materialization_state()["phase"], "dirty")
            self.assertEqual(store.materialization_state()["requested_epoch"], 1)

    def test_v4_migration_rejects_recoverable_task_without_immutable_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            store, task, _ = admit_test_task(vault, "invalid-migration")
            with store._transaction() as connection:
                connection.execute("update ingest_format set version='transactional_ingest.v4'")
                connection.execute("update tasks set command=null where task_id=?", (task["task_id"],))

            with self.assertRaisesRegex(Exception, "valid immutable command"):
                TransactionalIngestStore(vault)

    def test_pre_v4_store_is_rejected_instead_of_entering_a_compatibility_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            store = TransactionalIngestStore(vault)
            with store._transaction() as connection:
                connection.execute("update ingest_format set version='transactional_ingest.v3'")

            with self.assertRaisesRegex(Exception, "Unsupported transactional ingest store format"):
                TransactionalIngestStore(vault)

    def test_v4_migration_removes_old_lifecycles_and_normalizes_queued_work(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            store, task, attempt = admit_test_task(vault, "migration")
            with store._transaction() as connection:
                connection.execute("update ingest_format set version='transactional_ingest.v4'")
                connection.execute("update tasks set state='waiting_admission' where task_id=?", (task["task_id"],))
                connection.execute("update attempts set state='waiting_admission' where attempt_id=?", (attempt["attempt_id"],))
                connection.execute("create table derived_jobs(job_id text primary key)")
                connection.execute("create table segment_results(task_id text primary key)")
                connection.execute("create table task_commands(id integer primary key)")

            migrated = TransactionalIngestStore(vault)
            self.assertEqual(migrated.task(str(task["task_id"]))["state"], "queued")
            self.assertEqual(migrated.attempt(str(attempt["attempt_id"]))["state"], "queued")
            with migrated._read_connection() as connection:
                tables = {row[0] for row in connection.execute("select name from sqlite_master where type='table'")}
            self.assertNotIn("derived_jobs", tables)
            self.assertNotIn("segment_results", tables)
            self.assertNotIn("task_commands", tables)
            with migrated._read_connection() as connection:
                phase = connection.execute(
                    "select phase from ingest_migrations where name='transactional_ingest.v5'"
                ).fetchone()[0]
            self.assertEqual(phase, "index_ready")
            VaultMaterializer().reconcile(vault)
            with migrated._read_connection() as connection:
                phase = connection.execute(
                    "select phase from ingest_migrations where name='transactional_ingest.v5'"
                ).fetchone()[0]
            self.assertEqual(phase, "complete")

    def test_prepared_materialization_resumes_after_process_interruption(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            init_wiki_vault(vault)
            store = TransactionalIngestStore(vault)
            with patch("knoarbor.storage.materialization._publish_machine_index", side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    VaultMaterializer().reconcile(vault, force=True)

            self.assertEqual(store.materialization_state()["phase"], "prepared")
            state = VaultMaterializer().reconcile(vault)
            self.assertEqual(state["phase"], "clean")
            self.assertEqual(state["published_epoch"], state["requested_epoch"])
            self.assertEqual(open_index_snapshot(vault).generation_id, state["published_index_generation"])

    def test_external_local_wiki_edit_is_detected_by_bounded_reconciliation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            init_wiki_vault(vault)
            store = TransactionalIngestStore(vault)
            first = VaultMaterializer().reconcile(vault, force=True)
            page = vault / "wiki" / "pages" / "manual.md"
            page.write_text("# Manual\n\nLocal edit.\n", encoding="utf-8")

            second = VaultMaterializer().reconcile(vault)
            self.assertEqual(second["phase"], "clean")
            self.assertGreater(int(second["requested_epoch"]), int(first["requested_epoch"]))
            self.assertNotEqual(second["published_index_generation"], first["published_index_generation"])
            self.assertEqual(store.materialization_state()["published_epoch"], second["published_epoch"])

    def test_wiki_change_during_index_scan_discards_unstable_generation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            init_wiki_vault(vault)
            TransactionalIngestStore(vault)
            page = vault / "wiki" / "pages" / "during-build.md"
            calls = 0

            def prepare_with_edit(path: Path, *, target_generation: str | None = None):
                nonlocal calls
                calls += 1
                if calls == 1:
                    page.write_text("# During Build\n\nExternal local edit.\n", encoding="utf-8")
                return prepare_machine_index(path, target_generation=target_generation)

            with patch("knoarbor.storage.materialization.prepare_machine_index", side_effect=prepare_with_edit):
                first = VaultMaterializer().reconcile(vault, force=True)
                state = VaultMaterializer().reconcile(vault)

            self.assertNotEqual(first["phase"], "clean")
            self.assertEqual(state["phase"], "clean")
            self.assertEqual(calls, 2)
            snapshot = open_index_snapshot(vault)
            pages = (snapshot.path / "pages.json").read_text(encoding="utf-8")
            self.assertIn("during-build.md", pages)

    def test_startup_prunes_index_generations_unreachable_from_materialization_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            init_wiki_vault(vault)
            materializer = VaultMaterializer()
            for version in range(2):
                (vault / "wiki" / "pages" / "manual.md").write_text(
                    f"# Manual\n\nVersion {version}.\n",
                    encoding="utf-8",
                )
                materializer.reconcile(vault)

            generations = vault / ".knoarbor" / "index" / "generations"
            self.assertEqual(len([path for path in generations.iterdir() if path.is_dir()]), 3)

            removed = materializer.prune_unreachable_index_generations(vault)
            current = open_index_snapshot(vault)

            self.assertEqual(len(removed), 2)
            self.assertEqual([path.name for path in generations.iterdir() if path.is_dir()], [current.generation_id])

    def test_reconcile_rebuilds_an_unreadable_published_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            init_wiki_vault(vault)
            materializer = VaultMaterializer()
            before = open_index_snapshot(vault)
            expected_bytes = before.retrieval_path.read_bytes()
            before.retrieval_path.write_bytes(expected_bytes + b"corrupt")

            state = materializer.reconcile(vault)
            after = open_index_snapshot(vault)

            self.assertEqual(state["phase"], "clean")
            self.assertEqual(after.generation_id, before.generation_id)
            self.assertEqual(after.retrieval_path.read_bytes(), expected_bytes)

    def test_startup_pruning_preserves_current_and_prepared_generations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            init_wiki_vault(vault)
            materializer = VaultMaterializer()
            current = open_index_snapshot(vault)
            (vault / "wiki" / "pages" / "prepared.md").write_text("# Prepared\n", encoding="utf-8")
            with patch("knoarbor.storage.materialization._publish_machine_index", side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    materializer.reconcile(vault)

            state = TransactionalIngestStore(vault).materialization_state()
            prepared = str(state["prepared_index_generation"])

            self.assertEqual(materializer.prune_unreachable_index_generations(vault), [])
            self.assertEqual(
                {path.name for path in (vault / ".knoarbor" / "index" / "generations").iterdir() if path.is_dir()},
                {current.generation_id, prepared},
            )

    def test_local_operation_scheduler_deduplicates_only_live_operation(self) -> None:
        scheduler = LocalOperationScheduler(max_workers=2)
        release = threading.Event()
        calls = 0

        def operation(_token):
            nonlocal calls
            calls += 1
            release.wait(1)
            return calls

        first = scheduler.submit("task", operation)
        second = scheduler.submit("task", operation)
        self.assertIs(first, second)
        release.set()
        self.assertEqual(first.result(timeout=1), 1)
        deadline = time.time() + 1
        while scheduler._futures and time.time() < deadline:
            time.sleep(0.01)
        self.assertFalse(scheduler._futures)
        scheduler.shutdown()

    def test_force_invocation_is_persisted_and_distinguishes_user_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            generation = write_input_generation(vault, documents=[])
            contract = {"provider": {"name": "test"}}

            def command(invocation: str) -> IngestExecutionCommand:
                return IngestExecutionCommand(
                    generation_id=generation.generation_id,
                    request_kind="test",
                    vault_id="test",
                    vault_path=str(vault),
                    vault_identity=ensure_vault_identity(vault),
                    write=True,
                    write_report=False,
                    append_ledger=False,
                    force_reprocess=True,
                    force_invocation_id=invocation,
                    execution_contract=contract,
                    execution_contract_hash=execution_contract_hash(contract),
                )

            store = TransactionalIngestStore(vault)
            first, _ = store.submit_command(command("invocation-1"))
            duplicate, _ = store.submit_command(command("invocation-1"))
            second, _ = store.submit_command(command("invocation-2"))
            self.assertEqual(first["task_id"], duplicate["task_id"])
            self.assertNotEqual(first["task_id"], second["task_id"])

    def test_stale_attempt_lease_cannot_finish(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store, task, attempt = admit_test_task(Path(tmp_dir), "lease")
            lease = store.claim(str(task["task_id"]), str(attempt["attempt_id"]), owner_id="one", lease_seconds=0.01)
            time.sleep(0.02)
            with self.assertRaisesRegex(Exception, "Stale ingest worker"):
                store.finish(lease, state="completed")

    def test_two_local_processes_cannot_claim_the_same_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            _, task, attempt = admit_test_task(vault, "process-race")
            context = multiprocessing.get_context("spawn")
            start = context.Event()
            results = context.Queue()
            processes = [
                context.Process(
                    target=_claim_task,
                    args=(str(vault), str(task["task_id"]), str(attempt["attempt_id"]), start, results),
                )
                for _ in range(2)
            ]
            for process in processes:
                process.start()
            start.set()
            values = [results.get(timeout=5) for _ in processes]
            for process in processes:
                process.join(timeout=5)
                self.assertEqual(process.exitcode, 0)

            self.assertEqual(sorted(values), ["claimed", "conflict"])

    def test_vault_write_lock_serializes_two_local_processes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            context = multiprocessing.get_context("spawn")
            release = context.Event()
            events = context.Queue()
            holder = context.Process(target=_hold_vault_lock, args=(tmp_dir, release, events))
            contender = context.Process(target=_take_vault_lock, args=(tmp_dir, events))
            holder.start()
            self.assertEqual(events.get(timeout=5), "holder")
            contender.start()
            with self.assertRaises(queue.Empty):
                events.get(timeout=0.15)
            release.set()
            self.assertEqual(events.get(timeout=5), "contender")
            holder.join(timeout=5)
            contender.join(timeout=5)
            self.assertEqual(holder.exitcode, 0)
            self.assertEqual(contender.exitcode, 0)


def _claim_task(vault: str, task_id: str, attempt_id: str, start, results) -> None:
    start.wait()
    try:
        TransactionalIngestStore(Path(vault)).claim(
            task_id,
            attempt_id,
            owner_id=f"process:{multiprocessing.current_process().pid}",
            lease_seconds=30,
        )
        results.put("claimed")
    except StorageConflict:
        results.put("conflict")


def _hold_vault_lock(vault: str, release, events) -> None:
    with vault_write_lock(Path(vault)):
        events.put("holder")
        release.wait(5)


def _take_vault_lock(vault: str, events) -> None:
    with vault_write_lock(Path(vault)):
        events.put("contender")


if __name__ == "__main__":
    unittest.main()
