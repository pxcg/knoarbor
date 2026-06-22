from __future__ import annotations

import unittest

from pydantic import ValidationError

from knoarbor.core.schemas.knowledge_atoms import (
    KnowledgeAtomBatch,
    KnowledgeAtomObject,
    KnowledgeClaim,
    KnowledgeEvidenceSpan,
    KnowledgeFact,
    KnowledgeRelation,
)


def _evidence(excerpt: str = "SoundAnalysis emits classification windows.") -> KnowledgeEvidenceSpan:
    excerpt_hash = "hash_" + str(abs(hash(excerpt)) % 100000)
    return KnowledgeEvidenceSpan(
        source_digest_id="sd_ios_audio_001",
        source_path="sources/iOS-Audio.md",
        source_unit_index=2,
        excerpt=excerpt,
        excerpt_hash=excerpt_hash,
    )


class KnowledgeAtomSchemaTest(unittest.TestCase):
    def test_fact_requires_evidence(self) -> None:
        with self.assertRaises(ValidationError):
            KnowledgeFact(
                id="fact_without_evidence",
                statement="SoundAnalysis emits classification windows.",
                evidence=[],
            )

    def test_claim_requires_evidence_or_supporting_facts(self) -> None:
        with self.assertRaises(ValidationError):
            KnowledgeClaim(
                id="claim_without_support",
                claim="SoundAnalysis should not be the final hit timestamp detector.",
                claim_type="recommendation",
            )

        claim = KnowledgeClaim(
            id="claim_supported",
            claim="SoundAnalysis should be used as a coarse activity detector.",
            claim_type="recommendation",
            supporting_fact_ids=["fact_soundanalysis_windows"],
        )
        self.assertEqual(claim.supporting_fact_ids, ["fact_soundanalysis_windows"])

    def test_relation_requires_support(self) -> None:
        subject = KnowledgeAtomObject(object_type="concept", name="SoundAnalysis")
        obj = KnowledgeAtomObject(object_type="concept", name="Energy Peak Baseline")
        with self.assertRaises(ValidationError):
            KnowledgeRelation(
                id="rel_without_support",
                subject=subject,
                predicate="contrasts",
                object=obj,
            )

        relation = KnowledgeRelation(
            id="rel_supported",
            subject=subject,
            predicate="contrasts",
            object=obj,
            source_fact_ids=["fact_soundanalysis_windows"],
        )
        self.assertEqual(relation.predicate, "contrasts")

    def test_atom_batch_summary_counts_unique_evidence(self) -> None:
        evidence = _evidence()
        fact = KnowledgeFact(
            id="fact_soundanalysis_windows",
            statement="SoundAnalysis emits classification windows.",
            evidence=[evidence],
        )
        claim = KnowledgeClaim(
            id="claim_soundanalysis_activity_detector",
            claim="SoundAnalysis is activity-level rather than hit-timestamp-level.",
            claim_type="assessment",
            evidence=[evidence],
        )
        relation = KnowledgeRelation(
            id="rel_soundanalysis_mentions_ios_workflow",
            subject=KnowledgeAtomObject(object_type="concept", name="SoundAnalysis"),
            predicate="mentions",
            object=KnowledgeAtomObject(object_type="workflow", name="iOS Audio ML Workflow"),
            evidence=[_evidence("SoundAnalysis is part of the iOS audio workflow.")],
        )
        batch = KnowledgeAtomBatch(
            source_digest_id="sd_ios_audio_001",
            facts=[fact],
            claims=[claim],
            relations=[relation],
        )

        self.assertEqual(
            batch.summary(),
            {
                "facts": 1,
                "claims": 1,
                "relations": 1,
                "evidence_spans": 2,
            },
        )


if __name__ == "__main__":
    unittest.main()
