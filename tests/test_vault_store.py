from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.storage import VaultStore


class VaultStoreTests(unittest.TestCase):
    def test_read_pages_normalizes_wikilinks_and_deduplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            (vault / "concepts" / "Agent.md").write_text("# Agent\n\nLoop.", encoding="utf-8")

            pages = VaultStore(vault).read_pages(
                ["[[concepts/Agent|Agent]]", "concepts/Agent.md"],
                max_pages=5,
                max_chars_per_page=100,
            )

        self.assertEqual(len(pages), 1)
        self.assertTrue(pages[0].exists)
        self.assertEqual(pages[0].path, "concepts/Agent.md")

    def test_read_page_blocks_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            page = VaultStore(Path(tmp_dir)).read_page("../outside.md", max_chars=100)

        self.assertFalse(page.exists)
        self.assertEqual(page.error, "page path escapes vault")


if __name__ == "__main__":
    unittest.main()
