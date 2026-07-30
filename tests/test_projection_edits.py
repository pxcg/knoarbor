from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from knoarbor.core.errors import PolicyRejection, StorageConflict
from knoarbor.core.schemas.knowledge_atoms import (
    KnowledgeAtomBatch,
    KnowledgeAtomObject,
    KnowledgeClaim,
    KnowledgeEvidenceSpan,
    KnowledgeRelation,
)
from knoarbor.core.schemas.projection_edit import ProjectionEdit
from knoarbor.services.projection_edits import _edited_batch
from knoarbor.entrypoints.api import create_app
from knoarbor.services.wiki_pages import WikiPageService
from knoarbor.storage.materialization import VaultMaterializer
from knoarbor.storage.source_revisions import read_active_atom_batches, read_active_processing_records

from tests.transactional_ingest_helpers import publish_batch


class ProjectionEditTests(unittest.TestCase):
    def test_projection_edit_api_uses_structured_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            _publish_projection(vault)
            page = next((vault / "wiki" / "pages").glob("*.md"))
            client = TestClient(create_app())
            detail = client.get("/wiki/pages/content", params={"vault_path": str(vault), "path": page.name}).json()
            state = detail["editable_projection"]
            state["synthesis"] = "Edited through the structured API."
            edit = {
                "schema_version": "projection_edit.v1",
                "base_revision_id": state["base_revision_id"],
                "synthesis": state["synthesis"],
                "claims": [{"id": claim["id"], "claim": claim["claim"]} for claim in state["claims"]],
                "entities": state["entities"],
                "relations": state["relations"],
            }

            response = client.patch(
                "/wiki/pages/content",
                json={"vault_path": str(vault), "path": page.name, "edit": edit},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["editable_projection"]["synthesis"], "Edited through the structured API.")

    def test_consecutive_edits_preserve_prior_override_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            _publish_projection(vault)
            page = next((vault / "wiki" / "pages").glob("*.md"))
            first = _projection_edit(vault, page).model_copy(update={"synthesis": "User synthesis."})
            WikiPageService().edit_page(vault, page.name, first)
            state = _projection_edit(vault, page)
            second = state.model_copy(update={"claims": [state.claims[0].model_copy(update={"claim": "User claim."})]})

            WikiPageService().edit_page(vault, page.name, second)
            active = (read_active_processing_records(vault) or [])[0]

        self.assertEqual(active.metadata["edited_fields"], ["synthesis", "claims"])

    def test_relation_evidence_follows_current_supporting_claims(self) -> None:
        first = KnowledgeEvidenceSpan(source_record_id="sr:test", source_unit_id="unit:one", excerpt="First evidence.")
        second = KnowledgeEvidenceSpan(source_record_id="sr:test", source_unit_id="unit:two", excerpt="Second evidence.")
        current = KnowledgeAtomBatch(
            source_record_id="sr:test",
            claims=[
                KnowledgeClaim(id="claim:first", claim="First claim.", evidence=[first]),
                KnowledgeClaim(id="claim:second", claim="Second claim.", evidence=[second]),
            ],
            relations=[
                KnowledgeRelation(
                    id="relation:test",
                    subject=KnowledgeAtomObject(name="Subject"),
                    predicate="relates to",
                    object=KnowledgeAtomObject(name="Object"),
                    source_claim_ids=["claim:first"],
                    evidence=[first],
                )
            ],
        )
        edit = ProjectionEdit(
            base_revision_id="revision:test",
            claims=[{"id": claim.id, "claim": claim.claim} for claim in current.claims],
            relations=[
                {
                    "id": "relation:test",
                    "subject": {"name": "Subject"},
                    "predicate": "relates to",
                    "object": {"name": "Object"},
                    "source_claim_ids": ["claim:second"],
                }
            ],
        )

        edited = _edited_batch(current, edit)

        self.assertEqual(edited.relations[0].source_claim_ids, ["claim:second"])
        self.assertEqual(edited.relations[0].evidence, [second])

    def test_projection_edit_publishes_canonical_revision_and_rematerializes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            original = _publish_projection(vault)
            page = next((vault / "wiki" / "pages").glob("*.md"))
            edit = _projection_edit(vault, page)
            edited = edit.model_copy(
                update={
                    "synthesis": "Edited synthesis.",
                    "claims": [edit.claims[0].model_copy(update={"claim": "Edited claim."})],
                }
            )

            detail = WikiPageService().edit_page(vault, page.name, edited)

            active_record = (read_active_processing_records(vault) or [])[0]
            active_batch = (read_active_atom_batches(vault) or [])[0]
            materialized = page.read_text(encoding="utf-8")

        self.assertNotEqual(active_record.revision_id, original.revision_id)
        self.assertEqual(active_record.metadata["revision_origin"], "user_edit")
        self.assertEqual(active_record.metadata["parent_revision_id"], original.revision_id)
        self.assertEqual(active_record.metadata["edited_fields"], ["synthesis", "claims"])
        self.assertEqual(active_batch.synthesis, "Edited synthesis.")
        self.assertEqual(active_batch.claims[0].claim, "Edited claim.")
        self.assertEqual(active_batch.claims[0].evidence[0].source_unit_id, active_record.source_units[0].source_unit_id)
        self.assertIn("Edited synthesis.", materialized)
        self.assertIn("Edited claim.", materialized)
        self.assertEqual(detail.content, materialized)

    def test_synthesis_edit_preserves_unedited_relation_objects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            _publish_projection(vault)
            before = (read_active_atom_batches(vault) or [])[0]
            page = next((vault / "wiki" / "pages").glob("*.md"))
            edited = _projection_edit(vault, page).model_copy(update={"synthesis": "Edited synthesis."})

            WikiPageService().edit_page(vault, page.name, edited)
            active_record = (read_active_processing_records(vault) or [])[0]
            after = (read_active_atom_batches(vault) or [])[0]

        self.assertEqual(active_record.metadata["edited_fields"], ["synthesis"])
        self.assertEqual(_without_revision_ids(after.entities), _without_revision_ids(before.entities))
        self.assertEqual(after.claims[0].claim, before.claims[0].claim)
        self.assertEqual(
            _without_revision_ids(after.relations[0].subject),
            _without_revision_ids(before.relations[0].subject),
        )
        self.assertEqual(
            _without_revision_ids(after.relations[0].object),
            _without_revision_ids(before.relations[0].object),
        )
        self.assertEqual(after.relations[0].predicate, before.relations[0].predicate)
        self.assertEqual(after.relations[0].source_claim_ids, before.relations[0].source_claim_ids)

    def test_projection_edit_rejects_stale_revision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            _publish_projection(vault)
            page = next((vault / "wiki" / "pages").glob("*.md"))
            edited = _projection_edit(vault, page).model_copy(update={"base_revision_id": "revision:stale"})

            with self.assertRaises(StorageConflict):
                WikiPageService().edit_page(vault, page.name, edited)
            active = (read_active_processing_records(vault) or [])[0]

        self.assertEqual(active.metadata.get("revision_origin"), None)

    def test_projection_edit_rejects_claim_deletion_without_evidence_aware_operation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            _publish_projection(vault)
            page = next((vault / "wiki" / "pages").glob("*.md"))
            edited = _projection_edit(vault, page).model_copy(update={"claims": []})

            with self.assertRaises(PolicyRejection):
                WikiPageService().edit_page(vault, page.name, edited)

    def test_projection_edit_request_has_no_evidence_field(self) -> None:
        with self.assertRaises(ValueError):
            ProjectionEdit.model_validate(
                {
                    "base_revision_id": "revision:test",
                    "claims": [{"id": "claim:test", "claim": "Changed", "evidence": [{"excerpt": "Invented"}]}],
                }
            )


