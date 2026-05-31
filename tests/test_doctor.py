from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from knoarbor.cli import main
from knoarbor.entrypoints.api import create_app
from knoarbor.services.doctor import DoctorService


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
            vault = root / "wiki"
            notes = root / "notes"
            vault.mkdir()
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
                "      api_key_env: TEST_KNOARBOR_KEY\n"
                "connectors:\n"
                "  markdown:\n"
                "    enabled: true\n"
                "    settings:\n"
                "      roots:\n"
                f"        - {notes}\n",
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"TEST_KNOARBOR_KEY": "secret"}):
                report = DoctorService().run(config_path=config)

        self.assertEqual(report.status, "ok")
        checks = {check.name: check for check in report.checks}
        self.assertEqual(checks["models.api_key_env"].status, "ok")
        self.assertEqual(checks["connectors.markdown"].details["source_count"], 1)


class DoctorEntrypointTests(unittest.TestCase):
    def test_cli_doctor_json_returns_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            missing = Path(tmp_dir) / "missing.yaml"
            output = _capture_stdout(lambda: main(["--config", str(missing), "doctor", "--json"]))

        payload = json.loads(output["stdout"])
        self.assertEqual(output["exit_code"], 1)
        self.assertEqual(payload["schema_version"], "doctor_report.v1")
        self.assertEqual(payload["status"], "error")

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
