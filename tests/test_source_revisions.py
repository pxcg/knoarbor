from __future__ import annotations

import tempfile
import unittest
import json
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from knoarbor.core.errors import StorageConflict
from knoarbor.core.schemas.ingest_execution import IngestExecutionCommand, execution_contract_hash
from knoarbor.core.schemas.knowledge_atoms import (
    KnowledgeAtomBatch,
    KnowledgeAtomObject,
    KnowledgeClaim,
    KnowledgeEvidenceSpan,
    KnowledgeRelation,
)
from knoarbor.core.schemas.raw_evidence import SourceProcessingRecord, SourceUnitRecord
from knoarbor.core.schemas.source_record import SourceRecordAttachment
from knoarbor.runtime.transactional_ingest import TransactionalIngestStore
from knoarbor.storage.ingest_inputs import write_input_generation
from knoarbor.storage.materialization import VaultMaterializer
from knoarbor.storage.source_records import read_raw_evidence_records, read_source_processing_records
from knoarbor.storage.source_revisions import (
    RevisionDraft,
    migrate_legacy_fact_layout,
    prune_unreachable_fact_artifacts,
    publish_revision_draft,
    read_revision_atom_batch,
    read_revision_diagnostics,
)
from knoarbor.storage.vault_identity import ensure_vault_identity
from tests.transactional_ingest_helpers import admit_test_task


