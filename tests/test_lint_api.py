from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.entrypoints.api import create_app


class LintApiTests(unittest.TestCase):
    def test_lint_run_endpoint_returns_lint_run_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            client = TestClient(create_app())

            response = client.post(
                "/lint/run",
                json={
                    "obsidian_vault_path": tmp_dir,
                    "scope": {
                        "scope_id": "manual:test",
                        "trigger": "manual",
                        "source": {"kind": "api"},
                        "changed_pages": [],
                    },
                    "mode": "deterministic",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema_version"], "lint_run.v1")
        self.assertIn("deterministic_lint", payload)
        self.assertIn("policy_decision", payload)


if __name__ == "__main__":
    unittest.main()
