from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.storage import (
    available_title_path,
    normalize_source_digest_title,
    normalize_wiki_page_path,
    resolve_existing_by_hash,
    resolve_wiki_page,
    slugify_title,
)


class WikiPathsStorageTests(unittest.TestCase):
    def test_normalize_wiki_page_path_accepts_wikilinks(self) -> None:
        self.assertEqual(normalize_wiki_page_path("[[concepts/Agent|Agent]]"), "concepts/Agent.md")

    def test_resolve_wiki_page_blocks_invalid_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)

            with self.assertRaisesRegex(ValueError, "Invalid wiki page path"):
                resolve_wiki_page(vault, "../outside.md")

    def test_resolve_existing_by_hash_and_available_title_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            concepts = vault / "concepts"
            concepts.mkdir()
            existing = concepts / "Agent.md"
            existing.write_text("---\ncontent_hash: abc123\n---\n# Agent\n", encoding="utf-8")

            matched = resolve_existing_by_hash(vault, "concepts", "abc123")
            available = available_title_path(concepts, "Agent")

        self.assertEqual(matched, existing)
        self.assertEqual(available.name, "Agent-2.md")

    def test_slugify_title_removes_path_unsafe_characters(self) -> None:
        self.assertEqual(slugify_title("A/B: C?"), "AB-C")

    def test_slugify_title_removes_markdown_extension(self) -> None:
        self.assertEqual(slugify_title("LLM-Wiki.md"), "LLM-Wiki")
        self.assertEqual(slugify_title("Architecture.markdown"), "Architecture")

    def test_normalize_source_digest_title_is_source_scoped(self) -> None:
        self.assertEqual(normalize_source_digest_title("LLM-Wiki.md"), "LLM-Wiki Source")
        self.assertEqual(normalize_source_digest_title("Agent Source"), "Agent Source")
        self.assertEqual(normalize_source_digest_title("MiniMind 笔记源"), "MiniMind 笔记源")


if __name__ == "__main__":
    unittest.main()
