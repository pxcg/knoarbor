from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.core.wiki_lists import merge_unique_items
from knoarbor.retrieval.wiki_links import (
    replace_wikilink_targets,
    resolve_wikilink_target,
    sanitize_unresolved_wikilinks,
)


class WikiLinksRetrievalTests(unittest.TestCase):
    def test_merge_unique_items_prefers_aliased_wikilinks(self) -> None:
        merged = merge_unique_items(["[[Agent]]"], ["[[Agent|Agent Loop]]"])

        self.assertEqual(merged, ["[[Agent|Agent Loop]]"])

    def test_replace_wikilink_targets_preserves_heading_suffix(self) -> None:
        updated, replacements = replace_wikilink_targets(
            "See [[Old Page#Section|old section]] and [[Other]].",
            "Old Page",
            "New Page",
            "new section",
        )

        self.assertEqual(replacements, 1)
        self.assertIn("[[New Page#Section|new section]]", updated)
        self.assertIn("[[Other]]", updated)

    def test_resolve_wikilink_target_by_heading(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            pages = vault / "wiki" / "pages"
            pages.mkdir(parents=True)
            (pages / "agent-loop.md").write_text("# Agent Loop\n\nbody", encoding="utf-8")

            resolved = resolve_wikilink_target(vault, "Agent Loop")

        self.assertEqual(resolved, "agent-loop.md")

    def test_sanitize_unresolved_wikilinks_preserves_resolved_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            pages = vault / "wiki" / "pages"
            pages.mkdir(parents=True)
            (pages / "Agent.md").write_text("# Agent\n\nbody", encoding="utf-8")

            updated, removed = sanitize_unresolved_wikilinks(
                vault,
                "See [[Agent|Agent]] and [[Missing Concept|missing]].",
            )

        self.assertIn("[[Agent|Agent]]", updated)
        self.assertIn("missing", updated)
        self.assertNotIn("[[Missing Concept|missing]]", updated)
        self.assertEqual(removed, ["Missing Concept"])


if __name__ == "__main__":
    unittest.main()
