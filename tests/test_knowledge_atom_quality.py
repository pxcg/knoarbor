from __future__ import annotations

import unittest

from knoarbor.core.schemas.knowledge_atoms import (
    KnowledgeAtomBatch,
    KnowledgeAtomObject,
    KnowledgeClaim,
    KnowledgeEvidenceSpan,
    KnowledgeFact,
    KnowledgeRelation,
)
from knoarbor.semantic.knowledge_atom_quality import evaluate_knowledge_atoms


def _evidence(source_digest_id: str = "sd_agent") -> KnowledgeEvidenceSpan:
    return KnowledgeEvidenceSpan(
        source_digest_id=source_digest_id,
        source_path="raw/notes/Agent.md",
        source_unit_index=0,
        excerpt="Agent loop coordinates tool use.",
    )


class KnowledgeAtomQualityTests(unittest.TestCase):
    def test_quality_report_accepts_supported_atoms(self) -> None:
        batch = KnowledgeAtomBatch(
            source_digest_id="sd_agent",
            facts=[
                KnowledgeFact(
                    id="fact_agent_loop_tools",
                    statement="Agent loop coordinates tool use.",
                    evidence=[_evidence()],
                )
            ],
            claims=[
                KnowledgeClaim(
                    id="claim_agent_loop_production",
                    claim="Production agent loops need tool governance.",
                    claim_type="assessment",
                    supporting_fact_ids=["fact_agent_loop_tools"],
                )
            ],
            relations=[
                KnowledgeRelation(
                    id="rel_agent_loop_supports_tools",
                    subject=KnowledgeAtomObject(object_type="concept", name="Agent Loop"),
                    predicate="supports",
                    object=KnowledgeAtomObject(object_type="concept", name="Tool Governance"),
                    source_fact_ids=["fact_agent_loop_tools"],
                )
            ],
        )

        report = evaluate_knowledge_atoms(batch)

        self.assertEqual(report.summary()["unsupported"], 0)
        self.assertEqual(report.summary()["conflicting"], 0)
        self.assertEqual(report.summary()["rejected"], 0)

    def test_quality_report_flags_missing_support_ids_and_conflicts(self) -> None:
        subject = KnowledgeAtomObject(object_type="concept", name="Agent Loop")
        obj = KnowledgeAtomObject(object_type="concept", name="Workflow")
        batch = KnowledgeAtomBatch(
            source_digest_id="sd_agent",
            facts=[
                KnowledgeFact(
                    id="fact_agent_loop_tools",
                    statement="Agent loop coordinates tool use.",
                    evidence=[_evidence("other_digest")],
                )
            ],
            claims=[
                KnowledgeClaim(
                    id="claim_missing_fact",
                    claim="Agent loop should replace all workflows.",
                    claim_type="recommendation",
                    supporting_fact_ids=["missing_fact"],
                )
            ],
            relations=[
                KnowledgeRelation(
                    id="rel_supports",
                    subject=subject,
                    predicate="supports",
                    object=obj,
                    source_fact_ids=["missing_fact"],
                ),
                KnowledgeRelation(
                    id="rel_contradicts",
                    subject=subject,
                    predicate="contradicts",
                    object=obj,
                    evidence=[_evidence()],
                ),
            ],
        )

        report = evaluate_knowledge_atoms(batch)

        issue_types = {issue.issue_type for issue in report.issues}
        self.assertIn("unsupported_fact", issue_types)
        self.assertIn("unsupported_claim", issue_types)
        self.assertIn("unsupported_relation", issue_types)
        self.assertIn("conflicting_relation", issue_types)
        self.assertEqual(report.summary()["unsupported"], 3)
        self.assertEqual(report.summary()["conflicting"], 1)
        self.assertEqual(report.summary()["rejected"], 3)


if __name__ == "__main__":
    unittest.main()
