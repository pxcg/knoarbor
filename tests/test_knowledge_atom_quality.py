from __future__ import annotations

import unittest

from knoarbor.core.schemas.knowledge_atoms import (
    KnowledgeAtomBatch,
    KnowledgeAtomObject,
    KnowledgeClaim,
    KnowledgeEvidenceSpan,
    KnowledgeRelation,
)
from knoarbor.semantic.knowledge_atom_normalization import normalize_knowledge_atom_batch
from knoarbor.semantic.knowledge_atom_quality import evaluate_knowledge_atoms


def _evidence(source_digest_id: str = "sd_agent") -> KnowledgeEvidenceSpan:
    return KnowledgeEvidenceSpan(
        source_digest_id=source_digest_id,
        source_path="raw/inbox/notes/Agent.md",
        source_unit_index=0,
        excerpt="Agent loop coordinates tool use.",
    )


class KnowledgeAtomQualityTests(unittest.TestCase):
    def test_quality_report_accepts_supported_atoms(self) -> None:
        batch = KnowledgeAtomBatch(
            source_digest_id="sd_agent",
            entities=[
                KnowledgeAtomObject(object_type="knowledge_object", name="Agent Loop", atom_id="entity_agent_loop"),
                KnowledgeAtomObject(object_type="knowledge_object", name="Tool Governance", atom_id="entity_tool_governance"),
            ],
            claims=[
                KnowledgeClaim(
                    id="claim_agent_loop_production",
                    claim="Production agent loops need tool governance.",
                    claim_type="assessment",
                    evidence=[_evidence()],
                    entity_names=["Agent Loop", "Tool Governance"],
                )
            ],
            relations=[
                KnowledgeRelation(
                    id="rel_agent_loop_supports_tools",
                    subject=KnowledgeAtomObject(object_type="knowledge_object", name="Agent Loop"),
                    predicate="supports",
                    object=KnowledgeAtomObject(object_type="knowledge_object", name="Tool Governance"),
                    source_claim_ids=["claim_agent_loop_production"],
                )
            ],
        )

        report = evaluate_knowledge_atoms(batch)

        self.assertEqual(report.summary()["unsupported"], 0)
        self.assertEqual(report.summary()["conflicting"], 0)
        self.assertEqual(report.summary()["rejected"], 0)

    def test_quality_report_flags_missing_support_ids_and_conflicts(self) -> None:
        subject = KnowledgeAtomObject(object_type="knowledge_object", name="Agent Loop")
        obj = KnowledgeAtomObject(object_type="knowledge_object", name="Workflow")
        batch = KnowledgeAtomBatch(
            source_digest_id="sd_agent",
            entities=[
                KnowledgeAtomObject(object_type="knowledge_object", name="Agent Loop", atom_id="entity_agent_loop"),
                KnowledgeAtomObject(object_type="knowledge_object", name="Workflow", atom_id="entity_workflow"),
            ],
            claims=[
                KnowledgeClaim(
                    id="claim_missing_fact",
                    claim="Agent loop should replace all workflows.",
                    claim_type="recommendation",
                    evidence=[_evidence("other_digest")],
                    entity_names=["Agent Loop", "Workflow"],
                )
            ],
            relations=[
                KnowledgeRelation(
                    id="rel_supports",
                    subject=subject,
                    predicate="supports",
                    object=obj,
                    source_claim_ids=["missing_claim"],
                ),
                KnowledgeRelation(
                    id="rel_contradicts",
                    subject=subject,
                    predicate="contradicts",
                    object=obj,
                    source_claim_ids=["claim_missing_fact"],
                ),
            ],
        )

        report = evaluate_knowledge_atoms(batch)

        issue_types = {issue.issue_type for issue in report.issues}
        self.assertIn("unsupported_claim", issue_types)
        self.assertIn("unsupported_relation", issue_types)
        self.assertIn("conflicting_relation", issue_types)
        self.assertEqual(report.summary()["unsupported"], 2)
        self.assertEqual(report.summary()["conflicting"], 1)
        self.assertEqual(report.summary()["rejected"], 2)

    def test_quality_report_flags_undeclared_entities(self) -> None:
        batch = KnowledgeAtomBatch(
            source_digest_id="sd_agent",
            entities=[KnowledgeAtomObject(object_type="knowledge_object", name="Agent Loop", atom_id="entity_agent_loop")],
            claims=[
                KnowledgeClaim(
                    id="claim_agent_loop",
                    claim="Agent Loop coordinates tool governance.",
                    claim_type="definition",
                    evidence=[_evidence()],
                    entity_names=["Agent Loop", "Tool Governance"],
                )
            ],
            relations=[
                KnowledgeRelation(
                    id="rel_agent_loop_tools",
                    subject=KnowledgeAtomObject(object_type="knowledge_object", name="Agent Loop"),
                    predicate="coordinates",
                    object=KnowledgeAtomObject(object_type="knowledge_object", name="Tool Governance"),
                    source_claim_ids=["claim_agent_loop"],
                )
            ],
        )

        report = evaluate_knowledge_atoms(batch)

        issues = [issue for issue in report.issues if issue.issue_type == "undefined_entity_reference"]
        self.assertEqual(len(issues), 2)
        self.assertEqual(report.summary()["rejected"], 2)

    def test_normalization_closes_undeclared_entity_references(self) -> None:
        batch = KnowledgeAtomBatch(
            source_digest_id="sd_agent",
            entities=[KnowledgeAtomObject(object_type="knowledge_object", name="Agent Loop", atom_id="entity_agent_loop")],
            claims=[
                KnowledgeClaim(
                    id="claim_agent_loop",
                    claim="Agent Loop coordinates tool governance.",
                    claim_type="definition",
                    evidence=[_evidence()],
                    entity_names=["Agent Loop", "Tool Governance"],
                )
            ],
            relations=[
                KnowledgeRelation(
                    id="rel_agent_loop_tools",
                    subject=KnowledgeAtomObject(object_type="knowledge_object", name="Agent Loop"),
                    predicate="coordinates",
                    object=KnowledgeAtomObject(object_type="knowledge_object", name="Tool Governance"),
                    source_claim_ids=["claim_agent_loop"],
                )
            ],
        )

        normalized = normalize_knowledge_atom_batch(batch)
        report = evaluate_knowledge_atoms(normalized)

        self.assertIn("Tool Governance", [entity.name for entity in normalized.entities])
        self.assertTrue(any(item.startswith("auto_declared_entity:Tool Governance") for item in normalized.warnings))
        self.assertNotIn("undefined_entity_reference", {issue.issue_type for issue in report.issues})

    def test_quality_report_flags_entities_not_used_by_claims_or_relations(self) -> None:
        batch = KnowledgeAtomBatch(
            source_digest_id="sd_agent",
            entities=[
                KnowledgeAtomObject(object_type="knowledge_object", name="Agent Loop", atom_id="entity_agent_loop"),
                KnowledgeAtomObject(object_type="knowledge_object", name="Unused Object", atom_id="entity_unused"),
            ],
            claims=[
                KnowledgeClaim(
                    id="claim_agent_loop",
                    claim="Agent Loop coordinates tool use.",
                    claim_type="definition",
                    evidence=[_evidence()],
                    entity_names=["Agent Loop"],
                )
            ],
        )

        report = evaluate_knowledge_atoms(batch)

        self.assertIn("unused_entity", {issue.issue_type for issue in report.issues})
        self.assertEqual(report.summary()["rejected"], 0)


if __name__ == "__main__":
    unittest.main()
