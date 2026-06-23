from __future__ import annotations

import sys
import unittest
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.semantic import IngestSemanticWorkflow, SemanticRunner

from tests.harness.llm import ScriptedChatClient
from tests.harness.semantic_cases import (
    ingest_review_output,
    markdown_source_document,
    source_normalize_output,
    wiki_atom_extract_output,
    wiki_draft_batch_output,
    wiki_page_plan_output,
)


class IngestSemanticWorkflowTests(unittest.TestCase):
    def test_ingest_semantic_workflow_runs_four_contracts_without_writing(self) -> None:
        client = ScriptedChatClient(
            [
                source_normalize_output(),
                wiki_atom_extract_output(),
                wiki_page_plan_output(),
                wiki_draft_batch_output(),
                ingest_review_output(),
            ]
        )

        result = IngestSemanticWorkflow(SemanticRunner(client)).run(markdown_source_document())

        self.assertEqual(len(client.requests), 5)
        self.assertEqual(result.knowledge_extract.source.title, "Agent")
        self.assertIsNotNone(result.knowledge_atom_batch)
        self.assertEqual(result.knowledge_atom_batch.summary()["facts"], 1)
        self.assertEqual(result.wiki_page_plan.operations[0].title, "Agent Loop")
        self.assertEqual(result.wiki_draft_batch.drafts[0].title, "Agent Loop")
        self.assertEqual(result.ingest_draft_review.batch_decision, "approve")

    def test_draft_and_review_receive_shared_ingest_compile_context(self) -> None:
        client = ScriptedChatClient(
            [
                source_normalize_output(),
                wiki_atom_extract_output(),
                wiki_page_plan_output(),
                wiki_draft_batch_output(),
                ingest_review_output(),
            ]
        )
        candidate_page_context = {
            "pages": [
                {
                    "path": "concepts/Agent.md",
                    "exists": True,
                    "context_role": "target",
                    "content_kind": "full",
                    "title": "Agent",
                    "summary": "Existing agent page.",
                    "content": "# Agent\n\nExisting body.",
                }
            ],
            "stats": {"context_policy": "target_full_related_excerpt_candidate_profile"},
        }

        IngestSemanticWorkflow(SemanticRunner(client)).run(
            markdown_source_document(),
            candidate_page_context=candidate_page_context,
        )

        atom_payload = _dynamic_payload(client.requests[1])
        relation_payload = _dynamic_payload(client.requests[2])
        draft_payload = _dynamic_payload(client.requests[3])
        review_payload = _dynamic_payload(client.requests[4])
        self.assertIn("source_digest", atom_payload)
        self.assertEqual(relation_payload["knowledge_atoms"]["source_digest_id"], "sd_test_agent")
        self.assertEqual(relation_payload["knowledge_atoms"]["facts"][0]["id"], "fact_agent_loop_cycle")
        self.assertEqual(draft_payload["knowledge_atoms"]["source_digest_id"], "sd_test_agent")
        self.assertIn("ingest_compile_context", draft_payload)
        self.assertEqual(
            draft_payload["ingest_compile_context"],
            review_payload["ingest_compile_context"],
        )
        context = draft_payload["ingest_compile_context"]
        self.assertEqual(context["schema_version"], "ingest_compile_context.v1")
        self.assertEqual(context["operations"][0]["selected_fact_ids"], ["fact_agent_loop_cycle"])
        self.assertEqual(context["operations"][0]["selected_claim_ids"], ["claim_agent_loop_control_pattern"])
        self.assertEqual(context["operations"][0]["selected_relation_ids"], ["rel_agent_loop_mentions_control"])
        self.assertEqual(context["operations"][0]["source_digest_ids"], ["sd_test_agent"])
        self.assertEqual(context["page_context"]["targets"][0]["content_kind"], "full")
        self.assertEqual(context["context_policy"], "target_full_related_excerpt_candidate_profile")


def _dynamic_payload(request) -> dict[str, object]:
    marker = "Input JSON:\n"
    content = request.messages[-1].content
    return json.loads(content.split(marker, 1)[1])


if __name__ == "__main__":
    unittest.main()
