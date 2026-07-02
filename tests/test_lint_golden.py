from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.audit.lint_report import build_lint_run_record, render_lint_run_report
from knoarbor.core.schemas.maintenance import MaintenanceScope, MaintenanceScopeSource
from knoarbor.core.schemas.wiki_lint import LintRunRequest, WikiScanRequest
from knoarbor.pipelines import WikiLintPipeline

from tests.harness.lint_cases import LintStructuralFixtureWorkflow, create_lint_fixture_vault
from tests.harness.snapshot import assert_json_snapshot


FIXTURE_DIR = Path(__file__).resolve().parent / "harness" / "fixtures" / "lint"


class LintGoldenTests(unittest.TestCase):
    def test_deterministic_scan_matches_golden_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            create_lint_fixture_vault(vault)
            response = WikiLintPipeline().scan(WikiScanRequest(vault_path=str(vault)))

        assert_json_snapshot(self, _stable_scan_response(response), FIXTURE_DIR / "deterministic_scan.json")

    def test_semantic_maintenance_matches_golden_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            create_lint_fixture_vault(vault)
            response = WikiLintPipeline(LintStructuralFixtureWorkflow()).run_maintenance(
                LintRunRequest(
                    vault_path=str(vault),
                    scope=MaintenanceScope(
                        scope_id="golden:lint",
                        trigger="manual",
                        source=MaintenanceScopeSource(kind="test"),
                        changed_pages=["Agent-Loop.md"],
                    ),
                    mode="semantic",
                    include_related=True,
                    auto_apply_reviewed_changes=True,
                    write_report=False,
                    append_ledger=False,
                )
            )

        record = build_lint_run_record(response, run_id="golden-lint-run", previous_records=[])
        record["created_at"] = "2026-01-01 00:00:00"
        snapshot = {
            "result": _stable_lint_run_result(response),
            "report": _normalize_report(render_lint_run_report(record)),
        }
        assert_json_snapshot(self, snapshot, FIXTURE_DIR / "semantic_run.json")


def _stable_scan_response(response: Any) -> dict[str, object]:
    return {
        "pages": [
            {
                "path": page.path,
                "directory": page.directory,
                "title": page.title,
                "role": page.role,
                "headings": page.headings,
                "outgoing_links": page.outgoing_links,
            }
            for page in response.pages
        ],
        "issues": [_stable_issue(issue) for issue in response.issues],
        "fixes": [fix.model_dump(mode="json") for fix in response.fixes],
        "stats": _stable_stats(response.stats),
    }


def _stable_lint_run_result(response: Any) -> dict[str, object]:
    return {
        "mode": response.mode,
        "policy_decision": response.policy_decision.model_dump(mode="json"),
        "deterministic_issues": [_stable_issue(issue) for issue in response.deterministic_lint.issues],
        "semantic_candidates": response.semantic_candidates,
        "maintenance_review": response.maintenance_review,
        "queued_actions": response.queued_actions,
        "deferred_retries": response.deferred_retries,
        "applied_operations": [
            {
                "operation_id": item.get("operation_id"),
                "action": item.get("action"),
                "status": item.get("status"),
                "target_page": item.get("target_page"),
                "output_page": item.get("output_page"),
                "details": item.get("details"),
            }
            for item in response.applied_operations
        ],
        "written_pages": response.written_pages,
        "verifications": response.verifications,
        "rescan_issues": [_stable_issue(issue) for issue in response.rescan.issues] if response.rescan else None,
        "warnings": response.warnings,
    }


def _stable_issue(issue: Any) -> dict[str, object]:
    return {
        "code": issue.code,
        "severity": issue.severity,
        "path": issue.path,
        "message": issue.message,
        "details": issue.details,
    }


def _stable_stats(stats: dict[str, Any]) -> dict[str, object]:
    stable = dict(stats)
    graph = stable.get("graph_health")
    if isinstance(graph, dict):
        stable["graph_health"] = {
            "node_count": graph.get("node_count"),
            "component_count": graph.get("component_count"),
            "largest_component_size": graph.get("largest_component_size"),
            "isolated_page_count": graph.get("isolated_page_count"),
            "small_component_count": graph.get("small_component_count"),
            "hub_pages": graph.get("hub_pages"),
        }
    return stable


def _normalize_report(report: str) -> str:
    report = re.sub(r"- created_at: .+", "- created_at: <created_at>", report)
    report = re.sub(r"- elapsed_seconds: .+", "- elapsed_seconds: <elapsed>", report)
    report = re.sub(r"- tokens_per_second: .+", "- tokens_per_second: <tokens_per_second>", report)
    return report


if __name__ == "__main__":
    unittest.main()
