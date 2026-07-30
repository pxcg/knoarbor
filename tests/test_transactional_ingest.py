from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from knoarbor.core.errors import StorageConflict, UserInputError
from knoarbor.runtime.transactional_ingest import TransactionalIngestStore
from tests.transactional_ingest_helpers import admit_test_task


class TransactionalIngestStoreTests(unittest.TestCase):
    def test_submit_deduplicates_active_input_and_claim_fences_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store, task, attempt = admit_test_task(Path(tmp_dir), "same")
            _, duplicate_task, duplicate_attempt = admit_test_task(Path(tmp_dir), "same")
            lease = store.claim(task["task_id"], attempt["attempt_id"], owner_id="worker-a", lease_seconds=30)

            self.assertEqual(task["task_id"], duplicate_task["task_id"])
            self.assertEqual(attempt["attempt_id"], duplicate_attempt["attempt_id"])
            self.assertEqual(lease.attempt_id, attempt["attempt_id"])
            with self.assertRaises(StorageConflict):
                store.claim(task["task_id"], attempt["attempt_id"], owner_id="worker-b", lease_seconds=30)
            finished = store.finish(lease, state="completed", result={"processed": 1})
            self.assertEqual(finished["state"], "completed")

    def test_current_worker_can_renew_its_lease(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store, task, attempt = admit_test_task(Path(tmp_dir), "renew")
            lease = store.claim(task["task_id"], attempt["attempt_id"], owner_id="worker", lease_seconds=1)
            renewed = store.renew(lease, lease_seconds=30)
            self.assertEqual(renewed.epoch, lease.epoch)
            self.assertGreater(renewed.expires_at, lease.expires_at)

    def test_historical_attempt_cannot_cancel_current_recovery_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store, task, first = admit_test_task(Path(tmp_dir), "cancel")
            with store._transaction() as connection:
                connection.execute("update tasks set state='failed' where task_id=?", (task["task_id"],))
                connection.execute(
                    "update attempts set result=? where attempt_id=?",
                    ('{"failure":{"retryable":true}}', first["attempt_id"]),
                )
            _, second = store.admit_recovery(task["task_id"], expected_attempt_id=first["attempt_id"])

            with self.assertRaises(StorageConflict):
                store.request_cancel(task["task_id"], expected_attempt_id=first["attempt_id"])
            with self.assertRaises(UserInputError):
                store.admit_recovery(task["task_id"], expected_attempt_id=first["attempt_id"])
            self.assertNotEqual(first["attempt_id"], second["attempt_id"])

    def test_non_retryable_failure_cannot_be_recovered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store, task, attempt = admit_test_task(Path(tmp_dir), "non-retryable")
            store.fail_queued_task(
                task["task_id"],
                attempt["attempt_id"],
                error="bad input",
                result={"failure": {"retryable": False}},
            )

            assessment = store.recovery_assessment(task["task_id"], expected_attempt_id=attempt["attempt_id"])

            self.assertFalse(assessment["available"])
            with self.assertRaises(UserInputError):
                store.admit_recovery(task["task_id"], expected_attempt_id=attempt["attempt_id"])

    def test_expired_running_attempt_can_be_explicitly_recovered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store, task, attempt = admit_test_task(Path(tmp_dir), "expired")
            store.claim(task["task_id"], attempt["attempt_id"], owner_id="dead-worker", lease_seconds=1)
            with store._transaction() as connection:
                connection.execute("update tasks set lease_expires_at=? where task_id=?", (0, task["task_id"]))
            _, replacement = store.admit_recovery(task["task_id"], expected_attempt_id=attempt["attempt_id"])
            self.assertNotEqual(replacement["attempt_id"], attempt["attempt_id"])
            self.assertEqual(store.attempt(attempt["attempt_id"])["state"], "recovery_needed")

    def test_revision_publication_requires_current_lease_and_source_head(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store, task, attempt = admit_test_task(Path(tmp_dir), "publish")
            lease = store.claim(task["task_id"], attempt["attempt_id"], owner_id="worker-a", lease_seconds=30)
            revision = store.publish_revision(
                lease,
                source_id="source:a",
                expected_source_head=None,
                revision_id=store.new_revision_id(),
                manifest_path="revisions/one/manifest.json",
                manifest_hash="sha256:one",
                entity_contributions={"ent:one": {"name": "One"}},
            )

            self.assertTrue(revision.startswith("revision_"))
            with self.assertRaises(StorageConflict):
                store.publish_revision(
                    lease,
                    source_id="source:a",
                    expected_source_head=None,
                    revision_id=store.new_revision_id(),
                    manifest_path="revisions/two/manifest.json",
                    manifest_hash="sha256:two",
                )

    def test_empty_legacy_json_queue_marker_is_retired(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            legacy_queue = vault / ".knoarbor" / "ingest_queue"
            legacy_queue.mkdir(parents=True)

            TransactionalIngestStore(vault)

            self.assertFalse(legacy_queue.exists())

    def test_legacy_json_queue_with_data_is_rejected_explicitly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            legacy_queue = vault / ".knoarbor" / "ingest_queue"
            legacy_queue.mkdir(parents=True)
            (legacy_queue / "task.json").write_text("{}", encoding="utf-8")

            with self.assertRaisesRegex(StorageConflict, "removed JSON ingest queue format with retained data"):
                TransactionalIngestStore(vault)

if __name__ == "__main__":
    unittest.main()
