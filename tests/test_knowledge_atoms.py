from __future__ import annotations

import unittest

from pydantic import ValidationError

from knoarbor.core.schemas.knowledge_atoms import (
    KnowledgeAtomBatch,
    KnowledgeAtomObject,
    KnowledgeClaim,
    KnowledgeEvidenceSpan,
    KnowledgeRelation,
)


def _evidence(excerpt: str = "SoundAnalysis emits classification windows.") -> KnowledgeEvidenceSpan:
    excerpt_hash = "hash_" + str(abs(hash(excerpt)) % 100000)
    return KnowledgeEvidenceSpan(
        source_record_id="sr_ios_audio_001",
        source_path="sources/iOS-Audio.md",
        source_unit_index=2,
        excerpt=excerpt,
        excerpt_hash=excerpt_hash,
    )


class KnowledgeAtomSchemaTest(unittest.TestCase):
    def test_claim_requires_evidence(self) -> None:
        with self.assertRaises(ValidationError):
            KnowledgeClaim(
                id="claim_without_support",
                claim="SoundAnalysis should not be the final hit timestamp detector.",
            )

        claim = KnowledgeClaim(
            id="claim_supported",
            claim="SoundAnalysis should be used as a coarse activity detector.",
            evidence=[_evidence()],
            entity_names=["SoundAnalysis"],
        )
        self.assertEqual(claim.entity_names, ["SoundAnalysis"])

    def test_relation_requires_support(self) -> None:
        subject = KnowledgeAtomObject(object_type="knowledge_object", name="SoundAnalysis")
        obj = KnowledgeAtomObject(object_type="knowledge_object", name="Energy Peak Baseline")
        with self.assertRaises(ValidationError):
            KnowledgeRelation(
                id="rel_without_support",
                subject=subject,
                predicate="contrasts_with",
                object=obj,
            )

        relation = KnowledgeRelation(
            id="rel_supported",
            subject=subject,
            predicate="contrasts_with",
            object=obj,
            source_claim_ids=["claim_soundanalysis_activity_detector"],
            evidence=[_evidence()],
        )
        self.assertEqual(relation.predicate, "contrasts_with")

    def test_relation_accepts_source_language_predicates(self) -> None:
        subject = KnowledgeAtomObject(object_type="knowledge_object", name="SoundAnalysis")
        obj = KnowledgeAtomObject(object_type="knowledge_object", name="Energy Peak Baseline")
        for predicate in ("relates_to", "任务完成时返回", "has messageId"):
            with self.subTest(predicate=predicate):
                relation = KnowledgeRelation(
                    id=f"rel_{abs(hash(predicate))}",
                    subject=subject,
                    predicate=predicate,
                    object=obj,
                    source_claim_ids=["claim_soundanalysis_activity_detector"],
                    evidence=[_evidence()],
                )
                self.assertEqual(relation.predicate, predicate)

    def test_relation_rejects_empty_predicate(self) -> None:
        subject = KnowledgeAtomObject(object_type="knowledge_object", name="SoundAnalysis")
        obj = KnowledgeAtomObject(object_type="knowledge_object", name="Energy Peak Baseline")
        with self.assertRaises(ValidationError):
            KnowledgeRelation(
                id="rel_empty_predicate",
                subject=subject,
                predicate=" ",
                object=obj,
                source_claim_ids=["claim_soundanalysis_activity_detector"],
                evidence=[_evidence()],
            )

    def test_atom_batch_summary_counts_unique_evidence(self) -> None:
        evidence = _evidence()
        claim = KnowledgeClaim(
            id="claim_soundanalysis_activity_detector",
            claim="SoundAnalysis is activity-level rather than hit-timestamp-level.",
            evidence=[evidence],
            entity_names=["SoundAnalysis"],
        )
        relation = KnowledgeRelation(
            id="rel_soundanalysis_mentions_ios_workflow",
            subject=KnowledgeAtomObject(object_type="knowledge_object", name="SoundAnalysis"),
            predicate="includes",
            object=KnowledgeAtomObject(object_type="knowledge_object", name="iOS Audio ML Workflow"),
            source_claim_ids=["claim_soundanalysis_activity_detector"],
            evidence=[_evidence("SoundAnalysis is part of the iOS audio workflow.")],
        )
        batch = KnowledgeAtomBatch(
            source_record_id="sr_ios_audio_001",
            entities=[
                KnowledgeAtomObject(object_type="knowledge_object", name="SoundAnalysis", atom_id="entity_soundanalysis", evidence=[evidence]),
                KnowledgeAtomObject(
                    object_type="knowledge_object",
                    name="iOS Audio ML Workflow",
                    atom_id="entity_ios_audio_ml_workflow",
                    evidence=[_evidence("SoundAnalysis is part of the iOS audio workflow.")],
                ),
            ],
            claims=[claim],
            relations=[relation],
        )

        self.assertEqual(
            batch.summary(),
            {
                "entities": 2,
                "claims": 1,
                "relations": 1,
                "evidence_spans": 2,
            },
        )


if __name__ == "__main__":
    unittest.main()
