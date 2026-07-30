from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from knoarbor.core.errors import StorageConflict
from knoarbor.core.schemas.ingest_run import build_excerpt_source_document
from knoarbor.core.schemas.knowledge_atoms import KnowledgeAtomBatch, KnowledgeClaim, KnowledgeEvidenceSpan
from knoarbor.core.schemas.raw_revision_edit import RawRevisionEdit
from knoarbor.core.source_unitization import SourceUnitizer, attach_source_unitization
from knoarbor.entrypoints.api import create_app
from knoarbor.pipelines.ingest_auto import _auto_source_record
from knoarbor.services.raw_revision_edits import _edited_document, build_raw_revision_ingest_request, read_raw_revision_editor
from knoarbor.storage.materialization import VaultMaterializer
from knoarbor.storage.source_records import build_source_processing_record
from knoarbor.storage.source_revisions import read_active_processing_records
from knoarbor.storage.wiki_projection import source_projection_path
from tests.transactional_ingest_helpers import publish_batch, publish_record


class RawRevisionEditTests(unittest.TestCase):
    def test_raw_excerpt_revision_rebuilds_content_derived_metadata(self) -> None:
        original = build_excerpt_source_document(text="Old evidence.", title="Old title")
        selected_content = "Corrected evidence.\n\n## Detail\n\nNested evidence remains part of the excerpt."
        content = f"# New title\n\n## Selected Excerpt\n\n{selected_content}\n"

        revised = _edited_document(original, content, "revision:parent")
        unitization = SourceUnitizer().unitize(revised)

        self.assertEqual(revised.metadata["title"], "New title")
        self.assertEqual(revised.metadata["selected_fragments"], [selected_content])
        self.assertEqual(revised.metadata["excerpt_chars"], len(selected_content))
        self.assertEqual(revised.metadata["excerpt_lines"], len(selected_content.splitlines()))
        self.assertEqual(unitization.units[0].content, selected_content)
        self.assertNotIn("Old evidence.", unitization.units[0].content)

    def test_raw_excerpt_revision_without_selection_wrapper_uses_full_edited_content(self) -> None:
        original = build_excerpt_source_document(text="Old evidence.", title="Old title")
        content = "# Replacement title\n\nReplacement body with a different structure."

        revised = _edited_document(original, content, "revision:parent")
        unitization = SourceUnitizer().unitize(revised)

        self.assertEqual(revised.metadata["title"], "Replacement title")
        self.assertEqual(revised.metadata["selected_fragments"], [content])
        self.assertEqual(unitization.units[0].content, content)
        self.assertNotIn("Old evidence.", unitization.units[0].content)

    def test_raw_excerpt_revision_materializes_only_revised_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            original = build_excerpt_source_document(text="Old evidence.", title="Old title")
            content = "# New title\n\n## Selected Excerpt\n\nCorrected evidence.\n"
            revised = attach_source_unitization(_edited_document(original, content, "revision:parent"))
            source_file = revised.origin.raw_path
            source_record = _auto_source_record(revised, source_file)
            atom_batch = KnowledgeAtomBatch(
                source_record_id=source_record.record_id,
                synthesis="Revised synthesis.",
                claims=[
                    KnowledgeClaim(
                        id="claim:revised",
                        claim="Revised claim.",
                        evidence=[
                            KnowledgeEvidenceSpan(
                                source_record_id=source_record.record_id,
                                source_unit_index=0,
                                excerpt="Corrected evidence.",
                            )
                        ],
                    )
                ],
            )
            processing_record = build_source_processing_record(
                revised,
                source_record,
                source_path=source_file,
                ingest_profile="auto_index_metadata_v1",
                atom_batch=atom_batch,
            )
            processing_record = processing_record.model_copy(
                update={"page_paths": [source_projection_path(vault, processing_record)]}
            )
            publish_record(vault, processing_record, atom_batch)

            VaultMaterializer().reconcile(vault, force=True)
            projection = next((vault / "wiki/pages").glob("*.md")).read_text(encoding="utf-8")

        self.assertIn("# New title", projection)
        self.assertIn("Corrected evidence.", projection)
        self.assertNotIn("Old evidence.", projection)

    def test_raw_edit_builds_standard_ingest_for_the_same_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            _original_revision, page = _publish_raw_fixture(vault)
            state = read_raw_revision_editor(vault, page)
            assert state is not None

            request = build_raw_revision_ingest_request(
                vault,
                page,
                RawRevisionEdit(
                    base_revision_id=state.base_revision_id,
                    content=state.content.replace("evidence", "corrected evidence"),
                ),
                config_path="/tmp/config.yaml",
                vault_id="default",
            )

        assert request.source_document is not None
        self.assertEqual(request.kind, "document")
        self.assertEqual(request.execution, "queued")
        self.assertTrue(request.write)
        self.assertTrue(request.force_reprocess)
        self.assertTrue(request.auto_scoped_lint)
        self.assertEqual(request.source_document.source_id, "sr:test")
        self.assertEqual(request.source_document.origin.raw_path, "raw/test.md")
        self.assertEqual(request.source_document.metadata["raw_revision_parent_id"], state.base_revision_id)
        self.assertIn("corrected evidence", request.source_document.content.text)

    def test_raw_edit_rejects_stale_revision_before_submission(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            _original_revision, page = _publish_raw_fixture(vault)

            with self.assertRaises(StorageConflict):
                build_raw_revision_ingest_request(
                    vault,
                    page,
                    RawRevisionEdit(base_revision_id="revision:stale", content="Test source corrected evidence."),
                    config_path="/tmp/config.yaml",
                    vault_id="default",
                )

    def test_raw_revision_api_returns_queued_ingest_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            _original_revision, page = _publish_raw_fixture(vault)
            client = TestClient(create_app())
            detail = client.get("/wiki/pages/content", params={"vault_path": str(vault), "path": page.name}).json()
            state = detail["editable_raw"]

            with patch(
                "knoarbor.services.ingest_coordinator.IngestCoordinator.start",
                return_value=SimpleNamespace(status="queued", run_id="attempt:raw-edit", run=None),
            ) as start:
                response = client.patch(
                    "/wiki/pages/raw",
                    json={
                        "vault_path": str(vault),
                        "path": page.name,
                        "edit": {
                            "schema_version": "raw_revision_edit.v1",
                            "base_revision_id": state["base_revision_id"],
                            "content": state["content"].replace("evidence", "corrected evidence"),
                        },
                    },
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["flow"], "ingest")
        self.assertEqual(response.json()["execution"], "queued")
        self.assertEqual(response.json()["run_id"], "attempt:raw-edit")
        submitted = start.call_args.args[0]
        self.assertEqual(submitted.kind, "document")
        self.assertIn("corrected evidence", submitted.source_document.content.text)


def _publish_raw_fixture(vault: Path) -> tuple[str, Path]:
    publish_batch(
        vault,
        KnowledgeAtomBatch(
            source_record_id="sr:test",
            synthesis="Original synthesis.",
            claims=[
                KnowledgeClaim(
                    id="claim:test",
                    claim="Original claim.",
                    evidence=[KnowledgeEvidenceSpan(source_record_id="sr:test", excerpt="Test source evidence.")],
                )
            ],
        ),
        page_paths=["raw-test.md"],
    )
    VaultMaterializer().reconcile(vault, force=True)
    record = (read_active_processing_records(vault) or [])[0]
    page = next((vault / "wiki" / "pages").glob("*.md"))
    return record.revision_id or "", page


if __name__ == "__main__":
    unittest.main()
