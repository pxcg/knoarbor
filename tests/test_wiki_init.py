from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.storage.wiki_init import init_wiki_vault
from knoarbor.storage.wiki_index import machine_index_dir
from knoarbor.storage.wiki_paths import content_relative_path, resolve_existing_target, source_record_root


class WikiInitTests(unittest.TestCase):
    def test_init_wiki_vault_creates_log_index_and_runtime_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir) / "vaults" / "all"

            result = init_wiki_vault(vault)

            self.assertFalse((vault / "wiki" / "pages" / "SCHEMA.md").exists())
            self.assertTrue((vault / "wiki" / "log.md").exists())
            self.assertTrue((machine_index_dir(vault) / "manifest.json").exists())
            self.assertTrue((machine_index_dir(vault) / "graph_index.json").exists())
            self.assertTrue((vault / "raw").is_dir())
            self.assertFalse((vault / "sources").exists())
            self.assertTrue((vault / "wiki" / "sources").is_dir())
            self.assertTrue((vault / "wiki" / "pages").is_dir())
            self.assertFalse((vault / "wiki" / "pages" / "_views").exists())
            self.assertTrue((vault / "raw" / "inbox" / "documents").exists())
            self.assertTrue((vault / "raw" / "derived" / "markdown").exists())
            self.assertTrue((vault / "raw" / "derived" / "assets" / "images").exists())
            self.assertTrue((vault / "artifacts" / "chat").exists())
            self.assertTrue((vault / ".knoarbor" / "tmp").exists())
            self.assertFalse((vault / ".knoarbor" / "ingest").exists())
            self.assertFalse((vault / "raw" / "normalized").exists())
            self.assertFalse((vault / "raw" / "assets").exists())
            self.assertFalse((vault / "raw" / "sidecars").exists())
            self.assertFalse((vault / "raw" / "derived" / "assets" / "images" / "generated" / "chat").exists())
            self.assertIn("wiki/log.md", result.created_paths)
            self.assertEqual(source_record_root(vault), vault.resolve() / "wiki" / "sources")

    def test_source_record_target_resolves_inside_pages_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir) / "vaults" / "all"
            init_wiki_vault(vault)
            page = vault / "wiki" / "sources" / "A2A-Source.md"
            page.write_text("# A2A Source\n", encoding="utf-8")

            resolved = resolve_existing_target(vault, "sources/A2A-Source.md")

            self.assertEqual(resolved, page.resolve())
            self.assertEqual(content_relative_path(vault, page), "sources/A2A-Source.md")

if __name__ == "__main__":
    unittest.main()
