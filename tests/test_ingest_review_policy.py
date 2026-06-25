from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.core.schemas.knowledge_atoms import KnowledgeAtomQualityIssue, KnowledgeAtomQualityReport
from knoarbor.core.schemas.wiki_draft_batch import WikiDraftBatch, WikiDraftBatchItem
from knoarbor.core.schemas.wiki_page_plan import WikiCandidatePage, WikiPageOperation, WikiPagePlan
from knoarbor.core.schemas.wiki_write import WikiPatchInput
from knoarbor.pipelines.ingest_review_policy import IngestDraftReviewPolicy, auto_approve_ingest_draft_review


class IngestDraftReviewPolicyTests(unittest.TestCase):
    def test_low_risk_create_can_skip_semantic_review(self) -> None:
        page_plan = _page_plan(_create_operation())
        draft_batch = _draft_batch(_create_draft())
        decision = IngestDraftReviewPolicy().evaluate(
            page_plan=page_plan,
            draft_batch=draft_batch,
            atom_quality=_clean_atom_quality(),
        )

        self.assertFalse(decision.should_review)
        review = auto_approve_ingest_draft_review(
            page_plan=page_plan,
            draft_batch=draft_batch,
            policy_decision=decision,
        )
        self.assertEqual(review.batch_decision, "approve")
        self.assertEqual(review.decisions[0].write_safety, "safe_create")

    def test_update_operation_requires_semantic_review(self) -> None:
        page_plan = _page_plan(
            WikiPageOperation(
                action="update",
                target_page="Agent-Loop.md",
                page_dir="concepts",
                title="Agent Loop",
                knowledge_object="Agent Loop",
                selected_claim_ids=["claim_agent_loop"],
                source_digest_ids=["sd_agent"],
                decision_reason="Update existing page.",
            )
        )
        draft_batch = _draft_batch(
            _create_draft().model_copy(
                update={
                    "write_action": "update",
                    "target_page": "Agent-Loop.md",
                    "patches": [WikiPatchInput(operation="merge_list", section="Claims", items=["C1: Updated claim."])],
                }
            )
        )

        decision = IngestDraftReviewPolicy().evaluate(
            page_plan=page_plan,
            draft_batch=draft_batch,
            atom_quality=_clean_atom_quality(),
        )

        self.assertTrue(decision.should_review)
        self.assertIn("update", decision.triggers)
        self.assertEqual(decision.operation_indexes, [0])

    def test_duplicate_candidate_and_weak_evidence_require_semantic_review(self) -> None:
        operation = _create_operation().model_copy(
            update={
                "candidate_pages": [
                    WikiCandidatePage(path="Agent-Loop.md", title="Agent Loop", match_reason="Similar title.")
                ]
            }
        )
        decision = IngestDraftReviewPolicy().evaluate(
            page_plan=_page_plan(operation),
            draft_batch=_draft_batch(_create_draft()),
            atom_quality=KnowledgeAtomQualityReport(
                source_digest_id="sd_agent",
                extracted={"claims": 1},
                issues=[
                    KnowledgeAtomQualityIssue(
                        issue_type="unsupported_claim",
                        severity="warning",
                        atom_id="claim_agent_loop",
                        message="Claim evidence is weak.",
                    )
                ],
            ),
        )

        self.assertTrue(decision.should_review)
        self.assertIn("duplicate_candidate", decision.triggers)
        self.assertIn("weak_evidence", decision.triggers)


def _page_plan(operation: WikiPageOperation) -> WikiPagePlan:
    return WikiPagePlan(operations=[operation], overall_summary="Plan one page.")


def _create_operation() -> WikiPageOperation:
    return WikiPageOperation(
        action="create",
        page_dir="concepts",
        title="Agent Loop",
        knowledge_object="Agent Loop",
        selected_claim_ids=["claim_agent_loop"],
        source_digest_ids=["sd_agent"],
        decision_reason="Create durable page.",
    )


def _draft_batch(draft: WikiDraftBatchItem) -> WikiDraftBatch:
    return WikiDraftBatch(drafts=[draft], batch_summary="One draft.")


def _create_draft() -> WikiDraftBatchItem:
    return WikiDraftBatchItem(
        operation_index=0,
        write_action="create",
        title="Agent Loop",
        page_dir="concepts",
        question="Agent Loop",
        summary="Agent Loop is an execution control pattern.",
        claims=["C1: [[Agent Loop]] repeats observe, decide, act, and feedback."],
        entities=["[[Agent Loop]]"],
        relations=["[[Agent Loop]] | includes | [[Feedback Cycle]] | C1"],
        evidence=["C1 | sd_agent | unit:0 | source states the loop structure | high"],
        synthesis="Agent Loop coordinates repeated execution steps.",
        source_digest_ids=["sd_agent"],
        atom_ids=["claim_agent_loop"],
    )


def _clean_atom_quality() -> KnowledgeAtomQualityReport:
    return KnowledgeAtomQualityReport(
        source_digest_id="sd_agent",
        extracted={"claims": 1, "relations": 1, "entities": 1, "evidence_spans": 1},
        issues=[],
    )


if __name__ == "__main__":
    unittest.main()
