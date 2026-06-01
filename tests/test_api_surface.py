from __future__ import annotations

import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.entrypoints.api import create_app
from knoarbor.entrypoints.api_contract import removed_legacy_route_set, stable_route_set, ui_route_set
from knoarbor.core.errors import ERROR_HINTS
from knoarbor import __version__


class ApiSurfaceTests(unittest.TestCase):
    def test_openapi_version_matches_package_version(self) -> None:
        client = TestClient(create_app())

        payload = client.get("/openapi.json").json()

        self.assertEqual(payload["info"]["version"], __version__)

    def test_api_errors_use_public_error_catalog(self) -> None:
        client = TestClient(create_app())

        validation = client.post("/query", json={"query": ""})

        self.assertEqual(validation.status_code, 422)
        self.assertEqual(validation.json()["error"]["code"], "KA-INPUT-001")
        self.assertEqual(validation.json()["error"]["category"], "user_input_error")
        self.assertFalse(validation.json()["error"]["retryable"])
        self.assertIn("hint", validation.json()["error"])
        self.assertIn("details", validation.json()["error"])

    def test_openapi_exposes_only_public_long_term_routes(self) -> None:
        client = TestClient(create_app())

        paths = set(client.get("/openapi.json").json()["paths"])

        self.assertTrue(stable_route_set().issubset(paths))
        self.assertTrue(ui_route_set().issubset(paths))
        self.assertFalse(removed_legacy_route_set() & paths)

    def test_api_docs_cover_stable_public_routes(self) -> None:
        docs = (Path(__file__).resolve().parents[1] / "docs" / "API.md").read_text(encoding="utf-8")

        for route in sorted(stable_route_set()):
            self.assertIn(route, docs)
        for route in sorted(removed_legacy_route_set()):
            self.assertNotIn(route, docs)

    def test_error_code_docs_cover_public_error_catalog(self) -> None:
        root = Path(__file__).resolve().parents[1]
        docs = (root / "docs" / "ERROR_CODES.md").read_text(encoding="utf-8")
        zh_docs = (root / "docs" / "zh" / "ERROR_CODES.md").read_text(encoding="utf-8")

        for code in sorted(ERROR_HINTS):
            self.assertIn(code, docs)
            self.assertIn(code, zh_docs)

    def test_unexpected_api_errors_still_use_public_error_envelope(self) -> None:
        app = create_app()

        @app.get("/test/unexpected", include_in_schema=False)
        def unexpected() -> None:
            raise RuntimeError("boom")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/test/unexpected")

        self.assertEqual(response.status_code, 500)
        payload = response.json()
        self.assertEqual(payload["error"]["code"], "KA-INTERNAL-001")
        self.assertEqual(payload["error"]["category"], "internal_error")
        self.assertIn("hint", payload["error"])
        self.assertNotIn("Traceback", payload["detail"])

    def test_query_search_endpoint_returns_context_pack(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            (vault / "concepts" / "Agent-Loop.md").write_text(
                "# Agent Loop\n\n## Summary\n\nAgent loop coordinates reasoning and tool use.\n",
                encoding="utf-8",
            )
            client = TestClient(create_app())

            response = client.post(
                "/query",
                json={
                    "obsidian_vault_path": str(vault),
                    "query": "agent loop",
                    "max_results": 3,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["results"][0]["path"], "concepts/Agent-Loop.md")
        self.assertEqual(payload["results"][0]["excerpts"][0]["path"], "concepts/Agent-Loop.md")
        self.assertTrue(payload["answer_guidance"])
        self.assertIn("Match origin: direct", payload["context_pack"])
        self.assertIn("Why matched", payload["context_pack"])
        self.assertEqual(payload["stats"]["index_provider"], "machine")
        self.assertIn("query_ledger_path", payload["stats"])
        self.assertIn("initial_scope_dirs", payload["trace"])
        self.assertGreater(payload["stats"]["context_pack_chars"], 0)

    def test_query_trends_endpoint_returns_repeated_gaps(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            client = TestClient(create_app())
            for _ in range(2):
                response = client.post(
                    "/query",
                    json={
                        "obsidian_vault_path": str(vault),
                        "query": "missing topic",
                        "max_results": 3,
                    },
                )
                self.assertEqual(response.status_code, 200)

            trend_response = client.get(
                "/query/trends",
                params={
                    "obsidian_vault_path": str(vault),
                    "limit": 20,
                },
            )

        self.assertEqual(trend_response.status_code, 200)
        payload = trend_response.json()
        self.assertEqual(payload["sample_size"], 2)
        self.assertEqual(payload["no_result_count"], 2)
        self.assertEqual(payload["repeated_gap_queries"][0]["query"], "missing topic")

    def test_query_feedback_endpoint_records_feedback(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            client = TestClient(create_app())

            response = client.post(
                "/query/feedback",
                json={
                    "obsidian_vault_path": str(vault),
                    "query": "agent loop",
                    "useful": True,
                    "selected_paths": ["concepts/Agent-Loop.md"],
                },
            )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertTrue(payload["recorded"])
            self.assertTrue((vault / "maintenance" / "query_feedback_ledger.jsonl").exists())

    def test_query_endpoint_returns_context_pack(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            (vault / "concepts" / "Agent-Loop.md").write_text(
                "# Agent Loop\n\n## Summary\n\nAgent loop coordinates reasoning and tool use.\n",
                encoding="utf-8",
            )
            client = TestClient(create_app())

            response = client.post(
                "/query",
                json={
                    "obsidian_vault_path": str(vault),
                    "query": "agent loop",
                    "record_query": False,
                },
            )
            self.assertEqual(response.status_code, 200)
            payload = response.json()

        self.assertEqual(payload["schema_version"], "wiki_query.v1")
        self.assertEqual(payload["results"][0]["path"], "concepts/Agent-Loop.md")

    def test_run_ingest_file_records_preprocessor_error_for_pdf(self) -> None:
        import tempfile
        import time

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "wiki"
            vault.mkdir()
            pdf = root / "paper.pdf"
            pdf.write_bytes(b"%PDF")
            config = root / "config.yaml"
            config.write_text(f"vault:\n  path: {vault}\n", encoding="utf-8")
            client = TestClient(create_app())

            response = client.post(
                "/ingest",
                json={
                    "execution": "queued",
                    "kind": "file",
                    "config_path": str(config),
                    "input_path": str(pdf),
                    "write": False,
                },
            )
            self.assertEqual(response.status_code, 200)
            run_id = response.json()["run_id"]
            run_payload = {}
            for _ in range(20):
                run_response = client.get(f"/runs/{run_id}", params={"vault_path": str(vault)})
                self.assertEqual(run_response.status_code, 200)
                run_payload = run_response.json()
                if run_payload["status"] == "failed":
                    break
                time.sleep(0.05)

        self.assertEqual(run_payload["status"], "failed")
        self.assertEqual(run_payload["error_info"]["code"], "KA-DOC-001")
        self.assertIn("document_processing.mineru.enabled", run_payload["error"])

    def test_run_lint_records_missing_config_error(self) -> None:
        import tempfile
        import time

        with tempfile.TemporaryDirectory() as tmp_dir:
            missing_config = Path(tmp_dir) / "config.yaml"
            vault = Path(tmp_dir) / "wiki"
            vault.mkdir()
            client = TestClient(create_app())

            response = client.post(
                "/lint",
                json={
                    "execution": "queued",
                    "obsidian_vault_path": str(vault),
                    "config_path": str(missing_config),
                    "mode": "quality",
                    "scope": {
                        "scope_id": "test:missing-config",
                        "trigger": "manual",
                        "source": {"kind": "test"},
                        "changed_pages": [],
                        "recommended_lint_modes": ["quality"],
                        "reason": "Exercise missing config handling.",
                    },
                },
            )
            self.assertEqual(response.status_code, 200)
            run_id = response.json()["run_id"]
            run_payload = {}
            for _ in range(20):
                run_response = client.get(f"/runs/{run_id}", params={"vault_path": str(vault)})
                self.assertEqual(run_response.status_code, 200)
                run_payload = run_response.json()
                if run_payload["status"] == "failed":
                    break
                time.sleep(0.05)

            self.assertEqual(run_payload["status"], "failed")
            self.assertEqual(run_payload["error_info"]["code"], "KA-CFG-001")
            self.assertIn("Config file does not exist", run_payload["error"])

    def test_http_exception_uses_public_error_envelope(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            client = TestClient(create_app())

            response = client.get(
                "/wiki/page",
                params={"vault_path": str(vault), "path": "concepts/Missing.md"},
            )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "KA-INPUT-002")
        self.assertEqual(response.json()["error"]["category"], "user_input_error")
        self.assertIn("Vault file not found", response.json()["error"]["message"])


if __name__ == "__main__":
    unittest.main()
