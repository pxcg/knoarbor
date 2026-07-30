from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from knoarbor.core.schemas.knowledge_atoms import KnowledgeAtomBatch, KnowledgeAtomObject, KnowledgeClaim, KnowledgeEvidenceSpan, KnowledgeRelation
from knoarbor.storage import entity_registry
from knoarbor.storage.entity_registry import prepare_entity_identity_resolution, read_entity_registry
from knoarbor.storage.wiki_index import build_graph_index
from tests.transactional_ingest_helpers import publish_batch


def _batch(source_record_id: str, name: str, aliases: list[str] | None = None) -> KnowledgeAtomBatch:
    evidence = KnowledgeEvidenceSpan(source_record_id=source_record_id, source_unit_id="U0", excerpt="Source evidence")
    return KnowledgeAtomBatch(
        source_record_id=source_record_id,
        entities=[KnowledgeAtomObject(name=name, aliases=aliases or [], evidence=[evidence])],
        claims=[KnowledgeClaim(id="C1", claim=f"{name} is discussed.", entity_names=[name], evidence=[evidence])],
        relations=[KnowledgeRelation(id="R1", subject=KnowledgeAtomObject(name=name), predicate="relates to", object=KnowledgeAtomObject(name=name), source_claim_ids=["C1"], evidence=[evidence])],
    )


class EntityRegistryTests(unittest.TestCase):
    def test_entity_identity_has_no_independent_commit_or_restore_boundary(self) -> None:
        self.assertFalse(hasattr(entity_registry, "commit_entity_identity_resolution"))
        self.assertFalse(hasattr(entity_registry, "restore_entity_identity_resolution"))

    def test_alias_binds_separate_committed_sources_to_one_entity(self) -> None:
        with TemporaryDirectory() as directory:
            vault = Path(directory)
            first = prepare_entity_identity_resolution(vault, _batch("sr:one", "Agent-to-Agent", ["A2A"]), raw_record_id="raw:one").atom_batch
            publish_batch(vault, first, raw_record_id="raw:one", raw_revision_id="rawrev:one", page_paths=["pages/agent-to-agent.md"])
            second = prepare_entity_identity_resolution(vault, _batch("sr:two", "A2A"), raw_record_id="raw:two").atom_batch
            publish_batch(vault, second, raw_record_id="raw:two", raw_revision_id="rawrev:two", page_paths=["pages/a2a.md"])

            self.assertEqual(first.entities[0].atom_id, second.entities[0].atom_id)
            self.assertEqual(first.entities[0].aliases, ["A2A"])
            self.assertEqual(first.claims[0].entity_ids, [first.entities[0].atom_id])
            self.assertEqual(first.relations[0].subject.atom_id, first.entities[0].atom_id)
            registry = read_entity_registry(vault)
            self.assertEqual(len(registry.entries), 1)
            self.assertEqual({item.raw_record_id for item in registry.entries[0].contributions}, {"raw:one", "raw:two"})

    def test_unproven_names_do_not_merge(self) -> None:
        with TemporaryDirectory() as directory:
            vault = Path(directory)
            first = prepare_entity_identity_resolution(vault, _batch("sr:one", "Reward Hacking"), raw_record_id="raw:one").atom_batch
            publish_batch(vault, first, raw_record_id="raw:one", raw_revision_id="rawrev:one")
            second = prepare_entity_identity_resolution(vault, _batch("sr:two", "奖励作弊"), raw_record_id="raw:two").atom_batch
            publish_batch(vault, second, raw_record_id="raw:two", raw_revision_id="rawrev:two")
            self.assertNotEqual(first.entities[0].atom_id, second.entities[0].atom_id)
            self.assertEqual(len(read_entity_registry(vault).entries), 2)

    def test_revised_source_retracts_prior_contribution(self) -> None:
        with TemporaryDirectory() as directory:
            vault = Path(directory)
            old = prepare_entity_identity_resolution(vault, _batch("sr:old", "Agent-to-Agent", ["A2A"]), raw_record_id="raw:one").atom_batch
            publish_batch(vault, old, raw_record_id="raw:one", raw_revision_id="rawrev:old")
            new = prepare_entity_identity_resolution(vault, _batch("sr:new", "Agent-to-Agent", ["A2A Protocol"]), raw_record_id="raw:one").atom_batch
            publish_batch(vault, new, raw_record_id="raw:one", raw_revision_id="rawrev:new")
            entry = read_entity_registry(vault).entries[0]
            self.assertEqual(entry.contributions[0].source_record_id, "sr:new")
            self.assertNotIn("A2A", entry.aliases)

    def test_graph_uses_revision_backed_entity_ids_and_page_paths(self) -> None:
        with TemporaryDirectory() as directory:
            vault = Path(directory)
            first = prepare_entity_identity_resolution(vault, _batch("sr:one", "Agent-to-Agent", ["A2A"]), raw_record_id="raw:one").atom_batch
            publish_batch(vault, first, raw_record_id="raw:one", raw_revision_id="rawrev:one", page_paths=["pages/agent-to-agent.md"])
            second = prepare_entity_identity_resolution(vault, _batch("sr:two", "A2A"), raw_record_id="raw:two").atom_batch
            publish_batch(vault, second, raw_record_id="raw:two", raw_revision_id="rawrev:two", page_paths=["pages/a2a.md"])
            graph = build_graph_index(vault, pages=[])
            node = next(item for item in graph["nodes"] if item["id"] == first.entities[0].atom_id)
            self.assertEqual(node["pages"], ["pages/agent-to-agent.md", "pages/a2a.md"])
