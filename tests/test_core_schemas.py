from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import ValidationError

from knoarbor.core.schemas import KnowledgeEvent, KnowledgeExtract, MaintenanceScope, SourceDocument, SourceRef


class CoreSchemaTests(unittest.TestCase):
    def test_knowledge_extract_exported_from_core_schemas(self) -> None:
        self.assertEqual(KnowledgeExtract.model_fields["schema_version"].default, "knowledge_extract.v1")

    def test_source_ref_requires_stable_identity_fields(self) -> None:
        source_ref = SourceRef(
            source_id="markdown:file:notes/a",
            connector="markdown",
            source_type="markdown",
            uri="file:///notes/a.md",
            display_name="a.md",
        )

        self.assertEqual(source_ref.schema_version, "source_ref.v1")
        self.assertEqual(source_ref.connector, "markdown")

    def test_source_document_accepts_standard_external_document(self) -> None:
        document = SourceDocument(
            source_id="external:session-1",
            source_type="document",
            origin={
                "connector": "external",
                "uri": "external://workspace/session-1",
                "raw_path": "raw/documents/session-1.md",
            },
            content={"format": "markdown", "text": "# Note"},
            fingerprint={
                "content_hash": "sha256:abc",
                "connector_version": "external@1",
            },
        )

        self.assertEqual(document.checkpoint.mode, "full")
        self.assertEqual(document.origin.connector, "external")

    def test_source_document_rejects_unknown_source_type(self) -> None:
        with self.assertRaises(ValidationError):
            SourceDocument(
                source_id="bad",
                source_type="unknown",
                origin={"connector": "x", "uri": "x://1", "raw_path": "raw/x"},
                content={"format": "text", "text": ""},
                fingerprint={"content_hash": "hash", "connector_version": "x@1"},
            )

    def test_event_and_scope_contracts_are_explicit(self) -> None:
        event = KnowledgeEvent(
            event_id="evt_1",
            run_id="run_1",
            event_type="source.discovered",
            created_at="2026-05-17T00:00:00Z",
        )
        scope = MaintenanceScope(
            scope_id="scope_1",
            trigger="ingest",
            source={"kind": "latest_ingest", "run_id": "run_1"},
        )

        self.assertEqual(event.schema_version, "knowledge_event.v1")
        self.assertEqual(scope.schema_version, "maintenance_scope.v1")


if __name__ == "__main__":
    unittest.main()
