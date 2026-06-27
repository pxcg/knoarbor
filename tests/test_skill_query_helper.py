from __future__ import annotations

import argparse
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "integrations"
    / "skills"
    / "knoarbor-local"
    / "scripts"
    / "knoarbor.py"
)


def load_query_helper():
    spec = importlib.util.spec_from_file_location("knoarbor_skill_query_helper", SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load query helper from {SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class SkillQueryHelperTests(unittest.TestCase):
    def test_resolves_base_url_and_relative_vault_from_config(self) -> None:
        helper = load_query_helper()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "config.yaml"
            config_path.write_text(
                "server:\n  host: 127.0.0.1\n  port: 8123\nvault:\n  path: ./vaults/all\n",
                encoding="utf-8",
            )

            config = helper._load_yaml(config_path)

            self.assertEqual(helper._base_url_from_config(config), "http://127.0.0.1:8123")
            self.assertEqual(helper._vault_path_from_config(config, config_path), str((root / "vaults" / "all").resolve()))

    def test_resolves_default_vault_profile_from_config(self) -> None:
        helper = load_query_helper()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "config.yaml"
            config_path.write_text(
                "vaults:\n"
                "  default: team\n"
                "  profiles:\n"
                "    personal:\n"
                "      name: Personal\n"
                "      path: ./vaults/all\n"
                "    team:\n"
                "      name: Team\n"
                "      path: ./team-wiki\n"
                "vault:\n"
                "  path: ./vaults/all\n",
                encoding="utf-8",
            )

            config = helper._load_yaml(config_path)

        self.assertEqual(helper._vault_path_from_config(config, config_path), str((root / "team-wiki").resolve()))

    def test_runtime_resolves_requested_vault_id_from_config(self) -> None:
        helper = load_query_helper()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "config.yaml"
            config_path.write_text(
                "server:\n"
                "  host: 127.0.0.1\n"
                "  port: 8123\n"
                "vaults:\n"
                "  default: personal\n"
                "  profiles:\n"
                "    personal:\n"
                "      name: Personal\n"
                "      path: ./vaults/all\n"
                "    team:\n"
                "      name: Team\n"
                "      path: ./team-wiki\n",
                encoding="utf-8",
            )

            runtime = helper._runtime(
                argparse.Namespace(
                    base_url=None,
                    vault=None,
                    vault_id="team",
                    config=str(config_path),
                    timeout=1,
                    format="json",
                )
            )

        self.assertEqual(runtime.vault_id, "team")
        self.assertEqual(runtime.vault_name, "Team")
        self.assertEqual(runtime.vault_path, str((root / "team-wiki").resolve()))

    def test_runtime_keeps_missing_requested_vault_id_unresolved(self) -> None:
        helper = load_query_helper()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "config.yaml"
            config_path.write_text(
                "server:\n"
                "  host: 127.0.0.1\n"
                "  port: 8123\n"
                "vaults:\n"
                "  default: personal\n"
                "  profiles:\n"
                "    personal:\n"
                "      name: Personal\n"
                "      path: ./vaults/all\n",
                encoding="utf-8",
            )

            runtime = helper._runtime(
                argparse.Namespace(
                    base_url=None,
                    vault=None,
                    vault_id="missing",
                    config=str(config_path),
                    timeout=1,
                    format="json",
                )
            )

        self.assertEqual(runtime.vault_id, "missing")
        self.assertIsNone(runtime.vault_path)

    def test_prefers_runtime_endpoint_next_to_config(self) -> None:
        helper = load_query_helper()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "config.yaml"
            config_path.write_text(
                "server:\n  host: 127.0.0.1\n  port: 8123\nvault:\n  path: ./vaults/all\n",
                encoding="utf-8",
            )
            endpoint_dir = root / ".knoarbor"
            endpoint_dir.mkdir()
            (endpoint_dir / "endpoint.json").write_text(
                '{"base_url": "http://127.0.0.1:8124", "vault_path": "/tmp/endpoint-wiki"}',
                encoding="utf-8",
            )

            endpoint = helper._runtime_endpoint_data(config_path)
            self.assertEqual(helper._base_url_from_runtime_endpoint(endpoint), "http://127.0.0.1:8124")
            self.assertEqual(helper._vault_path_from_runtime_endpoint(endpoint), "/tmp/endpoint-wiki")

    def test_config_lookup_uses_current_project_candidates(self) -> None:
        helper = load_query_helper()
        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = Path.cwd()
            try:
                os.chdir(tmp)
                candidates = [str(item) for item in helper._config_candidates(None)]
            finally:
                os.chdir(old_cwd)

        self.assertIn(str((Path(tmp) / "config.yaml").resolve()), candidates)
        self.assertNotIn(str(Path.home() / "Projects" / "KnoArbor" / "config.yaml"), candidates)
        self.assertNotIn(str(Path.home() / "Projects" / "LLMWiki" / "config.yaml"), candidates)

    def test_runtime_uses_service_context_when_config_is_missing(self) -> None:
        helper = load_query_helper()

        def fake_get_json(url: str, *, timeout: float) -> dict[str, str]:
            self.assertEqual(url, "http://127.0.0.1:8123/runtime")
            self.assertEqual(timeout, 1)
            return {
                "base_url": "http://127.0.0.1:8123",
                "config_path": "/tmp/knoarbor/config.yaml",
                "vault_path": "/tmp/knoarbor/wiki",
            }

        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = Path.cwd()
            runtime_dir = Path(tmp) / "runtime"
            runtime_dir.mkdir()
            try:
                os.chdir(tmp)
                with patch.dict(os.environ, {"KNOARBOR_RUNTIME_DIR": str(runtime_dir)}), patch.object(helper, "_get_json", side_effect=fake_get_json):
                    runtime = helper._runtime(
                        argparse.Namespace(
                            base_url="http://127.0.0.1:8123",
                            vault=None,
                            config=None,
                            timeout=1,
                            format="json",
                        )
                    )
            finally:
                os.chdir(old_cwd)

        self.assertEqual(runtime.base_url, "http://127.0.0.1:8123")
        self.assertEqual(runtime.vault_path, "/tmp/knoarbor/wiki")
        self.assertEqual(runtime.config_path, Path("/tmp/knoarbor/config.yaml"))

    def test_runtime_uses_user_endpoint_before_default_port(self) -> None:
        helper = load_query_helper()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime_dir = root / "runtime"
            runtime_dir.mkdir()
            (runtime_dir / "endpoint.json").write_text(
                json.dumps(
                    {
                        "base_url": "http://127.0.0.1:8124",
                        "config_path": "/tmp/knoarbor/config.yaml",
                        "vault_path": "/tmp/knoarbor/wiki",
                    }
                ),
                encoding="utf-8",
            )
            old_cwd = Path.cwd()
            try:
                os.chdir(root)
                with patch.dict(os.environ, {"KNOARBOR_RUNTIME_DIR": str(runtime_dir)}), patch.object(helper, "_get_json") as get_json:
                    runtime = helper._runtime(
                        argparse.Namespace(
                            base_url=None,
                            vault=None,
                            config=None,
                            timeout=1,
                            format="json",
                        )
                    )
            finally:
                os.chdir(old_cwd)

        self.assertEqual(runtime.base_url, "http://127.0.0.1:8124")
        self.assertEqual(runtime.vault_path, "/tmp/knoarbor/wiki")
        self.assertEqual(runtime.config_path, Path("/tmp/knoarbor/config.yaml"))
        get_json.assert_not_called()

    def test_runtime_resolves_requested_vault_id_from_user_endpoint_profiles(self) -> None:
        helper = load_query_helper()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime_dir = root / "runtime"
            runtime_dir.mkdir()
            (runtime_dir / "endpoint.json").write_text(
                json.dumps(
                    {
                        "base_url": "http://127.0.0.1:8124",
                        "config_path": "/tmp/knoarbor/config.yaml",
                        "vault_id": "personal",
                        "vault_name": "Personal",
                        "vault_path": "/tmp/knoarbor/personal",
                        "vaults": [
                            {"id": "personal", "name": "Personal", "path": "/tmp/knoarbor/personal"},
                            {"id": "team", "name": "Team", "path": "/tmp/knoarbor/team"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            old_cwd = Path.cwd()
            try:
                os.chdir(root)
                with patch.dict(os.environ, {"KNOARBOR_RUNTIME_DIR": str(runtime_dir)}), patch.object(helper, "_get_json") as get_json:
                    runtime = helper._runtime(
                        argparse.Namespace(
                            base_url=None,
                            vault=None,
                            vault_id="team",
                            config=None,
                            timeout=1,
                            format="json",
                        )
                    )
            finally:
                os.chdir(old_cwd)

        self.assertEqual(runtime.base_url, "http://127.0.0.1:8124")
        self.assertEqual(runtime.vault_id, "team")
        self.assertEqual(runtime.vault_name, "Team")
        self.assertEqual(runtime.vault_path, "/tmp/knoarbor/team")
        self.assertEqual(runtime.config_path, Path("/tmp/knoarbor/config.yaml"))
        self.assertEqual(len(runtime.vaults), 2)
        get_json.assert_not_called()

    def test_missing_requested_vault_error_lists_available_vaults(self) -> None:
        helper = load_query_helper()
        runtime = helper.Runtime(
            base_url="http://127.0.0.1:8123",
            vault_path=None,
            config_path=Path("/tmp/config.yaml"),
            timeout=1,
            output_format="text",
            vault_id="missing",
            vaults=[
                {"id": "personal", "name": "Personal", "path": "/tmp/personal"},
                {"id": "team", "name": "Team", "path": "/tmp/team"},
            ],
        )

        with self.assertRaises(SystemExit) as raised, redirect_stderr(io.StringIO()) as stderr:
            helper._require_vault(runtime)

        self.assertEqual(raised.exception.code, 2)
        message = stderr.getvalue()
        self.assertIn("Requested vault ID: missing", message)
        self.assertIn("Available vault IDs: personal (Personal), team (Team)", message)

    def test_formats_knoarbor_error_envelope(self) -> None:
        helper = load_query_helper()
        error = urllib.error.HTTPError(
            url="http://127.0.0.1:8000/lint",
            code=422,
            msg="Unprocessable Entity",
            hdrs={},
            fp=io.BytesIO(
                b'{"error":{"code":"KA-INPUT-001","message":"Missing scope","hint":"Provide maintenance scope.","details":{"field":"scope"}}}'
            ),
        )

        message = helper._format_http_error(error)

        self.assertIn("HTTP 422", message)
        self.assertIn("[KA-INPUT-001] Missing scope", message)
        self.assertIn("hint: Provide maintenance scope.", message)
        self.assertIn('"field": "scope"', message)

    def test_formats_retrieval_response_for_host_ai(self) -> None:
        helper = load_query_helper()
        text = helper._format_query(
            {
                "query": "Agent Loop",
                "retrieval_mode": "machine_graph_led_bm25_balanced",
                "stats": {"vault_path": "/tmp/vaults/all"},
                "results": [
                    {
                        "path": "Agent-Loop.md",
                        "title": "Agent Loop",
                        "relevance": "high",
                        "match_kind": "direct",
                        "summary": "Agent Loop summary.",
                        "claims": ["Observe, think, act."],
                    }
                ],
                "context_pack": "context",
            }
        )

        self.assertIn("Agent Loop (Agent-Loop.md) [high, direct]", text)
        self.assertIn("Vault: /tmp/vaults/all", text)
        self.assertIn("Context Pack:", text)

    def test_formats_multi_vault_retrieval_response_for_host_ai(self) -> None:
        helper = load_query_helper()
        text = helper._format_query(
            {
                "query": "Agent Loop",
                "retrieval_mode": "machine_graph_led_bm25_balanced",
                "stats": {"multi_vault": True, "vault_count": 2},
                "results": [
                    {
                        "vault_id": "personal",
                        "vault_name": "Personal",
                        "path": "Agent-Loop.md",
                        "title": "Agent Loop",
                        "relevance": "high",
                        "match_kind": "direct",
                    },
                    {
                        "vault_id": "team",
                        "vault_name": "Team",
                        "path": "OpenClaw.md",
                        "title": "OpenClaw",
                        "relevance": "medium",
                        "match_kind": "related",
                    },
                ],
            }
        )

        self.assertIn("Personal · Agent Loop (Agent-Loop.md)", text)
        self.assertIn("Team · OpenClaw (OpenClaw.md)", text)

    def test_query_command_can_search_all_vaults_without_resolved_vault_path(self) -> None:
        helper = load_query_helper()
        runtime = helper.Runtime(
            base_url="http://127.0.0.1:8123",
            vault_path=None,
            config_path=Path("/tmp/config.yaml"),
            timeout=1,
            output_format="json",
        )
        args = argparse.Namespace(
            query="Agent Loop",
            mode="balanced",
            max_results=6,
            page_dirs=[],
            include_related=True,
            auto=True,
            all_vaults=True,
            query_vault_ids=[],
        )

        with patch.object(helper, "_post_json", return_value={"query": "Agent Loop", "results": []}) as post_json, redirect_stdout(io.StringIO()):
            exit_code = helper._cmd_query(args, runtime)

        self.assertEqual(exit_code, 0)
        payload = post_json.call_args.args[1]
        self.assertTrue(payload["all_vaults"])
        self.assertEqual(payload["vault_ids"], [])
        self.assertIsNone(payload["vault_path"])
        self.assertEqual(payload["config_path"], "/tmp/config.yaml")

    def test_query_command_can_search_selected_vault_ids_without_resolved_vault_path(self) -> None:
        helper = load_query_helper()
        runtime = helper.Runtime(
            base_url="http://127.0.0.1:8123",
            vault_path=None,
            config_path=Path("/tmp/config.yaml"),
            timeout=1,
            output_format="json",
        )
        args = argparse.Namespace(
            query="Agent Loop",
            mode="balanced",
            max_results=6,
            page_dirs=[],
            include_related=True,
            auto=True,
            all_vaults=False,
            query_vault_ids=["personal", "team"],
        )

        with patch.object(helper, "_post_json", return_value={"query": "Agent Loop", "results": []}) as post_json, redirect_stdout(io.StringIO()):
            exit_code = helper._cmd_query(args, runtime)

        self.assertEqual(exit_code, 0)
        payload = post_json.call_args.args[1]
        self.assertFalse(payload["all_vaults"])
        self.assertEqual(payload["vault_ids"], ["personal", "team"])
        self.assertIsNone(payload["vault_path"])

    def test_page_read_uses_resolved_vault_path_from_requested_vault_id(self) -> None:
        helper = load_query_helper()
        runtime = helper.Runtime(
            base_url="http://127.0.0.1:8123",
            vault_path="/tmp/team-wiki",
            config_path=Path("/tmp/config.yaml"),
            timeout=1,
            output_format="json",
            vault_id="team",
            vault_name="Team",
        )
        args = argparse.Namespace(page_command="read", path="Agent-Loop.md")

        with patch.object(helper, "_get_json", return_value={"path": "Agent-Loop.md", "content": "# Agent Loop"}) as get_json, redirect_stdout(io.StringIO()):
            exit_code = helper._cmd_page(args, runtime)

        self.assertEqual(exit_code, 0)
        url = get_json.call_args.args[0]
        self.assertIn("/wiki/pages/content", url)
        self.assertIn("vault_path=%2Ftmp%2Fteam-wiki", url)
        self.assertIn("vault_id=team", url)
        self.assertIn("config_path=%2Ftmp%2Fconfig.yaml", url)
        self.assertIn("path=Agent-Loop.md", url)

    def test_vaults_command_uses_public_vaults_endpoint(self) -> None:
        helper = load_query_helper()
        runtime = helper.Runtime(
            base_url="http://127.0.0.1:8123",
            vault_path="/tmp/personal",
            config_path=Path("/tmp/config.yaml"),
            timeout=1,
            output_format="text",
            vault_id="personal",
            vault_name="Personal",
        )
        args = argparse.Namespace(vaults_command="list")

        with patch.object(
            helper,
            "_get_json",
            return_value={
                "schema_version": "vaults.v1",
                "default_vault_id": "personal",
                "vaults": [{"id": "personal", "name": "Personal", "path": "/tmp/personal", "active": True, "exists": True}],
            },
        ) as get_json, redirect_stdout(io.StringIO()) as stdout:
            exit_code = helper._cmd_vaults(args, runtime)

        self.assertEqual(exit_code, 0)
        self.assertIn("/vaults", get_json.call_args.args[0])
        self.assertIn("config_path=%2Ftmp%2Fconfig.yaml", get_json.call_args.args[0])
        self.assertIn("* personal · Personal · available", stdout.getvalue())

    def test_page_relations_uses_resolved_vault_path_from_requested_vault_id(self) -> None:
        helper = load_query_helper()
        runtime = helper.Runtime(
            base_url="http://127.0.0.1:8123",
            vault_path="/tmp/team-wiki",
            config_path=Path("/tmp/config.yaml"),
            timeout=1,
            output_format="json",
            vault_id="team",
            vault_name="Team",
        )
        args = argparse.Namespace(page_command="relations", path="Agent-Loop.md")

        with patch.object(helper, "_get_json", return_value={"path": "Agent-Loop.md", "outgoing_pages": [], "incoming_pages": []}) as get_json, redirect_stdout(io.StringIO()):
            exit_code = helper._cmd_page(args, runtime)

        self.assertEqual(exit_code, 0)
        url = get_json.call_args.args[0]
        self.assertIn("/wiki/pages/relations", url)
        self.assertIn("vault_path=%2Ftmp%2Fteam-wiki", url)
        self.assertIn("vault_id=team", url)
        self.assertIn("config_path=%2Ftmp%2Fconfig.yaml", url)
        self.assertIn("path=Agent-Loop.md", url)

    def test_sources_catalog_uses_public_sources_endpoint(self) -> None:
        helper = load_query_helper()
        runtime = helper.Runtime(
            base_url="http://127.0.0.1:8123",
            vault_path="/tmp/team-wiki",
            config_path=Path("/tmp/config.yaml"),
            timeout=1,
            output_format="json",
            vault_id="team",
            vault_name="Team",
        )
        args = argparse.Namespace(sources_command="catalog", connector=["codex"])

        with patch.object(helper, "_get_json", return_value={"schema_version": "source_catalog.v1", "connectors": []}) as get_json, redirect_stdout(io.StringIO()):
            exit_code = helper._cmd_sources(args, runtime)

        self.assertEqual(exit_code, 0)
        url = get_json.call_args.args[0]
        self.assertIn("/sources", url)
        self.assertIn("config_path=%2Ftmp%2Fconfig.yaml", url)
        self.assertIn("connector=codex", url)

    def test_formats_sources_catalog_for_host_ai(self) -> None:
        helper = load_query_helper()
        text = helper._format_sources_catalog(
            {
                "connectors": [
                    {
                        "name": "codex",
                        "version": "codex@1",
                        "source_types": ["codex_chat"],
                        "supports_checkpoint": True,
                        "supports_segmentation_hint": True,
                    }
                ]
            }
        )

        self.assertIn("Source connectors: 1", text)
        self.assertIn("codex (codex@1) -> codex_chat", text)

    def test_runs_list_can_search_all_vaults(self) -> None:
        helper = load_query_helper()
        runtime = helper.Runtime(
            base_url="http://127.0.0.1:8123",
            vault_path=None,
            config_path=Path("/tmp/config.yaml"),
            timeout=1,
            output_format="json",
        )
        args = argparse.Namespace(runs_command="list", active_only=False, limit=10, all_vaults=True)

        with patch.object(helper, "_get_json", return_value={"runs": []}) as get_json, redirect_stdout(io.StringIO()):
            exit_code = helper._cmd_runs(args, runtime)

        self.assertEqual(exit_code, 0)
        url = get_json.call_args.args[0]
        self.assertIn("/runs", url)
        self.assertIn("all_vaults=true", url)
        self.assertIn("config_path=%2Ftmp%2Fconfig.yaml", url)

    def test_report_list_can_search_all_vaults(self) -> None:
        helper = load_query_helper()
        runtime = helper.Runtime(
            base_url="http://127.0.0.1:8123",
            vault_path=None,
            config_path=Path("/tmp/config.yaml"),
            timeout=1,
            output_format="json",
        )
        args = argparse.Namespace(report_command="list", all_vaults=True)

        with patch.object(helper, "_get_json", return_value={"reports": []}) as get_json, redirect_stdout(io.StringIO()):
            exit_code = helper._cmd_report(args, runtime)

        self.assertEqual(exit_code, 0)
        url = get_json.call_args.args[0]
        self.assertIn("/reports", url)
        self.assertIn("all_vaults=true", url)
        self.assertIn("config_path=%2Ftmp%2Fconfig.yaml", url)

    def test_ingest_command_sends_vault_id(self) -> None:
        helper = load_query_helper()
        runtime = helper.Runtime(
            base_url="http://127.0.0.1:8123",
            vault_path="/tmp/team-wiki",
            config_path=Path("/tmp/config.yaml"),
            timeout=1,
            output_format="json",
            vault_id="team",
            vault_name="Team",
        )
        args = argparse.Namespace(
            ingest_command="connector",
            execution="queued",
            write=True,
            write_report=True,
            append_ledger=True,
            provider=None,
            max_tokens=None,
            all=True,
            names=[],
        )

        with patch.object(helper, "_post_json", return_value={"flow": "ingest", "status": "queued"}) as post_json, redirect_stdout(io.StringIO()):
            exit_code = helper._cmd_ingest(args, runtime)

        self.assertEqual(exit_code, 0)
        payload = post_json.call_args.args[1]
        self.assertEqual(payload["vault_id"], "team")
        self.assertEqual(payload["vault_path"], "/tmp/team-wiki")
        self.assertEqual(payload["config_path"], "/tmp/config.yaml")

    def test_lint_command_sends_vault_id(self) -> None:
        helper = load_query_helper()
        runtime = helper.Runtime(
            base_url="http://127.0.0.1:8123",
            vault_path="/tmp/team-wiki",
            config_path=Path("/tmp/config.yaml"),
            timeout=1,
            output_format="json",
            vault_id="team",
            vault_name="Team",
        )
        args = argparse.Namespace(
            execution="queued",
            write=True,
            write_report=True,
            append_ledger=True,
            provider=None,
            max_tokens=None,
            mode="semantic_structural",
            profile="standard",
            apply_safe_fixes=True,
            auto_apply_reviewed=True,
            scope_pages=[],
        )

        with patch.object(helper, "_post_json", return_value={"flow": "lint", "status": "queued"}) as post_json, redirect_stdout(io.StringIO()):
            exit_code = helper._cmd_lint(args, runtime)

        self.assertEqual(exit_code, 0)
        payload = post_json.call_args.args[1]
        self.assertEqual(payload["vault_id"], "team")
        self.assertEqual(payload["vault_path"], "/tmp/team-wiki")
        self.assertEqual(payload["config_path"], "/tmp/config.yaml")

    def test_auto_query_settings_keep_balanced_by_default(self) -> None:
        helper = load_query_helper()
        settings = helper._query_settings(
            argparse.Namespace(
                auto=True,
                query="Agent Loop 是什么",
                mode="balanced",
                max_results=6,
            )
        )

        self.assertEqual(settings["mode"], "balanced")
        self.assertEqual(settings["max_results"], 4)

    def test_auto_query_settings_promote_detail_requests_to_deep_mode(self) -> None:
        helper = load_query_helper()
        settings = helper._query_settings(
            argparse.Namespace(
                auto=True,
                query="逐段分析 Agent Loop 页面全文",
                mode="balanced",
                max_results=6,
            )
        )

        self.assertEqual(settings["mode"], "deep")

    def test_auto_query_settings_can_be_disabled(self) -> None:
        helper = load_query_helper()
        settings = helper._query_settings(
            argparse.Namespace(
                auto=False,
                query="逐段分析 Agent Loop 页面全文",
                mode="balanced",
                max_results=6,
            )
        )

        self.assertEqual(settings["mode"], "balanced")
        self.assertEqual(settings["max_results"], 6)

    def test_check_mode_reports_service_and_vault(self) -> None:
        helper = load_query_helper()

        with patch.object(helper, "_get_json", return_value={"status": "ok"}), redirect_stdout(io.StringIO()):
            exit_code = helper._cmd_check(
                argparse.Namespace(),
                helper.Runtime(
                    base_url="http://127.0.0.1:8123",
                    vault_path="/tmp/vaults/all",
                    config_path=Path("/tmp/config.yaml"),
                    timeout=1,
                    output_format="json",
                ),
            )

        self.assertEqual(exit_code, 0)

    def test_check_mode_fails_without_vault(self) -> None:
        helper = load_query_helper()

        with (
            patch.object(helper, "_get_json", return_value={"status": "ok"}),
            redirect_stdout(io.StringIO()),
            redirect_stderr(io.StringIO()),
        ):
            exit_code = helper._cmd_check(
                argparse.Namespace(),
                helper.Runtime(
                    base_url="http://127.0.0.1:8123",
                    vault_path=None,
                    config_path=Path("/tmp/config.yaml"),
                    timeout=1,
                    output_format="json",
                ),
            )

        self.assertEqual(exit_code, 1)

    def test_print_or_format_supports_text_output(self) -> None:
        helper = load_query_helper()
        runtime = helper.Runtime(
            base_url="http://127.0.0.1:8123",
            vault_path="/tmp/vaults/all",
            config_path=Path("/tmp/config.yaml"),
            timeout=1,
            output_format="text",
        )

        output = io.StringIO()
        with redirect_stdout(output):
            helper._print_or_format({"ok": True}, runtime, formatter=lambda _: "plain text")

        self.assertEqual(output.getvalue().strip(), "plain text")

    def test_print_or_format_supports_json_output(self) -> None:
        helper = load_query_helper()
        runtime = helper.Runtime(
            base_url="http://127.0.0.1:8123",
            vault_path="/tmp/vaults/all",
            config_path=Path("/tmp/config.yaml"),
            timeout=1,
            output_format="json",
        )

        output = io.StringIO()
        with redirect_stdout(output):
            helper._print_or_format({"ok": True}, runtime, formatter=lambda _: "plain text")

        self.assertIn('"ok": true', output.getvalue())


if __name__ == "__main__":
    unittest.main()
