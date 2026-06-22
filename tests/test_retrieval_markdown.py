from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.retrieval.markdown import (
    SearchPage,
    build_inbound_paths,
    collect_search_pages,
    expand_related_pages,
    graph_relevance_boost,
    query_terms,
    score_pages,
)


class MarkdownRetrievalTests(unittest.TestCase):
    def test_query_terms_support_cjk_bigrams_and_trigrams(self) -> None:
        terms = query_terms("注意力机制")

        self.assertIn("注意力机制", terms)
        self.assertIn("注意", terms)
        self.assertIn("注意力", terms)

    def test_query_terms_filters_cjk_question_noise(self) -> None:
        terms = query_terms("Agent Loop 是什么？请基于我的知识库回答")

        self.assertIn("agent", terms)
        self.assertIn("loop", terms)
        self.assertNotIn("是什么", terms)
        self.assertNotIn("什么", terms)
        self.assertNotIn("知识库", terms)

    def test_collect_and_score_pages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            concepts = vault / "concepts"
            concepts.mkdir()
            (concepts / "Attention.md").write_text(
                "---\ntype: concept\nstatus: draft\ntags: attention, transformer\n---\n"
                "# Attention\n\n## Summary\n\nAttention weights tokens.\n\n## Key Points\n\n- Transformer uses attention.\n",
                encoding="utf-8",
            )

            pages = collect_search_pages(vault)
            scored = score_pages(pages, query_terms("attention transformer"), "attention transformer")

        self.assertEqual(len(pages), 1)
        self.assertIn("concepts/Attention.md", scored)
        self.assertIn("title", scored["concepts/Attention.md"].matched_fields)

    def test_collect_search_pages_supports_unified_root_pages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            pages_root = vault / "pages"
            pages_root.mkdir()
            (pages_root / "Agent-Loop.md").write_text(
                "---\npage_kind: concept\nfacets: agent_architecture\n---\n"
                "# Agent Loop\n\n## Summary\n\nA unified root page about agent loops.\n",
                encoding="utf-8",
            )

            pages = collect_search_pages(vault)
            scored = score_pages(pages, query_terms("agent loop"), "agent loop")

        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0].relative_path, "Agent-Loop.md")
        self.assertEqual(pages[0].directory, "pages")
        self.assertEqual(pages[0].page_kind, "concept")
        self.assertIn("agent_architecture", pages[0].facets)
        self.assertIn("Agent-Loop.md", scored)

    def test_bm25_prefers_page_identity_over_repeated_body_mentions(self) -> None:
        title_page = _page(
            "concepts/Agent-Loop.md",
            title="Agent Loop",
            summary="A maintained page about agent loop control.",
            body="Short canonical page.",
        )
        noisy_page = _page(
            "concepts/Noisy.md",
            title="Misc Notes",
            summary="Loose notes.",
            body="agent loop " * 80,
        )

        scored = score_pages([noisy_page, title_page], query_terms("agent loop"), "agent loop")
        ranked = sorted(scored.values(), key=lambda item: item.score, reverse=True)

        self.assertEqual(ranked[0].page.relative_path, "concepts/Agent-Loop.md")
        self.assertIn("title", ranked[0].matched_fields)

    def test_collect_search_pages_skips_maintenance_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "maintenance").mkdir()
            (vault / "maintenance" / "lint_run_report_20260521_123244.md").write_text(
                "# Lint Run Report\n\nRuntime maintenance artifact.",
                encoding="utf-8",
            )

            pages = collect_search_pages(vault)

        self.assertEqual(pages, [])

    def test_related_pages_expand_scored_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            concepts = vault / "concepts"
            concepts.mkdir()
            (concepts / "A.md").write_text(
                "# A\n\n## Summary\n\nAlpha topic.\n\n## Related Pages\n\n- [[concepts/B|B]]\n",
                encoding="utf-8",
            )
            (concepts / "B.md").write_text("# B\n\nBeta neighbor.", encoding="utf-8")

            pages = collect_search_pages(vault)
            scored = score_pages(pages, query_terms("Alpha"), "Alpha")
            expanded = expand_related_pages(scored, pages, "balanced")

        self.assertIn("concepts/B.md", expanded)
        self.assertIn("related_graph", expanded["concepts/B.md"].matched_fields)
        self.assertIn("outbound_link", expanded["concepts/B.md"].graph_reasons)

    def test_related_pages_expand_backlinks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            concepts = vault / "concepts"
            concepts.mkdir()
            (concepts / "A.md").write_text("# A\n\nAlpha seed.", encoding="utf-8")
            (concepts / "B.md").write_text(
                "# B\n\nBeta backlink.\n\n## Related Pages\n\n- [[concepts/A|A]]\n",
                encoding="utf-8",
            )

            pages = collect_search_pages(vault)
            scored = score_pages(pages, query_terms("Alpha"), "Alpha")
            expanded = expand_related_pages(scored, pages, "balanced")

        self.assertIn("concepts/B.md", expanded)
        self.assertIn("backlink", expanded["concepts/B.md"].graph_reasons)

    def test_graph_relevance_boost_explains_shared_source_and_type_affinity(self) -> None:
        seed = _page("concepts/A.md", source="raw/a.md", directory="concepts", page_type="concept")
        candidate = _page("concepts/B.md", source="raw/a.md", directory="concepts", page_type="concept")

        boost, reasons = graph_relevance_boost(seed, candidate, 10)

        self.assertGreater(boost, 0)
        self.assertIn("shared_source", reasons)
        self.assertIn("type_affinity", reasons)

    def test_build_inbound_paths_deduplicates_sources(self) -> None:
        pages = [
            _page("concepts/A.md", related_pages=["concepts/B.md", "concepts/B.md"]),
            _page("concepts/C.md", related_pages=["concepts/B.md"]),
        ]

        inbound = build_inbound_paths(pages)

        self.assertEqual(inbound["concepts/B.md"], ["concepts/A.md", "concepts/C.md"])


def _page(
    relative_path: str,
    *,
    title: str | None = None,
    source: str | None = None,
    directory: str = "concepts",
    page_type: str = "concept",
    related_pages: list[str] | None = None,
    summary: str = "",
    body: str = "",
):
    return SearchPage(
        path=Path("/tmp") / relative_path,
        relative_path=relative_path,
        directory=directory,
        title=title or Path(relative_path).stem,
        page_type=page_type,
        status="draft",
        source=source,
        tags=[],
        summary=summary,
        key_points=[],
        related_pages=related_pages or [],
        headings=[],
        body=body,
    )


if __name__ == "__main__":
    unittest.main()
