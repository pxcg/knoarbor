from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.maintenance.lint_collection import collect_pages
from knoarbor.maintenance.wiki_lint import lint_vault
from knoarbor.storage.materialization import VaultMaterializer


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
            VaultMaterializer().reconcile(vault, force=True)

            issues, stats = lint_vault(vault)

        self.assertEqual(issues, [])
        self.assertEqual(stats["page_count"], 0)

    def test_lint_collects_unified_root_page_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            pages_root = vault / "wiki" / "pages"
            pages_root.mkdir(parents=True)
            (pages_root / "Agent-Loop.md").write_text(
                "---\n---\n# Agent Loop\n\n"
                "## Summary\n\nAgent loop notes.\n\n"
                "## Claims\n\n- C1: **Agent loop** coordinates reasoning and tools.\n\n"
                "## Entities\n\n- Agent loop\n\n"
                "## Relations\n\n| Subject | Predicate | Object | Claim |\n|---|---|---|---|\n| Agent loop | coordinates | tools | C1 |\n\n"
                "## Evidence\n\n| Claim | Source | Range | Basis | Confidence |\n|---|---|---|---|---|\n| C1 | raw/inbox/notes/agent.md | unit:0 | Agent loop notes. | medium |\n\n"
                "## Synthesis\n\nAgent loop answer.\n\n",
                encoding="utf-8",
            )
            VaultMaterializer().reconcile(vault, force=True)

            pages = collect_pages(vault)
            issues, stats = lint_vault(vault)

        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0].relative_path, "Agent-Loop.md")
        self.assertEqual(pages[0].directory, "pages")
        self.assertEqual(pages[0].role, "knowledge_page")
        self.assertNotIn("unexpected_markdown_location", {issue.code for issue in issues})
        self.assertEqual(stats["roles"]["knowledge_page"], 1)

if __name__ == "__main__":
    unittest.main()
