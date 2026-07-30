from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.core.schemas.knowledge_atoms import (
    KnowledgeAtomBatch,
    KnowledgeAtomObject,
    KnowledgeClaim,
    KnowledgeEvidenceSpan,
    KnowledgeRelation,
)
from knoarbor.storage.knowledge_atom_index import (
    read_knowledge_atom_records,
)
from tests.transactional_ingest_helpers import publish_batch


def _evidence() -> KnowledgeEvidenceSpan:
    return KnowledgeEvidenceSpan(
        source_record_id="sr_agent",
        source_path="raw/inbox/notes/agent.md",
        source_unit_index=0,
        excerpt="Agent loops reason and act.",
    )


def _evidence_with_raw(source_record_id: str, raw_revision_id: str) -> KnowledgeEvidenceSpan:
    return KnowledgeEvidenceSpan(
        source_record_id=source_record_id,
        source_path="raw/inbox/notes/agent.md",
        source_unit_index=0,
        excerpt="Agent loops reason and act.",
        raw_record_id="raw:agent",
        raw_revision_id=raw_revision_id,
        source_unit_id=f"unit:{raw_revision_id}",
        processing_record_id=f"spr:{raw_revision_id}",
    )


def _batch(
    statement: str = "Agent loops reason and act.", *, source_record_id: str = "sr_agent", evidence: KnowledgeEvidenceSpan | None = None
) -> KnowledgeAtomBatch:
    evidence = evidence or _evidence()
    return KnowledgeAtomBatch(
        source_record_id=source_record_id,
        entities=[
            KnowledgeAtomObject(object_type="knowledge_object", name="Agent Loop", atom_id="entity_agent_loop", evidence=[evidence]),
            KnowledgeAtomObject(object_type="knowledge_object", name="Workflow", atom_id="entity_workflow", evidence=[evidence]),
        ],
        claims=[
            KnowledgeClaim(
                id="claim_agent_loop",
                claim=statement,
                evidence=[evidence],
                entity_names=["Agent Loop", "Workflow"],
            )
        ],
        relations=[
            KnowledgeRelation(
                id="rel_agent_loop",
                subject=KnowledgeAtomObject(object_type="knowledge_object", name="Agent Loop"),
                predicate="coordinates",
                object=KnowledgeAtomObject(object_type="knowledge_object", name="Workflow"),
                source_claim_ids=["claim_agent_loop"],
                evidence=[evidence],
            )
        ],
    )


class KnowledgeAtomIndexTests(unittest.TestCase):
    def test_published_revision_exposes_atom_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            publish_batch(vault, _batch(), page_paths=["Agent-Loop.md"])
            records = read_knowledge_atom_records(vault)

            self.assertEqual(len(records), 4)
            claim = next(record for record in records if record.atom_id == "claim_agent_loop")
            self.assertEqual(claim.atom_type, "claim")
            self.assertEqual(claim.page_paths, ["Agent-Loop.md"])

    def test_new_revision_replaces_same_raw_source_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            publish_batch(vault, _batch("Old statement."), raw_revision_id="rawrev:old", page_paths=["Agent-Loop.md"])
            publish_batch(vault, _batch("New statement."), raw_revision_id="rawrev:new", page_paths=["Agent-Loop.md"])
            records = read_knowledge_atom_records(vault)

            claims = [record for record in records if record.atom_type == "claim"]
            self.assertEqual(len(claims), 1)
            self.assertEqual(claims[0].text, "New statement.")

    def test_upsert_replaces_previous_revision_for_same_raw_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            old_batch = _batch(
                "Old statement.",
                source_record_id="sr_agent_old",
                evidence=_evidence_with_raw("sr_agent_old", "rawrev:old"),
            )
            new_batch = _batch(
                "New statement.",
                source_record_id="sr_agent_new",
                evidence=_evidence_with_raw("sr_agent_new", "rawrev:new"),
            )

            publish_batch(vault, old_batch, raw_revision_id="rawrev:old")
            publish_batch(vault, new_batch, raw_revision_id="rawrev:new")
            records = read_knowledge_atom_records(vault)

            self.assertEqual({record.source_record_id for record in records}, {"sr_agent_new"})
            self.assertEqual({record.raw_revision_id for record in records}, {"rawrev:new"})
            self.assertEqual([record.text for record in records if record.atom_type == "claim"], ["New statement."])


if __name__ == "__main__":
    unittest.main()
