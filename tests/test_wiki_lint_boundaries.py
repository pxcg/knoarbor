from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.maintenance.wiki_lint import lint_vault


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


if __name__ == "__main__":
    unittest.main()
