from __future__ import annotations

import unittest

from knoarbor.core.schemas.knowledge_atoms import (
    KnowledgeAtomBatch,
    KnowledgeAtomObject,
    KnowledgeClaim,
    KnowledgeEvidenceSpan,
    KnowledgeRelation,
)
from knoarbor.core.schemas.wiki_page_plan import WikiPageOperation, WikiPagePlan
from knoarbor.semantic.knowledge_atom_closure import close_operation_atoms, close_plan_atoms


class KnowledgeAtomClosureTests(unittest.TestCase):
    def test_claim_selection_closes_supported_relations_entities_and_evidence(self) -> None:
        batch = _batch()
        operation = _operation(selected_claim_ids=["claim_agent_loop"])

        closure = close_operation_atoms(batch, operation)

        self.assertEqual(closure.claim_ids, ["claim_agent_loop"])
        self.assertEqual(closure.relation_ids, ["rel_agent_loop_depends_on_memory"])
        self.assertEqual(closure.entity_names, ["Agent Loop", "Memory"])
        self.assertEqual(closure.source_digest_ids, ["sd_agent"])
        self.assertEqual(len(closure.evidence_keys), 2)
        self.assertEqual(closure.issues, [])

    def test_explicit_relation_reports_missing_source_claim(self) -> None:
        closure = close_operation_atoms(
            _batch(),
            _operation(selected_claim_ids=[], selected_relation_ids=["rel_agent_loop_depends_on_memory"]),
        )

        self.assertEqual(closure.claim_ids, [])
        self.assertEqual(closure.relation_ids, ["rel_agent_loop_depends_on_memory"])
        self.assertEqual([issue.code for issue in closure.issues], ["relation_selected_without_source_claim"])

    def test_plan_closure_returns_selected_batch_for_compile_agents(self) -> None:
        selected = close_plan_atoms(
            _batch(),
            WikiPagePlan(
                operations=[_operation(selected_claim_ids=["claim_agent_loop"])],
                overall_summary="Create agent loop page.",
            ),
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual([claim.id for claim in selected.claims], ["claim_agent_loop"])
        self.assertEqual([relation.id for relation in selected.relations], ["rel_agent_loop_depends_on_memory"])
        self.assertEqual([entity.name for entity in selected.entities], ["Agent Loop", "Memory"])
        self.assertEqual(len(selected.evidence), 2)

    def test_plan_closure_excludes_unselected_top_level_evidence(self) -> None:
        batch = _batch()
        selected = close_plan_atoms(
            batch.model_copy(
                update={
                    "evidence": [
                        *batch.evidence,
                        KnowledgeEvidenceSpan(
                            source_digest_id="sd_agent",
                            source_unit_index=99,
                            excerpt="This evidence belongs to an unselected source unit.",
                        ),
                    ]
                }
            ),
            WikiPagePlan(
                operations=[_operation(selected_claim_ids=["claim_agent_loop"])],
                overall_summary="Create agent loop page.",
            ),
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual([span.source_unit_index for span in selected.evidence], [0, 1])

    def test_plan_closure_keeps_inline_selected_evidence_without_top_level_batch_evidence(self) -> None:
        selected = close_plan_atoms(
            _batch().model_copy(update={"evidence": []}),
            WikiPagePlan(
                operations=[_operation(selected_claim_ids=["claim_agent_loop"])],
                overall_summary="Create agent loop page.",
            ),
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual([span.source_unit_index for span in selected.evidence], [0, 1])


def _batch() -> KnowledgeAtomBatch:
    claim_evidence = KnowledgeEvidenceSpan(
        source_digest_id="sd_agent",
        source_unit_index=0,
        excerpt="Agent loops need memory to preserve context.",
    )
    relation_evidence = KnowledgeEvidenceSpan(
        source_digest_id="sd_agent",
        source_unit_index=1,
        excerpt="Memory supports agent loop continuity.",
    )
    return KnowledgeAtomBatch(
        source_digest_id="sd_agent",
        entities=[
            KnowledgeAtomObject(object_type="concept", name="Agent Loop"),
            KnowledgeAtomObject(object_type="concept", name="Memory"),
            KnowledgeAtomObject(object_type="concept", name="Unselected"),
        ],
        claims=[
            KnowledgeClaim(
                id="claim_agent_loop",
                claim="Agent loops need memory to preserve context.",
                claim_type="definition",
                entity_names=["Agent Loop"],
                evidence=[claim_evidence],
            ),
            KnowledgeClaim(
                id="claim_unselected",
                claim="Unselected claims should stay outside the closure.",
                claim_type="assessment",
                entity_names=["Unselected"],
                evidence=[
                    KnowledgeEvidenceSpan(
                        source_digest_id="sd_agent",
                        source_unit_index=2,
                        excerpt="Unselected evidence.",
                    )
                ],
            ),
        ],
        relations=[
            KnowledgeRelation(
                id="rel_agent_loop_depends_on_memory",
                subject=KnowledgeAtomObject(object_type="concept", name="Agent Loop"),
                predicate="depends_on",
                object=KnowledgeAtomObject(object_type="concept", name="Memory"),
                source_claim_ids=["claim_agent_loop"],
                evidence=[relation_evidence],
            )
        ],
        evidence=[claim_evidence, relation_evidence],
    )


def _operation(
    *,
    selected_claim_ids: list[str],
    selected_relation_ids: list[str] | None = None,
) -> WikiPageOperation:
    return WikiPageOperation(
        action="create",
        page_dir="concepts",
        title="Agent Loop",
        knowledge_object="Agent Loop",
        selected_claim_ids=selected_claim_ids,
        selected_relation_ids=selected_relation_ids or [],
        source_digest_ids=["sd_agent"],
        decision_reason="Agent loop is a stable knowledge object.",
    )


if __name__ == "__main__":
    unittest.main()
