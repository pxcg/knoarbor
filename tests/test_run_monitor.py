from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from knoarbor.core.schemas.wiki_query import WikiSearchRequest
from knoarbor.runtime.run_monitor import RunMonitor, read_run, read_run_events
from knoarbor.services.run_manager import RunManager


class RunMonitorTests(unittest.TestCase):
    def test_monitor_writes_record_and_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            monitor = RunMonitor(vault_path=vault, flow="ingest", run_id="run-test")
            monitor.start(message="start")
            monitor.event("segment_started", stage="semantic", message="working")
            monitor.complete(message="done", result_summary={"written_pages": 1})
            record = read_run(vault, "run-test")
            self.assertEqual(record.status, "completed")
            self.assertEqual([item.sequence for item in read_run_events(vault, "run-test")], [1, 2, 3])

    def test_monitor_omits_raw_content_from_event_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            monitor = RunMonitor(vault_path=vault, flow="ingest", run_id="payload-test")
            monitor.start()
            monitor.event("source_units_created", payload={"content": "secret", "count": 2})
            payload = read_run_events(vault, "payload-test")[-1].payload
            self.assertNotIn("secret", str(payload))
            self.assertEqual(payload["count"], 2)

    def test_monitor_records_failure_and_partial_terminal_states(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            failed = RunMonitor(vault_path=vault, flow="ingest", run_id="failed")
            failed.start()
            failed.fail(ValueError("bad input"))
            partial = RunMonitor(vault_path=vault, flow="ingest", run_id="partial")
            partial.start()
            partial.partially_fail(message="one failed", result_summary={"failed": 1})
            self.assertEqual(read_run(vault, "failed").status, "failed")
            self.assertEqual(read_run(vault, "partial").status, "partially_failed")

    def test_two_monitor_instances_append_unique_sequences(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            first = RunMonitor(vault_path=vault, flow="ingest", run_id="shared")
            second = RunMonitor(vault_path=vault, flow="ingest", run_id="shared")
            first.queue()
            first.event("source_queued")
            second.event("source_queued")
            sequences = [item.sequence for item in read_run_events(vault, "shared")]
            self.assertEqual(sequences, [1, 2, 3])

    def test_run_manager_runs_non_ingest_background_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            started = RunManager().start_query(
                WikiSearchRequest(vault_path=str(vault), query="test"),
                lambda _request: {"query": "test", "results": []},
            )
            deadline = time.time() + 3
            while time.time() < deadline and read_run(vault, started.run_id).status not in {"completed", "failed"}:
                time.sleep(0.01)
            self.assertEqual(read_run(vault, started.run_id).status, "completed")


if __name__ == "__main__":
    unittest.main()
