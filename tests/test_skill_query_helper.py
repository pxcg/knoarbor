from __future__ import annotations

import importlib.util
import argparse
import io
import sys
import tempfile
import unittest
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
    / "query.py"
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
            (endpoint_dir / "endpoint.json").write_text('{"base_url": "http://127.0.0.1:8124"}', encoding="utf-8")

            self.assertEqual(helper._base_url_from_runtime_endpoint(config_path), "http://127.0.0.1:8124")

    def test_config_lookup_does_not_fall_back_to_legacy_project_name(self) -> None:
        helper = load_query_helper()
        candidates = [str(item) for item in helper._config_candidates(None)]

        self.assertIn(str(Path.cwd() / "config.yaml"), candidates)
        self.assertIn(str(Path.home() / "Projects" / "KnoArbor" / "config.yaml"), candidates)
        self.assertNotIn(str(Path.home() / "Projects" / "LLMWiki" / "config.yaml"), candidates)

    def test_formats_retrieval_response_for_host_ai(self) -> None:
        helper = load_query_helper()
        text = helper._format_response(
            {
                "query": "Agent Loop",
                "retrieval_mode": "machine_hybrid_balanced",
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
        self.assertIn("Context Pack:", text)

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
            exit_code = helper._run_check(
                "http://127.0.0.1:8123",
                "/tmp/wiki",
                Path("/tmp/config.yaml"),
                timeout=1,
                raw=True,
            )

        self.assertEqual(exit_code, 0)

    def test_check_mode_fails_without_vault(self) -> None:
        helper = load_query_helper()

        with (
            patch.object(helper, "_get_json", return_value={"status": "ok"}),
            redirect_stdout(io.StringIO()),
            redirect_stderr(io.StringIO()),
        ):
            exit_code = helper._run_check(
                "http://127.0.0.1:8123",
                None,
                Path("/tmp/config.yaml"),
                timeout=1,
                raw=True,
            )

        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
