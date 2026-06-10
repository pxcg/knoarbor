from __future__ import annotations

import sys
import unittest
import os
import tomllib
from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.entrypoints.api import create_app
from knoarbor.entrypoints.api_contract import stable_route_set, ui_route_set
from knoarbor.core.errors import ERROR_HINTS
from knoarbor import __version__


@contextmanager
def _chdir(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def _write_run_record(vault: Path, run_id: str, updated_at: str) -> None:
    run_dir = vault / ".knoarbor" / "runs"
    run_dir.mkdir(parents=True)
    (run_dir / f"{run_id}.json").write_text(
        f"""{{
  "schema_version": "run_record.v1",
  "run_id": "{run_id}",
  "flow": "ingest",
  "status": "completed",
  "stage": "completed",
  "message": "completed",
  "started_at": "{updated_at}",
  "updated_at": "{updated_at}",
  "last_heartbeat_at": "{updated_at}",
  "finished_at": "{updated_at}",
  "elapsed_seconds": 1.0,
  "progress": {{"completed": 1}},
  "metrics": {{}},
  "metadata": {{}},
  "result_summary": {{"report_path": "maintenance/ingest_report.md"}},
  "error_info": {{}},
  "cancel_requested": false
}}""",
        encoding="utf-8",
    )


REMOVED_PROTOTYPE_ROUTES = {
    "/ingest/run",
    "/ingest/document",
    "/ingest/file",
    "/runs/ingest",
    "/runs/ingest-file",
    "/runs/lint",
    "/runs/query",
    "/runs/active",
    "/runs/{run_id}/rerun-failed",
    "/lint/run",
    "/query/search",
    "/connectors/discover",
    "/sources/normalize",
    "/sources/normalize_batch",
    "/read_wiki_pages",
    "/write_wiki_drafts",
    "/write_maintenance_report",
    "/append_maintenance_ledger",
    "/scan_wiki",
    "/select_lint_candidates",
    "/lint_wiki",
    "/apply_wiki_operations",
    "/wiki_context",
    "/wiki/page",
    "/wiki/backlinks",
}


class ApiSurfaceTests(unittest.TestCase):
    def test_package_version_metadata_is_synchronized(self) -> None:
        pyproject = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8"))

        self.assertEqual(pyproject["project"]["version"], __version__)

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
        self.assertFalse(REMOVED_PROTOTYPE_ROUTES & paths)

    def test_runtime_endpoint_returns_integration_context(self) -> None:
        client = TestClient(create_app())

        response = client.get("/runtime")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema_version"], "runtime_context.v1")
        self.assertTrue(payload["service_online"])
        self.assertTrue(payload["base_url"].startswith("http://testserver"))
        self.assertIn("config_path", payload)
        self.assertIn("vault_path", payload)
        self.assertIn("endpoint_path", payload)
        self.assertIn("user_endpoint_path", payload)
        self.assertIn("errors", payload)

    def test_vaults_endpoint_lists_configured_profiles(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            personal = root / "personal"
            team = root / "team"
            personal.mkdir()
            team.mkdir()
            config = root / "config.yaml"
            config.write_text(
                f"""
vaults:
  default: personal
  profiles:
    personal:
      name: Personal
      path: {personal}
    team:
      name: Team
      path: {team}
""",
                encoding="utf-8",
            )
            client = TestClient(create_app())

            response = client.get("/vaults", params={"config_path": str(config)})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema_version"], "vaults.v1")
        self.assertEqual(payload["default_vault_id"], "personal")
        self.assertEqual([item["id"] for item in payload["vaults"]], ["personal", "team"])
        self.assertTrue(payload["vaults"][0]["active"])
        self.assertTrue(payload["vaults"][0]["exists"])

    def test_vaults_endpoint_materializes_single_vault_config(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "wiki"
            vault.mkdir()
            config = root / "config.yaml"
            config.write_text(
                f"""
project:
  name: Local Wiki
vault:
  path: {vault}
""",
                encoding="utf-8",
            )
            client = TestClient(create_app())

            response = client.get("/vaults", params={"config_path": str(config)})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["default_vault_id"], "default")
        self.assertEqual(payload["vaults"][0]["id"], "default")
        self.assertEqual(payload["vaults"][0]["name"], "Local Wiki")
        self.assertTrue(payload["vaults"][0]["active"])
        self.assertTrue(payload["vaults"][0]["exists"])

    def test_sources_endpoint_returns_connector_catalog(self) -> None:
        client = TestClient(create_app())

        response = client.get("/sources")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["schema_version"], "source_catalog.v1")
        connectors = {item["name"]: item for item in payload["connectors"]}
        self.assertIn("markdown", connectors)
        self.assertEqual(connectors["markdown"]["source_types"], ["markdown"])
        self.assertIn("roots", connectors["markdown"]["settings_schema"]["properties"])
        self.assertIn("codex", connectors)
        self.assertEqual(connectors["codex"]["source_types"], ["codex_chat"])

    def test_sources_endpoint_can_annotate_configured_connectors(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "wiki"
            vault.mkdir()
            config = root / "config.yaml"
            config.write_text(
                f"""
vault:
  path: {vault}
connectors:
  markdown:
    enabled: true
    settings:
      roots:
        - {root}
""",
                encoding="utf-8",
            )
            client = TestClient(create_app())

            response = client.get("/sources", params={"config_path": str(config), "connector": "markdown"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["connectors"]), 1)
        self.assertEqual(payload["connectors"][0]["name"], "markdown")
        self.assertTrue(payload["connectors"][0]["configured"])
        self.assertTrue(payload["connectors"][0]["enabled"])

    def test_api_docs_cover_stable_public_routes(self) -> None:
        docs = (Path(__file__).resolve().parents[1] / "docs" / "API.md").read_text(encoding="utf-8")

        for route in sorted(stable_route_set()):
            self.assertIn(route, docs)
        for route in sorted(REMOVED_PROTOTYPE_ROUTES):
            self.assertNotIn(f"`{route}`", docs)

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
                    "vault_path": str(vault),
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

    def test_query_endpoint_accepts_vault_id(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            team_vault = root / "team-wiki"
            (team_vault / "concepts").mkdir(parents=True)
            (team_vault / "concepts" / "Team-Agent.md").write_text(
                "# Team Agent\n\n## Summary\n\nTeam agent coordination note.\n",
                encoding="utf-8",
            )
            (root / "config.yaml").write_text(
                f"""
vaults:
  default: personal
  profiles:
    personal:
      name: Personal
      path: ./personal-wiki
    team:
      name: Team
      path: {team_vault}
models:
  providers: {{}}
connectors: {{}}
""",
                encoding="utf-8",
            )
            with _chdir(root):
                client = TestClient(create_app())
                response = client.post(
                    "/query",
                    json={"config_path": str(root / "config.yaml"), "vault_id": "team", "query": "team agent", "max_results": 3},
                )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["stats"]["vault_id"], "team")
        self.assertEqual(payload["stats"]["vault_name"], "Team")
        self.assertEqual(payload["results"][0]["path"], "concepts/Team-Agent.md")

    def test_query_endpoint_accepts_all_vaults(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            personal_vault = root / "personal-wiki"
            team_vault = root / "team-wiki"
            (personal_vault / "concepts").mkdir(parents=True)
            (team_vault / "concepts").mkdir(parents=True)
            (personal_vault / "concepts" / "Personal-Agent.md").write_text(
                "# Personal Agent\n\n## Summary\n\nPersonal agent loop note.\n",
                encoding="utf-8",
            )
            (team_vault / "concepts" / "Team-Agent.md").write_text(
                "# Team Agent\n\n## Summary\n\nTeam agent coordination note.\n",
                encoding="utf-8",
            )
            (root / "config.yaml").write_text(
                f"""
vaults:
  default: personal
  profiles:
    personal:
      name: Personal
      path: {personal_vault}
    team:
      name: Team
      path: {team_vault}
models:
  providers: {{}}
connectors: {{}}
""",
                encoding="utf-8",
            )
            with _chdir(root):
                client = TestClient(create_app())
                response = client.post(
                    "/query",
                    json={"config_path": str(root / "config.yaml"), "all_vaults": True, "query": "agent", "max_results": 5},
                )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["stats"]["multi_vault"])
        self.assertEqual(payload["stats"]["vault_ids"], ["personal", "team"])
        self.assertEqual({result["vault_id"] for result in payload["results"]}, {"personal", "team"})
        self.assertIn("# Personal", payload["context_pack"])
        self.assertIn("# Team", payload["context_pack"])

    def test_query_trends_endpoint_returns_repeated_gaps(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            client = TestClient(create_app())
            for _ in range(2):
                response = client.post(
                    "/query",
                    json={
                        "vault_path": str(vault),
                        "query": "missing topic",
                        "max_results": 3,
                    },
                )
                self.assertEqual(response.status_code, 200)

            trend_response = client.get(
                "/query/trends",
                params={
                    "vault_path": str(vault),
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
                    "vault_path": str(vault),
                    "query": "agent loop",
                    "useful": True,
                    "selected_paths": ["concepts/Agent-Loop.md"],
                },
            )

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertTrue(payload["recorded"])
            self.assertTrue((vault / "maintenance" / "query_feedback_ledger.jsonl").exists())

    def test_reports_endpoints_list_and_read_markdown_reports(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            maintenance = vault / "maintenance"
            maintenance.mkdir()
            report = maintenance / "ingest_report_20260604_120000.md"
            report.write_text("# Ingest Report\n\n- written_pages: 2\n", encoding="utf-8")
            client = TestClient(create_app())

            list_response = client.get("/reports", params={"vault_path": str(vault)})
            self.assertEqual(list_response.status_code, 200)
            list_payload = list_response.json()
            self.assertEqual(list_payload["reports"][0]["path"], "maintenance/ingest_report_20260604_120000.md")
            self.assertEqual(list_payload["reports"][0]["kind"], "ingest")

            read_response = client.get(
                "/reports/content",
                params={"vault_path": str(vault), "path": "maintenance/ingest_report_20260604_120000.md"},
            )
            self.assertEqual(read_response.status_code, 200)
            read_payload = read_response.json()
            self.assertEqual(read_payload["path"], "maintenance/ingest_report_20260604_120000.md")
            self.assertIn("written_pages", read_payload["content"])

    def test_reports_endpoint_accepts_all_vaults(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            personal = root / "personal-wiki"
            team = root / "team-wiki"
            for vault, name in [(personal, "personal"), (team, "team")]:
                maintenance = vault / "maintenance"
                maintenance.mkdir(parents=True)
                (maintenance / f"ingest_report_{name}.md").write_text(f"# {name.title()} Ingest Report\n", encoding="utf-8")
            config_path = root / "config.yaml"
            config_path.write_text(
                f"""
vaults:
  default: personal
  profiles:
    personal:
      name: Personal
      path: {personal}
    team:
      name: Team
      path: {team}
models:
  providers: {{}}
connectors: {{}}
""",
                encoding="utf-8",
            )
            client = TestClient(create_app())
            response = client.get("/reports", params={"config_path": str(config_path), "all_vaults": "true"})

        self.assertEqual(response.status_code, 200)
        reports = response.json()["reports"]
        self.assertEqual({report["vault_id"] for report in reports}, {"personal", "team"})
        self.assertEqual({report["vault_name"] for report in reports}, {"Personal", "Team"})

    def test_runs_endpoint_accepts_all_vaults(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            personal = root / "personal-wiki"
            team = root / "team-wiki"
            _write_run_record(personal, "20260604_personal", "2026-06-04T12:00:00")
            _write_run_record(team, "20260604_team", "2026-06-04T12:01:00")
            config_path = root / "config.yaml"
            config_path.write_text(
                f"""
vaults:
  default: personal
  profiles:
    personal:
      name: Personal
      path: {personal}
    team:
      name: Team
      path: {team}
models:
  providers: {{}}
connectors: {{}}
""",
                encoding="utf-8",
            )
            client = TestClient(create_app())
            response = client.get("/runs", params={"config_path": str(config_path), "all_vaults": "true", "limit": 10})

        self.assertEqual(response.status_code, 200)
        runs = response.json()["runs"]
        self.assertEqual({run["vault_id"] for run in runs}, {"personal", "team"})
        self.assertEqual(runs[0]["run_id"], "20260604_team")

    def test_lint_endpoint_accepts_vault_id_without_vault_path(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            personal = root / "personal-wiki"
            team = root / "team-wiki"
            personal.mkdir()
            (team / "concepts").mkdir(parents=True)
            (team / "concepts" / "Team-Agent.md").write_text("# Team Agent\n\n## Source\n\nraw/team.md\n", encoding="utf-8")
            config_path = root / "config.yaml"
            config_path.write_text(
                f"""
vaults:
  default: personal
  profiles:
    personal:
      name: Personal
      path: {personal}
    team:
      name: Team
      path: {team}
models:
  providers: {{}}
connectors: {{}}
""",
                encoding="utf-8",
            )
            client = TestClient(create_app())
            response = client.post(
                "/lint",
                json={
                    "execution": "direct",
                    "config_path": str(config_path),
                    "vault_id": "team",
                    "mode": "deterministic",
                    "write_report": False,
                    "append_ledger": False,
                    "scope": {
                        "scope_id": "test:team",
                        "trigger": "manual",
                        "source": {"kind": "test"},
                        "changed_pages": [],
                        "recommended_lint_modes": ["deterministic"],
                        "reason": "Exercise vault_id lint selection.",
                    },
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["flow"], "lint")
        self.assertEqual(payload["execution"], "direct")
        self.assertEqual(payload["result"]["deterministic_lint"]["stats"]["page_count"], 1)

    def test_queued_ingest_uses_selected_vault_for_run_record(self) -> None:
        import tempfile
        import time

        from knoarbor.core.schemas.ingest_run import IngestRunRequest
        from knoarbor.runtime.run_monitor import read_run
        from knoarbor.services.run_manager import RunManager

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            personal = root / "personal-wiki"
            team = root / "team-wiki"
            personal.mkdir()
            team.mkdir()
            config_path = root / "config.yaml"
            config_path.write_text(
                f"""
vaults:
  default: personal
  profiles:
    personal:
      name: Personal
      path: {personal}
    team:
      name: Team
      path: {team}
models:
  providers: {{}}
connectors: {{}}
""",
                encoding="utf-8",
            )

            started = RunManager().start_ingest(
                IngestRunRequest(config_path=str(config_path), vault_id="team", write=False),
                lambda request: {"ok": True, "vault_id": request.vault_id},
            )

            self.assertEqual(started.run.vault_id, "team")
            self.assertEqual(started.run.vault_name, "Team")
            self.assertEqual(started.run.vault_path, str(team.resolve()))
            self.assertTrue((team / ".knoarbor" / "runs" / f"{started.run_id}.json").exists())
            self.assertFalse((personal / ".knoarbor" / "runs" / f"{started.run_id}.json").exists())
            for _ in range(20):
                record = read_run(team, started.run_id)
                if record.status == "completed":
                    break
                time.sleep(0.05)
            self.assertEqual(record.status, "completed")

    def test_queued_lint_response_includes_selected_vault_metadata(self) -> None:
        import tempfile
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            personal = root / "personal-wiki"
            team = root / "team-wiki"
            personal.mkdir()
            team.mkdir()
            config_path = root / "config.yaml"
            config_path.write_text(
                f"""
vaults:
  default: personal
  profiles:
    personal:
      name: Personal
      path: {personal}
    team:
      name: Team
      path: {team}
models:
  providers: {{}}
connectors: {{}}
""",
                encoding="utf-8",
            )
            client = TestClient(create_app())
            with patch("knoarbor.services.run_manager.LocalRunQueue.submit", return_value=None):
                response = client.post(
                    "/lint",
                    json={
                        "execution": "queued",
                        "config_path": str(config_path),
                        "vault_id": "team",
                        "mode": "deterministic",
                        "write_report": False,
                        "append_ledger": False,
                        "scope": {
                            "scope_id": "test:team",
                            "trigger": "manual",
                            "source": {"kind": "test"},
                            "changed_pages": [],
                            "recommended_lint_modes": ["deterministic"],
                            "reason": "Exercise queued vault metadata.",
                        },
                    },
                )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["execution"], "queued")
        self.assertEqual(payload["run"]["vault_id"], "team")
        self.assertEqual(payload["run"]["vault_name"], "Team")
        self.assertEqual(payload["run"]["vault_path"], str(team.resolve()))

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
                    "vault_path": str(vault),
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
                    "vault_path": str(vault),
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

    def test_wiki_pages_endpoint_accepts_vault_id(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            archive_vault = root / "archive-wiki"
            (archive_vault / "entities").mkdir(parents=True)
            (archive_vault / "concepts").mkdir(parents=True)
            (archive_vault / "entities" / "Archive.md").write_text("# Archive\n\nStored page.\n", encoding="utf-8")
            (archive_vault / "concepts" / "Archive-Concept.md").write_text(
                "# Archive Concept\n\nSee [[entities/Archive|Archive]].\n",
                encoding="utf-8",
            )
            (root / "config.yaml").write_text(
                f"""
vaults:
  default: archive
  profiles:
    archive:
      name: Archive
      path: {archive_vault}
models:
  providers: {{}}
connectors: {{}}
""",
                encoding="utf-8",
            )
            with _chdir(root):
                client = TestClient(create_app())
                response = client.get("/wiki/pages", params={"config_path": str(root / "config.yaml"), "vault_id": "archive"})
                content_response = client.get(
                    "/wiki/pages/content",
                    params={"config_path": str(root / "config.yaml"), "vault_id": "archive", "path": "concepts/Archive-Concept.md"},
                )
                links_response = client.get(
                    "/wiki/pages/links",
                    params={"config_path": str(root / "config.yaml"), "vault_id": "archive", "path": "concepts/Archive-Concept.md"},
                )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["vault_path"], str(archive_vault.resolve()))
        self.assertEqual(payload["vault_id"], "archive")
        self.assertEqual(payload["vault_name"], "Archive")
        self.assertEqual({page["path"] for page in payload["pages"]}, {"entities/Archive.md", "concepts/Archive-Concept.md"})
        self.assertEqual(content_response.status_code, 200)
        content_payload = content_response.json()
        self.assertEqual(content_payload["path"], "concepts/Archive-Concept.md")
        self.assertEqual(content_payload["vault_id"], "archive")
        self.assertEqual(content_payload["vault_name"], "Archive")
        self.assertIn("See [[entities/Archive|Archive]]", content_payload["content"])
        self.assertEqual(links_response.status_code, 200)
        links_payload = links_response.json()
        self.assertEqual(links_payload["vault_id"], "archive")
        self.assertEqual(links_payload["vault_name"], "Archive")
        self.assertEqual(links_payload["outbound_links"][0]["target_path"], "entities/Archive.md")

    def test_http_exception_uses_public_error_envelope(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            client = TestClient(create_app())

            response = client.get(
                "/wiki/pages/content",
                params={"vault_path": str(vault), "path": "concepts/Missing.md"},
            )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "KA-INPUT-002")
        self.assertEqual(response.json()["error"]["category"], "user_input_error")
        self.assertIn("Vault file not found", response.json()["error"]["message"])


if __name__ == "__main__":
    unittest.main()
