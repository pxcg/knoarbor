from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


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


if __name__ == "__main__":
    unittest.main()
