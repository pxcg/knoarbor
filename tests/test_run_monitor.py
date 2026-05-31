from __future__ import annotations

import tempfile
import threading
import time
import unittest
import json
from datetime import datetime, timedelta
from pathlib import Path

from knoarbor.core.schemas.ingest_run import IngestFileRunRequest, IngestRecoveryRunRequest
from knoarbor.core.schemas.wiki_query import WikiSearchRequest
from knoarbor.runtime import KNOWN_RUN_EVENT_TYPES, RunReporter, run_monitor_context
from knoarbor.runtime.run_monitor import RunMonitor, list_runs, read_run, read_run_events, request_cancel
from knoarbor.services.run_manager import RunManager


class RunMonitorTests(unittest.TestCase):
    def test_monitor_writes_record_and_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            monitor = RunMonitor(vault_path=vault, flow="ingest", run_id="run-test")
            monitor.start(message="start")
            monitor.event("segment_started", stage="semantic", message="working", progress={"total": 2, "completed": 1})
            monitor.complete(message="done", result_summary={"written_pages": 1})

            record = list_runs(vault).runs[0]
            events = read_run_events(vault, "run-test")

        self.assertEqual(record.status, "completed")
        self.assertEqual(record.result_summary["written_pages"], 1)
        self.assertEqual([event.event_type for event in events], ["run_started", "segment_started", "run_completed"])

    def test_reporter_uses_frozen_event_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            monitor = RunMonitor(vault_path=vault, flow="ingest", run_id="reporter-test")
            monitor.start(message="start")
            with run_monitor_context(monitor):
                RunReporter.current().model_call_retrying(
                    contract_name="source_normalize",
                    schema_version="knowledge_extract.v1",
                    attempt=2,
                    max_attempts=3,
                    previous_error=RuntimeError("temporary"),
                    backoff_seconds=0,
                )
            monitor.complete(message="done")
            events = read_run_events(vault, "reporter-test")

        self.assertIn("model_call_retrying", KNOWN_RUN_EVENT_TYPES)
        self.assertTrue(any(event.event_type == "model_call_retrying" for event in events))
        retry_event = next(event for event in events if event.event_type == "model_call_retrying")
        self.assertEqual(retry_event.payload["previous_error"]["code"], "KA-INTERNAL-001")
        self.assertIn("hint", retry_event.payload["previous_error"])

    def test_monitor_records_structured_failure_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            monitor = RunMonitor(vault_path=vault, flow="ingest", run_id="fail-test")
            monitor.start(message="start")
            monitor.fail(FileNotFoundError("missing source"))

            record = list_runs(vault).runs[0]
            events = read_run_events(vault, "fail-test")

        self.assertEqual(record.status, "failed")
        self.assertEqual(record.error_info["code"], "KA-INPUT-002")
        self.assertIn("KA-INPUT-002", record.error or "")
        failed_event = next(event for event in events if event.event_type == "run_failed")
        self.assertEqual(failed_event.payload["error"]["code"], "KA-INPUT-002")

    def test_monitor_records_partial_failure_as_terminal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            monitor = RunMonitor(vault_path=vault, flow="ingest", run_id="partial-test")
            monitor.start(message="start")
            monitor.partially_fail(message="one source failed", result_summary={"processed": 2, "failed": 1})

            record = list_runs(vault).runs[0]
            events = read_run_events(vault, "partial-test")

        self.assertEqual(record.status, "partially_failed")
        self.assertEqual(record.stage, "partially_failed")
        self.assertEqual(record.result_summary["failed"], 1)
        self.assertTrue(any(event.event_type == "run_partially_failed" for event in events))

    def test_stale_cancelling_run_is_reconciled_to_cancelled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            monitor = RunMonitor(vault_path=vault, flow="lint", run_id="stale-cancel")
            monitor.queue(message="queued")
            record = request_cancel(vault, "stale-cancel")
            old_heartbeat = (datetime.now() - timedelta(minutes=5)).isoformat(timespec="seconds")
            data = record.model_dump()
            data["last_heartbeat_at"] = old_heartbeat
            data["updated_at"] = old_heartbeat
            monitor.record_path.write_text(json.dumps(data), encoding="utf-8")

            active = list_runs(vault, active_only=True).runs
            reconciled = read_run(vault, "stale-cancel")
            events = read_run_events(vault, "stale-cancel")

        self.assertEqual(active, [])
        self.assertEqual(reconciled.status, "cancelled")
        self.assertTrue(any(event.event_type == "run_cancelled" and event.payload.get("reconciled") for event in events))

    def test_repeated_cancel_does_not_refresh_cancelling_heartbeat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            monitor = RunMonitor(vault_path=vault, flow="lint", run_id="repeat-cancel")
            monitor.queue(message="queued")
            first = request_cancel(vault, "repeat-cancel")
            old_heartbeat = (datetime.now() - timedelta(seconds=10)).isoformat(timespec="seconds")
            data = first.model_dump()
            data["last_heartbeat_at"] = old_heartbeat
            monitor.record_path.write_text(json.dumps(data), encoding="utf-8")

            second = request_cancel(vault, "repeat-cancel")

        self.assertEqual(second.status, "cancelling")
        self.assertEqual(second.last_heartbeat_at, old_heartbeat)

    def test_run_manager_runs_background_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            manager = RunManager()
            started = manager.start_query(
                WikiSearchRequest(obsidian_vault_path=str(vault), query="agent", record_query=False),
                lambda request: {"query": request.query, "results": []},
            )
            for _ in range(20):
                record = manager.read(str(vault), started.run_id)
                if record.status == "completed":
                    break
                time.sleep(0.05)
            events = manager.events(str(vault), started.run_id).events

        self.assertEqual(record.status, "completed")
        self.assertTrue(any(event.event_type == "worker_started" for event in events))

    def test_run_manager_marks_ingest_result_with_failures_as_partial(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            config = vault / "config.yaml"
            config.write_text(f"vault:\n  path: {vault}\n", encoding="utf-8")
            manager = RunManager()
            started = manager.start_ingest_file(
                request=IngestFileRunRequest(
                    config_path=str(config),
                    input_path=str(vault / "source.md"),
                    write=False,
                ),
                runner=lambda _request: {
                    "stats": {
                        "source_count": 2,
                        "processed_count": 1,
                        "failed_count": 1,
                        "failed_segment_count": 0,
                        "document_processing_failed_count": 0,
                    }
                },
            )
            for _ in range(20):
                record = manager.read(str(vault), started.run_id)
                if record.status == "partially_failed":
                    break
                time.sleep(0.05)
            events = manager.events(str(vault), started.run_id).events

        self.assertEqual(record.status, "partially_failed")
        self.assertEqual(record.result_summary["stats"]["failed_count"], 1)
        self.assertTrue(any(event.event_type == "run_partially_failed" for event in events))

    def test_run_manager_recovers_ingest_run_from_previous_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            config = vault / "config.yaml"
            config.write_text(f"vault:\n  path: {vault}\n", encoding="utf-8")
            manager = RunManager()
            first = manager.start_ingest_file(
                request=IngestFileRunRequest(config_path=str(config), input_path=str(vault / "source.md"), write=False),
                runner=lambda _request: {"stats": {"failed_count": 1}},
            )
            for _ in range(20):
                first_record = manager.read(str(vault), first.run_id)
                if first_record.status == "partially_failed":
                    break
                time.sleep(0.05)

            recovered_inputs: list[str] = []
            second = manager.start_ingest_recovery(
                str(vault),
                first.run_id,
                IngestRecoveryRunRequest(write=True),
                ingest_runner=lambda _request: {"stats": {"failed_count": 0}},
                ingest_file_runner=lambda request: recovered_inputs.append(request.input_path) or {"stats": {"failed_count": 0}},
            )
            for _ in range(20):
                second_record = manager.read(str(vault), second.run_id)
                if second_record.status == "completed":
                    break
                time.sleep(0.05)

        self.assertEqual(first_record.status, "partially_failed")
        self.assertEqual(second_record.status, "completed")
        self.assertEqual(recovered_inputs, [str(vault / "source.md")])
        self.assertEqual(second_record.metadata["recovery_of_run_id"], first.run_id)

    def test_run_manager_serializes_runs_for_one_vault(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            manager = RunManager()
            release_first = threading.Event()
            first_started = threading.Event()
            order: list[str] = []

            def runner(request: WikiSearchRequest) -> dict[str, object]:
                order.append(request.query)
                if request.query == "first":
                    first_started.set()
                    release_first.wait(2)
                return {"query": request.query, "results": []}

            first = manager.start_query(WikiSearchRequest(obsidian_vault_path=str(vault), query="first", record_query=False), runner)
            self.assertEqual(first.status, "queued")
            self.assertTrue(first_started.wait(2))

            second = manager.start_query(WikiSearchRequest(obsidian_vault_path=str(vault), query="second", record_query=False), runner)
            time.sleep(0.1)
            second_record = manager.read(str(vault), second.run_id)
            self.assertEqual(second_record.status, "queued")
            self.assertEqual(order, ["first"])
            self.assertTrue((vault / ".knoarbor" / "queue" / f"{first.run_id}.json").exists())
            self.assertTrue((vault / ".knoarbor" / "queue" / f"{second.run_id}.json").exists())

            release_first.set()
            for _ in range(40):
                first_record = manager.read(str(vault), first.run_id)
                second_record = manager.read(str(vault), second.run_id)
                if first_record.status == "completed" and second_record.status == "completed":
                    break
                time.sleep(0.05)

        self.assertEqual(first_record.status, "completed")
        self.assertEqual(second_record.status, "completed")
        self.assertEqual(order, ["first", "second"])


if __name__ == "__main__":
    unittest.main()
