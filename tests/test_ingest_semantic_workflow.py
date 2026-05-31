from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.semantic import IngestSemanticWorkflow, SemanticRunner

from tests.harness.llm import ScriptedChatClient
from tests.harness.semantic_cases import (
    ingest_review_output,
    markdown_source_document,
    source_normalize_output,
    wiki_draft_batch_output,
    wiki_relation_output,
)


class IngestSemanticWorkflowTests(unittest.TestCase):
    def test_ingest_semantic_workflow_runs_four_contracts_without_writing(self) -> None:
        client = ScriptedChatClient(
            [
                source_normalize_output(),
                wiki_relation_output(),
                wiki_draft_batch_output(),
                ingest_review_output(),
            ]
        )

        result = IngestSemanticWorkflow(SemanticRunner(client)).run(markdown_source_document())

        self.assertEqual(len(client.requests), 4)
        self.assertEqual(result.knowledge_extract.source.title, "Agent")
        self.assertEqual(result.wiki_relation_plan.operations[0].title, "Agent Loop")
        self.assertEqual(result.wiki_draft_batch.drafts[0].title, "Agent Loop")
        self.assertEqual(result.ingest_draft_review.batch_decision, "approve")


if __name__ == "__main__":
    unittest.main()
