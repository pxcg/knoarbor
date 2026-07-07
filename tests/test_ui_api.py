from __future__ import annotations

import sys
import tempfile
import unittest
import re
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.entrypoints.api import create_app
from knoarbor.storage.wiki_init import init_wiki_vault
from knoarbor.storage.vault_layout import raw_derived_asset_images_root
from knoarbor.storage.wiki_paths import content_root, source_digest_root


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

    def test_desktop_mode_does_not_serve_static_ui(self) -> None:
        with patch.dict("os.environ", {"KNOARBOR_DESKTOP": "1"}):
            client = TestClient(create_app())

        self.assertEqual(client.get("/ui").status_code, 404)
        self.assertEqual(client.get("/ui/assets/index.js").status_code, 404)

        with tempfile.TemporaryDirectory() as tmp_dir:
            response = client.get(
                "/ui/api/config/diagnostics",
                params={"config_path": str(Path(tmp_dir) / "config.yaml")},
            )

        self.assertEqual(response.status_code, 200)

    def test_vault_assets_read_raw_derived_asset_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault_path = Path(tmp_dir) / "vault"
            init_wiki_vault(vault_path)
            asset_dir = raw_derived_asset_images_root(vault_path)
            asset_dir.mkdir(parents=True, exist_ok=True)
            asset_path = asset_dir / "figure.png"
            asset_path.write_bytes(b"fake-png")
            client = TestClient(create_app())

            response = client.get(
                "/ui/api/vault-assets/images/figure.png",
                params={"vault_path": str(vault_path)},
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, b"fake-png")

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
      api_key: test-key
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
                            "api_key": "test-key",
                            "model": "local-model",
                            "json_mode": False,
                            "context_window": 32768,
                            "max_output_tokens": 8000,
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

    def test_ui_config_form_round_trips_image_generation_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.yaml"
            vault_path = Path(tmp_dir) / "vaults" / "default"
            client = TestClient(create_app())

            response = client.put(
                "/ui/api/config/form",
                json={
                    "config_path": str(config_path),
                    "project_name": "KnoArbor",
                    "vault_path": str(vault_path),
                    "server_host": "127.0.0.1",
                    "server_port": 8000,
                    "default_provider": "",
                    "default_max_tokens": 30000,
                    "request_timeout_seconds": 600,
                    "providers": [],
                    "image_default_provider": "sensenova",
                    "image_request_timeout_seconds": 120,
                    "image_providers": [
                        {
                            "name": "sensenova",
                            "adapter": "sensenova_image",
                            "base_url": "https://token.sensenova.cn/v1",
                            "endpoint_path": "/images/generations",
                            "api_key": "test-key",
                            "model": "sensenova-u1-fast",
                            "tls_ca_file": "",
                            "resolution": "2720*1536",
                            "num_inference_steps": 20,
                            "guidance": 4,
                            "extra_body": {},
                        }
                    ],
                },
            )

            self.assertEqual(response.status_code, 200)
            saved = config_path.read_text(encoding="utf-8")
            self.assertIn("image_generation:", saved)
            self.assertIn("default_provider: sensenova", saved)
            self.assertIn("model: sensenova-u1-fast", saved)
            form_response = client.get("/ui/api/config/form", params={"config_path": str(config_path)})
            self.assertEqual(form_response.status_code, 200)
            payload = form_response.json()
            self.assertEqual(payload["image_default_provider"], "sensenova")
            self.assertEqual(payload["image_providers"][0]["adapter"], "sensenova_image")
            self.assertEqual(payload["image_providers"][0]["resolution"], "2720*1536")

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
            self.assertEqual(providers["vllm"]["context_window"], 32768)
            self.assertEqual(providers["vllm"]["max_output_tokens"], 8000)

            diagnostics_response = client.get("/ui/api/config/diagnostics", params={"config_path": str(config_path)})
            self.assertEqual(diagnostics_response.status_code, 200)
            diagnostics = {item["name"]: item for item in diagnostics_response.json()["providers"]}
            self.assertTrue(diagnostics["ollama"]["ok"])
            self.assertTrue(diagnostics["vllm"]["ok"])
            self.assertIn("context_window=32768", diagnostics["vllm"]["detail"])
            self.assertIn("max_output_tokens=8000", diagnostics["vllm"]["detail"])
            self.assertFalse(diagnostics["cloud_missing_env"]["ok"])
            self.assertEqual(diagnostics["cloud_missing_env"]["detail"], "api_key")

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
                    "codex_raw_output_dir": str(vault_path / "raw" / "normalized" / "chats"),
                    "markdown_enabled": True,
                    "markdown_roots": [str(vault_path / "raw" / "inbox" / "notes")],
                    "markdown_raw_output_dir": str(vault_path / "raw" / "inbox" / "notes"),
                    "mineru_enabled": True,
                    "mineru_endpoint": "http://127.0.0.1:30000",
                    "mineru_input_dir": str(vault_path / "raw" / "inbox" / "documents"),
                    "mineru_output_dir": str(vault_path / "raw" / "normalized" / "markdown"),
                },
            )

            self.assertEqual(response.status_code, 200)
            saved = config_path.read_text(encoding="utf-8")
            self.assertIn("path: ./vaults/all", saved)
            self.assertIn("roots: []", saved)
            self.assertIn("raw_output_dir: ./vaults/all/raw/inbox/chats", saved)
            self.assertIn("input_dir: null", saved)
            self.assertIn("output_dir: ./vaults/all/raw/derived/markdown", saved)
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
                    "mineru_backend": "hybrid-engine",
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
            self.assertIn("mode: auto", saved)
            self.assertIn("timeout_seconds: 900", saved)
            self.assertIn("backend: pipeline", saved)
            self.assertIn("return_middle_json: false", saved)
            self.assertIn("lang_list: ch,en", saved)
            self.assertIn("formula_enable: true", saved)
            self.assertIn("table_enable: false", saved)
            self.assertNotIn("server_url: http://127.0.0.1:30000", saved)
            self.assertIn("start_page_id: 0", saved)
            self.assertIn("end_page_id: 99999", saved)
            self.assertIn("custom_flag: 'on'", saved)

            form_response = client.get("/ui/api/config/form", params={"config_path": str(config_path)})
            self.assertEqual(form_response.status_code, 200)
            payload = form_response.json()
            self.assertEqual(payload["mineru_backend"], "pipeline")
            self.assertEqual(payload["mineru_parse_method"], "auto")
            self.assertEqual(payload["mineru_timeout_seconds"], 900)
            self.assertEqual(payload["mineru_patterns"], ["*.pdf", "*.docx", "*.pptx", "*.ppt", "*.xlsx", "*.xls", "*.png", "*.jpg", "*.jpeg", "*.webp", "*.bmp"])
            self.assertTrue(payload["mineru_recursive"])
            self.assertFalse(payload["mineru_return_middle_json"])
            self.assertEqual(payload["mineru_lang_list"], "ch,en")
            self.assertTrue(payload["mineru_formula_enable"])
            self.assertFalse(payload["mineru_table_enable"])
            self.assertEqual(payload["mineru_server_url"], "")
            self.assertEqual(payload["mineru_start_page_id"], 0)
            self.assertEqual(payload["mineru_end_page_id"], 99999)
            self.assertIn("custom_flag", payload["mineru_extra_fields_json"])

    def test_ui_config_form_enables_mineru_when_endpoint_is_configured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config_path = root / "config.yaml"
            client = TestClient(create_app())

            response = client.put(
                "/ui/api/config/form",
                json={
                    "config_path": str(config_path),
                    "project_name": "KnoArbor",
                    "vault_path": str(root / "vaults" / "default"),
                    "server_host": "127.0.0.1",
                    "server_port": 8000,
                    "default_provider": "",
                    "default_max_tokens": 30000,
                    "request_timeout_seconds": 600,
                    "providers": [],
                    "markdown_enabled": True,
                    "markdown_roots": [],
                    "mineru_enabled": False,
                    "mineru_endpoint": "http://127.0.0.1:18080/file_parse",
                },
            )

            self.assertEqual(response.status_code, 200)
            saved = config_path.read_text(encoding="utf-8")
            self.assertIn("enabled: true", saved)
            form_response = client.get("/ui/api/config/form", params={"config_path": str(config_path)})
            self.assertEqual(form_response.status_code, 200)
            self.assertTrue(form_response.json()["mineru_enabled"])

    def test_ui_config_form_does_not_persist_default_chat_session_dirs(self) -> None:
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
            self.assertNotIn("sessions_dir: ~/.codex/sessions", saved)
            self.assertNotIn("sessions_dir: ~/.hermes/sessions", saved)
            self.assertNotIn("sessions_dir: ~/.openclaw/agents/main/sessions", saved)
            self.assertNotIn("sessions_dir: ~/.claude/projects", saved)
            form_response = client.get("/ui/api/config/form", params={"config_path": str(config_path)})
            self.assertEqual(form_response.status_code, 200)
            self.assertIn("codex", form_response.json()["detected_chat_source_dirs"])

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
      raw_output_dir: ./vaults/all/raw/inbox/notes
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
      raw_output_dir: ./vaults/all/raw/inbox/notes
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

    def test_ui_config_allows_local_api_key_fields(self) -> None:
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

            self.assertEqual(response.status_code, 200)
            self.assertTrue(config_path.exists())
            self.assertEqual(response.json()["summary"]["provider_count"], 1)
            self.assertNotIn("sk-testsecret123456", str(response.json()["summary"]))

    def test_ui_status_returns_vault_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault_path = Path(tmp_dir) / "vaults" / "all"
            init_wiki_vault(vault_path)
            (content_root(vault_path) / "Unit.md").write_text(
                "# Unit\n\n## Summary\n\nA unit page.\n",
                encoding="utf-8",
            )
            (vault_path / "raw" / "notes").mkdir(parents=True, exist_ok=True)
            (vault_path / "raw" / "notes" / "unit.md").write_text("# Unit", encoding="utf-8")
            client = TestClient(create_app())

            response = client.get("/ui/api/status", params={"vault_path": str(vault_path)})

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["pages"], 1)
            self.assertEqual(payload["directories"]["pages"], 1)
            self.assertEqual(payload["raw_sources"], 1)
            self.assertIsInstance(payload["issues"], int)

    def test_ui_graph_returns_nodes_edges_and_stats(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault_path = Path(tmp_dir) / "vaults" / "all"
            init_wiki_vault(vault_path)
            source_path = source_digest_root(vault_path) / "Source.md"
            concept_path = content_root(vault_path) / "Agent-Loop.md"
            source_path.write_text(
                "---\nrole: source_digest\n---\n# Source\n\n## Source Identity\n\n- Raw source: raw/inbox/notes/source.md\n- Content hash: test\n\n## Source Units\n\n- U1: Agent loop source notes.\n\n## Contribution Map\n\n- [[Agent-Loop|Agent Loop]]: source support\n\n## Raw Source\n\n- raw/inbox/notes/source.md\n",
                encoding="utf-8",
            )
            concept_path.write_text(
                "---\nrole: knowledge_page\n---\n# Agent Loop\n\n## Summary\n\nAgent loop summary.\n",
                encoding="utf-8",
            )
            client = TestClient(create_app())

            response = client.get("/ui/api/graph", params={"vault_path": str(vault_path), "view": "page"})

            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["graph_kind"], "page")
            self.assertEqual(payload["stats"]["page_count"], 1)
            self.assertEqual(payload["stats"]["edge_count"], 0)
            self.assertEqual(payload["stats"]["orphan_count"], 1)
            self.assertNotIn("sources", payload["stats"]["directory_counts"])
            self.assertNotIn("source_digest", payload["stats"]["role_counts"])
            self.assertEqual(payload["stats"]["role_counts"]["knowledge_page"], 1)
            self.assertFalse(any(node["id"] == "sources/Source.md" for node in payload["nodes"]))
            self.assertEqual(payload["stats"]["entity_counts"], {})

    def test_ui_graph_defaults_to_page_graph(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault_path = Path(tmp_dir) / "vaults" / "default"
            init_wiki_vault(vault_path)
            (content_root(vault_path) / "Agent-Loop.md").write_text(
                "---\nrole: knowledge_page\n---\n# Agent Loop\n\n## Summary\n\nAgent Loop coordinates tool-using agent execution.\n\n[[Tool-Call]]\n",
                encoding="utf-8",
            )
            (content_root(vault_path) / "Tool-Call.md").write_text(
                "---\nrole: knowledge_page\n---\n# Tool Call\n\n## Summary\n\nA tool call page.\n",
                encoding="utf-8",
            )
            client = TestClient(create_app())

            default_response = client.get("/ui/api/graph", params={"vault_path": str(vault_path)})
            explicit_response = client.get("/ui/api/graph", params={"vault_path": str(vault_path), "view": "page"})

            self.assertEqual(default_response.status_code, 200)
            self.assertEqual(explicit_response.status_code, 200)
            for payload in (default_response.json(), explicit_response.json()):
                self.assertEqual(payload["graph_kind"], "page")
                self.assertEqual(payload["stats"]["page_count"], 2)
                self.assertEqual(payload["stats"]["edge_count"], 1)
                self.assertEqual({node["id"] for node in payload["nodes"]}, {"Agent-Loop.md", "Tool-Call.md"})
                self.assertEqual(payload["edges"][0]["kind"], "wikilink")


if __name__ == "__main__":
    unittest.main()
