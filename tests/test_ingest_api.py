from __future__ import annotations

import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.entrypoints.api import create_app
from knoarbor.core.schemas.ingest_pipeline import IngestPipelineResult, IngestSourceResult
from knoarbor.services import ApplicationServices


class FakeIngestService:
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


class IngestApiTests(unittest.TestCase):
    def test_ingest_run_endpoint_uses_high_level_ingest_service(self) -> None:
        services = ApplicationServices()
        services.ingest = FakeIngestService()
        client = TestClient(create_app(services))

        response = client.post("/ingest/run", json={"write": False})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["stats"]["source_count"], 1)
        self.assertEqual(payload["results"][0]["connector"], "markdown")

    def test_ingest_document_endpoint_accepts_source_document(self) -> None:
        services = ApplicationServices()
        services.ingest = FakeIngestService()
        client = TestClient(create_app(services))

        response = client.post(
            "/ingest/document",
            json={
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
                }
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["connector"], "markdown")
        self.assertEqual(payload["source_file"], "raw/notes/test.md")


if __name__ == "__main__":
    unittest.main()
