from __future__ import annotations

import io
import json
import socket
import sys
import tempfile
import unittest
from argparse import _SubParsersAction
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.cli import build_parser, main


def _subcommand_names(parser) -> set[str]:
    for action in parser._actions:
        if isinstance(action, _SubParsersAction):
            return set(action.choices)
    return set()


class CliTests(unittest.TestCase):
    def test_cli_command_contract_is_stable_and_documented(self) -> None:
        parser = build_parser()
        commands = _subcommand_names(parser)
        docs = (Path(__file__).resolve().parents[1] / "docs" / "CLI.md").read_text(encoding="utf-8")

        expected_commands = {
            "contracts",
            "doctor",
            "ingest",
            "ingest-document",
            "ingest-file",
            "init",
            "lint",
            "lint-plan",
            "lint-run",
            "query",
            "query-feedback",
            "run-cancel",
            "run-contract",
            "run-events",
            "run-rerun-failed",
            "runs",
            "scan",
            "serve",
            "sources",
            "status",
        }

        self.assertEqual(commands, expected_commands)
        for command in sorted(commands):
            self.assertIn(f"### `{command}`", docs)

    def test_cli_help_keeps_core_command_groups_visible(self) -> None:
        output = io.StringIO()

        with redirect_stdout(output), self.assertRaises(SystemExit) as raised:
            main(["--help"])

        self.assertEqual(raised.exception.code, 0)
        help_text = output.getvalue()
        for command in ("ingest", "lint-run", "query", "runs", "serve"):
            self.assertIn(command, help_text)

    def test_cli_errors_include_code_and_hint(self) -> None:
        stderr = io.StringIO()

        with redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
            main(["--config", "/tmp/knoarbor-missing-config.yaml", "status"])

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("[KA-CFG-001]", stderr.getvalue())
        self.assertIn("hint:", stderr.getvalue())

    def test_query_command_prints_context_pack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            config = vault.parent / "config.yaml"
            config.write_text(f"vault:\n  path: {vault}\n", encoding="utf-8")
            (vault / "concepts" / "Agent-Loop.md").write_text(
                "# Agent Loop\n\n## Summary\n\nAgent loop uses observe, decide, act, and feedback.\n",
                encoding="utf-8",
            )
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = main(["--config", str(config), "query", "agent loop"])

            self.assertEqual(exit_code, 0)
            self.assertIn("Agent Loop", output.getvalue())
            self.assertIn("concepts/Agent-Loop.md", output.getvalue())
            self.assertTrue((vault / "maintenance" / "query_ledger.jsonl").exists())

    def test_query_command_can_write_query_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            (vault / "concepts").mkdir()
            config = vault.parent / "config.yaml"
            config.write_text(f"vault:\n  path: {vault}\n", encoding="utf-8")
            (vault / "concepts" / "Agent-Loop.md").write_text(
                "# Agent Loop\n\n## Summary\n\nAgent loop uses observe, decide, act, and feedback.\n",
                encoding="utf-8",
            )
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = main(["--config", str(config), "query", "agent loop", "--write-report"])

            self.assertEqual(exit_code, 0)
            self.assertIn("report: maintenance/query_report_", output.getvalue())
            reports = list((vault / "maintenance").glob("query_report_*.md"))
            self.assertEqual(len(reports), 1)
            self.assertIn("# Query Report", reports[0].read_text(encoding="utf-8"))

    def test_query_feedback_command_records_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            config = vault.parent / "config.yaml"
            config.write_text(f"vault:\n  path: {vault}\n", encoding="utf-8")
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = main(
                    [
                        "--config",
                        str(config),
                        "query-feedback",
                        "agent loop",
                        "--useful",
                        "--selected-path",
                        "concepts/Agent-Loop.md",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertIn("recorded: True", output.getvalue())
            self.assertTrue((vault / "maintenance" / "query_feedback_ledger.jsonl").exists())

    def test_scan_command_prints_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = Path(tmp_dir) / "config.yaml"
            config.write_text(f"vault:\n  path: {tmp_dir}\n", encoding="utf-8")
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = main(["--config", str(config), "scan"])

        self.assertEqual(exit_code, 0)
        self.assertIn("pages:", output.getvalue())
        self.assertIn("issues:", output.getvalue())

    def test_sources_command_prints_enabled_connector_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "wiki"
            notes = root / "notes"
            vault.mkdir()
            notes.mkdir()
            (notes / "note.md").write_text("# Note\n\nBody.", encoding="utf-8")
            config = root / "config.yaml"
            config.write_text(
                f"vault:\n  path: {vault}\n"
                "connectors:\n"
                "  markdown:\n"
                "    enabled: true\n"
                "    settings:\n"
                "      roots:\n"
                f"        - {notes}\n",
                encoding="utf-8",
            )
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = main(["--config", str(config), "sources"])

        self.assertEqual(exit_code, 0)
        self.assertIn("connectors: 1", output.getvalue())
        self.assertIn("items: 1", output.getvalue())
        self.assertIn("Note", output.getvalue())

    def test_sources_json_is_compact_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "wiki"
            notes = root / "notes"
            vault.mkdir()
            notes.mkdir()
            (notes / "note.md").write_text("# Note\n\nLong body.", encoding="utf-8")
            config = root / "config.yaml"
            config.write_text(
                f"vault:\n  path: {vault}\n"
                "connectors:\n"
                "  markdown:\n"
                "    enabled: true\n"
                "    settings:\n"
                "      roots:\n"
                f"        - {notes}\n",
                encoding="utf-8",
            )
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = main(["--config", str(config), "sources", "--json"])

        payload = json.loads(output.getvalue())
        content = payload["results"][0]["items"][0]["document"]["content"]
        self.assertEqual(exit_code, 0)
        self.assertNotIn("text", content)
        self.assertNotIn("sections", content)
        self.assertGreater(content["text_chars"], 0)

    def test_contracts_command_prints_known_contracts(self) -> None:
        output = io.StringIO()

        with redirect_stdout(output):
            exit_code = main(["contracts"])

        self.assertEqual(exit_code, 0)
        self.assertIn("source_normalize", output.getvalue())
        self.assertIn("lint_maintenance_review", output.getvalue())

    def test_cli_errors_use_public_error_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            missing_config = Path(tmp_dir) / "missing.yaml"
            error = io.StringIO()

            with redirect_stderr(error):
                with self.assertRaises(SystemExit) as raised:
                    main(["--config", str(missing_config), "status"])

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("[KA-CFG-001] user_input_error", error.getvalue())

    def test_serve_command_prints_management_ui_url(self) -> None:
        output = io.StringIO()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "wiki").mkdir()
            config = root / "config.yaml"
            config.write_text("vault:\n  path: ./wiki\n", encoding="utf-8")

            with patch("uvicorn.run") as uvicorn_run, redirect_stdout(output):
                exit_code = main(["--config", str(config), "serve", "--host", "0.0.0.0", "--port", "8010"])

        self.assertEqual(exit_code, 0)
        self.assertIn("KnoArbor UI: http://127.0.0.1:8010", output.getvalue())
        self.assertIn("UI alias: http://127.0.0.1:8010/ui", output.getvalue())
        self.assertIn("API docs: http://127.0.0.1:8010/docs", output.getvalue())
        uvicorn_run.assert_called_once()

    def test_serve_command_switches_when_port_is_occupied(self) -> None:
        output = io.StringIO()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "wiki").mkdir()
            config = root / "config.yaml"
            config.write_text("vault:\n  path: ./wiki\n", encoding="utf-8")
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.bind(("127.0.0.1", 0))
                sock.listen(1)
                occupied_port = sock.getsockname()[1]

                with patch("uvicorn.run") as uvicorn_run, redirect_stdout(output):
                    exit_code = main(["--config", str(config), "serve", "--host", "127.0.0.1", "--port", str(occupied_port)])

            endpoint = json.loads((root / ".knoarbor" / "endpoint.json").read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertIn(f"Configured port {occupied_port} is in use; using", output.getvalue())
        self.assertNotEqual(endpoint["port"], occupied_port)
        self.assertEqual(endpoint["base_url"], f"http://127.0.0.1:{endpoint['port']}")
        uvicorn_run.assert_called_once()
        self.assertEqual(uvicorn_run.call_args.kwargs["port"], endpoint["port"])

    def test_parser_exposes_local_semantic_workflow_commands(self) -> None:
        parser = build_parser()

        init_args = parser.parse_args(["init"])
        status_args = parser.parse_args(["status"])
        doctor_args = parser.parse_args(["doctor"])
        ingest_args = parser.parse_args(["ingest"])
        ingest_no_follow_args = parser.parse_args(["ingest", "--no-follow"])
        ingest_json_args = parser.parse_args(["ingest", "--json"])
        ingest_document_args = parser.parse_args(["ingest-document", "--input", "source.json"])
        ingest_file_args = parser.parse_args(["ingest-file", "--input", "paper.pdf"])
        lint_run_args = parser.parse_args(["lint-run"])
        lint_args = parser.parse_args(["lint-plan"])

        self.assertEqual(init_args.command, "init")
        self.assertEqual(status_args.command, "status")
        self.assertEqual(doctor_args.command, "doctor")
        self.assertEqual(ingest_args.command, "ingest")
        self.assertIsNone(ingest_args.follow)
        self.assertFalse(ingest_no_follow_args.follow)
        self.assertIsNone(ingest_json_args.follow)
        self.assertEqual(ingest_document_args.command, "ingest-document")
        self.assertEqual(ingest_file_args.command, "ingest-file")
        self.assertIsNone(ingest_file_args.follow)
        self.assertEqual(lint_run_args.command, "lint-run")
        self.assertEqual(lint_args.command, "lint-plan")

    def test_lint_run_command_prints_unified_maintenance_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = Path(tmp_dir) / "config.yaml"
            config.write_text(f"vault:\n  path: {tmp_dir}\n", encoding="utf-8")
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = main(["--config", str(config), "lint-run", "--no-follow"])

        self.assertEqual(exit_code, 0)
        self.assertIn("mode: semantic_structural", output.getvalue())
        self.assertIn("recommended_mode:", output.getvalue())

    def test_lint_run_follow_without_model_uses_structural_scan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = Path(tmp_dir) / "config.yaml"
            config.write_text(f"vault:\n  path: {tmp_dir}\n", encoding="utf-8")
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = main(["--config", str(config), "lint-run", "--follow"])

        self.assertEqual(exit_code, 0)
        self.assertIn("status=completed", output.getvalue())
        self.assertIn("summary:", output.getvalue())


if __name__ == "__main__":
    unittest.main()
