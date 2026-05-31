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
                    obsidian_vault_path=str(vault),
                    query="agent loop",
                    mode="balanced",
                    page_dirs=["concepts"],
                    max_results=5,
                    include_related=True,
                    record_query=False,
                )
            )

        match_kinds = {result.path: result.match_kind for result in response.results}
        self.assertEqual(response.schema_version, "wiki_query.v1")
        self.assertEqual(match_kinds["concepts/Agent-Loop.md"], "direct")
        self.assertEqual(match_kinds["entities/OpenClaw.md"], "related")
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
        self.assertEqual(response.trace["gap_count"], 0)
        self.assertIn("Match origin: related", response.context_pack)

    def test_full_query_context_returns_complete_page_body_without_pack_truncation(self) -> None:
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
                    obsidian_vault_path=str(vault),
                    query="agent loop",
                    context_format="full",
                    max_context_chars=1000,
                    record_query=False,
                )
            )

        self.assertIn(long_body.strip(), response.context_pack)
        self.assertEqual(response.stats["context_format"], "full")
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
                    obsidian_vault_path=str(vault),
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
                obsidian_vault_path=str(vault),
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
