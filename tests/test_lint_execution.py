from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from knoarbor.core.schemas.knowledge_atoms import KnowledgeAtomBatch
from knoarbor.core.schemas.maintenance import MaintenanceScope, MaintenanceScopeSource
from knoarbor.core.schemas.raw_evidence import SourceProcessingRecord
from knoarbor.core.schemas.sources import SourceContent, SourceDocument, SourceFingerprint, SourceOrigin
from knoarbor.core.schemas.wiki_lint import LintRunRequest
from knoarbor.pipelines.lint import WikiLintPipeline
from knoarbor.pipelines.lint_execution import LintExecutionRouter
from knoarbor.storage.materialization import VaultMaterializer

from tests.transactional_ingest_helpers import publish_batch


class FakeIngestCoordinator:
    def __init__(self) -> None:
        self.requests = []

    def start(self, request, *, foreground=False):
        self.requests.append((request, foreground))
        return SimpleNamespace(run_id="reingest-run")


class FakeMaterializer:
    def __init__(self) -> None:
        self.calls = []

    def reconcile(self, vault, *, force=False):
        self.calls.append((Path(vault), force))
        return {"phase": "clean"}


class LintExecutionRouterTests(unittest.TestCase):
    def test_lint_restores_drifted_projection_and_rescans(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            publish_batch(
                vault,
                KnowledgeAtomBatch(source_record_id="sr:test", synthesis="Canonical synthesis."),
                page_paths=["rawtest--test.md"],
            )
            VaultMaterializer().reconcile(vault, force=True)
            page = next((vault / "wiki" / "pages").glob("*.md"))
            page.write_text("# Drifted\n", encoding="utf-8")

            result = WikiLintPipeline().run_maintenance(
                LintRunRequest(
                    vault_path=str(vault),
                    scope=MaintenanceScope(
                        scope_id="test:auto-repair",
                        trigger="manual",
                        source=MaintenanceScopeSource(kind="test"),
                    ),
                    mode="deterministic",
                    write_report=False,
                    append_ledger=False,
                )
            )

            repaired = page.read_text(encoding="utf-8")

        self.assertIn("schema_version: wiki_projection.v1", repaired)
        self.assertTrue(any(item["status"] == "completed" for item in result.repair_results))
        self.assertEqual(result.post_repair_lint.issues, [])

    def test_reingest_is_deduplicated_per_canonical_source(self) -> None:
        ingest = FakeIngestCoordinator()
        router = LintExecutionRouter(ingest=ingest, materializer=FakeMaterializer())
        record = _processing_record()
        actions = [_reingest_action("weak_claim"), _reingest_action("weak_relation")]

        with (
            tempfile.TemporaryDirectory() as tmp_dir,
            patch(
                "knoarbor.pipelines.lint_execution.read_active_processing_records",
                return_value=[record],
            ),
            patch(
                "knoarbor.pipelines.lint_execution._load_source_document",
                return_value=_source_document(),
            ),
        ):
            results = router.execute(
                tmp_dir,
                actions,
                config_path=None,
                vault_id=None,
                provider="fake",
                max_tokens=1000,
            )

        self.assertEqual(len(ingest.requests), 1)
        self.assertEqual([item["status"] for item in results], ["completed", "deduplicated"])
        request, foreground = ingest.requests[0]
        self.assertTrue(foreground)
        self.assertTrue(request.force_reprocess)
        self.assertFalse(request.auto_scoped_lint)
        self.assertEqual(request.source_document.source_id, "source:test")

    def test_projection_and_index_repairs_share_one_materialization(self) -> None:
        materializer = FakeMaterializer()
        router = LintExecutionRouter(ingest=FakeIngestCoordinator(), materializer=materializer)
        actions = [
            _rebuild_action("projection_rebuild_request"),
            _rebuild_action("index_rebuild_request"),
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            results = router.execute(
                tmp_dir,
                actions,
                config_path=None,
                vault_id=None,
                provider=None,
                max_tokens=None,
            )

        self.assertEqual(len(materializer.calls), 1)
        self.assertEqual(results[0]["status"], "completed")


def _processing_record() -> SourceProcessingRecord:
    return SourceProcessingRecord.model_validate(
        {
            "processing_record_id": "spr:test",
            "raw_record_id": "raw:test",
            "raw_revision_id": "rawrev:test",
            "revision_id": "revision:test",
            "source_record_id": "sr:test",
            "source": {
                "raw_record_id": "raw:test",
                "raw_revision_id": "rawrev:test",
                "source_id": "source:test",
                "source_type": "markdown",
                "connector": "markdown",
                "raw_path": "raw/inbox/notes/test.md",
                "title": "Test",
                "content_hash": "sha256:test",
                "metadata": {
                    "content_format": "markdown",
                    "origin": {
                        "connector": "markdown",
                        "uri": "file:///test.md",
                        "raw_path": "raw/inbox/notes/test.md",
                    },
                },
            },
            "source_units": [
                {
                    "source_unit_id": "unit:test",
                    "raw_record_id": "raw:test",
                    "raw_revision_id": "rawrev:test",
                    "unit_index": 0,
                    "content": "# Test\n\nA source-backed claim.",
                }
            ],
            "page_paths": ["Test--abc.md"],
        }
    )


def _source_document() -> SourceDocument:
    return SourceDocument(
        source_id="source:test",
        source_type="markdown",
        origin=SourceOrigin(
            connector="markdown",
            uri="file:///test.md",
            raw_path="raw/inbox/notes/test.md",
        ),
        content=SourceContent(format="markdown", text="# Test\n\nA source-backed claim."),
        fingerprint=SourceFingerprint(
            content_hash="sha256:test",
            connector_version="test.v1",
        ),
    )


def _reingest_action(issue_type: str) -> dict[str, object]:
    return {
        "action": "reingest_request",
        "owner": "ingest",
        "target": "raw:test",
        "source_record_id": "sr:test",
        "target_page": "Test--abc.md",
        "issue_type": issue_type,
    }


def _rebuild_action(action: str) -> dict[str, object]:
    return {
        "action": action,
        "owner": "projection_publication" if action.startswith("projection") else "index_publication",
        "target": "Test--abc.md",
        "target_page": "Test--abc.md",
        "issue_type": "drift",
    }
