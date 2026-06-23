from __future__ import annotations

import unittest

from knoarbor.core.schemas.knowledge_atoms import (
    KnowledgeAtomBatch,
    KnowledgeAtomObject,
    KnowledgeClaim,
    KnowledgeEvidenceSpan,
    KnowledgeRelation,
)
from knoarbor.core.schemas.knowledge_extract import CompileContext, ContentUnit, KnowledgeExtract, KnowledgeSource
from knoarbor.pipelines.ingest_aggregation import SegmentSemanticArtifacts, aggregate_segment_semantic_artifacts
from knoarbor.semantic.source_digest import build_source_digest_from_extract


class IngestAggregationTests(unittest.TestCase):
    def test_aggregates_segments_into_source_level_atom_contract(self) -> None:
        first = _artifact(0, "Agent Loop", "Agent loop repeats observe, reason, act, and feedback.")
        second = _artifact(1, "Agent Loop Duplicate", "Agent loop repeats observe, reason, act, and feedback.")

        result = aggregate_segment_semantic_artifacts([first, second])

        self.assertEqual(result.stats["segment_count"], 2)
        self.assertEqual(result.stats["claims"], 1)
        self.assertEqual(result.stats["relations"], 1)
        self.assertEqual(result.stats["atom_quality_rejected"], 0)
        self.assertEqual(result.knowledge_atom_quality.summary()["claims"], 1)
        self.assertEqual(result.knowledge_atom_batch.source_digest_id, result.source_digest.digest_id)
        self.assertEqual(result.knowledge_atom_batch.claims[0].id, "claim_agent_loop")
        self.assertEqual(
            [span.source_unit_index for span in result.knowledge_atom_batch.claims[0].evidence],
            [0, 1],
        )
        self.assertEqual(result.source_digest.summary_counts()["contributions"], 1)
        self.assertEqual(result.source_digest.contribution_map[0].item_id, "claim_agent_loop")
        self.assertEqual(result.source_digest.contribution_map[0].evidence_unit_ids, ["U1", "U2"])

    def test_single_segment_is_enriched_with_source_audit_contributions(self) -> None:
        artifact = _artifact(0, "Agent Loop", "Agent loop repeats observe, reason, act, and feedback.")

        result = aggregate_segment_semantic_artifacts([artifact])

        self.assertEqual(result.stats["segment_count"], 1)
        self.assertEqual(result.source_digest.contribution_map[0].status, "pending")
        self.assertEqual(result.source_digest.contribution_map[0].target_page, None)
        self.assertEqual(result.knowledge_atom_quality.summary()["unsupported"], 0)


def _artifact(segment_index: int, title: str, claim_text: str) -> SegmentSemanticArtifacts:
    extract = KnowledgeExtract(
        source=KnowledgeSource(
            source_type="markdown",
            source_app="markdown",
            source_id="raw:agent",
            source_path="raw/notes/agent.md",
            title=title,
        ),
        content_units=[
            ContentUnit(
                index=0,
                unit_type="section",
                role="note",
                title=title,
                content=claim_text,
            )
        ],
        compile_context=CompileContext(primary_content=claim_text),
        confidence=0.9,
        warnings=[],
    )
    digest = build_source_digest_from_extract(extract, digest_id=f"sd_segment_{segment_index}")
    evidence = KnowledgeEvidenceSpan(
        source_digest_id=digest.digest_id,
        source_path="raw/notes/agent.md",
        source_unit_index=0,
        excerpt=claim_text,
    )
    batch = KnowledgeAtomBatch(
        source_digest_id=digest.digest_id,
        entities=[
            KnowledgeAtomObject(object_type="concept", name="Agent Loop"),
            KnowledgeAtomObject(object_type="concept", name="Control Cycle"),
        ],
        claims=[
            KnowledgeClaim(
                id="claim_agent_loop",
                claim=claim_text,
                claim_type="definition",
                evidence=[evidence],
                entity_names=["Agent Loop", "Control Cycle"],
                confidence=0.9,
            )
        ],
        relations=[
            KnowledgeRelation(
                id="rel_agent_loop_cycle",
                subject=KnowledgeAtomObject(object_type="concept", name="Agent Loop"),
                predicate="relates_to",
                object=KnowledgeAtomObject(object_type="concept", name="Control Cycle"),
                source_claim_ids=["claim_agent_loop"],
                evidence=[evidence],
                reason="Agent loop is described as a repeated control cycle.",
                confidence=0.85,
            )
        ],
    )
    return SegmentSemanticArtifacts(
        knowledge_extract=extract,
        source_digest=digest,
        knowledge_atom_batch=batch,
    )


if __name__ == "__main__":
    unittest.main()
