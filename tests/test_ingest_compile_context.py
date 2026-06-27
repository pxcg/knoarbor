from __future__ import annotations

import unittest

from knoarbor.core.schemas.knowledge_extract import KnowledgeExtract
from knoarbor.core.schemas.wiki_page_plan import WikiPageOperation, WikiPagePlan
from knoarbor.semantic.ingest_compile_context import build_ingest_compile_context

from tests.harness.semantic_cases import source_normalize_output


class IngestCompileContextTests(unittest.TestCase):
    def test_build_groups_pages_by_context_role(self) -> None:
        extract = KnowledgeExtract.model_validate(source_normalize_output()["output"])
        page_plan = WikiPagePlan(
            operations=[
                WikiPageOperation(
                    action="update",
                    target_page="Agent.md",
                    page_dir="pages",
                    canonical_path="Agent.md",
                    title="Agent",
                    knowledge_object="Agent",
                    selected_claim_ids=["claim_agent_loop_control_pattern"],
                    source_digest_ids=["sd_test_agent"],
                    decision_reason="Update existing page.",
                )
            ],
            overall_summary="Update one page.",
        )
        candidate_page_context = {
            "pages": [
                {
                    "path": "Agent.md",
                    "exists": True,
                    "context_role": "target",
                    "content_kind": "full",
                    "title": "Agent",
                    "summary": "Agent summary.",
                    "relations": [{"subject": "Agent Loop", "predicate": "uses", "object": "Tools", "claim": "C1"}],
                    "content": "# Agent\n\nBody.",
                },
                {
                    "path": "Loop.md",
                    "exists": True,
                    "context_role": "related",
                    "content_kind": "excerpt",
                    "title": "Loop",
                    "summary": "Loop summary.",
                    "content": "Summary:\nLoop summary.",
                },
                {
                    "path": "Candidate.md",
                    "exists": True,
                    "context_role": "candidate",
                    "content_kind": "profile",
                    "title": "Candidate",
                    "summary": "Candidate summary.",
                    "content": "",
                },
            ],
            "stats": {
                "context_policy": "target_full_related_excerpt_candidate_profile",
                "materialized_context_chars": 35,
            },
        }

        context = build_ingest_compile_context(extract, page_plan, candidate_page_context)

        self.assertEqual(context.schema_version, "ingest_compile_context.v1")
        self.assertEqual(context.current_content.title, "Agent")
        self.assertEqual(context.operations[0].target_page, "Agent.md")
        self.assertEqual(context.operations[0].canonical_path, "Agent.md")
        self.assertEqual(context.page_context.targets[0].content_kind, "full")
        self.assertEqual(
            context.page_context.targets[0].relations,
            [{"subject": "Agent Loop", "predicate": "uses", "object": "Tools", "claim": "C1"}],
        )
        self.assertEqual(context.page_context.related[0].content_kind, "excerpt")
        self.assertEqual(context.page_context.candidates[0].content_kind, "profile")
        self.assertEqual(context.stats["materialized_context_chars"], 35)


if __name__ == "__main__":
    unittest.main()
