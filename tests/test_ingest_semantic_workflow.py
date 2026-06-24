from __future__ import annotations

from copy import deepcopy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.pipelines.ingest_context import IngestContextProvider
from knoarbor.pipelines.ingest_semantic import IngestSemanticRunner
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
    def test_ingest_semantic_runner_extract_source_uses_digest_only_atom_input(self) -> None:
        client = ScriptedChatClient(
            [
                source_normalize_output(),
                wiki_atom_extract_output(),
            ]
        )
        workflow = IngestSemanticWorkflow(SemanticRunner(client))
        runner = IngestSemanticRunner(
            semantic_workflow=workflow,
            context_provider=IngestContextProvider(),
        )

        result = runner.extract_source(document=markdown_source_document(), max_tokens=None)

        self.assertEqual(result.knowledge_atom_batch.summary()["claims"], 1)
        atom_payload = _dynamic_payload(client.requests[1])
        self.assertIn("source_digest", atom_payload)
        self.assertNotIn("knowledge_extract", atom_payload)

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
        self.assertTrue(result.source_digest.digest_id.startswith("sd_"))
        self.assertIsNotNone(result.knowledge_atom_batch)
        self.assertIsNotNone(result.knowledge_atom_quality)
        self.assertEqual(result.knowledge_atom_batch.summary()["claims"], 1)
        self.assertEqual(result.knowledge_atom_quality.summary()["claims"], 1)
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
        plan_payload = _dynamic_payload(client.requests[2])
        draft_payload = _dynamic_payload(client.requests[3])
        review_payload = _dynamic_payload(client.requests[4])
        self.assertIn("source_digest", atom_payload)
        self.assertNotIn("knowledge_extract", atom_payload)
        self.assertNotIn("knowledge_extract", plan_payload)
        self.assertTrue(str(plan_payload["source_digest"]["digest_id"]).startswith("sd_"))
        self.assertIn("raw_source", plan_payload["source_digest"])
        self.assertIn("content_hash", plan_payload["source_digest"])
        self.assertIn("contribution_map", plan_payload["source_digest"])
        self.assertIn("unresolved_items", plan_payload["source_digest"])
        self.assertEqual(plan_payload["source_digest"]["units"][0]["summary"], "Agent")
        self.assertNotIn("evidence", plan_payload["source_digest"]["units"][0])
        self.assertEqual(plan_payload["knowledge_atoms"]["source_digest_id"], "sd_test_agent")
        self.assertEqual(plan_payload["knowledge_atoms"]["claims"][0]["id"], "claim_agent_loop_control_pattern")
        self.assertEqual(draft_payload["knowledge_atoms"]["source_digest_id"], "sd_test_agent")
        self.assertIn("page_assembly", draft_payload)
        self.assertEqual(draft_payload["page_assembly"]["schema_version"], "page_assembly.v1")
        self.assertEqual(draft_payload["page_assembly"]["operations"][0]["claims"][0]["number"], "C1")
        self.assertEqual(
            draft_payload["page_assembly"]["operations"][0]["relations"][0]["triple"],
            "[[Agent Loop]] | includes | [[Agent Control]] | C1",
        )
        self.assertIn("ingest_compile_context", draft_payload)
        self.assertNotIn("knowledge_extract", draft_payload)
        self.assertNotIn("wiki_page_plan", draft_payload)
        self.assertNotIn("wiki_operations", draft_payload)
        self.assertNotIn("candidate_page_context", draft_payload)
        self.assertNotIn("knowledge_extract", review_payload)
        self.assertNotIn("wiki_page_plan", review_payload)
        self.assertNotIn("candidate_page_context", review_payload)
        self.assertEqual(
            draft_payload["ingest_compile_context"],
            review_payload["ingest_compile_context"],
        )
        context = draft_payload["ingest_compile_context"]
        self.assertEqual(context["schema_version"], "ingest_compile_context.v1")
        self.assertEqual(context["operations"][0]["selected_claim_ids"], ["claim_agent_loop_control_pattern"])
        self.assertEqual(context["operations"][0]["selected_relation_ids"], ["rel_agent_loop_mentions_control"])
        self.assertEqual(context["operations"][0]["source_digest_ids"], ["sd_test_agent"])
        self.assertEqual(context["page_context"]["targets"][0]["content_kind"], "full")
        self.assertEqual(context["context_policy"], "target_full_related_excerpt_candidate_profile")
        self.assertEqual(context["current_content"]["primary_content"], "")
        self.assertEqual(context["current_content"]["source_text_policy"], "omitted_after_atom_extraction")

    def test_draft_compile_receives_only_page_plan_selected_atoms(self) -> None:
        atom_output = _atom_output_with_unselected_material()
        client = ScriptedChatClient(
            [
                source_normalize_output(),
                atom_output,
                wiki_page_plan_output(),
                wiki_draft_batch_output(),
                ingest_review_output(),
            ]
        )

        IngestSemanticWorkflow(SemanticRunner(client)).run(markdown_source_document())

        draft_payload = _dynamic_payload(client.requests[3])
        atom_payload = draft_payload["knowledge_atoms"]
        self.assertEqual(_ids(atom_payload["claims"]), ["claim_agent_loop_control_pattern"])
        self.assertEqual(_ids(atom_payload["relations"]), ["rel_agent_loop_mentions_control"])
        self.assertEqual([item["atom_id"] for item in atom_payload["entities"]], ["entity_agent_loop", "entity_agent_control"])


def _dynamic_payload(request) -> dict[str, object]:
    marker = "Input JSON:\n"
    content = request.messages[-1].content
    return json.loads(content.split(marker, 1)[1])


def _ids(items: list[dict[str, object]]) -> list[str]:
    return [str(item["id"]) for item in items]


def _atom_output_with_unselected_material() -> dict[str, object]:
    output = deepcopy(wiki_atom_extract_output())
    atom_batch = output["output"]
    assert isinstance(atom_batch, dict)
    atom_batch["entities"].append(
        {
            "object_type": "knowledge_object",
            "name": "Noise",
            "atom_id": "entity_noise",
        }
    )
    atom_batch["claims"].append(
        {
            "id": "claim_unselected_noise",
            "claim": "Unselected material is unrelated to the planned page.",
            "claim_type": "assessment",
            "stance": "asserted",
            "evidence": [
                {
                    "source_digest_id": "sd_test_agent",
                    "source_path": "raw/notes/Agent.md",
                    "source_unit_index": 0,
                    "excerpt": "Noise background.",
                }
            ],
            "entity_names": ["Noise"],
            "confidence": 0.7,
        }
    )
    atom_batch["relations"].append(
        {
            "id": "rel_unselected_noise",
            "subject": {"object_type": "knowledge_object", "name": "Noise"},
            "predicate": "coordinates",
            "object": {"object_type": "knowledge_object", "name": "Background"},
            "source_claim_ids": ["claim_unselected_noise"],
            "evidence": [],
            "reason": "Noise is unrelated.",
            "confidence": 0.7,
        }
    )
    return output


if __name__ == "__main__":
    unittest.main()
