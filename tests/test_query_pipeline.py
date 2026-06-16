from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.pipelines import QueryPipeline, QueryPipelineRequest
from knoarbor.audit.query_ledger import append_query_record, build_query_trend
from knoarbor.core.schemas.wiki_query import WikiSearchRequest
from knoarbor.presenters.wiki_context import search_query
from knoarbor.services.wiki_search import WikiSearchService
from knoarbor.retrieval.index_provider import IndexRequest
from knoarbor.retrieval.markdown import SearchPage


class FakeIndexProvider:
    name = "fake"

    def __init__(self, pages: list[SearchPage]) -> None:
        self.pages = pages
        self.last_request: IndexRequest | None = None
        self.requests: list[IndexRequest] = []

    def collect(self, request: IndexRequest) -> list[SearchPage]:
        self.last_request = request
        self.requests.append(request)
        return self.pages


class QueryPipelineTests(unittest.TestCase):
    def test_query_pipeline_returns_ranked_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            concepts = vault / "concepts"
            concepts.mkdir()
            (concepts / "Agent-Loop.md").write_text(
                "# Agent Loop\n\n## Summary\n\nAgent loop uses observe, decide, act, and feedback.\n\n## Key Points\n\n- ReAct is a common loop pattern.\n",
                encoding="utf-8",
            )

            result = QueryPipeline().run(
                QueryPipelineRequest(
                    vault_path=vault,
                    query="agent loop",
                    limit=3,
                )
            )

        self.assertEqual(result.retrieval_mode, "machine_hybrid_balanced")
        self.assertEqual(result.matches[0].page.relative_path, "concepts/Agent-Loop.md")
        self.assertIn("title", result.matches[0].matched_terms)
        self.assertEqual(result.stats["index_provider"], "machine")
        self.assertIn("title", result.stats["field_weights"])
        self.assertGreaterEqual(result.stats["direct_match_count"], 1)
        self.assertEqual(result.stats["returned_count"], 1)

    def test_query_pipeline_reads_machine_index_pages_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            concepts = vault / "pages" / "concepts"
            concepts.mkdir(parents=True)
            (concepts / "Agent-Loop.md").write_text(
                "# Agent Loop\n\n## Summary\n\nAgent loop uses reasoning and tool calls.\n",
                encoding="utf-8",
            )

            result = QueryPipeline().run(
                QueryPipelineRequest(
                    vault_path=vault,
                    query="agent loop",
                    limit=3,
                )
            )

        self.assertEqual(result.matches[0].page.relative_path, "concepts/Agent-Loop.md")
        self.assertIn("tool calls", result.matches[0].page.body)

    def test_query_pipeline_filters_page_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            (vault / "entities").mkdir()
            (vault / "concepts" / "Agent.md").write_text("# Agent Concept\n\nLoop pattern.", encoding="utf-8")
            (vault / "entities" / "Agent.md").write_text("# Agent Entity\n\nNamed product.", encoding="utf-8")

            result = QueryPipeline().run(
                QueryPipelineRequest(
                    vault_path=vault,
                    query="agent",
                    page_dirs=["entities"],
                    limit=5,
                )
            )

        self.assertEqual([item.page.relative_path for item in result.matches], ["entities/Agent.md"])
        self.assertEqual(result.stats["page_count"], 1)

    def test_query_pipeline_uses_index_provider_boundary(self) -> None:
        page = SearchPage(
            path=Path("/tmp/concepts/Agent.md"),
            relative_path="concepts/Agent.md",
            directory="concepts",
            title="Agent",
            page_type="concept",
            status="draft",
            source=None,
            tags=["agent"],
            summary="Agent loop summary.",
            key_points=["Loop control."],
            related_pages=[],
            headings=["Summary"],
            body="Agent loop body.",
        )
        provider = FakeIndexProvider([page])

        result = QueryPipeline(index_provider=provider).run(
            QueryPipelineRequest(
                vault_path=Path("/tmp"),
                query="agent loop",
                page_dirs=["concepts"],
                include_related=False,
            )
        )

        self.assertEqual(result.stats["index_provider"], "fake")
        self.assertEqual(provider.last_request.page_dirs, ["concepts"])
        self.assertEqual(result.matches[0].page.relative_path, "concepts/Agent.md")

    def test_query_response_marks_cross_directory_related_expansion_by_origin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            (vault / "entities").mkdir()
            (vault / "concepts" / "Agent-Loop.md").write_text(
                "# Agent Loop\n\n"
                "## Summary\n\nAgent loop uses repeated reasoning and tool calls.\n\n"
                "## Related Pages\n\n- [[entities/OpenClaw|OpenClaw]]\n",
                encoding="utf-8",
            )
            (vault / "entities" / "OpenClaw.md").write_text(
                "# OpenClaw\n\n"
                "## Summary\n\nA local coding system.\n",
                encoding="utf-8",
            )

            response = search_query(
                WikiSearchRequest(
                    vault_path=str(vault),
                    query="agent loop",
                    mode="balanced",
                    page_dirs=["concepts"],
                    max_results=5,
                    include_related=True,
                    record_query=False,
                )
            )

        match_kinds = {result.path: result.match_kind for result in response.results}
        roles = {result.path: result.role for result in response.results}
        self.assertEqual(response.schema_version, "wiki_query.v1")
        self.assertEqual(match_kinds["concepts/Agent-Loop.md"], "direct")
        self.assertEqual(match_kinds["entities/OpenClaw.md"], "related")
        self.assertEqual(roles["concepts/Agent-Loop.md"], "primary")
        self.assertEqual(roles["entities/OpenClaw.md"], "supporting")
        self.assertEqual([page.path for page in response.primary_pages], ["concepts/Agent-Loop.md"])
        self.assertEqual([page.path for page in response.supporting_pages], ["entities/OpenClaw.md"])
        self.assertEqual(response.source_pages, [])
        related = next(result for result in response.results if result.path == "entities/OpenClaw.md")
        self.assertIn("related_graph", related.matched_fields)
        self.assertEqual(response.stats["page_count"], 1)
        self.assertEqual(response.stats["direct_page_count"], 1)
        self.assertEqual(response.stats["graph_page_count"], 2)
        self.assertEqual(response.trace["schema_version"], "query_trace.v1")
        self.assertEqual(response.trace["initial_scope_dirs"], ["concepts"])
        self.assertEqual(response.trace["expanded_scope_dirs"], ["concepts", "entities"])
        self.assertEqual(response.trace["related_seed_pages"], ["concepts/Agent-Loop.md"])
        self.assertEqual(response.trace["related_result_paths"], ["entities/OpenClaw.md"])
        self.assertEqual(response.trace["returned_count"], 2)
        self.assertEqual(response.trace["origin_counts"], {"direct": 1, "related": 1})
        self.assertEqual(response.trace["role_counts"], {"primary": 1, "supporting": 1, "source": 0})
        self.assertEqual(response.trace["gap_count"], 0)
        self.assertEqual(response.answer_scope.kind, "narrow")
        self.assertEqual(response.answer_set.kind, "single_page")
        self.assertEqual(response.answer_set.primary_paths, ["concepts/Agent-Loop.md"])
        self.assertEqual(response.answer_set.supporting_paths, ["entities/OpenClaw.md"])
        self.assertEqual(response.evidence_coverage.primary_count, 1)
        self.assertIn("Match origin: related", response.context_pack)

    def test_broad_query_builds_multi_page_answer_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            (vault / "entities").mkdir()
            (vault / "concepts" / "Agent-Loop.md").write_text(
                "# Agent Loop\n\n## Summary\n\nAgent loop explains reasoning and tool execution patterns.\n",
                encoding="utf-8",
            )
            (vault / "concepts" / "Session-Memory.md").write_text(
                "# Session Memory\n\n## Summary\n\nSession memory supports long-running agent loops and context compaction.\n",
                encoding="utf-8",
            )
            (vault / "entities" / "OpenClaw.md").write_text(
                "# OpenClaw\n\n## Summary\n\nOpenClaw implements production agent loop infrastructure.\n",
                encoding="utf-8",
            )

            response = search_query(
                WikiSearchRequest(
                    vault_path=str(vault),
                    query="Agent Loop 架构和模式有哪些",
                    mode="balanced",
                    max_results=5,
                    record_query=False,
                )
            )

        self.assertEqual(response.answer_scope.kind, "broad")
        self.assertEqual(response.answer_set.kind, "multi_page")
        self.assertEqual(response.primary_pages[0].path, response.answer_set.primary_paths[0])
        self.assertGreaterEqual(len(response.answer_set.supporting_paths), 1)
        self.assertGreaterEqual(response.evidence_coverage.supporting_count, 1)

    def test_context_pack_orders_answer_roles_before_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            (vault / "sources").mkdir()
            (vault / "concepts" / "Agent-Loop.md").write_text(
                "# Agent Loop\n\n"
                "## Summary\n\nAgent loop explains reasoning and tool execution.\n",
                encoding="utf-8",
            )
            (vault / "sources" / "Agent-Loop-Source.md").write_text(
                "# Agent Loop Source\n\n"
                "## Summary\n\nAgent loop source digest.\n\n"
                "## Key Points\n\n- Agent loop source digest.\n\n"
                + "agent loop source digest " * 80,
                encoding="utf-8",
            )

            response = search_query(
                WikiSearchRequest(
                    vault_path=str(vault),
                    query="Agent Loop 是什么",
                    mode="balanced",
                    max_results=5,
                    record_query=False,
                )
            )

        self.assertEqual(response.primary_pages[0].path, "concepts/Agent-Loop.md")
        self.assertEqual([page.path for page in response.source_pages], ["sources/Agent-Loop-Source.md"])
        self.assertEqual(response.answer_set.source_paths, [])
        primary_index = response.context_pack.index("Agent Loop (concepts/Agent-Loop.md")
        source_index = response.context_pack.index("Agent Loop Source (sources/Agent-Loop-Source.md")
        self.assertLess(primary_index, source_index)
        self.assertNotIn("是什么", response.evidence_coverage.missing_facets)
        self.assertIn("Source digest pages are kept for provenance.", response.answer_set.reason)

    def test_source_query_can_use_source_digest_as_primary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            (vault / "sources").mkdir()
            (vault / "concepts" / "Agent-Loop.md").write_text(
                "# Agent Loop\n\n## Summary\n\nAgent loop explains reasoning and tool execution.\n",
                encoding="utf-8",
            )
            (vault / "sources" / "Agent-Loop-Source.md").write_text(
                "# Agent Loop Source\n\n## Summary\n\nSource digest for agent loop notes.\n",
                encoding="utf-8",
            )

            response = search_query(
                WikiSearchRequest(
                    vault_path=str(vault),
                    query="Agent Loop 的来源是什么",
                    mode="balanced",
                    max_results=5,
                    record_query=False,
                )
            )

        self.assertEqual(response.primary_pages[0].path, "sources/Agent-Loop-Source.md")
        self.assertEqual(response.answer_set.stop_reason, "source_intent_selected")

    def test_redundant_candidate_is_reported_without_entering_answer_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            (vault / "concepts" / "Agent-Loop.md").write_text(
                "# Agent Loop\n\n## Summary\n\nAgent loop explains reasoning and tool execution patterns.\n\n## Tags\n\n- agent\n- loop\n",
                encoding="utf-8",
            )
            (vault / "concepts" / "Agent-Loop-Notes.md").write_text(
                "# Agent Loop Notes\n\n## Summary\n\nAgent loop explains reasoning and tool execution patterns.\n\n## Tags\n\n- agent\n- loop\n",
                encoding="utf-8",
            )
            (vault / "entities" ).mkdir()
            (vault / "entities" / "OpenClaw.md").write_text(
                "# OpenClaw\n\n## Summary\n\nOpenClaw implements production agent loop infrastructure.\n\n## Tags\n\n- implementation\n",
                encoding="utf-8",
            )

            response = search_query(
                WikiSearchRequest(
                    vault_path=str(vault),
                    query="Agent Loop 架构和模式有哪些",
                    mode="balanced",
                    max_results=6,
                    record_query=False,
                )
            )

        rejected_paths = {item.path for item in response.rejected_candidates}
        self.assertIn("concepts/Agent-Loop-Notes.md", rejected_paths)
        self.assertNotIn("concepts/Agent-Loop-Notes.md", response.answer_set.primary_paths)
        self.assertIn("rejected_candidates", response.trace)

    def test_query_context_preserves_answer_bearing_wiki_pages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            (vault / "entities").mkdir()
            (vault / "concepts" / "Agent-Loop.md").write_text(
                "# Agent Loop\n\n"
                "## Summary\n\nAgent loop summary.\n\n"
                "## Answer\n\n"
                "Primary maintained page body should stay intact for answer synthesis.\n\n"
                "## Related Pages\n\n- [[entities/OpenClaw|OpenClaw]]\n",
                encoding="utf-8",
            )
            (vault / "entities" / "OpenClaw.md").write_text(
                "# OpenClaw\n\n"
                "## Summary\n\nOpenClaw supports production agent loop execution.\n\n"
                "## Answer\n\n"
                "Supporting implementation details should remain structured evidence, not full page body.\n",
                encoding="utf-8",
            )

            response = search_query(
                WikiSearchRequest(
                    vault_path=str(vault),
                    query="agent loop",
                    mode="balanced",
                    max_results=5,
                    include_related=True,
                    record_query=False,
                )
            )

        primary = response.primary_pages[0]
        supporting = next(result for result in response.results if result.path == "entities/OpenClaw.md")
        self.assertIn("Primary maintained page body should stay intact", primary.content or "")
        self.assertIn("Full page body:", response.context_pack)
        self.assertIn("Primary maintained page body should stay intact", response.context_pack)
        self.assertIn("Supporting implementation details should remain structured evidence", supporting.content or "")
        self.assertIn("OpenClaw supports production agent loop execution", response.context_pack)
        self.assertIn("Supporting implementation details should remain structured evidence", response.context_pack)

    def test_primary_page_body_is_preserved_even_when_context_budget_is_small(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            long_body = "Agent loop detail. " * 500
            (vault / "concepts" / "Agent-Loop.md").write_text(
                "# Agent Loop\n\n"
                "## Summary\n\nAgent loop summary.\n\n"
                "## Answer\n\n"
                f"{long_body}\n",
                encoding="utf-8",
            )

            response = search_query(
                WikiSearchRequest(
                    vault_path=str(vault),
                    query="agent loop",
                    max_context_chars=1000,
                    record_query=False,
                )
            )

        self.assertIn(long_body.strip(), response.context_pack)
        self.assertEqual(response.stats["context_strategy"], "page_first_primary_full")
        self.assertFalse(response.stats["context_pack_truncated"])
        self.assertFalse(response.results[0].content_truncated)

    def test_query_service_writes_optional_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            (vault / "concepts" / "Agent-Loop.md").write_text(
                "# Agent Loop\n\n"
                "## Summary\n\nAgent loop uses repeated reasoning and tool calls.\n\n"
                "## Key Points\n\n- ReAct is a common loop pattern.\n",
                encoding="utf-8",
            )

            response = WikiSearchService().search(
                WikiSearchRequest(
                    vault_path=str(vault),
                    query="agent loop",
                    record_query=False,
                    write_report=True,
                )
            )

            report_path = vault / str(response.stats["query_report_path"])
            self.assertTrue(report_path.exists())
            report = report_path.read_text(encoding="utf-8")
            self.assertIn("# Query Report", report)
            self.assertIn("## Answer Guidance", report)
            self.assertIn("concepts/Agent-Loop.md", report)

    def test_query_trend_summarizes_repeated_gaps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            request = WikiSearchRequest(
                vault_path=str(vault),
                query="missing topic",
                record_query=False,
            )
            response = search_query(request)

            append_query_record(vault, request, response)
            append_query_record(vault, request, response)
            trend = build_query_trend(vault)

        self.assertEqual(trend["sample_size"], 2)
        self.assertEqual(trend["no_result_count"], 2)
        self.assertEqual(trend["repeated_gap_queries"], [{"query": "missing topic", "count": 2}])


if __name__ == "__main__":
    unittest.main()
