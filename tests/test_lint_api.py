from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.entrypoints.api import create_app


class LintApiTests(unittest.TestCase):
    def test_run_lint_direct_returns_result_without_run_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            client = TestClient(create_app())

            response = client.post(
                "/lint",
                json={
                    "execution": "direct",
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
        self.assertEqual(payload["flow"], "lint")
        self.assertEqual(payload["execution"], "direct")
        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["result"]["schema_version"], "lint_run.v1")
        self.assertIsNone(payload["run_id"])

    def test_run_lint_returns_observable_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            client = TestClient(create_app())

            response = client.post(
                "/lint",
                json={
                    "execution": "queued",
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
            response_payload = response.json()
            self.assertEqual(response_payload["flow"], "lint")
            self.assertEqual(response_payload["execution"], "queued")
            run_id = response_payload["run_id"]
            payload = _wait_for_run(client, tmp_dir, run_id)

        self.assertEqual(payload["status"], "completed")
        self.assertEqual(payload["flow"], "lint")


def _wait_for_run(client: TestClient, vault_path: str, run_id: str) -> dict:
    payload = {}
    for _ in range(20):
        response = client.get(f"/runs/{run_id}", params={"vault_path": vault_path})
        response.raise_for_status()
        payload = response.json()
        if payload["status"] == "completed":
            return payload
        time.sleep(0.05)
    return payload


if __name__ == "__main__":
    unittest.main()
