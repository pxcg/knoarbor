from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.core.schemas.knowledge_atoms import KnowledgeAtomBatch, KnowledgeAtomObject, KnowledgeEvidenceSpan, KnowledgeFact
from knoarbor.core.schemas.knowledge_extract import KnowledgeExtract
from knoarbor.core.schemas.wiki_page_plan import WikiPageOperation, WikiPagePlan
from knoarbor.pipelines.ingest_context import IngestContextProvider
from knoarbor.pipelines.query import QueryPipelineResult
from knoarbor.retrieval.markdown import ScoredPage, SearchPage
from knoarbor.storage import update_machine_index

from tests.harness.semantic_cases import source_normalize_output


class CountingQueryPipeline:
    def __init__(self, page: SearchPage) -> None:
        self.index_provider = type("Provider", (), {"name": "counting"})()
        self.page = page
        self.calls = 0

    def run(self, request):
        self.calls += 1
        return QueryPipelineResult(
            query=request.query,
            retrieval_mode="counting_hybrid_balanced",
            matches=[
                ScoredPage(
                    page=self.page,
                    score=5.0,
                    matched_fields={"title"},
                    matched_terms={"title": ["agent"]},
                )
            ],
            gaps=[],
            warnings=[],
            stats={"returned_count": 1},
        )


