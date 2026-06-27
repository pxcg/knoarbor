from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.retrieval.markdown import SearchPage
from knoarbor.retrieval.page_graph import build_inbound_paths, graph_relevance_boost, related_candidate_paths


class PageGraphRetrievalTests(unittest.TestCase):
    def test_related_candidate_paths_uses_outbound_links_and_backlinks(self) -> None:
        seed = _page("A.md", outbound_links=["B.md"])
        inbound = {"A.md": ["C.md"], "B.md": ["A.md"]}

        candidates = related_candidate_paths(seed, inbound)

        self.assertEqual(candidates, ["B.md", "C.md"])

    def test_graph_relevance_boost_explains_outbound_link(self) -> None:
        seed = _page("A.md", directory="pages", outbound_links=["B.md"])
        candidate = _page("B.md", directory="pages")

        boost, reasons = graph_relevance_boost(seed, candidate, 10)

        self.assertGreater(boost, 0)
        self.assertIn("outbound_link", reasons)

    def test_build_inbound_paths_deduplicates_sources(self) -> None:
        pages = [
            _page("A.md", outbound_links=["B.md", "B.md"]),
            _page("C.md", outbound_links=["B.md"]),
        ]

        inbound = build_inbound_paths(pages)

        self.assertEqual(inbound["B.md"], ["A.md", "C.md"])


def _page(
    relative_path: str,
    *,
    title: str | None = None,
    directory: str = "pages",
    outbound_links: list[str] | None = None,
):
    return SearchPage(
        path=Path("/tmp") / relative_path,
        relative_path=relative_path,
        directory=directory,
        title=title or Path(relative_path).stem,
        role="knowledge_page",
        entities=[],
        summary="",
        claim_points=[],
        outbound_links=outbound_links or [],
        headings=[],
        body="",
    )


if __name__ == "__main__":
    unittest.main()
