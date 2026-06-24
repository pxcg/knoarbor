from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.retrieval.markdown import SearchPage
from knoarbor.retrieval.page_graph import build_inbound_paths, graph_relevance_boost, related_candidate_paths


class PageGraphRetrievalTests(unittest.TestCase):
    def test_related_candidate_paths_uses_outbound_links_and_backlinks(self) -> None:
        seed = _page("concepts/A.md", related_pages=["concepts/B.md"])
        inbound = {"concepts/A.md": ["concepts/C.md"], "concepts/B.md": ["concepts/A.md"]}

        candidates = related_candidate_paths(seed, inbound)

        self.assertEqual(candidates, ["concepts/B.md", "concepts/C.md"])

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
        summary="",
        key_points=[],
        related_pages=related_pages or [],
        headings=[],
        body="",
    )


if __name__ == "__main__":
    unittest.main()
