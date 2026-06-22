from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.maintenance.lint_collection import collect_pages
from knoarbor.maintenance.wiki_lint import lint_vault
from knoarbor.storage import update_index


class WikiLintBoundaryTests(unittest.TestCase):
    def test_lint_ignores_maintenance_reports_as_system_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            maintenance = vault / "maintenance"
            maintenance.mkdir()
            (maintenance / "lint_run_report_20260521_123244.md").write_text(
                "# Lint Run Report\n\nRuntime maintenance artifact.",
                encoding="utf-8",
            )
            (vault / "index.md").write_text("# Index\n", encoding="utf-8")

            issues, stats = lint_vault(vault)

        self.assertEqual(issues, [])
        self.assertEqual(stats["page_count"], 0)

    def test_lint_collects_unified_root_page_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            pages_root = vault / "pages"
            pages_root.mkdir()
            (pages_root / "Agent-Loop.md").write_text(
                "---\npage_kind: concept\nstatus: draft\nsource: raw/notes/agent.md\nfacets: agent_architecture\n---\n"
                "# Agent Loop\n\n"
                "## Summary\n\nAgent loop notes.\n\n"
                "## Answer\n\nAgent loop answer.\n\n"
                "## Key Points\n\n- Loop.\n\n"
                "## Related Pages\n\n- 暂无关联知识\n\n"
                "## Tags\n\n- agent\n\n"
                "## Source\n\n- raw/notes/agent.md\n",
                encoding="utf-8",
            )
            update_index(vault)

            pages = collect_pages(vault)
            issues, stats = lint_vault(vault)

        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0].relative_path, "Agent-Loop.md")
        self.assertEqual(pages[0].directory, "pages")
        self.assertEqual(pages[0].page_kind, "concept")
        self.assertEqual(pages[0].role, "knowledge_page")
        self.assertIn("agent_architecture", pages[0].facets)
        self.assertNotIn("unexpected_markdown_location", {issue.code for issue in issues})
        self.assertEqual(stats["page_kinds"]["concept"], 1)
        self.assertEqual(stats["roles"]["knowledge_page"], 1)

    def test_lint_flags_source_digest_outside_sources_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            pages_root = vault / "pages"
            pages_root.mkdir()
            (pages_root / "Agent-Source.md").write_text(
                "---\npage_kind: source_digest\nstatus: draft\nsource: raw/notes/agent.md\n---\n"
                "# Agent Source\n\n## Summary\n\nDigest.\n\n## Source Focus\n\nAgent.\n\n"
                "## Answer\n\nDigest answer.\n\n## Related Pages\n\n- 暂无关联知识\n\n"
                "## Tags\n\n- source\n\n## Source\n\n- raw/notes/agent.md\n",
                encoding="utf-8",
            )
            update_index(vault)

            issues, _stats = lint_vault(vault)

        self.assertIn("source_digest_wrong_location", {issue.code for issue in issues})


if __name__ == "__main__":
    unittest.main()