class SourceRevisionTests(unittest.TestCase):
    def test_full_source_replacement_releases_only_unreferenced_contained_images(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            images = vault / "raw" / "derived" / "assets" / "images"
            images.mkdir(parents=True)
            old_image = images / "old.png"
            shared_image = images / "shared.png"
            current_image = images / "current.png"
            outside_image = vault / "raw" / "outside.png"
            non_image = images / "notes.bin"
            for path in (old_image, shared_image, current_image, outside_image, non_image):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(path.name.encode())

            first = _record("first", raw_record_id="raw:primary").model_copy(
                update={
                    "attachments": [
                        _image_attachment("old.png"),
                        _image_attachment("shared.png"),
                        _image_attachment("../outside.png"),
                        SourceRecordAttachment(
                            attachment_type="file",
                            name="notes.bin",
                            relative_path="raw/derived/assets/images/notes.bin",
                        ),
                    ]
                }
            )
            shared = _record("shared", raw_record_id="raw:shared").model_copy(
                update={"attachments": [_image_attachment("shared.png")]}
            )
            replacement = _record("replacement", raw_record_id="raw:primary").model_copy(
                update={"attachments": [_image_attachment("current.png")]}
            )

            _publish_record(vault, "first", first)
            _publish_record(vault, "shared", shared)
            _publish_record(vault, "replacement", replacement)

            self.assertFalse(old_image.exists())
            self.assertTrue(shared_image.exists())
            self.assertTrue(current_image.exists())
            self.assertTrue(outside_image.exists())
            self.assertTrue(non_image.exists())

            _publish_record(vault, "shared-replacement", _record("shared-replacement", raw_record_id="raw:shared"))

            self.assertFalse(shared_image.exists())
            self.assertTrue(current_image.exists())

    def test_idempotent_revision_reuse_does_not_release_active_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            image = vault / "raw" / "derived" / "assets" / "images" / "active.png"
            image.parent.mkdir(parents=True)
            image.write_bytes(b"active")
            record = _record("idempotent").model_copy(update={"attachments": [_image_attachment("active.png")]})
            draft = RevisionDraft(processing_record=record, atom_batch=_batch("idempotent"))
            store, task, attempt = admit_test_task(vault, "idempotent")
            lease = store.claim(str(task["task_id"]), str(attempt["attempt_id"]), owner_id="test", lease_seconds=30)

            first, _ = publish_revision_draft(vault, store=store, lease=lease, draft=draft)
            second, _ = publish_revision_draft(vault, store=store, lease=lease, draft=draft)

            self.assertEqual(second, first)
            self.assertTrue(image.exists())

    def test_failed_head_publication_does_not_release_active_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            image = vault / "raw" / "derived" / "assets" / "images" / "active.png"
            image.parent.mkdir(parents=True)
            image.write_bytes(b"active")
            _publish_record(
                vault,
                "active",
                _record("active", raw_record_id="raw:failure").model_copy(
                    update={"attachments": [_image_attachment("active.png")]}
                ),
            )
            store, task, attempt = admit_test_task(vault, "replacement")
            lease = store.claim(str(task["task_id"]), str(attempt["attempt_id"]), owner_id="test", lease_seconds=30)

            with patch.object(store, "publish_revision", side_effect=StorageConflict("concurrent replacement")):
                with self.assertRaises(StorageConflict):
                    publish_revision_draft(
                        vault,
                        store=store,
                        lease=lease,
                        draft=RevisionDraft(
                            processing_record=_record("replacement", raw_record_id="raw:failure"),
                            atom_batch=_batch("replacement"),
                        ),
                    )

            self.assertTrue(image.exists())

    def test_startup_pruning_removes_only_unreachable_fact_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            revision = _publish_test_revision(vault, "protected")
            store = TransactionalIngestStore(vault)
            protected = vault / str(store.revision_manifest(revision)["manifest_path"])
            unreachable = protected.parent / "unreachable"
            unreachable.mkdir()
            (unreachable / "partial.json").write_text("{}", encoding="utf-8")
            staging = vault / ".knoarbor" / "facts" / ".staging" / "interrupted"
            staging.mkdir(parents=True)

            removed = prune_unreachable_fact_artifacts(vault, store=store)

            self.assertTrue(protected.is_dir())
            self.assertFalse(unreachable.exists())
            self.assertFalse(staging.exists())
            self.assertEqual(len(removed), 2)

    def test_projection_is_a_minimal_extraction_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            image = vault / "raw" / "derived" / "assets" / "images" / "diagram.png"
            image.parent.mkdir(parents=True)
            image.write_bytes(b"png")
            record = _record("inventory").model_copy(
                update={
                    "source_units": [
                        SourceUnitRecord(
                            source_unit_id="unit:inventory",
                            raw_record_id="raw:inventory",
                            raw_revision_id="rawrev:inventory",
                            unit_index=0,
                            title="Architecture",
                            content="A2A uses Agent Card. " + "Evidence detail. " * 40,
                            excerpt="A2A uses Agent Card. " + "Evidence detail. " * 40,
                            structural_path=["Architecture"],
                            source_path="raw/inventory.md",
                        )
                    ],
                    "attachments": [
                        SourceRecordAttachment(
                            attachment_id="image:diagram",
                            attachment_type="image",
                            name="diagram.png",
                            topic="Protocol diagram",
                            description="A2A protocol components.",
                            path=str(image),
                            relative_path="raw/derived/assets/images/diagram.png",
                            mime_type="image/png",
                        )
                    ],
                }
            )
            evidence = KnowledgeEvidenceSpan(
                source_record_id="source:inventory",
                source_unit_id="unit:inventory",
                source_unit_index=0,
                source_path="raw/inventory.md",
                excerpt="A2A uses Agent Card. " + "Evidence detail. " * 40,
            )
            claim = KnowledgeClaim(id="claim:one", claim="A2A uses Agent Card.", entity_names=["A2A", "Agent Card"], evidence=[evidence])
            batch = KnowledgeAtomBatch(
                source_record_id="source:inventory",
                synthesis="Locate A2A protocol structure and Agent Card usage.",
                entities=[
                    KnowledgeAtomObject(name="A2A", aliases=["Agent-to-Agent"], evidence=[evidence]),
                    KnowledgeAtomObject(name="Agent Card", evidence=[evidence]),
                ],
                claims=[claim],
                relations=[
                    KnowledgeRelation(
                        id="relation:one",
                        subject=KnowledgeAtomObject(name="A2A"),
                        predicate="uses",
                        object=KnowledgeAtomObject(name="Agent Card"),
                        source_claim_ids=[claim.id],
                        evidence=[evidence],
                    )
                ],
            )
            store, task, attempt = admit_test_task(vault, "inventory")
            lease = store.claim(task["task_id"], attempt["attempt_id"], owner_id="worker", lease_seconds=30)
            revision, fact_dir = publish_revision_draft(
                vault, store=store, lease=lease, draft=RevisionDraft(processing_record=record, atom_batch=batch)
            )
            VaultMaterializer().reconcile(vault)
            content = next((vault / "wiki" / "pages").glob("*.md")).read_text(encoding="utf-8")
            persisted_knowledge = (fact_dir / "knowledge.json").read_text(encoding="utf-8")
            hydrated = read_revision_atom_batch(vault, revision)

            self.assertIn("### C1\n\nA2A uses Agent Card.", content)
            self.assertIn("> A2A uses Agent Card.", content)
            self.assertEqual(content.count("Evidence detail."), 40)
            self.assertIn("Architecture · unit 1", content)
            self.assertIn("A2A (aliases: Agent-to-Agent)", content)
            self.assertIn("R1: A2A -> uses -> Agent Card (supporting claims: C1)", content)
            self.assertIn("![Protocol diagram](../../raw/derived/assets/images/diagram.png)", content)
            self.assertNotIn("claim:one", content)
            self.assertNotIn("[[A2A]]", content)
            self.assertNotIn("Evidence detail.", persisted_knowledge)
            self.assertIn("Evidence detail.", hydrated.claims[0].evidence[0].excerpt)

    def test_precise_claim_evidence_is_hydrated_from_its_character_span(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            unit_text = "Before. Precise evidence. After."
            unit_start = 100
            quote = "Precise evidence."
            quote_start = unit_start + unit_text.index(quote)
            record = _record("precise").model_copy(
                update={
                    "source_units": [
                        SourceUnitRecord(
                            source_unit_id="unit:precise",
                            raw_record_id="raw:precise",
                            raw_revision_id="rawrev:precise",
                            unit_index=0,
                            content=unit_text,
                            excerpt=unit_text,
                            char_start=unit_start,
                            char_end=unit_start + len(unit_text),
                            source_path="raw/precise.md",
                        )
                    ]
                }
            )
            evidence = KnowledgeEvidenceSpan(
                source_record_id="source:precise",
                source_unit_id="unit:precise",
                source_unit_index=0,
                source_path="raw/precise.md",
                excerpt=quote,
                char_start=quote_start,
                char_end=quote_start + len(quote),
            )
            batch = KnowledgeAtomBatch(
                source_record_id="source:precise",
                claims=[KnowledgeClaim(id="claim:precise", claim=quote, evidence=[evidence])],
            )
            store, task, attempt = admit_test_task(vault, "precise")
            lease = store.claim(task["task_id"], attempt["attempt_id"], owner_id="worker", lease_seconds=30)
            revision, fact_dir = publish_revision_draft(
                vault,
                store=store,
                lease=lease,
                draft=RevisionDraft(processing_record=record, atom_batch=batch),
            )

            persisted = json.loads((fact_dir / "knowledge.json").read_text(encoding="utf-8"))
            hydrated = read_revision_atom_batch(vault, revision)

            self.assertNotIn("excerpt", persisted["claims"][0]["evidence"][0])
            self.assertEqual(hydrated.claims[0].evidence[0].excerpt, quote)
            self.assertEqual(hydrated.claims[0].evidence[0].char_start, quote_start)
            self.assertEqual(hydrated.claims[0].evidence[0].char_end, quote_start + len(quote))

    def test_invalid_persisted_evidence_range_never_widens_to_the_unit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            unit_text = "Precise evidence only."
            record = _record("invalid-range").model_copy(
                update={
                    "source_units": [
                        SourceUnitRecord(
                            source_unit_id="unit:invalid-range",
                            raw_record_id="raw:invalid-range",
                            raw_revision_id="rawrev:invalid-range",
                            unit_index=0,
                            content=unit_text,
                            excerpt=unit_text,
                            char_start=0,
                            char_end=len(unit_text),
                        )
                    ]
                }
            )
            evidence = KnowledgeEvidenceSpan(
                source_record_id="source:invalid-range",
                source_unit_id="unit:invalid-range",
                excerpt="invalid",
                char_start=len(unit_text) + 1,
                char_end=len(unit_text) + 4,
            )
            batch = KnowledgeAtomBatch(
                source_record_id="source:invalid-range",
                claims=[KnowledgeClaim(id="claim:invalid-range", claim="Invalid range.", evidence=[evidence])],
            )
            store, task, attempt = admit_test_task(vault, "invalid-range")
            lease = store.claim(task["task_id"], attempt["attempt_id"], owner_id="worker", lease_seconds=30)
            revision, _ = publish_revision_draft(
                vault,
                store=store,
                lease=lease,
                draft=RevisionDraft(processing_record=record, atom_batch=batch),
            )

            with self.assertRaisesRegex(ValueError, "outside source unit range"):
                read_revision_atom_batch(vault, revision)

    def test_legacy_fact_generation_migrates_without_fallback_reader(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            revision = _publish_test_revision(vault, "legacy")
            store = TransactionalIngestStore(vault)
            current = store.revision_manifest(revision)
            current_path = vault / str(current["manifest_path"])
            source = json.loads((current_path / "source.json").read_text(encoding="utf-8"))
            knowledge = json.loads((current_path / "knowledge.json").read_text(encoding="utf-8"))
            source["schema_version"] = "source_processing_record.v1"
            source.pop("attachments", None)
            knowledge["schema_version"] = "knowledge_atoms.v2"
            legacy = vault / ".knoarbor" / "source_revisions" / "generations" / "legacy"
            legacy.mkdir(parents=True)
            _write_json(legacy / "source_processing_record.json", source)
            _write_json(legacy / "knowledge_atom_batch.json", knowledge)
            _write_json(legacy / "diagnostics.json", {})
            manifest = {
                "schema_version": "source_revision_manifest.v1",
                "revision_id": revision,
                "files": ["source_processing_record.json", "knowledge_atom_batch.json", "diagnostics.json"],
                "file_hashes": {
                    name: _file_hash(legacy / name)
                    for name in ("source_processing_record.json", "knowledge_atom_batch.json", "diagnostics.json")
                },
            }
            manifest_hash = _payload_hash(manifest)
            manifest["manifest_hash"] = manifest_hash
            _write_json(legacy / "manifest.json", manifest)
            store.replace_revision_manifest(
                revision,
                manifest_path=str(legacy.relative_to(vault)),
                manifest_hash=manifest_hash,
            )
            for path in sorted(current_path.rglob("*"), reverse=True):
                path.unlink() if path.is_file() else path.rmdir()
            current_path.rmdir()

            self.assertEqual(migrate_legacy_fact_layout(vault, store=store), 1)
            migrated = vault / str(store.revision_manifest(revision)["manifest_path"])
            self.assertEqual(
                {path.name for path in migrated.iterdir()}, {"source.json", "knowledge.json", "diagnostics.json", "manifest.json"}
            )
            self.assertFalse((vault / ".knoarbor" / "source_revisions").exists())
            self.assertEqual(read_source_processing_records(vault)[0].schema_version, "source_processing_record.v2")

    def test_revision_persists_compilation_diagnostics_with_integrity_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            store, task, attempt = admit_test_task(vault, "diagnostics")
            lease = store.claim(task["task_id"], attempt["attempt_id"], owner_id="worker", lease_seconds=30)
            revision, generation = publish_revision_draft(
                vault,
                store=store,
                lease=lease,
                draft=RevisionDraft(
                    processing_record=_record("diagnostics"),
                    atom_batch=_batch("diagnostics"),
                    diagnostics={"schema_version": "ingest_diagnostics.v1", "rejected_relations": []},
                ),
            )

            self.assertTrue((generation / "diagnostics.json").is_file())
            self.assertEqual(read_revision_diagnostics(vault, revision)["schema_version"], "ingest_diagnostics.v1")

    def test_force_reprocess_creates_a_new_factual_revision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            store = TransactionalIngestStore(vault)
            generation = write_input_generation(vault, documents=[])
            contract = {"test": "force"}

            def command(force: bool, invocation: str | None) -> IngestExecutionCommand:
                return IngestExecutionCommand(
                    generation_id=generation.generation_id,
                    request_kind="test",
                    vault_id="test",
                    vault_path=str(vault),
                    vault_identity=ensure_vault_identity(vault),
                    write=True,
                    write_report=False,
                    append_ledger=False,
                    force_reprocess=force,
                    force_invocation_id=invocation,
                    execution_contract=contract,
                    execution_contract_hash=execution_contract_hash(contract),
                )

            revisions = []
            for force, invocation in ((False, None), (True, "force-1")):
                task, attempt = store.submit_command(command(force, invocation))
                lease = store.claim(str(task["task_id"]), str(attempt["attempt_id"]), owner_id="worker", lease_seconds=30)
                revision, _ = publish_revision_draft(
                    vault,
                    store=store,
                    lease=lease,
                    draft=RevisionDraft(processing_record=_record("force", raw_record_id="raw:force"), atom_batch=_batch("force")),
                )
                store.finish(lease, state="completed")
                revisions.append(revision)

            self.assertNotEqual(revisions[0], revisions[1])
            self.assertEqual(store.source_head("raw:force"), revisions[1])

    def test_same_task_input_revision_publication_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            store, task, attempt = admit_test_task(vault, "same")
            lease = store.claim(task["task_id"], attempt["attempt_id"], owner_id="worker", lease_seconds=30)
            draft = RevisionDraft(processing_record=_record("same"), atom_batch=_batch("same"))

            first, _ = publish_revision_draft(vault, store=store, lease=lease, draft=draft)
            second, _ = publish_revision_draft(vault, store=store, lease=lease, draft=draft)

            self.assertEqual(first, second)
            fact_revisions = [path for path in (vault / ".knoarbor" / "facts").glob("*/*") if path.is_dir()]
            self.assertEqual(len(fact_revisions), 1)

    def test_materialization_rebuilds_views_without_republishing_facts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            revision = _publish_test_revision(vault, "one")
            state = VaultMaterializer().reconcile(vault)

            self.assertEqual(state["phase"], "clean")
            self.assertEqual(TransactionalIngestStore(vault).source_head("raw:one"), revision)
            pages = list((vault / "wiki" / "pages").glob("*.md"))
            self.assertEqual(len(pages), 1)
            first_projection = pages[0].read_text(encoding="utf-8")

            rebuilt = VaultMaterializer().reconcile(vault, force=True)
            self.assertEqual(TransactionalIngestStore(vault).source_head("raw:one"), revision)
            self.assertGreater(int(rebuilt["requested_epoch"]), int(state["requested_epoch"]))
            self.assertEqual(pages[0].read_text(encoding="utf-8"), first_projection)

    def test_active_revision_missing_fact_file_raises_integrity_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            revision = _publish_test_revision(vault, "one")
            manifest = TransactionalIngestStore(vault).revision_manifest(revision)
            (vault / str(manifest["manifest_path"]) / "source.json").unlink()

            with self.assertRaisesRegex(RuntimeError, "file failed integrity verification"):
                read_source_processing_records(vault)

    def test_staged_generation_is_visible_only_through_source_head(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            revision = _publish_test_revision(vault, "one")
            published = read_source_processing_records(vault)[0]

            self.assertEqual(published.revision_id, revision)
            self.assertEqual(published.processing_record_id, "spr:one")
            self.assertIsNone(published.window_id)
            self.assertEqual(read_raw_evidence_records(vault), [])

    def test_session_windows_preserve_prior_committed_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            image = vault / "raw" / "derived" / "assets" / "images" / "first-window.png"
            image.parent.mkdir(parents=True)
            image.write_bytes(b"first-window")
            for index in (1, 2):
                store, task, attempt = admit_test_task(vault, f"session-{index}")
                lease = store.claim(task["task_id"], attempt["attempt_id"], owner_id="worker", lease_seconds=30)
                record = _record(str(index), raw_record_id="raw:chat", source_type="generic_chat")
                if index == 1:
                    record = record.model_copy(update={"attachments": [_image_attachment("first-window.png")]})
                publish_revision_draft(
                    vault,
                    store=store,
                    lease=lease,
                    draft=RevisionDraft(
                        processing_record=record,
                        atom_batch=_batch(str(index)),
                        window_id=f"chat:window:{index}",
                        window_from_index=index - 1,
                        window_to_index=index - 1,
                    ),
                )
                store.finish(lease, state="completed")
            self.assertEqual([record.processing_record_id for record in read_source_processing_records(vault)], ["spr:1", "spr:2"])
            self.assertTrue(image.exists())

    def test_session_append_rejects_non_contiguous_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            store, task, attempt = admit_test_task(vault, "session-gap")
            lease = store.claim(task["task_id"], attempt["attempt_id"], owner_id="worker", lease_seconds=30)
            draft = RevisionDraft(
                processing_record=_record("one", raw_record_id="raw:chat", source_type="generic_chat"),
                atom_batch=_batch("one"),
                window_id="chat:0",
                window_from_index=0,
                window_to_index=0,
            )
            publish_revision_draft(vault, store=store, lease=lease, draft=draft)
            with self.assertRaisesRegex(Exception, "next contiguous"):
                publish_revision_draft(
                    vault,
                    store=store,
                    lease=lease,
                    draft=draft.__class__(
                        processing_record=draft.processing_record,
                        atom_batch=draft.atom_batch,
                        window_id="chat:2",
                        window_from_index=2,
                        window_to_index=2,
                    ),
                )


def _record(suffix: str, *, raw_record_id: str | None = None, source_type: str = "markdown") -> SourceProcessingRecord:
    raw_id = raw_record_id or f"raw:{suffix}"
    return SourceProcessingRecord.model_validate(
        {
            "processing_record_id": f"spr:{suffix}",
            "raw_record_id": raw_id,
            "raw_revision_id": f"rawrev:{suffix}",
            "source_record_id": f"source:{suffix}",
            "page_paths": [f"pages/{suffix}.md"],
            "source": {
                "raw_record_id": raw_id,
                "raw_revision_id": f"rawrev:{suffix}",
                "source_id": suffix,
                "source_type": source_type,
                "connector": "test",
                "content_hash": suffix,
                "normalized_content_hash": suffix,
            },
        }
    )


def _batch(suffix: str) -> KnowledgeAtomBatch:
    return KnowledgeAtomBatch(source_record_id=f"source:{suffix}")


def _publish_test_revision(vault: Path, suffix: str) -> str:
    store, task, attempt = admit_test_task(vault, f"revision-{suffix}")
    lease = store.claim(str(task["task_id"]), str(attempt["attempt_id"]), owner_id="test", lease_seconds=30)
    revision, _ = publish_revision_draft(
        vault,
        store=store,
        lease=lease,
        draft=RevisionDraft(processing_record=_record(suffix), atom_batch=_batch(suffix)),
    )
    store.finish(lease, state="completed")
    return revision


def _publish_record(vault: Path, label: str, record: SourceProcessingRecord) -> str:
    store, task, attempt = admit_test_task(vault, label)
    lease = store.claim(str(task["task_id"]), str(attempt["attempt_id"]), owner_id="test", lease_seconds=30)
    revision, _ = publish_revision_draft(
        vault,
        store=store,
        lease=lease,
        draft=RevisionDraft(processing_record=record, atom_batch=KnowledgeAtomBatch(source_record_id=record.source_record_id)),
    )
    store.finish(lease, state="completed")
    return revision


def _image_attachment(name: str) -> SourceRecordAttachment:
    return SourceRecordAttachment(
        attachment_type="image",
        name=Path(name).name,
        relative_path=f"raw/derived/assets/images/{name}",
    )


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _payload_hash(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"sha256:{sha256(encoded.encode('utf-8')).hexdigest()}"


def _file_hash(path: Path) -> str:
    return f"sha256:{sha256(path.read_bytes()).hexdigest()}"


if __name__ == "__main__":
    unittest.main()
