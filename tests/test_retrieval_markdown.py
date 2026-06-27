from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.retrieval.markdown import (
    SearchPage,
    collect_search_pages,
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
            pages_root = vault / "wiki" / "pages"
            pages_root.mkdir(parents=True)
            (pages_root / "Attention.md").write_text(
                "---\n---\n"
                "# Attention\n\n## Summary\n\nAttention weights tokens.\n\n## Claims\n\n- C1: [[Attention]] weights [[Token]] context.\n\n## Entities\n\n- [[Attention]]\n- [[Transformer]]\n",
                encoding="utf-8",
            )

            pages = collect_search_pages(vault)
            scored = score_pages(pages, query_terms("attention transformer"), "attention transformer")

        self.assertEqual(len(pages), 1)
        self.assertIn("Attention.md", scored)
        self.assertIn("title", scored["Attention.md"].matched_fields)

    def test_collect_search_pages_extracts_relation_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            pages_root = vault / "wiki" / "pages"
            pages_root.mkdir(parents=True)
            (pages_root / "Agent-Loop.md").write_text(
                "# Agent Loop\n\n"
                "## Summary\n\nAgent Loop coordinates tool execution.\n\n"
                "## Relations\n\n"
                "| Subject | Predicate | Object | Based on |\n"
                "|---|---|---|---|\n"
                "| [[Agent Loop]] | coordinates | [[Tool Execution]] | C1 |\n",
                encoding="utf-8",
            )

            pages = collect_search_pages(vault)

        self.assertEqual(
            pages[0].relations,
            [{"subject": "Agent Loop", "predicate": "coordinates", "object": "Tool Execution", "claim": "C1"}],
        )

    def test_collect_search_pages_supports_unified_root_pages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            pages_root = vault / "wiki" / "pages"
            pages_root.mkdir(parents=True)
            (pages_root / "Agent-Loop.md").write_text(
                "# Agent Loop\n\n## Summary\n\nA unified root page about agent loops.\n",
                encoding="utf-8",
            )

            pages = collect_search_pages(vault)
            scored = score_pages(pages, query_terms("agent loop"), "agent loop")

        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0].relative_path, "Agent-Loop.md")
        self.assertEqual(pages[0].directory, "pages")
        self.assertEqual(pages[0].role, "knowledge_page")
        self.assertIn("Agent-Loop.md", scored)

    def test_bm25_prefers_page_identity_over_repeated_body_mentions(self) -> None:
        title_page = _page(
            "Agent-Loop.md",
            directory="pages",
            title="Agent Loop",
            summary="A maintained page about agent loop control.",
            body="Short canonical page.",
        )
        noisy_page = _page(
            "Noisy.md",
            directory="pages",
            title="Misc Notes",
            summary="Loose notes.",
            body="agent loop " * 80,
        )

        scored = score_pages([noisy_page, title_page], query_terms("agent loop"), "agent loop")
        ranked = sorted(scored.values(), key=lambda item: item.score, reverse=True)

        self.assertEqual(ranked[0].page.relative_path, "Agent-Loop.md")
        self.assertIn("title", ranked[0].matched_fields)

    def test_collect_search_pages_skips_maintenance_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "maintenance" / "reports" / "lint").mkdir(parents=True)
            (vault / "maintenance" / "reports" / "lint" / "lint_run_report_20260521_123244.md").write_text(
                "# Lint Run Report\n\nRuntime maintenance artifact.",
                encoding="utf-8",
            )

            pages = collect_search_pages(vault)

        self.assertEqual(pages, [])

def _page(
    relative_path: str,
    *,
    title: str | None = None,
    directory: str = "pages",
    outbound_links: list[str] | None = None,
    summary: str = "",
    body: str = "",
):
    return SearchPage(
        path=Path("/tmp") / relative_path,
        relative_path=relative_path,
        directory=directory,
        title=title or Path(relative_path).stem,
        role="knowledge_page",
        entities=[],
        summary=summary,
        claim_points=[],
        outbound_links=outbound_links or [],
        headings=[],
        body=body,
    )


if __name__ == "__main__":
    unittest.main()
