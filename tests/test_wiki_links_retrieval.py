from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.core.wiki_lists import merge_unique_items
from knoarbor.retrieval.wiki_links import (
    add_related_links,
    replace_wikilink_targets,
    resolve_wikilink_target,
    sanitize_unresolved_wikilinks,
)


class WikiLinksRetrievalTests(unittest.TestCase):
    def test_merge_unique_items_prefers_aliased_wikilinks(self) -> None:
        merged = merge_unique_items(["[[concepts/Agent]]"], ["[[concepts/Agent|Agent Loop]]"])

        self.assertEqual(merged, ["[[concepts/Agent|Agent Loop]]"])

    def test_replace_wikilink_targets_preserves_heading_suffix(self) -> None:
        updated, replacements = replace_wikilink_targets(
            "See [[Old Page#Section|old section]] and [[Other]].",
            "Old Page",
            "concepts/New Page",
            "new section",
        )

        self.assertEqual(replacements, 1)
        self.assertIn("[[concepts/New Page#Section|new section]]", updated)
        self.assertIn("[[Other]]", updated)

    def test_resolve_wikilink_target_by_heading(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            concepts = vault / "concepts"
            concepts.mkdir()
            (concepts / "agent-loop.md").write_text("# Agent Loop\n\nbody", encoding="utf-8")

            resolved = resolve_wikilink_target(vault, "Agent Loop")

        self.assertEqual(resolved, "concepts/agent-loop.md")

    def test_add_related_links_deduplicates_existing_links(self) -> None:
        content = "# Page\n\n## Related Pages\n\n- [[concepts/Agent]]\n"
        updated, changed = add_related_links(content, ["[[concepts/Agent|Agent]]", "[[entities/OpenClaw]]"])

        self.assertTrue(changed)
        self.assertIn("[[concepts/Agent|Agent]]", updated)
        self.assertIn("[[entities/OpenClaw]]", updated)
        self.assertEqual(updated.count("concepts/Agent"), 1)

    def test_sanitize_unresolved_wikilinks_preserves_resolved_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            concepts = vault / "concepts"
            concepts.mkdir()
            (concepts / "Agent.md").write_text("# Agent\n\nbody", encoding="utf-8")

            updated, removed = sanitize_unresolved_wikilinks(
                vault,
                "See [[concepts/Agent|Agent]] and [[Missing Concept|missing]].",
            )

        self.assertIn("[[concepts/Agent|Agent]]", updated)
        self.assertIn("missing", updated)
        self.assertNotIn("[[Missing Concept|missing]]", updated)
        self.assertEqual(removed, ["Missing Concept"])


if __name__ == "__main__":
    unittest.main()
