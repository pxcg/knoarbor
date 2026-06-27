from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.core.schemas.knowledge_atoms import (
    KnowledgeAtomBatch,
    KnowledgeAtomObject,
    KnowledgeClaim,
    KnowledgeEvidenceSpan,
    KnowledgeRelation,
)
from knoarbor.core.schemas.knowledge_extract import KnowledgeExtract
from knoarbor.core.schemas.wiki_page_plan import WikiPageOperation, WikiPagePlan
from knoarbor.pipelines.ingest_context import IngestContextProvider, build_ingest_query
from knoarbor.pipelines.query import QueryPipelineResult
from knoarbor.retrieval.markdown import ScoredPage, SearchPage
from knoarbor.storage import update_machine_index

from tests.harness.semantic_cases import source_normalize_output


class CountingQueryPipeline:
    def __init__(self, page: SearchPage) -> None:
        self.index_provider = self
        self.name = "counting"
        self.page = page
        self.calls = 0

    def collect(self, request):
        self.calls += 1
        return [self.page]

    def run(self, request):
        return QueryPipelineResult(
            query=request.query,
            retrieval_mode="counting_graph_led_bm25_balanced",
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
    def test_ingest_query_prefers_atom_signals_over_full_source_body(self) -> None:
        extract = KnowledgeExtract.model_validate(
            source_normalize_output(
                title="Noisy Source",
                content="NoisyBodyOnlyPhrase should not be used once atom signals exist.",
            )["output"]
        )
        atom_batch = KnowledgeAtomBatch(
            source_digest_id="sd_query_policy",
            entities=[KnowledgeAtomObject(object_type="knowledge_object", name="GraphSignalEntity")],
            claims=[
                KnowledgeClaim(
                    id="claim_query_policy",
                    claim="GraphSignalEntity drives the retrieval signal.",
                    claim_type="assessment",
                    evidence=[
                        KnowledgeEvidenceSpan(
                            source_digest_id="sd_query_policy",
                            source_path="raw/inbox/notes/query-policy.md",
                            excerpt="GraphSignalEntity appears here.",
                        )
                    ],
                    entity_names=["GraphSignalEntity"],
                )
            ],
            relations=[
                KnowledgeRelation(
                    id="rel_query_policy",
                    subject=KnowledgeAtomObject(object_type="knowledge_object", name="GraphSignalEntity"),
                    predicate="includes",
                    object=KnowledgeAtomObject(object_type="knowledge_object", name="Retrieval Policy"),
                    source_claim_ids=["claim_query_policy"],
                )
            ],
        )

        query = build_ingest_query(extract, atom_batch)

        self.assertIn("GraphSignalEntity", query)
        self.assertIn("Retrieval Policy", query)
        self.assertNotIn("NoisyBodyOnlyPhrase", query)

    def test_ingest_query_falls_back_to_source_body_before_atoms_exist(self) -> None:
        extract = KnowledgeExtract.model_validate(
            source_normalize_output(
                title="Fallback Source",
                content="FallbackBodySignal remains useful before atom extraction.",
            )["output"]
        )

        query = build_ingest_query(extract)

        self.assertIn("FallbackBodySignal", query)

    def test_build_reuses_same_run_query_cache(self) -> None:
        page = SearchPage(
            path=Path("/tmp/Agent.md"),
            relative_path="Agent.md",
            directory="pages",
            title="Agent",
            role="knowledge_page",
            entities=["agent"],
            summary="Agent summary.",
            claim_points=[],
            outbound_links=[],
            headings=["Summary"],
            body="Agent body.",
        )
        query_pipeline = CountingQueryPipeline(page)
        provider = IngestContextProvider(query_pipeline=query_pipeline)
        extract = KnowledgeExtract.model_validate(source_normalize_output()["output"])

        first = provider.build(Path("/tmp/vaults/all"), extract)
        second = provider.build(Path("/tmp/vaults/all"), extract)

        self.assertEqual(query_pipeline.calls, 1)
        self.assertEqual(first.candidates[0].path, "Agent.md")
        self.assertEqual(second.candidates[0].path, "Agent.md")
        self.assertFalse(first.stats["page_plan_candidate_body_included"])
        self.assertEqual(first.stats["page_plan_context_policy"], "graph_first_lightweight_page_profiles_without_page_body")

    def test_relation_candidates_are_profiles_without_body_or_field_slicing(self) -> None:
        page = SearchPage(
            path=Path("/tmp/Agent.md"),
            relative_path="Agent.md",
            directory="pages",
            title="Agent",
            role="knowledge_page",
            entities=[f"entity-{index}" for index in range(16)],
            summary="Line one.\n\nLine two.",
            claim_points=[f"claim {index}" for index in range(10)],
            relations=[
                {"subject": "Agent Loop", "predicate": "uses", "object": "Tool Execution", "claim": "C1"},
                {"subject": "Agent Loop", "predicate": "uses", "object": "Tool Execution", "claim": "C1"},
            ],
            outbound_links=[f"Linked-{index}.md" for index in range(14)],
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
        self.assertEqual(candidate["entities"], page.entities)
        self.assertEqual(candidate["claim_points"], page.claim_points)
        self.assertEqual(candidate["relations"], [{"subject": "Agent Loop", "predicate": "uses", "object": "Tool Execution", "claim": "C1"}])
        self.assertEqual(candidate["outbound_links"], page.outbound_links)
        self.assertGreater(context.stats["page_plan_profile_chars"], 0)

    def test_graph_first_candidates_use_atom_entities_before_text_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "pages").mkdir(parents=True)
            _write_page(
                vault / "wiki" / "pages" / "Graph-Candidate.md",
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
                entities=[
                    KnowledgeAtomObject(object_type="knowledge_object", name="GraphOnlyEntity"),
                    KnowledgeAtomObject(object_type="knowledge_object", name="Graph Candidate"),
                ],
                claims=[
                    KnowledgeClaim(
                        id="claim_graph_only",
                        claim="GraphOnlyEntity is related to Graph Candidate.",
                        claim_type="assessment",
                        evidence=[
                            KnowledgeEvidenceSpan(
                                source_digest_id="sd_graph_only",
                                source_path="raw/inbox/notes/graph-only.md",
                                excerpt="GraphOnlyEntity appears in the source.",
                            )
                        ],
                        entity_names=["GraphOnlyEntity", "Graph Candidate"],
                    )
                ],
                relations=[
                    KnowledgeRelation(
                        id="rel_graph_only",
                        subject=KnowledgeAtomObject(object_type="knowledge_object", name="GraphOnlyEntity"),
                        predicate="includes",
                        object=KnowledgeAtomObject(object_type="knowledge_object", name="Graph Candidate"),
                        source_claim_ids=["claim_graph_only"],
                    )
                ],
            )

            context = IngestContextProvider().build(vault, extract, knowledge_atom_batch=atom_batch)

        self.assertEqual(context.candidates[0].path, "Graph-Candidate.md")
        self.assertEqual(context.stats["graph_first_candidate_count"], 1)
        self.assertEqual(context.stats["pre_rerank_candidate_count"], 1)
        self.assertIn("GraphOnlyEntity", context.query)
        self.assertIn("graph_recall", context.candidates[0].matched_fields)

    def test_materialize_cache_is_local_and_clearable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "pages").mkdir(parents=True)
            page = vault / "wiki" / "pages" / "Agent.md"
            page.write_text("# Agent\n\nOld content.", encoding="utf-8")
            provider = IngestContextProvider()
            page_plan = WikiPagePlan(
                operations=[
                    WikiPageOperation(
                        action="update",
                        target_page="Agent.md",
                        page_dir="pages",
                        title="Agent",
                        knowledge_object="Agent",
                        selected_claim_ids=["claim_agent"],
                        source_digest_ids=["sd_agent"],
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
            (vault / "wiki" / "pages").mkdir(parents=True)
            _write_page(
                vault / "wiki" / "pages" / "Target.md",
                "# Target\n\n## Summary\n\nTarget summary.\n\n## Claims\n\n- C1: **Target** has existing body.\n\n## Synthesis\n\nExisting target body.",
            )
            _write_page(
                vault / "wiki" / "pages" / "Related.md",
                "# Related\n\n## Summary\n\nRelated summary.\n\n## Claims\n\n- C1: **Related** provides context.\n\n## Synthesis\n\nRelated body should not be passed in full.",
            )
            _write_page(
                vault / "wiki" / "pages" / "Candidate.md",
                "# Candidate\n\n## Summary\n\nCandidate summary.\n\n## Claims\n\n- C1: **Candidate** is a broad match.\n\n## Synthesis\n\nCandidate body should not enter context.",
            )
            page_plan = WikiPagePlan(
                operations=[
                    WikiPageOperation(
                        action="update",
                        target_page="Target.md",
                        page_dir="pages",
                        title="Target",
                        knowledge_object="Target",
                        selected_claim_ids=["claim_target"],
                        source_digest_ids=["sd_target"],
                        candidate_pages=[
                            {
                                "path": "Related.md",
                                "title": "Related",
                                "match_reason": "Related background.",
                            },
                            {
                                "path": "Candidate.md",
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
        self.assertEqual(pages["Target.md"].context_role, "target")
        self.assertEqual(pages["Target.md"].content_kind, "full")
        self.assertIn("Existing target body", pages["Target.md"].content)
        self.assertEqual(pages["Related.md"].context_role, "candidate")
        self.assertEqual(pages["Related.md"].content_kind, "profile")
        self.assertEqual(pages["Related.md"].summary, "Related summary.")
        self.assertNotIn("Related body should not be passed in full", pages["Related.md"].content)
        self.assertEqual(pages["Candidate.md"].context_role, "candidate")
        self.assertEqual(pages["Candidate.md"].content_kind, "profile")
        self.assertEqual(pages["Candidate.md"].content, "")
        self.assertEqual(context.stats["full_body_pages"], 1)
        self.assertEqual(context.stats["excerpt_pages"], 0)
        self.assertEqual(context.stats["profile_only_pages"], 2)
        self.assertEqual(context.stats["context_policy"], "target_full_related_excerpt_candidate_profile")

    def test_materialize_uses_highest_context_role_for_duplicate_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "pages").mkdir(parents=True)
            _write_page(vault / "wiki" / "pages" / "Agent.md", "# Agent\n\n## Summary\n\nAgent summary.\n\n## Synthesis\n\nFull target body.")
            page_plan = WikiPagePlan(
                operations=[
                    WikiPageOperation(
                        action="update",
                        target_page="Agent",
                        page_dir="pages",
                        title="Agent",
                        knowledge_object="Agent",
                        selected_claim_ids=["claim_agent"],
                        source_digest_ids=["sd_agent"],
                        candidate_pages=[
                            {
                                "path": "Agent.md",
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
