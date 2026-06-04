from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.entrypoints.api import create_app
from knoarbor.core.schemas.ingest_pipeline import IngestPipelineResult, IngestSourceResult
from knoarbor.services import ApplicationServices


class FakeIngestService:
    def run_unified(self, request):
        if request.kind == "document":
            return self.run_document(request.to_document_request())
        if request.kind == "folder":
            return self.run_folder(request.to_folder_request())
        if request.kind == "file":
            return self.run_file(request.to_file_request())
        return self.run(request.to_connectors_request())

    def run(self, request) -> IngestPipelineResult:
        return IngestPipelineResult(
            results=[
                IngestSourceResult(
                    connector="markdown",
                    source_id="source:1",
                    source_file="raw/notes/source.md",
                    should_process=True,
                    mode="new",
                    reason="Test ingest run.",
                )
            ],
            stats={"source_count": 1, "processed_count": 1, "skipped_count": 0, "written_count": 0, "failed_count": 0},
        )

    def run_document(self, request) -> IngestSourceResult:
        return IngestSourceResult(
            connector=request.source_document.origin.connector,
            source_id=request.source_document.source_id,
            source_file=request.source_document.origin.raw_path,
            should_process=True,
            mode="new",
            reason="Test document ingest.",
        )

    def run_file(self, request) -> IngestPipelineResult:
        return self.run(request)

    def run_folder(self, request) -> IngestPipelineResult:
        return IngestPipelineResult(
            results=[
                IngestSourceResult(
                    connector="markdown",
                    source_id="folder:1",
                    source_file=request.input_path,
                    should_process=True,
                    mode="folder",
                    reason="Test folder ingest.",
                )
            ],
            stats={"source_count": 1, "processed_count": 1, "skipped_count": 0, "written_count": 0, "failed_count": 0},
        )


class IngestApiTests(unittest.TestCase):
    def test_run_ingest_direct_returns_result_without_run_record(self) -> None:
        services = ApplicationServices()
        services.ingest = FakeIngestService()
        client = TestClient(create_app(services))

        response = client.post(
            "/ingest",
            json={"execution": "direct", "kind": "connectors", "write": False},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["flow"], "ingest")
        self.assertEqual(payload["execution"], "direct")
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["result"]["stats"]["source_count"], 1)
        self.assertIsNone(payload["run_id"])

    def test_run_ingest_connectors_uses_high_level_ingest_service(self) -> None:
        services = ApplicationServices()
        services.ingest = FakeIngestService()
        client = TestClient(create_app(services))

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "wiki"
            vault.mkdir()
            config = root / "config.yaml"
            config.write_text(f"vault:\n  path: {vault}\n", encoding="utf-8")
            response = client.post(
                "/ingest",
                json={"execution": "queued", "kind": "connectors", "config_path": str(config), "write": False},
            )
            self.assertEqual(response.status_code, 200)
            response_payload = response.json()
            self.assertEqual(response_payload["flow"], "ingest")
            self.assertEqual(response_payload["execution"], "queued")
            run_id = response_payload["run_id"]
            payload = _wait_for_run(client, str(vault), run_id)

        self.assertEqual(payload["status"], "completed")

    def test_recovery_kind_rejects_direct_execution(self) -> None:
        client = TestClient(create_app())

        response = client.post(
            "/ingest",
            json={
                "execution": "direct",
                "kind": "recovery",
                "recovery_vault_path": "/tmp/wiki",
                "recovery_of_run_id": "run-1",
            },
        )

        self.assertEqual(response.status_code, 422)

    def test_run_ingest_document_accepts_source_document(self) -> None:
        services = ApplicationServices()
        services.ingest = FakeIngestService()
        client = TestClient(create_app(services))

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "wiki"
            vault.mkdir()
            config = root / "config.yaml"
            config.write_text(f"vault:\n  path: {vault}\n", encoding="utf-8")
            response = client.post(
                "/ingest",
                json={
                    "execution": "queued",
                    "kind": "document",
                    "config_path": str(config),
                    "obsidian_vault_path": str(vault),
                    "source_document": {
                        "schema_version": "source_document.v1",
                        "source_id": "note:test",
                        "source_type": "markdown",
                        "origin": {
                            "connector": "markdown",
                            "uri": "file:///tmp/test.md",
                            "raw_path": "raw/notes/test.md",
                        },
                        "metadata": {"title": "Test"},
                        "content": {"format": "markdown", "text": "# Test\n\nBody."},
                        "fingerprint": {"content_hash": "abc123", "connector_version": "test"},
                        "checkpoint": {"mode": "full"},
                    },
                },
            )
            self.assertEqual(response.status_code, 200)
            response_payload = response.json()
            self.assertEqual(response_payload["flow"], "ingest")
            self.assertEqual(response_payload["execution"], "queued")
            run_id = response_payload["run_id"]
            payload = _wait_for_run(client, str(vault), run_id)

        self.assertEqual(payload["status"], "completed")

    def test_run_ingest_folder_accepts_queued_folder_input(self) -> None:
        services = ApplicationServices()
        services.ingest = FakeIngestService()
        client = TestClient(create_app(services))

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "wiki"
            folder = root / "notes"
            vault.mkdir()
            folder.mkdir()
            config = root / "config.yaml"
            config.write_text(f"vault:\n  path: {vault}\n", encoding="utf-8")
            response = client.post(
                "/ingest",
                json={
                    "execution": "queued",
                    "kind": "folder",
                    "config_path": str(config),
                    "input_path": str(folder),
                    "write": False,
                },
            )
            self.assertEqual(response.status_code, 200)
            response_payload = response.json()
            self.assertEqual(response_payload["flow"], "ingest")
            self.assertEqual(response_payload["execution"], "queued")
            run_id = response_payload["run_id"]
            payload = _wait_for_run(client, str(vault), run_id)

        self.assertEqual(payload["status"], "completed")


def _wait_for_run(client: TestClient, vault_path: str, run_id: str) -> dict:
    payload = {}
    for _ in range(20):
        response = client.get(f"/runs/{run_id}", params={"vault_path": vault_path})
        response.raise_for_status()
        payload = response.json()
        if payload["status"] == "completed":
            return payload
        time.sleep(0.05)
    return payload


if __name__ == "__main__":
    unittest.main()
