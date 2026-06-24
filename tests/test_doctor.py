from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from knoarbor.cli import main
from knoarbor.entrypoints.api import create_app
from knoarbor.semantic import ProviderHealthCheck
from knoarbor.services.doctor import DoctorService
from knoarbor.storage.wiki_init import init_wiki_vault


class DoctorServiceTests(unittest.TestCase):
    def test_reports_missing_config_without_throwing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            report = DoctorService().run(config_path=Path(tmp_dir) / "missing.yaml")

        self.assertEqual(report.status, "error")
        self.assertEqual(report.summary["error"], 1)
        self.assertEqual(report.checks[0].name, "config.exists")

    def test_reports_ready_minimal_markdown_setup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "vaults" / "all"
            notes = root / "notes"
            init_wiki_vault(vault)
            notes.mkdir()
            (vault / "pages" / "Note.md").write_text("# Note\n\nCompiled page.", encoding="utf-8")
            (notes / "note.md").write_text("# Note\n\nBody.", encoding="utf-8")
            config = root / "config.yaml"
            config.write_text(
                f"vault:\n  path: {vault}\n"
                "models:\n"
                "  default_provider: local\n"
                "  providers:\n"
                "    local:\n"
                "      base_url: http://127.0.0.1:11434/v1\n"
                "      model: qwen\n"
                "      context_window: 32768\n"
                "      max_output_tokens: 8000\n"
                "connectors:\n"
                "  markdown:\n"
                "    enabled: true\n"
                "    settings:\n"
                "      roots:\n"
                f"        - {notes}\n",
                encoding="utf-8",
            )
            with patch(
                "knoarbor.services.doctor.ModelGateway.check",
                return_value=ProviderHealthCheck(
                    available=True,
                    structured_output=True,
                    message="ok",
                    details={"models_list_valid": True, "model_count": 1, "model_ids": ["qwen"], "configured_model_found": True},
                ),
            ):
                report = DoctorService().run(config_path=config)

        self.assertEqual(report.status, "ok")
        checks = {check.name: check for check in report.checks}
        self.assertEqual(checks["models.api_key_env"].status, "ok")
        self.assertEqual(checks["models.endpoint"].status, "ok")
        self.assertEqual(checks["models.default_provider"].details["context_window"], 32768)
        self.assertEqual(checks["models.default_provider"].details["effective_max_tokens"], 8000)
        self.assertEqual(checks["models.structured_output"].status, "ok")
        self.assertEqual(checks["connectors.markdown"].details["source_count"], 1)
        self.assertEqual(checks["wiki.content"].status, "ok")
        self.assertTrue(report.next_steps)

    def test_reports_empty_vault_next_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "vaults" / "all"
            notes = root / "notes"
            vault.mkdir(parents=True)
            notes.mkdir()
            for name in ["SCHEMA.md", "index.md", "log.md", ".knoarborignore"]:
                (vault / name).write_text("", encoding="utf-8")
            (notes / "note.md").write_text("# Note\n\nBody.", encoding="utf-8")
            config = root / "config.yaml"
            config.write_text(
                f"vault:\n  path: {vault}\n"
                "models:\n"
                "  default_provider: local\n"
                "  providers:\n"
                "    local:\n"
                "      base_url: http://127.0.0.1:11434/v1\n"
                "      model: qwen\n"
                "connectors:\n"
                "  markdown:\n"
                "    enabled: true\n"
                "    settings:\n"
                "      roots:\n"
                f"        - {notes}\n",
                encoding="utf-8",
            )
            with patch(
                "knoarbor.services.doctor.ModelGateway.check",
                return_value=ProviderHealthCheck(
                    available=True,
                    structured_output=True,
                    message="ok",
                    details={"models_list_valid": True, "model_count": 1, "model_ids": ["qwen"], "configured_model_found": True},
                ),
            ):
                report = DoctorService().run(config_path=config)

        checks = {check.name: check for check in report.checks}
        self.assertEqual(report.status, "warning")
        self.assertEqual(checks["wiki.content"].status, "warning")
        self.assertTrue(any("ingest" in step for step in report.next_steps))

    def test_lightweight_doctor_skips_runtime_connector_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "vaults" / "all"
            missing_notes = root / "missing-notes"
            vault.mkdir(parents=True)
            for name in ["SCHEMA.md", "index.md", "log.md", ".knoarborignore"]:
                (vault / name).write_text("", encoding="utf-8")
            config = root / "config.yaml"
            config.write_text(
                f"vault:\n  path: {vault}\n"
                "models:\n"
                "  default_provider: local\n"
                "  providers:\n"
                "    local:\n"
                "      base_url: http://127.0.0.1:11434/v1\n"
                "      model: qwen\n"
                "connectors:\n"
                "  markdown:\n"
                "    enabled: true\n"
                "    settings:\n"
                "      roots:\n"
                f"        - {missing_notes}\n",
                encoding="utf-8",
            )

            report = DoctorService().run(config_path=config, check_model_runtime=False, check_connector_runtime=False)

        checks = {check.name: check for check in report.checks}
        self.assertEqual(checks["connectors.enabled"].status, "ok")
        self.assertNotIn("connectors.markdown", checks)

    def test_runtime_doctor_warns_when_local_provider_has_no_models(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "vaults" / "all"
            vault.mkdir(parents=True)
            for name in ["SCHEMA.md", "index.md", "log.md", ".knoarborignore"]:
                (vault / name).write_text("", encoding="utf-8")
            config = root / "config.yaml"
            config.write_text(
                f"vault:\n  path: {vault}\n"
                "models:\n"
                "  default_provider: ollama\n"
                "  providers:\n"
                "    ollama:\n"
                "      base_url: http://127.0.0.1:11434/v1\n"
                "      model: qwen3:14b\n"
                "      json_mode: false\n"
                "connectors: {}\n",
                encoding="utf-8",
            )
            with patch(
                "knoarbor.services.doctor.ModelGateway.check",
                return_value=ProviderHealthCheck(
                    available=True,
                    structured_output=False,
                    message="Provider endpoint responded to /models.",
                    details={"models_list_valid": True, "model_count": 0, "model_ids": [], "configured_model_found": False},
                ),
            ):
                report = DoctorService().run(config_path=config)

        checks = {check.name: check for check in report.checks}
        self.assertEqual(checks["models.endpoint"].status, "ok")
        self.assertEqual(checks["models.configured_model"].status, "warning")
        self.assertIn("no models", checks["models.configured_model"].message)
        self.assertTrue(any("qwen3:14b" in step for step in report.next_steps))

    def test_reports_all_vault_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            personal = root / "personal-wiki"
            missing_team = root / "missing-team-wiki"
            personal.mkdir()
            for name in ["SCHEMA.md", "index.md", "log.md", ".knoarborignore"]:
                (personal / name).write_text("", encoding="utf-8")
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
      path: {missing_team}
models:
  default_provider: local
  providers:
    local:
      base_url: http://127.0.0.1:11434/v1
      model: qwen
connectors: {{}}
""",
                encoding="utf-8",
            )

            report = DoctorService().run(config_path=config, check_model_runtime=False, check_connector_runtime=False)

        checks = {check.name: check for check in report.checks}
        self.assertEqual(checks["vault.profiles"].status, "ok")
        self.assertEqual(checks["vault.profiles"].details["active_vault_id"], "personal")
        self.assertEqual(checks["vault.profile.personal"].status, "ok")
        self.assertTrue(checks["vault.profile.personal"].details["active"])
        self.assertEqual(checks["vault.profile.team"].status, "warning")
        self.assertFalse(checks["vault.profile.team"].details["active"])


class DoctorEntrypointTests(unittest.TestCase):
    def test_cli_doctor_json_returns_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            missing = Path(tmp_dir) / "missing.yaml"
            output = _capture_stdout(lambda: main(["--config", str(missing), "doctor", "--json"]))

        payload = json.loads(output["stdout"])
        self.assertEqual(output["exit_code"], 1)
        self.assertEqual(payload["schema_version"], "doctor_report.v1")
        self.assertEqual(payload["status"], "error")
        self.assertTrue(payload["next_steps"])

    def test_api_doctor_returns_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            missing = Path(tmp_dir) / "missing.yaml"
            client = TestClient(create_app())
            response = client.get("/doctor", params={"config_path": str(missing)})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "error")


def _capture_stdout(callable_object):
    import io
    from contextlib import redirect_stdout

    output = io.StringIO()
    with redirect_stdout(output):
        exit_code = callable_object()
    return {"exit_code": exit_code, "stdout": output.getvalue()}
