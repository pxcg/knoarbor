from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.retrieval.graph_led import GraphLedRetrievalRequest, GraphLedRetriever
from knoarbor.retrieval.index_provider import MarkdownIndexProvider
from knoarbor.storage import update_machine_index


class GraphLedRetrievalTests(unittest.TestCase):
    def test_bm25_does_not_add_pages_outside_graph_recall(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "pages").mkdir()
            (vault / "pages" / "Agent-Loop.md").write_text(
                "# Agent Loop\n\n## Summary\n\nAgent loop coordinates tool use.\n\n## Entities\n\n- [[Agent Loop]]\n",
                encoding="utf-8",
            )
            (vault / "pages" / "Noisy.md").write_text(
                "# Misc\n\n## Summary\n\nLoose notes.\n\n" + "agent loop " * 80,
                encoding="utf-8",
            )
            update_machine_index(vault)

            result = GraphLedRetriever(MarkdownIndexProvider()).retrieve(
                GraphLedRetrievalRequest(vault_path=vault, query="agent loop", limit=5)
            )

        self.assertEqual([item.page.relative_path for item in result.matches], ["Agent-Loop.md"])
        self.assertEqual(result.stats["bm25_reranked_count"], 1)

    def test_bm25_reranks_only_graph_recalled_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "pages").mkdir()
            (vault / "pages" / "Agent-Loop.md").write_text(
                "# Agent Loop\n\n"
                "## Summary\n\nAgent loop coordinates tool use.\n\n"
                "## Entities\n\n- [[Agent Loop]]\n\n"
                "## Relations\n\n"
                "| Subject | Predicate | Object | Based on |\n"
                "|---|---|---|---|\n"
                "| [[Agent Loop]] | uses | [[Tool Execution]] | C1 |\n",
                encoding="utf-8",
            )
            (vault / "pages" / "Tool-Execution.md").write_text(
                "# Tool Execution\n\n## Summary\n\nTool execution is a runtime stage for agent loop systems.\n\n## Entities\n\n- [[Tool Execution]]\n",
                encoding="utf-8",
            )
            update_machine_index(vault)

            result = GraphLedRetriever(MarkdownIndexProvider()).retrieve(
                GraphLedRetrievalRequest(vault_path=vault, query="tool execution", limit=5)
            )

        self.assertEqual(result.matches[0].page.relative_path, "Tool-Execution.md")
        self.assertEqual({item.page.relative_path for item in result.matches}, {"Agent-Loop.md", "Tool-Execution.md"})
        self.assertGreaterEqual(result.stats["graph_candidate_count"], 2)


if __name__ == "__main__":
    unittest.main()
