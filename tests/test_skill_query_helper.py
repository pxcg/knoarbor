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
    / "query"
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
                "server:\n  host: 127.0.0.1\n  port: 8123\nvault:\n  path: ./wiki\n",
                encoding="utf-8",
            )

            config = helper._load_yaml(config_path)

            self.assertEqual(helper._base_url_from_config(config), "http://127.0.0.1:8123")
            self.assertEqual(helper._vault_path_from_config(config, config_path), str((root / "wiki").resolve()))

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
                "      path: ./wiki\n"
                "    team:\n"
                "      name: Team\n"
                "      path: ./team-wiki\n"
                "vault:\n"
                "  path: ./wiki\n",
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
                "      path: ./wiki\n"
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
                "      path: ./wiki\n",
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
                "server:\n  host: 127.0.0.1\n  port: 8123\nvault:\n  path: ./wiki\n",
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

    def test_config_lookup_does_not_fall_back_to_legacy_project_name(self) -> None:
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
                "retrieval_mode": "machine_hybrid_balanced",
                "stats": {"vault_path": "/tmp/wiki"},
                "results": [
                    {
                        "path": "concepts/Agent-Loop.md",
                        "title": "Agent Loop",
                        "relevance": "high",
                        "match_kind": "direct",
                        "summary": "Agent Loop summary.",
                        "key_points": ["Observe, think, act."],
                    }
                ],
                "context_pack": "context",
            }
        )

        self.assertIn("Agent Loop (concepts/Agent-Loop.md) [high, direct]", text)
        self.assertIn("Vault: /tmp/wiki", text)
        self.assertIn("Context Pack:", text)

    def test_formats_multi_vault_retrieval_response_for_host_ai(self) -> None:
        helper = load_query_helper()
        text = helper._format_query(
            {
                "query": "Agent Loop",
                "retrieval_mode": "machine_hybrid_balanced",
                "stats": {"multi_vault": True, "vault_count": 2},
                "results": [
                    {
                        "vault_id": "personal",
                        "vault_name": "Personal",
                        "path": "concepts/Agent-Loop.md",
                        "title": "Agent Loop",
                        "relevance": "high",
                        "match_kind": "direct",
                    },
                    {
                        "vault_id": "team",
                        "vault_name": "Team",
                        "path": "entities/OpenClaw.md",
                        "title": "OpenClaw",
                        "relevance": "medium",
                        "match_kind": "related",
                    },
                ],
            }
        )

        self.assertIn("Personal · Agent Loop (concepts/Agent-Loop.md)", text)
        self.assertIn("Team · OpenClaw (entities/OpenClaw.md)", text)

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
            context_format="compact",
            max_results=6,
            page_dirs=[],
            include_related=True,
            include_content=False,
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
            context_format="compact",
            max_results=6,
            page_dirs=[],
            include_related=True,
            include_content=False,
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

    def test_auto_query_settings_keep_compact_by_default(self) -> None:
        helper = load_query_helper()
        settings = helper._query_settings(
            argparse.Namespace(
                auto=True,
                query="Agent Loop 是什么",
                mode="balanced",
                context_format="compact",
                max_results=6,
                include_content=False,
            )
        )

        self.assertEqual(settings["mode"], "balanced")
        self.assertEqual(settings["context_format"], "compact")
        self.assertEqual(settings["max_results"], 4)
        self.assertFalse(settings["include_content"])

    def test_auto_query_settings_promote_full_content_requests(self) -> None:
        helper = load_query_helper()
        settings = helper._query_settings(
            argparse.Namespace(
                auto=True,
                query="逐段分析 Agent Loop 页面全文",
                mode="balanced",
                context_format="compact",
                max_results=6,
                include_content=False,
            )
        )

        self.assertEqual(settings["mode"], "deep")
        self.assertEqual(settings["context_format"], "full")
        self.assertTrue(settings["include_content"])

    def test_auto_query_settings_can_be_disabled(self) -> None:
        helper = load_query_helper()
        settings = helper._query_settings(
            argparse.Namespace(
                auto=False,
                query="逐段分析 Agent Loop 页面全文",
                mode="balanced",
                context_format="compact",
                max_results=6,
                include_content=False,
            )
        )

        self.assertEqual(settings["mode"], "balanced")
        self.assertEqual(settings["context_format"], "compact")
        self.assertEqual(settings["max_results"], 6)

    def test_check_mode_reports_service_and_vault(self) -> None:
        helper = load_query_helper()

        with patch.object(helper, "_get_json", return_value={"status": "ok"}), redirect_stdout(io.StringIO()):
            exit_code = helper._cmd_check(
                argparse.Namespace(),
                helper.Runtime(
                    base_url="http://127.0.0.1:8123",
                    vault_path="/tmp/wiki",
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
            vault_path="/tmp/wiki",
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
            vault_path="/tmp/wiki",
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
