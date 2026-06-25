from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.core.ignore import KnoArborIgnore
from knoarbor.storage.wiki_init import init_wiki_vault, migrate_wiki_pages_layout
from knoarbor.storage.wiki_paths import content_relative_path, resolve_existing_target, source_digest_root


class WikiInitTests(unittest.TestCase):
    def test_init_wiki_vault_creates_schema_index_log_and_ignore(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir) / "vaults" / "all"

            result = init_wiki_vault(vault)

            self.assertTrue((vault / "pages" / "SCHEMA.md").exists())
            self.assertTrue((vault / "pages" / "log.md").exists())
            self.assertTrue((vault / ".knoarbor" / "index" / "manifest.json").exists())
            self.assertTrue((vault / ".knoarbor" / "index" / "graph_index.json").exists())
            self.assertTrue((vault / ".knoarborignore").exists())
            self.assertTrue((vault / "raw").is_dir())
            self.assertFalse((vault / "sources").exists())
            self.assertTrue((vault / "pages" / "sources").is_dir())
            self.assertFalse((vault / "pages" / "concepts").exists())
            self.assertFalse((vault / "pages" / "_views").exists())
            self.assertFalse((vault / "raw" / "documents" / "markdown").exists())
            self.assertIn("pages/SCHEMA.md", result.created_paths)
            self.assertEqual(source_digest_root(vault), vault.resolve() / "pages" / "sources")

    def test_migrate_wiki_pages_layout_moves_legacy_content_and_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir) / "vaults" / "all"
            (vault / "concepts").mkdir(parents=True)
            (vault / "sources").mkdir()
            (vault / "maintenance").mkdir()
            (vault / "raw" / "notes").mkdir(parents=True)
            (vault / "concepts" / "Agent.md").write_text("# Agent\n", encoding="utf-8")
            (vault / "sources" / "Agent-Source.md").write_text("# Agent Source\n", encoding="utf-8")
            (vault / "maintenance" / "lint_report.md").write_text("# Report\n", encoding="utf-8")

            result = migrate_wiki_pages_layout(vault)

            self.assertTrue((vault / "pages" / "concepts" / "Agent.md").exists())
            self.assertTrue((vault / "pages" / "sources" / "Agent-Source.md").exists())
            self.assertTrue((vault / ".knoarbor" / "index" / "manifest.json").exists())
            self.assertTrue((vault / ".knoarbor" / "index" / "graph_index.json").exists())
            self.assertFalse((vault / "concepts").exists())
            self.assertFalse((vault / "sources").exists())
            self.assertTrue((vault / "maintenance" / "lint_report.md").exists())
            self.assertIn("concepts", result.moved_paths)
            self.assertIn("sources", result.moved_paths)

    def test_source_digest_target_resolves_inside_pages_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir) / "vaults" / "all"
            init_wiki_vault(vault)
            page = vault / "pages" / "sources" / "A2A-Source.md"
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
