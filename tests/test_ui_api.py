from __future__ import annotations

import sys
import tempfile
import unittest
import re
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.entrypoints.api import create_app
from knoarbor.storage.wiki_init import init_wiki_vault
from knoarbor.storage.wiki_paths import content_root


class UiApiTests(unittest.TestCase):
    def test_ui_assets_are_served(self) -> None:
        client = TestClient(create_app())

        index = client.get("/ui")

        self.assertEqual(index.status_code, 200)
        self.assertIn("KnoArbor Console", index.text)
        asset_paths = set(re.findall(r'(?:src|href)="/ui/(assets/[^"]+\.(?:js|css))"', index.text))
        self.assertTrue(asset_paths)
        self.assertTrue(any(path.endswith(".js") for path in asset_paths))
        self.assertTrue(any(path.endswith(".css") for path in asset_paths))
        for asset_path in asset_paths:
            asset = client.get(f"/ui/{asset_path}")
            self.assertEqual(asset.status_code, 200)
        for root_asset in ("favicon.ico", "site.webmanifest", "knoarbor-logo.svg"):
            asset = client.get(f"/ui/{root_asset}")
            self.assertEqual(asset.status_code, 200)

    def test_ui_config_can_validate_and_save_local_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.yaml"
            vault_path = Path(tmp_dir) / "vaults" / "all"
            content = f"""
vault:
  path: {vault_path.as_posix()}
models:
  default_provider: deepseek
  providers:
    deepseek:
      base_url: https://api.deepseek.com
      api_key_env: DEEPSEEK_API_KEY
      model: deepseek-chat
"""
            client = TestClient(create_app())

            response = client.put("/ui/api/config", json={"config_path": str(config_path), "content": content})

            self.assertEqual(response.status_code, 200)
            self.assertTrue(config_path.exists())
            self.assertEqual(response.json()["summary"]["default_provider"], "deepseek")
            self.assertEqual(response.json()["summary"]["vault_path"], str(vault_path.resolve()))

    def test_ui_config_resolves_relative_vault_from_config_location(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.yaml"
            config_path.write_text(
                """
vault:
  path: ./vaults/all
models:
  providers: {}
""",
                encoding="utf-8",
            )
            client = TestClient(create_app())

            response = client.get("/ui/api/config", params={"config_path": str(config_path)})

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["summary"]["vault_path"], str((Path(tmp_dir) / "vaults" / "all").resolve()))

    def test_ui_config_form_round_trips_provider_json_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.yaml"
            vault_path = Path(tmp_dir) / "vaults" / "all"
            client = TestClient(create_app())

            response = client.put(
                "/ui/api/config/form",
                json={
                    "config_path": str(config_path),
                    "project_name": "KnoArbor",
                    "vault_path": str(vault_path),
                    "server_host": "127.0.0.1",
                    "server_port": 8000,
                    "default_provider": "local",
                    "default_max_tokens": 30000,
                    "request_timeout_seconds": 600,
                    "providers": [
                        {
                            "name": "local",
                            "base_url": "http://localhost:1234/v1",
                            "api_key_env": "LOCAL_API_KEY",
                            "model": "local-model",
                            "json_mode": False,
                            "context_window": 32768,
                            "max_output_tokens": 8000,
                            "api_key_configured": False,
                        }
                    ],
                    "openclaw_enabled": True,
                    "openclaw_sessions_dir": str(Path(tmp_dir) / "openclaw"),
                    "openclaw_raw_output_dir": str(vault_path / "raw" / "chats"),
                },
            )

            self.assertEqual(response.status_code, 200)
            saved = config_path.read_text(encoding="utf-8")
            self.assertIn("json_mode: false", saved)
            self.assertIn("openclaw:", saved)
            self.assertIn("sessions_dir:", saved)
            form_response = client.get("/ui/api/config/form", params={"config_path": str(config_path)})
            self.assertEqual(form_response.status_code, 200)
            self.assertFalse(form_response.json()["providers"][0]["json_mode"])
            self.assertEqual(form_response.json()["providers"][0]["context_window"], 32768)
            self.assertEqual(form_response.json()["providers"][0]["max_output_tokens"], 8000)
            self.assertTrue(form_response.json()["openclaw_enabled"])

    def test_ui_config_marks_local_model_provider_ready_without_api_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.yaml"
            config_path.write_text(
                """
vault:
  path: ./vaults/all
models:
  default_provider: vllm
  providers:
    cloud_missing_env:
      base_url: https://example.com/v1
      model: cloud-model
    ollama:
      base_url: http://localhost:11434/v1
      model: qwen2.5:14b
      json_mode: false
      context_window: 32768
      max_output_tokens: 8000
    vllm:
      base_url: http://127.0.0.1:8001/v1
      model: local-model
      json_mode: false
      context_window: 32768
      max_output_tokens: 8000
""",
                encoding="utf-8",
            )
            client = TestClient(create_app())

            form_response = client.get("/ui/api/config/form", params={"config_path": str(config_path)})
            self.assertEqual(form_response.status_code, 200)
            providers = {item["name"]: item for item in form_response.json()["providers"]}
            self.assertTrue(providers["ollama"]["api_key_configured"])
            self.assertTrue(providers["vllm"]["api_key_configured"])
            self.assertEqual(providers["vllm"]["context_window"], 32768)
            self.assertEqual(providers["vllm"]["max_output_tokens"], 8000)
            self.assertFalse(providers["cloud_missing_env"]["api_key_configured"])

            diagnostics_response = client.get("/ui/api/config/diagnostics", params={"config_path": str(config_path)})
            self.assertEqual(diagnostics_response.status_code, 200)
            diagnostics = {item["name"]: item for item in diagnostics_response.json()["providers"]}
            self.assertTrue(diagnostics["ollama"]["ok"])
            self.assertTrue(diagnostics["vllm"]["ok"])
            self.assertIn("context_window=32768", diagnostics["vllm"]["detail"])
            self.assertIn("max_output_tokens=8000", diagnostics["vllm"]["detail"])
            self.assertFalse(diagnostics["cloud_missing_env"]["ok"])
            self.assertEqual(diagnostics["cloud_missing_env"]["detail"], "api_key_env")

    def test_ui_config_form_saves_multiple_vault_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_path = root / "config.yaml"
            client = TestClient(create_app())

            response = client.put(
                "/ui/api/config/form",
                json={
                    "config_path": str(config_path),
                    "project_name": "Team Vault",
                    "vault_path": str(root / "team-wiki"),
                    "vault_id": "team",
                    "vaults": [
                        {"id": "personal", "name": "Personal Vault", "path": str(root / "vaults" / "all"), "active": False},
                        {"id": "team", "name": "Team Vault", "path": str(root / "team-wiki"), "active": True},
                    ],
                    "server_host": "127.0.0.1",
                    "server_port": 8000,
                    "default_provider": "",
                    "default_max_tokens": 30000,
                    "request_timeout_seconds": 600,
                    "providers": [],
                },
            )

            self.assertEqual(response.status_code, 200)
            saved = config_path.read_text(encoding="utf-8")
            self.assertIn("vaults:", saved)
            self.assertIn("default: team", saved)
            self.assertIn("name: Team Vault", saved)
            form_response = client.get("/ui/api/config/form", params={"config_path": str(config_path)})
            self.assertEqual(form_response.status_code, 200)
            payload = form_response.json()
            self.assertEqual(payload["vault_id"], "team")
            self.assertEqual(payload["vault_path"], str((root / "team-wiki").resolve()))
            self.assertEqual(len(payload["vaults"]), 2)

    def test_ui_config_form_saves_project_internal_paths_as_relative(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_path = root / "config.yaml"
            vault_path = root / "vaults" / "all"
            external_sessions = root.parent / f"{root.name}-external-codex"
            client = TestClient(create_app())

            response = client.put(
                "/ui/api/config/form",
                json={
                    "config_path": str(config_path),
                    "project_name": "KnoArbor",
                    "vault_path": str(vault_path),
                    "server_host": "127.0.0.1",
                    "server_port": 8000,
                    "default_provider": "local",
                    "default_max_tokens": 30000,
                    "request_timeout_seconds": 600,
                    "providers": [],
                    "codex_enabled": True,
                    "codex_sessions_dir": str(external_sessions),
                    "codex_raw_output_dir": str(vault_path / "raw" / "chats"),
                    "markdown_enabled": True,
                    "markdown_roots": [str(vault_path / "raw" / "notes")],
                    "markdown_raw_output_dir": str(vault_path / "raw" / "notes"),
                    "mineru_enabled": True,
                    "mineru_endpoint": "http://127.0.0.1:30000",
                    "mineru_input_dir": str(vault_path / "raw" / "documents" / "originals"),
                    "mineru_output_dir": str(vault_path / "raw" / "documents" / "markdown"),
                },
            )

            self.assertEqual(response.status_code, 200)
            saved = config_path.read_text(encoding="utf-8")
            self.assertIn("path: ./vaults/all", saved)
            self.assertIn("- ./vaults/all/raw/notes", saved)
            self.assertIn("raw_output_dir: ./vaults/all/raw/chats", saved)
            self.assertIn("input_dir: ./vaults/all/raw/documents/originals", saved)
            self.assertIn("output_dir: ./vaults/all/raw/documents/markdown", saved)
            self.assertIn(f"sessions_dir: {external_sessions.as_posix()}", saved)

    def test_ui_config_form_round_trips_mineru_advanced_options(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_path = root / "config.yaml"
            client = TestClient(create_app())

            response = client.put(
                "/ui/api/config/form",
                json={
                    "config_path": str(config_path),
                    "project_name": "KnoArbor",
                    "vault_path": str(root / "vaults" / "all"),
                    "server_host": "127.0.0.1",
                    "server_port": 8000,
                    "default_provider": "",
                    "default_max_tokens": 30000,
                    "request_timeout_seconds": 600,
                    "providers": [],
                    "markdown_enabled": True,
                    "markdown_roots": [],
                    "mineru_enabled": True,
                    "mineru_endpoint": "http://127.0.0.1:18000/file_parse",
                    "mineru_input_dir": str(root / "vaults" / "all" / "raw" / "documents" / "originals"),
                    "mineru_backend": "hybrid-auto-engine",
                    "mineru_parse_method": "ocr",
                    "mineru_timeout_seconds": 900,
                    "mineru_patterns": ["*.pdf", "*.docx"],
                    "mineru_recursive": False,
                    "mineru_return_md": True,
                    "mineru_return_middle_json": True,
                    "mineru_return_model_output": False,
                    "mineru_return_content_list": True,
                    "mineru_return_images": False,
                    "mineru_response_format_zip": False,
                    "mineru_lang_list": "ch,en",
                    "mineru_formula_enable": True,
                    "mineru_table_enable": False,
                    "mineru_server_url": "http://127.0.0.1:30000",
                    "mineru_start_page_id": 1,
                    "mineru_end_page_id": 9,
                    "mineru_extra_fields_json": '{"custom_flag": "on"}',
                },
            )

            self.assertEqual(response.status_code, 200)
            saved = config_path.read_text(encoding="utf-8")
            self.assertIn("mode: ocr", saved)
            self.assertIn("timeout_seconds: 900", saved)
            self.assertIn("backend: hybrid-auto-engine", saved)
            self.assertIn("return_middle_json: true", saved)
            self.assertIn("lang_list: ch,en", saved)
            self.assertIn("formula_enable: true", saved)
            self.assertIn("table_enable: false", saved)
            self.assertIn("server_url: http://127.0.0.1:30000", saved)
            self.assertIn("start_page_id: 1", saved)
            self.assertIn("end_page_id: 9", saved)
            self.assertIn("custom_flag: 'on'", saved)

            form_response = client.get("/ui/api/config/form", params={"config_path": str(config_path)})
            self.assertEqual(form_response.status_code, 200)
            payload = form_response.json()
            self.assertEqual(payload["mineru_backend"], "hybrid-auto-engine")
            self.assertEqual(payload["mineru_parse_method"], "ocr")
            self.assertEqual(payload["mineru_timeout_seconds"], 900)
            self.assertEqual(payload["mineru_patterns"], ["*.pdf", "*.docx"])
            self.assertFalse(payload["mineru_recursive"])
            self.assertTrue(payload["mineru_return_middle_json"])
            self.assertEqual(payload["mineru_lang_list"], "ch,en")
            self.assertTrue(payload["mineru_formula_enable"])
            self.assertFalse(payload["mineru_table_enable"])
            self.assertEqual(payload["mineru_server_url"], "http://127.0.0.1:30000")
            self.assertEqual(payload["mineru_start_page_id"], 1)
            self.assertEqual(payload["mineru_end_page_id"], 9)
            self.assertIn("custom_flag", payload["mineru_extra_fields_json"])

    def test_ui_config_form_uses_default_chat_session_dirs_when_enabled_without_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_path = root / "config.yaml"
            client = TestClient(create_app())

            response = client.put(
                "/ui/api/config/form",
                json={
                    "config_path": str(config_path),
                    "project_name": "KnoArbor",
                    "vault_path": str(root / "vaults" / "all"),
                    "server_host": "127.0.0.1",
                    "server_port": 8000,
                    "default_provider": "",
                    "default_max_tokens": 30000,
                    "request_timeout_seconds": 600,
                    "providers": [],
                    "codex_enabled": True,
                    "codex_sessions_dir": "",
                    "hermes_enabled": True,
                    "hermes_sessions_dir": "",
                    "openclaw_enabled": True,
                    "openclaw_sessions_dir": "",
                    "claude_code_enabled": True,
                    "claude_code_sessions_dir": "",
                    "markdown_enabled": True,
                    "markdown_roots": [],
                    "mineru_enabled": False,
                },
            )

            self.assertEqual(response.status_code, 200)
            saved = config_path.read_text(encoding="utf-8")
            self.assertIn("sessions_dir: ~/.codex/sessions", saved)
            self.assertIn("sessions_dir: ~/.hermes/sessions", saved)
            self.assertIn("sessions_dir: ~/.openclaw/agents/main/sessions", saved)
            self.assertIn("sessions_dir: ~/.claude/projects", saved)

    def test_ui_config_diagnostics_include_connector_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir) / "notes"
            root.mkdir()
            (root / "unit.md").write_text("# Unit\n", encoding="utf-8")
            config_path = Path(tmp_dir) / "config.yaml"
            config_path.write_text(
                f"""
vault:
  path: ./vaults/all
connectors:
  markdown:
    enabled: true
    settings:
      roots:
        - {root.as_posix()}
      raw_output_dir: ./vaults/all/raw/notes
models:
  providers: {{}}
""",
                encoding="utf-8",
            )
            client = TestClient(create_app())

            response = client.get("/ui/api/config/diagnostics", params={"config_path": str(config_path), "refresh_source_counts": "true"})

            self.assertEqual(response.status_code, 200)
            markdown = next(item for item in response.json()["connectors"] if item["name"] == "markdown")
            self.assertTrue(markdown["ok"])
            self.assertEqual(markdown["source_types"], ["markdown"])
            self.assertTrue(markdown["supports_checkpoint"])
            self.assertFalse(markdown["supports_segmentation_hint"])
            self.assertEqual(markdown["count"], 1)

            cached_response = client.get("/ui/api/config/diagnostics", params={"config_path": str(config_path)})
            self.assertEqual(cached_response.status_code, 200)
            cached_markdown = next(item for item in cached_response.json()["connectors"] if item["name"] == "markdown")
            self.assertEqual(cached_markdown["count"], 1)

    def test_ui_config_diagnostics_keep_contracts_on_missing_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            missing = Path(tmp_dir) / "missing"
            config_path = Path(tmp_dir) / "config.yaml"
            config_path.write_text(
                f"""
vault:
  path: ./vaults/all
connectors:
  markdown:
    enabled: true
    settings:
      roots:
        - {missing.as_posix()}
      raw_output_dir: ./vaults/all/raw/notes
models:
  providers: {{}}
""",
                encoding="utf-8",
            )
            client = TestClient(create_app())

            response = client.get("/ui/api/config/diagnostics", params={"config_path": str(config_path)})

            self.assertEqual(response.status_code, 200)
            markdown = next(item for item in response.json()["connectors"] if item["name"] == "markdown")
            self.assertFalse(markdown["ok"])
            self.assertEqual(markdown["code"], "path_missing")
            self.assertEqual(markdown["source_types"], ["markdown"])
            self.assertEqual(markdown["detail"], "")

    def test_ui_config_diagnostics_include_vault_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            personal = root / "personal-wiki"
            missing_team = root / "team-wiki"
            personal.mkdir()
            config_path = root / "config.yaml"
            config_path.write_text(
                f"""
vaults:
  default: personal
  profiles:
    personal:
      name: Personal
      path: {personal.as_posix()}
    team:
      name: Team
      path: {missing_team.as_posix()}
models:
  providers: {{}}
connectors: {{}}
""",
                encoding="utf-8",
            )
            client = TestClient(create_app())

            response = client.get("/ui/api/config/diagnostics", params={"config_path": str(config_path)})

            self.assertEqual(response.status_code, 200)
            paths = {item["name"]: item for item in response.json()["paths"]}
            self.assertIn("vault", paths)
            self.assertIn("vault.personal", paths)
            self.assertIn("vault.team", paths)
            self.assertTrue(paths["vault.personal"]["ok"])
            self.assertEqual(paths["vault.personal"]["detail"], "Personal (active)")
            self.assertFalse(paths["vault.team"]["ok"])
            self.assertEqual(paths["vault.team"]["code"], "path_missing")
            self.assertEqual(paths["vault.team"]["detail"], "Team (available)")

    def test_ui_config_rejects_inline_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.yaml"
            client = TestClient(create_app())

            response = client.put(
                "/ui/api/config",
                json={
                    "config_path": str(config_path),
                    "content": "vault:\n  path: ./vaults/all\nmodels:\n  providers:\n    x:\n      api_key: sk-testsecret123456\n",
                },
            )

            self.assertEqual(response.status_code, 400)
            self.assertIn("inline secrets", response.json()["detail"])

    def test_ui_status_returns_vault_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault_path = Path(tmp_dir) / "vaults" / "all"
            init_wiki_vault(vault_path)
            (content_root(vault_path) / "concepts" / "Unit.md").write_text(
                "# Unit\n\n## Summary\n\nA unit page.\n",
                encoding="utf-8",
            )
            (vault_path / "raw" / "notes" / "unit.md").write_text("# Unit", encoding="utf-8")
            client = TestClient(create_app())

            response = client.get("/ui/api/status", params={"vault_path": str(vault_path)})

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["pages"], 1)
            self.assertEqual(payload["directories"]["concepts"], 1)
            self.assertEqual(payload["raw_sources"], 1)
            self.assertIsInstance(payload["issues"], int)

    def test_ui_graph_returns_nodes_edges_and_stats(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault_path = Path(tmp_dir) / "vaults" / "all"
            init_wiki_vault(vault_path)
            source_path = content_root(vault_path) / "sources" / "Source.md"
            concept_path = content_root(vault_path) / "concepts" / "Agent-Loop.md"
            source_path.write_text(
                "# Source\n\n---\ntype: source\nsource: raw/notes/source.md\ntags: [source-digest]\n---\n\n"
                "## Summary\n\nSource summary.\n\n## Related Pages\n\n- [[concepts/Agent-Loop|Agent Loop]]\n",
                encoding="utf-8",
            )
            concept_path.write_text(
                "# Agent Loop\n\n---\ntype: concept\ntags: [agent]\n---\n\n## Summary\n\nAgent loop summary.\n",
                encoding="utf-8",
            )
            client = TestClient(create_app())

            response = client.get("/ui/api/graph", params={"vault_path": str(vault_path)})

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["stats"]["page_count"], 2)
            self.assertEqual(payload["stats"]["edge_count"], 1)
            self.assertEqual(payload["stats"]["orphan_count"], 0)
            self.assertEqual(payload["stats"]["directory_counts"]["sources"], 1)
            self.assertEqual(payload["stats"]["tag_counts"]["agent"], 1)
            self.assertEqual(payload["edges"][0]["source"], "sources/Source.md")
            self.assertEqual(payload["edges"][0]["target"], "concepts/Agent-Loop.md")


if __name__ == "__main__":
    unittest.main()
