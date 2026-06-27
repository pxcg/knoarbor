from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.pipelines import QueryPipeline, QueryPipelineRequest
from knoarbor.audit.query_ledger import append_query_record, build_query_trend
from knoarbor.core.schemas.knowledge_atoms import KnowledgeAtomBatch, KnowledgeClaim, KnowledgeEvidenceSpan
from knoarbor.core.schemas.wiki_query import WikiSearchRequest
from knoarbor.presenters.wiki_context import search_query
from knoarbor.services.wiki_search import WikiSearchService
from knoarbor.retrieval.index_provider import IndexRequest
from knoarbor.retrieval.markdown import SearchPage
from knoarbor.storage.knowledge_atom_index import KnowledgeAtomPageRef, upsert_knowledge_atom_batch


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
            pages = vault / "wiki" / "pages"
            pages.mkdir(parents=True)
            sources = vault / "wiki" / "sources"
            sources.mkdir()
            (pages / "Agent-Loop.md").write_text(
                "# Agent Loop\n\n## Summary\n\nAgent loop uses observe, decide, act, and feedback.\n\n## Claims\n\n- C1: ReAct is a common loop pattern.\n",
                encoding="utf-8",
            )

            result = QueryPipeline().run(
                QueryPipelineRequest(
                    vault_path=vault,
                    query="agent loop",
                    limit=3,
                )
            )

        self.assertEqual(result.retrieval_mode, "machine_graph_led_bm25_balanced")
        self.assertEqual(result.matches[0].page.relative_path, "Agent-Loop.md")
        self.assertIn("title", result.matches[0].matched_terms)
        self.assertEqual(result.stats["index_provider"], "machine")
        self.assertIn("title", result.stats["field_weights"])
        self.assertGreaterEqual(result.stats["direct_match_count"], 1)
        self.assertEqual(result.stats["returned_count"], 1)

    def test_query_pipeline_reads_machine_index_pages_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            pages = vault / "wiki" / "pages"
            pages.mkdir(parents=True)
            (pages / "Agent-Loop.md").write_text(
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

        self.assertEqual(result.matches[0].page.relative_path, "Agent-Loop.md")
        self.assertIn("tool calls", result.matches[0].page.body)

    def test_query_pipeline_filters_page_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            pages = vault / "wiki" / "pages"
            sources = vault / "wiki" / "sources"
            pages.mkdir(parents=True)
            sources.mkdir(parents=True)
            (pages / "Agent.md").write_text("# Agent\n\nLoop pattern.", encoding="utf-8")
            (sources / "Agent-Source.md").write_text("# Agent Source\n\nNamed product source.", encoding="utf-8")

            result = QueryPipeline().run(
                QueryPipelineRequest(
                    vault_path=vault,
                    query="agent",
                    page_dirs=["sources"],
                    limit=5,
                )
            )

        self.assertEqual([item.page.relative_path for item in result.matches], ["sources/Agent-Source.md"])
        self.assertEqual(result.stats["page_count"], 1)

    def test_query_pipeline_filters_unified_page_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            pages = vault / "wiki" / "pages"
            pages.mkdir(parents=True)
            sources = vault / "wiki" / "sources"
            sources.mkdir()
            (pages / "Routing.md").write_text(
                "---\n"
                "---\n\n"
                "# Routing\n\n## Summary\n\nRouting plans agent tasks and selects tools.\n",
                encoding="utf-8",
            )
            (sources / "Routing-Source.md").write_text(
                "---\n"
                "---\n\n"
                "# Routing Source\n\n## Summary\n\nSource digest for routing notes.\n",
                encoding="utf-8",
            )
            (pages / "Memory.md").write_text(
                "---\n"
                "---\n\n"
                "# Memory\n\n## Summary\n\nMemory stores dialogue facts.\n",
                encoding="utf-8",
            )

            directory_result = QueryPipeline().run(
                QueryPipelineRequest(
                    vault_path=vault,
                    query="routing",
                    page_dirs=["pages"],
                    limit=5,
                )
            )
            source_result = QueryPipeline().run(
                QueryPipelineRequest(
                    vault_path=vault,
                    query="routing",
                    page_roles=["source_digest"],
                    limit=5,
                )
            )
            role_result = QueryPipeline().run(
                QueryPipelineRequest(
                    vault_path=vault,
                    query="routing",
                    page_roles=["knowledge_page"],
                    limit=5,
                )
            )

        self.assertEqual(
            {item.page.relative_path for item in directory_result.matches},
            {"Routing.md"},
        )
        self.assertEqual([item.page.relative_path for item in source_result.matches], ["sources/Routing-Source.md"])
        self.assertIn("Routing.md", [item.page.relative_path for item in role_result.matches])
        self.assertEqual(directory_result.stats["initial_scope_roles"], ["knowledge_page"])

    def test_query_pipeline_expands_results_through_machine_graph_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            pages = vault / "wiki" / "pages"
            pages.mkdir(parents=True)
            (pages / "Agent-Loop.md").write_text(
                "# Agent Loop\n\n"
                "## Summary\n\nAgent loop coordinates model reasoning.\n\n"
                "## Claims\n\n- C1: [[Agent Loop]] coordinates [[Tool Execution]].\n\n"
                "## Entities\n\n- [[Agent Loop]]\n- [[Tool Execution]]\n\n"
                "## Relations\n\n"
                "| Subject | Predicate | Object | Based on |\n"
                "|---|---|---|---|\n"
                "| [[Agent Loop]] | coordinates | [[Tool Execution]] | C1 |\n\n"
                "## Evidence\n\n"
                "| Claim | Source | Range | Basis | Confidence |\n"
                "|---|---|---|---|---|\n"
                "| C1 | sources/Agent-Loop-Source.md | section:loop | explicit source statement | high |\n\n"
                "## Synthesis\n\nAgent loop is the runtime control page.\n",
                encoding="utf-8",
            )
            (pages / "Tool-Execution.md").write_text(
                "# Tool Execution\n\n"
                "## Summary\n\nRuntime invocation and permission handling.\n\n"
                "## Claims\n\n- C1: [[Tool Execution]] executes approved tool calls.\n\n"
                "## Entities\n\n- [[Tool Execution]]\n",
                encoding="utf-8",
            )

            result = QueryPipeline().run(
                QueryPipelineRequest(
                    vault_path=vault,
                    query="agent loop",
                    limit=5,
                    include_related=True,
                )
            )

        paths = [item.page.relative_path for item in result.matches]
        expanded = next(item for item in result.matches if item.page.relative_path == "Tool-Execution.md")
        self.assertIn("Agent-Loop.md", paths)
        self.assertIn("Tool-Execution.md", paths)
        self.assertIn("graph_index", expanded.matched_fields)
        self.assertTrue(any(reason.startswith("relation:") or reason.startswith("shared_entity:") for reason in expanded.graph_reasons))
        self.assertIn("Agent-Loop.md", result.stats["graph_index_seed_pages"])
        self.assertIn("Tool-Execution.md", result.stats["graph_index_result_paths"])

    def test_query_pipeline_uses_index_provider_boundary(self) -> None:
        page = SearchPage(
            path=Path("/tmp/Agent.md"),
            relative_path="Agent.md",
            directory="pages",
            title="Agent",
            role="knowledge_page",
            entities=["agent"],
            summary="Agent loop summary.",
            claim_points=["Loop control."],
            outbound_links=[],
            headings=["Summary"],
            body="Agent loop body.",
        )
        provider = FakeIndexProvider([page])

        result = QueryPipeline(index_provider=provider).run(
            QueryPipelineRequest(
                vault_path=Path("/tmp"),
                query="agent loop",
                page_dirs=["pages"],
                include_related=False,
            )
        )

        self.assertEqual(result.stats["index_provider"], "fake")
        self.assertEqual(provider.last_request.page_dirs, ["pages"])
        self.assertEqual(result.matches[0].page.relative_path, "Agent.md")

    def test_query_response_marks_cross_directory_related_expansion_by_origin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "pages").mkdir(parents=True, exist_ok=True)
            (vault / "wiki" / "pages" / "Agent-Loop.md").write_text(
                "# Agent Loop\n\n"
                "## Summary\n\nAgent loop uses repeated reasoning and tool calls.\n\n"
                "## Claims\n\n- C1: [[Agent Loop]] relates to [[OpenClaw]].\n",
                encoding="utf-8",
            )
            (vault / "wiki" / "pages" / "OpenClaw.md").write_text(
                "# OpenClaw\n\n"
                "## Summary\n\nA local coding system.\n",
                encoding="utf-8",
            )

            response = search_query(
                WikiSearchRequest(
                    vault_path=str(vault),
                    query="agent loop",
                    mode="balanced",
                    page_dirs=["pages"],
                    max_results=5,
                    include_related=True,
                    record_query=False,
                )
            )

        match_kinds = {result.path: result.match_kind for result in response.results}
        roles = {result.path: result.role for result in response.results}
        self.assertEqual(response.schema_version, "wiki_query.v1")
        self.assertEqual(match_kinds["Agent-Loop.md"], "direct")
        self.assertEqual(match_kinds["OpenClaw.md"], "related")
        self.assertEqual(roles["Agent-Loop.md"], "primary")
        self.assertEqual(roles["OpenClaw.md"], "supporting")
        self.assertEqual([page.path for page in response.primary_pages], ["Agent-Loop.md"])
        self.assertEqual([page.path for page in response.supporting_pages], ["OpenClaw.md"])
        self.assertEqual(response.source_pages, [])
        related = next(result for result in response.results if result.path == "OpenClaw.md")
        self.assertIn("related_graph", related.matched_fields)
        self.assertEqual(response.stats["page_count"], 2)
        self.assertEqual(response.stats["direct_page_count"], 2)
        self.assertEqual(response.stats["graph_page_count"], 2)
        self.assertEqual(response.trace["schema_version"], "query_trace.v1")
        self.assertEqual(response.trace["initial_scope_dirs"], ["pages"])
        self.assertEqual(response.trace["expanded_scope_dirs"], ["pages"])
        self.assertEqual(response.trace["related_seed_pages"], ["Agent-Loop.md"])
        self.assertEqual(response.trace["related_result_paths"], ["OpenClaw.md"])
        self.assertEqual(response.trace["returned_count"], 2)
        self.assertEqual(response.trace["origin_counts"], {"direct": 1, "related": 1})
        self.assertEqual(response.trace["role_counts"], {"primary": 1, "supporting": 1, "source": 0})
        self.assertEqual(response.trace["gap_count"], 0)
        self.assertEqual(response.answer_scope.kind, "narrow")
        self.assertEqual(response.answer_set.kind, "single_page")
        self.assertEqual(response.answer_set.primary_paths, ["Agent-Loop.md"])
        self.assertEqual(response.answer_set.supporting_paths, ["OpenClaw.md"])
        self.assertEqual(response.evidence_coverage.primary_count, 1)
        self.assertIn("Match origin: related", response.context_pack)

    def test_broad_query_builds_multi_page_answer_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "pages").mkdir(parents=True, exist_ok=True)
            (vault / "wiki" / "pages" / "Agent-Loop.md").write_text(
                "# Agent Loop\n\n## Summary\n\nAgent loop explains reasoning and tool execution patterns.\n\n## Entities\n\n- [[Agent Loop]]\n",
                encoding="utf-8",
            )
            (vault / "wiki" / "pages" / "Session-Memory.md").write_text(
                "# Session Memory\n\n## Summary\n\nSession memory supports long-running agent loops and context compaction.\n\n## Entities\n\n- [[Agent Loop]]\n- [[Session Memory]]\n",
                encoding="utf-8",
            )
            (vault / "wiki" / "pages" / "OpenClaw.md").write_text(
                "# OpenClaw\n\n## Summary\n\nOpenClaw implements production agent loop infrastructure.\n\n## Entities\n\n- [[Agent Loop]]\n- [[OpenClaw]]\n",
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
            (vault / "wiki" / "pages").mkdir(parents=True)
            (vault / "wiki" / "sources").mkdir()
            (vault / "wiki" / "pages" / "Agent-Loop.md").write_text(
                "# Agent Loop\n\n"
                "## Summary\n\nAgent loop explains reasoning and tool execution.\n",
                encoding="utf-8",
            )
            (vault / "wiki" / "sources" / "Agent-Loop-Source.md").write_text(
                "# Agent Loop Source\n\n"
                "## Summary\n\nAgent loop source digest.\n\n"
                "## Claims\n\n- C1: Agent loop source digest.\n\n"
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

        self.assertEqual(response.primary_pages[0].path, "Agent-Loop.md")
        self.assertEqual([page.path for page in response.source_pages], ["sources/Agent-Loop-Source.md"])
        self.assertEqual(response.answer_set.source_paths, ["sources/Agent-Loop-Source.md"])
        primary_index = response.context_pack.index("Agent Loop (Agent-Loop.md")
        source_index = response.context_pack.index("Agent Loop Source (sources/Agent-Loop-Source.md")
        self.assertLess(primary_index, source_index)
        self.assertNotIn("是什么", response.evidence_coverage.missing_dimensions)
        self.assertIn("Source digest pages are kept for provenance.", response.answer_set.reason)

    def test_source_query_can_use_source_digest_as_primary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "pages").mkdir(parents=True)
            (vault / "wiki" / "sources").mkdir()
            (vault / "wiki" / "pages" / "Agent-Loop.md").write_text(
                "# Agent Loop\n\n## Summary\n\nAgent loop explains reasoning and tool execution.\n",
                encoding="utf-8",
            )
            (vault / "wiki" / "sources" / "Agent-Loop-Source.md").write_text(
                "# Agent Loop Source\n\n## Summary\n\nSource digest for Agent Loop provenance and 来源 notes.\n",
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
            (vault / "wiki" / "pages").mkdir(parents=True)
            (vault / "wiki" / "pages" / "Agent-Loop.md").write_text(
                "# Agent Loop\n\n## Summary\n\nAgent loop explains reasoning and tool execution patterns.\n\n## Entities\n\n- Agent Loop\n- Agent Control\n",
                encoding="utf-8",
            )
            (vault / "wiki" / "pages" / "Agent-Loop-Notes.md").write_text(
                "# Agent Loop Notes\n\n## Summary\n\nAgent loop explains reasoning and tool execution patterns.\n\n## Entities\n\n- Agent Loop\n- Agent Control\n",
                encoding="utf-8",
            )
            (vault / "wiki" / "pages").mkdir(parents=True, exist_ok=True)
            (vault / "wiki" / "pages" / "OpenClaw.md").write_text(
                "# OpenClaw\n\n## Summary\n\nOpenClaw implements production agent loop infrastructure.\n\n## Entities\n\n- OpenClaw\n",
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
        self.assertIn("Agent-Loop-Notes.md", rejected_paths)
        self.assertNotIn("Agent-Loop-Notes.md", response.answer_set.primary_paths)
        self.assertIn("rejected_candidates", response.trace)

    def test_query_context_preserves_answer_bearing_wiki_pages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "pages").mkdir(parents=True, exist_ok=True)
            (vault / "wiki" / "pages" / "Agent-Loop.md").write_text(
                "# Agent Loop\n\n"
                "## Summary\n\nAgent loop summary.\n\n"
                "## Synthesis\n\n"
                "Primary maintained page body should stay intact for answer synthesis.\n\n"
                "## Relations\n\n- [[Agent Loop]] | implemented by | [[OpenClaw]] | C1\n",
                encoding="utf-8",
            )
            (vault / "wiki" / "pages" / "OpenClaw.md").write_text(
                "# OpenClaw\n\n"
                "## Summary\n\nOpenClaw supports production agent loop execution.\n\n"
                "## Synthesis\n\n"
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
        supporting = next(result for result in response.results if result.path == "OpenClaw.md")
        self.assertIn("Primary maintained page body should stay intact", primary.content or "")
        self.assertIn("Full page body:", response.context_pack)
        self.assertIn("Primary maintained page body should stay intact", response.context_pack)
        self.assertIn("Supporting implementation details should remain structured evidence", supporting.content or "")
        self.assertIn("OpenClaw supports production agent loop execution", response.context_pack)
        self.assertIn("Supporting implementation details should remain structured evidence", response.context_pack)

    def test_query_results_include_page_atom_trace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "pages").mkdir(parents=True)
            (vault / "wiki" / "pages" / "Agent-Loop.md").write_text(
                "# Agent Loop\n\n"
                "## Summary\n\nAgent loop coordinates reasoning and tool execution.\n",
                encoding="utf-8",
            )
            batch = KnowledgeAtomBatch(
                source_digest_id="sd_agent_loop",
                claims=[
                    KnowledgeClaim(
                        id="claim_agent_loop_cycle",
                        claim="Agent loop coordinates reasoning and tool execution.",
                        claim_type="definition",
                        evidence=[
                            KnowledgeEvidenceSpan(
                                source_digest_id="sd_agent_loop",
                                source_path="raw/inbox/notes/agent.md",
                                excerpt="Agent loop coordinates reasoning and tool execution.",
                            )
                        ],
                    )
                ],
            )
            upsert_knowledge_atom_batch(
                vault,
                batch,
                [
                    KnowledgeAtomPageRef(
                        path="Agent-Loop.md",
                        source_digest_ids=["sd_agent_loop"],
                        atom_ids=["claim_agent_loop_cycle"],
                    )
                ],
            )

            response = search_query(
                WikiSearchRequest(
                    vault_path=str(vault),
                    query="agent loop",
                    record_query=False,
                )
            )

        self.assertEqual(response.results[0].atom_traces[0].atom_id, "claim_agent_loop_cycle")
        self.assertEqual(response.results[0].atom_traces[0].source_digest_id, "sd_agent_loop")
        self.assertEqual(response.stats["atom_trace_count"], 1)
        self.assertEqual(response.trace["atom_trace_counts"], {"Agent-Loop.md": 1})
        self.assertEqual(response.trace["top_matches"][0]["atom_trace_count"], 1)

    def test_primary_page_body_is_preserved_even_when_context_budget_is_small(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "wiki" / "pages").mkdir(parents=True)
            long_body = "Agent loop detail. " * 500
            (vault / "wiki" / "pages" / "Agent-Loop.md").write_text(
                "# Agent Loop\n\n"
                "## Summary\n\nAgent loop summary.\n\n"
                "## Synthesis\n\n"
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
            (vault / "wiki" / "pages").mkdir(parents=True)
            (vault / "wiki" / "pages" / "Agent-Loop.md").write_text(
                "# Agent Loop\n\n"
                "## Summary\n\nAgent loop uses repeated reasoning and tool calls.\n\n"
                "## Claims\n\n- C1: ReAct is a common loop pattern.\n",
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
            self.assertIn("## Response Guidance", report)
            self.assertIn("Agent-Loop.md", report)

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
