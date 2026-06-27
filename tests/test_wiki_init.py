from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.core.ignore import KnoArborIgnore
from knoarbor.storage.wiki_init import init_wiki_vault
from knoarbor.storage.wiki_paths import content_relative_path, resolve_existing_target, source_digest_root


class WikiInitTests(unittest.TestCase):
    def test_init_wiki_vault_creates_log_index_and_ignore(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir) / "vaults" / "all"

            result = init_wiki_vault(vault)

            self.assertFalse((vault / "wiki" / "pages" / "SCHEMA.md").exists())
            self.assertTrue((vault / "wiki" / "log.md").exists())
            self.assertTrue((vault / ".knoarbor" / "index" / "manifest.json").exists())
            self.assertTrue((vault / ".knoarbor" / "index" / "graph_index.json").exists())
            self.assertTrue((vault / ".knoarborignore").exists())
            self.assertTrue((vault / "raw").is_dir())
            self.assertFalse((vault / "sources").exists())
            self.assertTrue((vault / "wiki" / "sources").is_dir())
            self.assertTrue((vault / "wiki" / "pages").is_dir())
            self.assertFalse((vault / "wiki" / "pages" / "_views").exists())
            self.assertTrue((vault / "raw" / "inbox" / "documents").exists())
            self.assertTrue((vault / "raw" / "normalized" / "markdown").exists())
            self.assertTrue((vault / "raw" / "assets" / "images").exists())
            self.assertIn("wiki/log.md", result.created_paths)
            self.assertEqual(source_digest_root(vault), vault.resolve() / "wiki" / "sources")

    def test_source_digest_target_resolves_inside_pages_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir) / "vaults" / "all"
            init_wiki_vault(vault)
            page = vault / "wiki" / "sources" / "A2A-Source.md"
            page.write_text("# A2A Source\n", encoding="utf-8")

            resolved = resolve_existing_target(vault, "sources/A2A-Source.md")

            self.assertEqual(resolved, page.resolve())
            self.assertEqual(content_relative_path(vault, page), "sources/A2A-Source.md")

    def test_knoarborignore_supports_negation_and_directory_patterns(self) -> None:
        matcher = KnoArborIgnore(["confidential/", "*.key", "!confidential/public.md"])

        self.assertTrue(matcher.ignored("confidential/private.md"))
        self.assertTrue(matcher.ignored("secret.key"))
        self.assertFalse(matcher.ignored("confidential/public.md"))


if __name__ == "__main__":
    unittest.main()
