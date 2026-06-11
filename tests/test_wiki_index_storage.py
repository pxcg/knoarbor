from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.storage import ensure_machine_index, index_entry, is_machine_index_stale, machine_index_dir, update_index, wiki_link_for_path


class WikiIndexStorageTests(unittest.TestCase):
    def test_update_index_catalogs_generated_pages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            page = vault / "concepts" / "Agent.md"
            page.write_text(
                "---\ntype: concept\nstatus: draft\ntags: agent, loop\n---\n"
                "# Agent\n\n## Summary\n\nAgent loop notes.\n",
                encoding="utf-8",
            )

            update_index(vault)
            content = (vault / "index.md").read_text(encoding="utf-8")
            pages = json.loads((machine_index_dir(vault) / "pages.json").read_text(encoding="utf-8"))
            search = json.loads((machine_index_dir(vault) / "search.json").read_text(encoding="utf-8"))

        self.assertIn("[[concepts/Agent|Agent]]", content)
        self.assertIn("tags: agent, loop", content)
        self.assertEqual(pages["pages"][0]["path"], "concepts/Agent.md")
        self.assertEqual(search["entries"][0]["title"], "Agent")

    def test_machine_index_records_links_and_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            (vault / "sources").mkdir()
            (vault / "sources" / "Source.md").write_text("# Source\n", encoding="utf-8")
            (vault / "concepts" / "Agent.md").write_text(
                "---\ntype: concept\nsource: raw/notes/agent.md\n---\n"
                "# Agent\n\n## Summary\n\nLinks to [[sources/Source|source]].\n",
                encoding="utf-8",
            )

            update_index(vault)
            links = json.loads((machine_index_dir(vault) / "links.json").read_text(encoding="utf-8"))
            sources = json.loads((machine_index_dir(vault) / "sources.json").read_text(encoding="utf-8"))

        self.assertEqual(links["links"][0]["target_path"], "sources/Source.md")
        self.assertEqual(sources["sources"][0]["source"], "raw/notes/agent.md")

    def test_machine_index_stale_detection_refreshes_after_page_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            (vault / "concepts" / "Agent.md").write_text("# Agent\n", encoding="utf-8")

            update_index(vault)
            self.assertFalse(is_machine_index_stale(vault))
            (vault / "concepts" / "Agent.md").write_text("# Agent\n\n## Summary\n\nUpdated.", encoding="utf-8")

            self.assertTrue(is_machine_index_stale(vault))
            ensure_machine_index(vault)
            pages = json.loads((machine_index_dir(vault) / "pages.json").read_text(encoding="utf-8"))

        self.assertEqual(pages["pages"][0]["summary"], "Updated.")

    def test_update_index_skips_maintenance_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "maintenance").mkdir()
            (vault / "maintenance" / "lint_run_report_20260521_123244.md").write_text(
                "# Lint Run Report\n\nRuntime maintenance artifact.",
                encoding="utf-8",
            )

            update_index(vault)
            content = (vault / "pages" / "index.md").read_text(encoding="utf-8")

        self.assertNotIn("lint_run_report", content)
        self.assertNotIn("maintenance/", content)

    def test_index_entry_and_wikilink_use_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "entities").mkdir()
            page = vault / "entities" / "MiniMind.md"
            page.write_text("# MiniMind\n\n## Summary\n\nA small model project.", encoding="utf-8")

            entry = index_entry(vault, page)
            link = wiki_link_for_path(vault, page, "MiniMind")

        self.assertIn("[[entities/MiniMind|MiniMind]]", entry)
        self.assertEqual(link, "[[entities/MiniMind|MiniMind]]")


if __name__ == "__main__":
    unittest.main()