class IngestContextProviderTests(unittest.TestCase):
    def test_build_reuses_same_run_query_cache(self) -> None:
        page = SearchPage(
            path=Path("/tmp/concepts/Agent.md"),
            relative_path="concepts/Agent.md",
            directory="concepts",
            title="Agent",
            page_type="concept",
            status="draft",
            source=None,
            tags=["agent"],
            summary="Agent summary.",
            key_points=[],
            related_pages=[],
            headings=["Summary"],
            body="Agent body.",
        )
        query_pipeline = CountingQueryPipeline(page)
        provider = IngestContextProvider(query_pipeline=query_pipeline)
        extract = KnowledgeExtract.model_validate(source_normalize_output()["output"])

        first = provider.build(Path("/tmp/vaults/all"), extract)
        second = provider.build(Path("/tmp/vaults/all"), extract)

        self.assertEqual(query_pipeline.calls, 1)
        self.assertEqual(first.candidates[0].path, "concepts/Agent.md")
        self.assertEqual(second.candidates[0].path, "concepts/Agent.md")
        self.assertFalse(first.stats["page_plan_candidate_body_included"])
        self.assertEqual(first.stats["page_plan_context_policy"], "graph_first_lightweight_page_profiles_without_page_body")

    def test_relation_candidates_are_profiles_without_body_or_field_slicing(self) -> None:
        page = SearchPage(
            path=Path("/tmp/concepts/Agent.md"),
            relative_path="concepts/Agent.md",
            directory="concepts",
            title="Agent",
            page_type="concept",
            status="draft",
            source="raw/notes/agent.md",
            tags=[f"tag-{index}" for index in range(16)],
            summary="Line one.\n\nLine two.",
            key_points=[f"point {index}" for index in range(10)],
            related_pages=[f"concepts/Related-{index}.md" for index in range(14)],
            headings=["Summary"],
            body="Full page body must not enter relation wiki_context.",
        )
        provider = IngestContextProvider(query_pipeline=CountingQueryPipeline(page))
        extract = KnowledgeExtract.model_validate(source_normalize_output()["output"])

        context = provider.build(Path("/tmp/vaults/all"), extract)
        payload = context.model_dump()
        candidate = payload["candidates"][0]

        self.assertNotIn("body", candidate)
        self.assertNotIn("content", candidate)
        self.assertNotIn("answer", candidate)
        self.assertEqual(candidate["summary"], "Line one. Line two.")
        self.assertEqual(candidate["tags"], page.tags)
        self.assertEqual(candidate["key_points"], page.key_points)
        self.assertEqual(candidate["related_pages"], page.related_pages)
        self.assertGreater(context.stats["page_plan_profile_chars"], 0)

    def test_graph_first_candidates_use_atom_entities_before_text_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            _write_page(
                vault / "concepts" / "Graph-Candidate.md",
                "# Graph Candidate\n\n"
                "## Summary\n\nA page that should be found through entity graph signals.\n\n"
                "## Claims\n\n- C1: [[GraphOnlyEntity]] is represented in the graph.\n\n"
                "## Entities\n\n- [[GraphOnlyEntity]]\n",
            )
            update_machine_index(vault)
            extract = KnowledgeExtract.model_validate(
                source_normalize_output(title="Zzzqxv", content="Plomter qivrax zednort.")["output"]
            )
            atom_batch = KnowledgeAtomBatch(
                source_digest_id="sd_graph_only",
                facts=[
                    KnowledgeFact(
                        id="fact_graph_only",
                        statement="GraphOnlyEntity appears in the source.",
                        subject=KnowledgeAtomObject(object_type="entity", name="GraphOnlyEntity"),
                        evidence=[
                            KnowledgeEvidenceSpan(
                                source_digest_id="sd_graph_only",
                                source_path="raw/notes/graph-only.md",
                                excerpt="GraphOnlyEntity appears in the source.",
                            )
                        ],
                    )
                ],
            )

            context = IngestContextProvider().build(vault, extract, knowledge_atom_batch=atom_batch)

        self.assertEqual(context.candidates[0].path, "concepts/Graph-Candidate.md")
        self.assertEqual(context.stats["graph_first_candidate_count"], 1)
        self.assertEqual(context.stats["text_candidate_count"], 0)
        self.assertIn("graph_first", context.candidates[0].matched_fields)

    def test_materialize_cache_is_local_and_clearable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            page = vault / "concepts" / "Agent.md"
            page.write_text("# Agent\n\nOld content.", encoding="utf-8")
            provider = IngestContextProvider()
            page_plan = WikiPagePlan(
                operations=[
                    WikiPageOperation(
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

            first = provider.materialize(vault, page_plan)
            page.write_text("# Agent\n\nNew content.", encoding="utf-8")
            second = provider.materialize(vault, page_plan)
            provider.clear_cache()
            third = provider.materialize(vault, page_plan)

        self.assertIn("Old content", first.pages[0].content)
        self.assertIn("Old content", second.pages[0].content)
        self.assertIn("New content", third.pages[0].content)

    def test_materialize_layers_target_related_and_candidate_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            _write_page(
                vault / "concepts" / "Target.md",
                "# Target\n\n## Summary\n\nTarget summary.\n\n## Answer\n\nExisting target body.",
            )
            _write_page(
                vault / "concepts" / "Related.md",
                "# Related\n\n## Summary\n\nRelated summary.\n\n## Key Points\n\n- Related point\n\n## Answer\n\nRelated body should not be passed in full.",
            )
            _write_page(
                vault / "concepts" / "Candidate.md",
                "# Candidate\n\n## Summary\n\nCandidate summary.\n\n## Answer\n\nCandidate body should not enter context.",
            )
            page_plan = WikiPagePlan(
                operations=[
                    WikiPageOperation(
                        action="update",
                        target_page="concepts/Target.md",
                        page_dir="concepts",
                        title="Target",
                        knowledge_object="Target",
                        related_pages=[
                            {
                                "path": "concepts/Related.md",
                                "title": "Related",
                                "relation": "background",
                                "reason": "Related background.",
                            }
                        ],
                        candidate_pages=[
                            {
                                "path": "concepts/Candidate.md",
                                "title": "Candidate",
                                "match_reason": "Broad match.",
                            }
                        ],
                        decision_reason="Update target.",
                    )
                ],
                overall_summary="Layered context.",
            )

            context = IngestContextProvider().materialize(vault, page_plan)

        pages = {page.path: page for page in context.pages}
        self.assertEqual(pages["concepts/Target.md"].context_role, "target")
        self.assertEqual(pages["concepts/Target.md"].content_kind, "full")
        self.assertIn("Existing target body", pages["concepts/Target.md"].content)
        self.assertEqual(pages["concepts/Related.md"].context_role, "related")
        self.assertEqual(pages["concepts/Related.md"].content_kind, "excerpt")
        self.assertIn("Related summary", pages["concepts/Related.md"].content)
        self.assertNotIn("Related body should not be passed in full", pages["concepts/Related.md"].content)
        self.assertEqual(pages["concepts/Candidate.md"].context_role, "candidate")
        self.assertEqual(pages["concepts/Candidate.md"].content_kind, "profile")
        self.assertEqual(pages["concepts/Candidate.md"].content, "")
        self.assertEqual(context.stats["full_body_pages"], 1)
        self.assertEqual(context.stats["excerpt_pages"], 1)
        self.assertEqual(context.stats["profile_only_pages"], 1)
        self.assertEqual(context.stats["context_policy"], "target_full_related_excerpt_candidate_profile")

    def test_materialize_uses_highest_context_role_for_duplicate_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            _write_page(vault / "concepts" / "Agent.md", "# Agent\n\n## Answer\n\nFull target body.")
            page_plan = WikiPagePlan(
                operations=[
                    WikiPageOperation(
                        action="update",
                        target_page="concepts/Agent",
                        page_dir="concepts",
                        title="Agent",
                        knowledge_object="Agent",
                        candidate_pages=[
                            {
                                "path": "concepts/Agent.md",
                                "title": "Agent",
                                "match_reason": "Duplicate candidate.",
                            }
                        ],
                        decision_reason="Update existing page.",
                    )
                ],
                overall_summary="Update one page.",
            )

            context = IngestContextProvider().materialize(vault, page_plan)

        self.assertEqual(len(context.pages), 1)
        self.assertEqual(context.pages[0].context_role, "target")
        self.assertEqual(context.pages[0].content_kind, "full")
        self.assertIn("Full target body", context.pages[0].content)


def _write_page(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
