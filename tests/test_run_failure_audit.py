from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.core.schemas.ingest_run import IngestFileRunRequest
from knoarbor.core.schemas.maintenance import MaintenanceScope, MaintenanceScopeSource
from knoarbor.core.schemas.wiki_lint import LintRunRequest
from knoarbor.core.schemas.wiki_query import WikiSearchRequest
from knoarbor.services.ingest import IngestService
from knoarbor.services.wiki_search import WikiSearchService
from knoarbor.services.wiki_linter import WikiLinterService


class RunFailureAuditTests(unittest.TestCase):
    def test_ingest_file_failure_writes_failure_report_and_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "vaults" / "all"
            vault.mkdir(parents=True)
            config_path = root / "config.yaml"
            config_path.write_text(Path("config.example.yaml").read_text().replace("./vaults/default", str(vault)), encoding="utf-8")
            pdf_path = root / "sample.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n% test")

            request = IngestFileRunRequest(
                input_path=str(pdf_path),
                config_path=str(config_path),
                write_report=True,
                append_ledger=True,
            )
            with self.assertRaises(Exception):
                IngestService().run_file(request)

            reports = sorted((vault / "maintenance" / "reports" / "ingest").glob("ingest_run_report_*.md"))
            ledgers = sorted((vault / ".knoarbor" / "ledgers").glob("ingest.jsonl"))
            self.assertEqual(len(reports), 1)
            self.assertEqual(len(ledgers), 1)
            report = reports[0].read_text(encoding="utf-8")
            self.assertIn("- flow: ingest", report)
            self.assertIn("- status: failed", report)
            self.assertIn("- error_code: KA-DOC-001", report)

    def test_lint_failure_writes_failure_report_and_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            request = LintRunRequest(
                vault_path=str(vault),
                config_path=str(vault / "missing-config.yaml"),
                scope=MaintenanceScope(
                    scope_id="failure-test",
                    trigger="manual",
                    source=MaintenanceScopeSource(kind="test"),
                ),
                mode="semantic",
                write_report=True,
                append_ledger=True,
            )
            with self.assertRaises(Exception):
                WikiLinterService().run_maintenance(request)

            reports = sorted((vault / "maintenance" / "reports" / "lint").glob("lint_run_report_*.md"))
            ledgers = sorted((vault / ".knoarbor" / "ledgers").glob("lint_run.jsonl"))
            self.assertEqual(len(reports), 1)
            self.assertEqual(len(ledgers), 1)
            report = reports[0].read_text(encoding="utf-8")
            self.assertIn("- flow: lint", report)
            self.assertIn("- status: failed", report)
            self.assertIn("- error_code: KA-CFG-001", report)

    def test_query_failure_writes_failure_report_and_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            request = WikiSearchRequest(
                vault_path=str(vault),
                query="agent loop",
                record_query=True,
                write_report=True,
            )
            with patch("knoarbor.services.wiki_search.search_query", side_effect=RuntimeError("query failed")):
                with self.assertRaises(RuntimeError):
                    WikiSearchService().search(request)

            reports = sorted((vault / "maintenance" / "reports" / "query").glob("query_run_report_*.md"))
            ledgers = sorted((vault / ".knoarbor" / "ledgers").glob("query.jsonl"))
            self.assertEqual(len(reports), 1)
            self.assertEqual(len(ledgers), 1)
            report = reports[0].read_text(encoding="utf-8")
            self.assertIn("- flow: query", report)
            self.assertIn("- status: failed", report)
            self.assertIn("- error_code: KA-INTERNAL-001", report)


if __name__ == "__main__":
    unittest.main()
