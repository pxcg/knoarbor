from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.retrieval.markdown import collect_search_pages, expand_related_pages, query_terms, score_pages


class MarkdownRetrievalTests(unittest.TestCase):
    def test_query_terms_support_cjk_bigrams_and_trigrams(self) -> None:
        terms = query_terms("注意力机制")

        self.assertIn("注意力机制", terms)
        self.assertIn("注意", terms)
        self.assertIn("注意力", terms)

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


if __name__ == "__main__":
    unittest.main()