def _publish_projection(vault: Path):
    evidence = KnowledgeEvidenceSpan(
        source_record_id="sr:test",
        source_unit_id="unit:placeholder",
        excerpt="Original source evidence.",
    )
    publish_batch(
        vault,
        KnowledgeAtomBatch(
            source_record_id="sr:test",
            synthesis="Original synthesis.",
            entities=[
                KnowledgeAtomObject(
                    name="Subject",
                    atom_id="entity:subject",
                    aliases=["Subject alias"],
                    evidence=[evidence],
                ),
                KnowledgeAtomObject(name="Object", atom_id="entity:object", evidence=[evidence]),
            ],
            claims=[
                KnowledgeClaim(
                    id="claim:test",
                    claim="Original claim.",
                    evidence=[evidence],
                )
            ],
            relations=[
                KnowledgeRelation(
                    id="relation:test",
                    subject=KnowledgeAtomObject(name="Subject", atom_id="entity:subject"),
                    predicate="relates to",
                    object=KnowledgeAtomObject(name="Object", atom_id="entity:object"),
                    source_claim_ids=["claim:test"],
                    evidence=[evidence],
                )
            ],
        ),
        page_paths=["rawtest--test.md"],
    )
    VaultMaterializer().reconcile(vault, force=True)
    return (read_active_processing_records(vault) or [])[0]


def _projection_edit(vault: Path, page: Path) -> ProjectionEdit:
    state = WikiPageService().read_page(vault, page.name).editable_projection
    assert state is not None
    return ProjectionEdit(
        base_revision_id=state.base_revision_id,
        synthesis=state.synthesis,
        claims=[{"id": claim.id, "claim": claim.claim} for claim in state.claims],
        entities=state.entities,
        relations=state.relations,
    )


def _without_revision_ids(value):
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if isinstance(value, list):
        return [_without_revision_ids(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _without_revision_ids(item)
            for key, item in value.items()
            if key != "revision_id"
        }
    return value
