from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.cli import main


class DesktopConfigCliTests(unittest.TestCase):
    def test_desktop_config_reads_and_writes_form_without_http(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_path = root / "config.yaml"
            vault_path = root / "vaults" / "default"
            config_path.write_text(
                "vault:\n"
                "  path: ./vaults/default\n"
                "models:\n"
                "  providers: {}\n",
                encoding="utf-8",
            )

            read_payload = self._run_cli(["--config", str(config_path), "desktop-config", "read-form", "--json"])
            self.assertEqual(read_payload["vault_path"], str(vault_path.resolve()))

            form_payload = {
                **read_payload,
                "project_name": "Desktop IPC",
                "providers": [
                    {
                        "name": "local",
                        "base_url": "http://127.0.0.1:11434/v1",
                        "api_key": "",
                        "model": "qwen3",
                    }
                ],
                "default_provider": "local",
            }
            form_payload["vaults"][0]["name"] = "Desktop IPC"
            form_payload.pop("diagnostics", None)

            write_payload = self._run_cli(
                ["--config", str(config_path), "desktop-config", "write-form", "--json"],
                stdin=json.dumps(form_payload),
            )

            self.assertTrue(write_payload["saved"])
            self.assertEqual(write_payload["summary"]["default_provider"], "local")
            saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["project"]["name"], "Desktop IPC")
            self.assertEqual(saved["models"]["providers"]["local"]["model"], "qwen3")

    def _run_cli(self, argv: list[str], *, stdin: str = "") -> dict[str, object]:
        stdout = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO(stdin)), redirect_stdout(stdout):
            exit_code = main(argv)
        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertIsInstance(payload, dict)
        return payload


if __name__ == "__main__":
    unittest.main()
