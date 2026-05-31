from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.semantic import LintSemanticWorkflow, SemanticRunner

from tests.harness.llm import ScriptedChatClient
from tests.harness.semantic_cases import lint_candidates_output, lint_draft_batch_output, lint_review_output


class LintSemanticWorkflowTests(unittest.TestCase):
    def test_lint_semantic_workflow_runs_model_steps_without_writing(self) -> None:
        client = ScriptedChatClient(
            [
                lint_candidates_output(),
                lint_review_output(),
                lint_draft_batch_output(),
            ]
        )
        workflow = LintSemanticWorkflow(SemanticRunner(client))

        candidates = workflow.diagnose_structural({"scan": {"issues": []}})
        review = workflow.review({"operations": [candidates.candidates[0].model_dump()]})
        drafts = workflow.compile_drafts({"approved_operations": [review.decisions[0].model_dump()]})

        self.assertEqual(len(client.requests), 3)
        self.assertEqual(candidates.candidates[0].issue_type, "broken_link")
        self.assertEqual(review.decisions[0].decision, "approve")
        self.assertEqual(drafts.drafts[0].page_dir, "sources")


if __name__ == "__main__":
    unittest.main()
