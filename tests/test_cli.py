from __future__ import annotations

import io
import json
import os
import socket
import sys
import tempfile
import unittest
from argparse import _SubParsersAction
from contextlib import contextmanager
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.cli import build_parser, main


@contextmanager
def _chdir(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


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
            "first-run",
            "ingest",
            "init",
            "lint",
            "lint-plan",
            "query",
            "query-feedback",
            "run-contract",
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
        for command in ("ingest", "lint", "query", "runs", "serve"):
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

    def test_query_command_accepts_vault_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            personal = root / "personal-wiki"
            team = root / "team-wiki"
            (personal / "concepts").mkdir(parents=True)
            (team / "concepts").mkdir(parents=True)
            (personal / "concepts" / "Personal.md").write_text("# Personal\n\n## Summary\n\nPersonal note.\n", encoding="utf-8")
            (team / "concepts" / "Team-Agent.md").write_text("# Team Agent\n\n## Summary\n\nTeam agent note.\n", encoding="utf-8")
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
models:
  providers: {{}}
connectors: {{}}
""",
                encoding="utf-8",
            )
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = main(["--config", str(config), "query", "--vault-id", "team", "team agent"])

        self.assertEqual(exit_code, 0)
        self.assertIn("Team Agent", output.getvalue())
        self.assertIn("concepts/Team-Agent.md", output.getvalue())
        self.assertNotIn("Personal.md", output.getvalue())

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

    def test_init_creates_local_config_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "my-wiki"
            output = io.StringIO()

            with _chdir(root), redirect_stdout(output):
                exit_code = main(["init", "--vault", str(vault)])

            config = root / "config.yaml"
            self.assertEqual(exit_code, 0)
            self.assertTrue(config.exists())
            self.assertTrue((vault / "SCHEMA.md").exists())
            self.assertIn("config:", output.getvalue())
            self.assertIn("created", output.getvalue())

    def test_first_run_creates_config_vault_and_prints_next_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "wiki"
            output = io.StringIO()

            with _chdir(root), redirect_stdout(output):
                exit_code = main(["first-run", "--vault", str(vault)])

            self.assertIn(exit_code, {0, 1})
            self.assertTrue((root / "config.yaml").exists())
            self.assertTrue((vault / "index.md").exists())
            self.assertTrue((vault / "raw" / "notes" / "agent-loop.md").exists())
            self.assertIn("Next steps:", output.getvalue())
            self.assertIn("example:", output.getvalue())

    def test_first_run_can_skip_bundled_example(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "wiki"
            output = io.StringIO()

            with _chdir(root), redirect_stdout(output):
                exit_code = main(["first-run", "--vault", str(vault), "--no-example"])

            self.assertIn(exit_code, {0, 1})
            self.assertFalse((vault / "raw" / "notes" / "agent-loop.md").exists())
            self.assertNotIn("example:", output.getvalue())
            self.assertNotIn("bundled example", output.getvalue())
            self.assertIn("Put Markdown notes", output.getvalue())

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
            runtime_dir = root / "runtime"
            (root / "wiki").mkdir()
            config = root / "config.yaml"
            config.write_text("vault:\n  path: ./wiki\n", encoding="utf-8")

            with patch.dict(os.environ, {"KNOARBOR_RUNTIME_DIR": str(runtime_dir)}), patch("uvicorn.run") as uvicorn_run, redirect_stdout(output):
                exit_code = main(["--config", str(config), "serve", "--host", "0.0.0.0", "--port", "8010"])
            user_endpoint_exists = (runtime_dir / "endpoint.json").exists()

        self.assertEqual(exit_code, 0)
        self.assertIn("KnoArbor UI: http://127.0.0.1:8010", output.getvalue())
        self.assertIn("UI alias: http://127.0.0.1:8010/ui", output.getvalue())
        self.assertIn("API docs: http://127.0.0.1:8010/docs", output.getvalue())
        self.assertTrue(user_endpoint_exists)
        uvicorn_run.assert_called_once()

    def test_serve_command_switches_when_port_is_occupied(self) -> None:
        output = io.StringIO()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime_dir = root / "runtime"
            (root / "wiki").mkdir()
            config = root / "config.yaml"
            config.write_text("vault:\n  path: ./wiki\n", encoding="utf-8")
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.bind(("127.0.0.1", 0))
                sock.listen(1)
                occupied_port = sock.getsockname()[1]

                with patch.dict(os.environ, {"KNOARBOR_RUNTIME_DIR": str(runtime_dir)}), patch("uvicorn.run") as uvicorn_run, redirect_stdout(output):
                    exit_code = main(["--config", str(config), "serve", "--host", "127.0.0.1", "--port", str(occupied_port)])

            endpoint = json.loads((root / ".knoarbor" / "endpoint.json").read_text(encoding="utf-8"))
            user_endpoint = json.loads((runtime_dir / "endpoint.json").read_text(encoding="utf-8"))

        self.assertEqual(exit_code, 0)
        self.assertIn(f"Configured port {occupied_port} is in use; using", output.getvalue())
        self.assertNotEqual(endpoint["port"], occupied_port)
        self.assertEqual(endpoint["base_url"], f"http://127.0.0.1:{endpoint['port']}")
        self.assertEqual(endpoint["config_path"], str(config.resolve()))
        self.assertEqual(endpoint["vault_path"], str((root / "wiki").resolve()))
        self.assertEqual(user_endpoint, endpoint)
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
        ingest_input_args = parser.parse_args(["ingest", "--input", "paper.pdf"])
        ingest_source_document_args = parser.parse_args(["ingest", "--source-document", "source.json"])
        ingest_recovery_args = parser.parse_args(["ingest", "--recover-run-id", "run-1"])
        runs_list_args = parser.parse_args(["runs", "list", "--active"])
        run_events_args = parser.parse_args(["runs", "events", "run-1"])
        run_events_late_vault_args = parser.parse_args(["runs", "events", "run-1", "--vault", "./wiki"])
        run_cancel_args = parser.parse_args(["runs", "cancel", "run-1"])
        lint_primary_args = parser.parse_args(["lint"])
        lint_args = parser.parse_args(["lint-plan"])

        self.assertEqual(init_args.command, "init")
        self.assertEqual(status_args.command, "status")
        self.assertEqual(doctor_args.command, "doctor")
        self.assertEqual(ingest_args.command, "ingest")
        self.assertIsNone(ingest_args.follow)
        self.assertFalse(ingest_no_follow_args.follow)
        self.assertIsNone(ingest_json_args.follow)
        self.assertEqual(ingest_input_args.input, "paper.pdf")
        self.assertEqual(ingest_source_document_args.source_document, "source.json")
        self.assertEqual(ingest_recovery_args.recover_run_id, "run-1")
        self.assertEqual(runs_list_args.runs_command, "list")
        self.assertTrue(runs_list_args.active)
        self.assertEqual(run_events_args.runs_command, "events")
        self.assertEqual(run_events_args.run_id, "run-1")
        self.assertEqual(run_events_late_vault_args.vault, "./wiki")
        self.assertEqual(run_cancel_args.runs_command, "cancel")
        self.assertEqual(run_cancel_args.run_id, "run-1")
        self.assertEqual(lint_primary_args.command, "lint")
        self.assertEqual(lint_primary_args.mode, "structural")
        self.assertEqual(lint_args.command, "lint-plan")

    def test_lint_command_prints_unified_maintenance_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = Path(tmp_dir) / "config.yaml"
            config.write_text(f"vault:\n  path: {tmp_dir}\n", encoding="utf-8")
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = main(["--config", str(config), "lint", "--no-follow"])

        self.assertEqual(exit_code, 0)
        self.assertIn("mode: semantic_structural", output.getvalue())
        self.assertIn("recommended_mode:", output.getvalue())

    def test_lint_run_follow_without_model_uses_structural_scan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = Path(tmp_dir) / "config.yaml"
            config.write_text(f"vault:\n  path: {tmp_dir}\n", encoding="utf-8")
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = main(["--config", str(config), "lint", "--follow"])

        self.assertEqual(exit_code, 0)
        self.assertIn("status=completed", output.getvalue())
        self.assertIn("summary:", output.getvalue())


if __name__ == "__main__":
    unittest.main()
