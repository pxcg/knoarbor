from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.semantic import IngestSemanticWorkflow, LintSemanticWorkflow, SemanticRunner

from tests.harness.llm import ScriptedChatClient
from tests.harness.semantic_cases import (
    ingest_review_output,
    lint_candidates_output,
    lint_draft_batch_output,
    lint_review_output,
    markdown_source_document,
    source_normalize_output,
    wiki_draft_batch_output,
    wiki_relation_output,
)
from tests.harness.snapshot import assert_json_snapshot


FIXTURE_DIR = Path(__file__).resolve().parent / "harness" / "fixtures" / "semantic"


class SemanticGoldenTests(unittest.TestCase):
    def test_ingest_agent_loop_workflow_matches_golden_fixture(self) -> None:
        client = ScriptedChatClient(
            [
                source_normalize_output(),
                wiki_relation_output(),
                wiki_draft_batch_output(),
                ingest_review_output(),
            ]
        )

        result = IngestSemanticWorkflow(SemanticRunner(client)).run(markdown_source_document())

        assert_json_snapshot(self, result, FIXTURE_DIR / "ingest_agent_loop_workflow.json")

    def test_lint_broken_link_workflow_matches_golden_fixture(self) -> None:
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

        assert_json_snapshot(
            self,
            {
                "candidates": candidates.model_dump(mode="json"),
                "drafts": drafts.model_dump(mode="json"),
                "review": review.model_dump(mode="json"),
            },
            FIXTURE_DIR / "lint_broken_link_workflow.json",
        )


if __name__ == "__main__":
    unittest.main()
