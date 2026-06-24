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
    KnowledgeAtomPageRef,
    knowledge_atom_index_path,
    read_knowledge_atom_records,
    upsert_knowledge_atom_batch,
)


def _evidence() -> KnowledgeEvidenceSpan:
    return KnowledgeEvidenceSpan(source_digest_id="sd_agent", source_path="raw/notes/agent.md", excerpt="Agent loops reason and act.")


def _batch(statement: str = "Agent loops reason and act.") -> KnowledgeAtomBatch:
    evidence = _evidence()
    return KnowledgeAtomBatch(
        source_digest_id="sd_agent",
        entities=[
            KnowledgeAtomObject(object_type="knowledge_object", name="Agent Loop", atom_id="entity_agent_loop"),
            KnowledgeAtomObject(object_type="knowledge_object", name="Workflow", atom_id="entity_workflow"),
        ],
        claims=[
            KnowledgeClaim(
                id="claim_agent_loop",
                claim=statement,
                claim_type="assessment",
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
            )
        ],
        evidence=[evidence],
    )


class KnowledgeAtomIndexTests(unittest.TestCase):
    def test_upserts_and_reads_atom_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            page_refs = [
                KnowledgeAtomPageRef(
                    path="concepts/Agent-Loop.md",
                    source_digest_ids=["sd_agent"],
                    atom_ids=["entity_agent_loop", "claim_agent_loop"],
                )
            ]

            path = upsert_knowledge_atom_batch(vault, _batch(), page_refs)
            records = read_knowledge_atom_records(vault)

            self.assertEqual(path, knowledge_atom_index_path(vault))
            self.assertEqual(len(records), 5)
            claim = next(record for record in records if record.atom_id == "claim_agent_loop")
            self.assertEqual(claim.atom_type, "claim")
            self.assertEqual(claim.page_paths, ["concepts/Agent-Loop.md"])

    def test_upsert_replaces_same_source_digest_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            page_refs = [KnowledgeAtomPageRef(path="concepts/Agent-Loop.md", source_digest_ids=["sd_agent"], atom_ids=["claim_agent_loop"])]

            upsert_knowledge_atom_batch(vault, _batch("Old statement."), page_refs)
            upsert_knowledge_atom_batch(vault, _batch("New statement."), page_refs)
            records = read_knowledge_atom_records(vault)

            claims = [record for record in records if record.atom_type == "claim"]
            self.assertEqual(len(claims), 1)
            self.assertEqual(claims[0].text, "New statement.")


if __name__ == "__main__":
    unittest.main()
