from __future__ import annotations

import unittest

from knoarbor.core.schemas.knowledge_extract import KnowledgeExtract
from knoarbor.core.schemas.wiki_relation_plan import WikiRelationOperation, WikiRelationPlan
from knoarbor.semantic.ingest_compile_context import build_ingest_compile_context

from tests.harness.semantic_cases import source_normalize_output


class IngestCompileContextTests(unittest.TestCase):
    def test_build_groups_pages_by_context_role(self) -> None:
        extract = KnowledgeExtract.model_validate(source_normalize_output()["output"])
        relation_plan = WikiRelationPlan(
            operations=[
                WikiRelationOperation(
                    action="update",
                    target_page="concepts/Agent.md",
                    page_dir="concepts",
                    title="Agent",
                    knowledge_object="Agent",
                    decision_reason="Update existing page.",
                )
            ],
            overall_summary="Update one page.",
        )
        candidate_page_context = {
            "pages": [
                {
                    "path": "concepts/Agent.md",
                    "exists": True,
                    "context_role": "target",
                    "content_kind": "full",
                    "title": "Agent",
                    "summary": "Agent summary.",
                    "content": "# Agent\n\nBody.",
                },
                {
                    "path": "concepts/Loop.md",
                    "exists": True,
                    "context_role": "related",
                    "content_kind": "excerpt",
                    "title": "Loop",
                    "summary": "Loop summary.",
                    "content": "Summary:\nLoop summary.",
                },
                {
                    "path": "concepts/Candidate.md",
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

        context = build_ingest_compile_context(extract, relation_plan, candidate_page_context)

        self.assertEqual(context.schema_version, "ingest_compile_context.v1")
        self.assertEqual(context.current_content.title, "Agent")
        self.assertEqual(context.operations[0].target_page, "concepts/Agent.md")
        self.assertEqual(context.page_context.targets[0].content_kind, "full")
        self.assertEqual(context.page_context.related[0].content_kind, "excerpt")
        self.assertEqual(context.page_context.candidates[0].content_kind, "profile")
        self.assertEqual(context.stats["materialized_context_chars"], 35)


if __name__ == "__main__":
    unittest.main()
