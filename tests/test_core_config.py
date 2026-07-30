from __future__ import annotations

import os
import sys
import tempfile
import unittest
from importlib.resources import files
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.core.config import (
    ConfigMigrationError,
    IngestSegmentationConfig,
    KnoArborConfig,
    ModelProviderConfig,
    default_config_path,
    load_config,
    migrate_config_data,
    prepare_config_data,
)
from knoarbor.services.ui_config import UiConfigService, config_to_form, render_config_from_form
from knoarbor.services.ui_config_models import UiConfigFormUpdateRequest, UiConfigUpdateRequest


class ConfigTests(unittest.TestCase):
    def test_repository_and_packaged_config_examples_match(self) -> None:
        root = Path(__file__).parents[1]

        self.assertEqual(
            (root / "config.example.yaml").read_text(encoding="utf-8"),
            (root / "src" / "knoarbor" / "config.example.yaml").read_text(encoding="utf-8"),
        )

    def test_ingest_segmentation_budget_requires_soft_under_max(self) -> None:
        with self.assertRaises(ValueError):
            IngestSegmentationConfig(soft_chars_per_segment=5000, max_chars_per_segment=3000)

    def test_config_loads_from_mapping(self) -> None:
        config = KnoArborConfig.model_validate(
            {
                "vault": {"path": "./vaults/all"},
                "document_processing": {
                    "mineru": {"enabled": False, "output_dir": "./mineru-md"},
                },
                "connectors": {
                    "markdown": {"enabled": True, "settings": {"roots": ["./notes"]}},
                },
            }
        )

        self.assertEqual(config.vault.path, Path("vaults/all"))
        self.assertEqual(config.document_processing.mineru.output_dir, Path("mineru-md"))
        self.assertEqual(config.enabled_connectors(), ["markdown"])
        self.assertEqual(config.config_version, 3)
        self.assertEqual(config.models.default_max_tokens, 30000)
        self.assertEqual(config.models.request_timeout_seconds, 600.0)
        self.assertEqual(config.active_vault_id(), "default")
        self.assertEqual(config.vault_profiles_summary()[0]["path"], "vaults/all")

    def test_mineru_backend_accepts_only_published_values(self) -> None:
        for backend in ("pipeline", "vlm-auto-engine", "hybrid-auto-engine"):
            with self.subTest(backend=backend):
                config = KnoArborConfig.model_validate(
                    {
                        "vault": {"path": "./vaults/all"},
                        "document_processing": {"mineru": {"extra_fields": {"backend": backend}}},
                    }
                )
                self.assertEqual(config.document_processing.mineru.extra_fields["backend"], backend)

    def test_mineru_backend_rejects_unsupported_values(self) -> None:
        for backend in ("vlm-engine", "hybrid-engine", "vlm-http-client"):
            with self.subTest(backend=backend):
                with self.assertRaisesRegex(ValueError, f"Unsupported MinerU backend '{backend}'"):
                    KnoArborConfig.model_validate(
                        {
                            "vault": {"path": "./vaults/all"},
                            "document_processing": {"mineru": {"extra_fields": {"backend": backend}}},
                        }
                    )

    def test_openai_chat_image_provider_uses_chat_completions_default_endpoint(self) -> None:
        config = KnoArborConfig.model_validate(
            {
                "vault": {"path": "./vaults/all"},
                "image_generation": {
                    "providers": {
                        "local-chat-image": {
                            "adapter": "openai_chat_image",
                            "base_url": "https://text2image.local/v1",
                            "api_key": "test-key",
                            "model": "SenseNova-U1-8B",
                        }
                    }
                },
            }
        )

        self.assertEqual(config.image_generation.providers["local-chat-image"].endpoint_path, "/chat/completions")

    def test_provider_base_url_normalizes_exact_completion_endpoint(self) -> None:
        provider = ModelProviderConfig(
            base_url="https://models.example.test/compatible-mode/v1/chat/completions/",
            model="chat-model",
        )

        self.assertEqual(provider.base_url, "https://models.example.test/compatible-mode/v1")

    def test_ui_form_persists_canonical_provider_base_url(self) -> None:
        form = UiConfigFormUpdateRequest.model_validate(
            {
                "project_name": "Default",
                "vault_path": "./vaults/default",
                "default_provider": "chat",
                "providers": [
                    {
                        "name": "chat",
                        "base_url": "https://models.example.test/v1/chat/completions/",
                        "model": "chat-model",
                    }
                ],
            }
        )

        rendered = yaml.safe_load(
            render_config_from_form(form, {"config_version": 3}, base_dir=Path.cwd())
        )

        self.assertEqual(rendered["models"]["providers"]["chat"]["base_url"], "https://models.example.test/v1")

    def test_provider_base_url_rejects_ambiguous_or_credential_bearing_urls(self) -> None:
        invalid_urls = (
            "https://models.example.test/v1/chat/com",
            "https://models.example.test/v1/chat/completions/extra",
            "https://user:secret@models.example.test/v1",
            "https://models.example.test/v1?token=secret",
            "models.example.test/v1",
        )
        for base_url in invalid_urls:
            with self.subTest(base_url=base_url):
                with self.assertRaises(ValueError):
                    ModelProviderConfig(base_url=base_url, model="chat-model")

    def test_image_provider_full_endpoint_is_split_from_base_url(self) -> None:
        config = KnoArborConfig.model_validate(
            {
                "vault": {"path": "./vaults/all"},
                "image_generation": {
                    "providers": {
                        "image": {
                            "adapter": "sensenova_image",
                            "base_url": "https://images.example.test/v1/images/generations",
                            "model": "image-model",
                        }
                    }
                },
            }
        )

        provider = config.image_generation.providers["image"]
        self.assertEqual(provider.base_url, "https://images.example.test/v1")
        self.assertEqual(provider.endpoint_path, "/images/generations")

    def test_invalid_config_write_does_not_replace_active_private_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "config.yaml"
            original = "config_version: 3\nvault:\n  path: ./vaults/default\n"
            path.write_text(original, encoding="utf-8")

            with self.assertRaises(Exception):
                UiConfigService().write_raw(
                    UiConfigUpdateRequest(config_path=str(path), content="config_version: [")
                )

            self.assertEqual(path.read_text(encoding="utf-8"), original)

    @unittest.skipIf(os.name == "nt", "POSIX permission bits are not available on Windows")
    def test_valid_config_write_is_private(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "config.yaml"
            UiConfigService().write_raw(
                UiConfigUpdateRequest(
                    config_path=str(path),
                    content="config_version: 3\nvault:\n  path: ./vaults/default\n",
                )
            )

            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_ui_config_form_preserves_chat_auto_ingest(self) -> None:
        config = KnoArborConfig.model_validate(
            {
                "vault": {"path": "./vaults/all"},
                "chat": {
                    "auto_ingest": {"enabled": True, "min_user_turns": 3},
                },
            }
        )
        form = config_to_form(config)
        payload = form.model_dump()
        rendered = render_config_from_form(UiConfigFormUpdateRequest.model_validate(payload), {"chat": {"auto_ingest": {"enabled": True, "min_user_turns": 3}}}, base_dir=Path.cwd())
        data = yaml.safe_load(rendered)

        self.assertEqual(data["chat"]["auto_ingest"]["enabled"], True)
        self.assertEqual(data["chat"]["auto_ingest"]["min_user_turns"], 3)

    def test_ui_config_form_repairs_dangling_default_provider(self) -> None:
        form = UiConfigFormUpdateRequest.model_validate(
            {
                "project_name": "Default",
                "vault_path": "./vaults/default",
                "default_provider": "custom",
                "providers": [
                    {
                        "name": "deepseek",
                        "base_url": "https://api.deepseek.com/v1",
                        "model": "deepseek-chat",
                    }
                ],
            }
        )

        data = yaml.safe_load(
            render_config_from_form(
                form,
                {"config_version": 3},
                base_dir=Path.cwd(),
            )
        )

        self.assertEqual(data["config_version"], 3)
        self.assertEqual(data["models"]["default_provider"], "deepseek")

    def test_vault_profiles_select_active_vault(self) -> None:
        config = KnoArborConfig.model_validate(
            {
                "vault": {"path": "./old-wiki"},
                "vaults": {
                    "default": "team",
                    "profiles": {
                        "personal": {"name": "Personal", "path": "./vaults/all"},
                        "team": {"name": "Team", "path": "./team-wiki"},
                    },
                },
            }
        )

        self.assertEqual(config.vault.path, Path("team-wiki"))
        self.assertEqual(config.active_vault_id(), "team")
        self.assertEqual(config.active_vault_name(), "Team")

    def test_vault_profiles_reject_missing_default(self) -> None:
        with self.assertRaisesRegex(ValueError, "vaults.default"):
            KnoArborConfig.model_validate(
                {
                    "vault": {"path": "./vaults/all"},
                    "vaults": {
                        "default": "missing",
                        "profiles": {"personal": {"name": "Personal", "path": "./vaults/all"}},
                    },
                }
            )

    def test_config_loads_from_yaml_file_and_resolves_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "vaults" / "all").mkdir(parents=True)
            path = root / "config.yaml"
            path.write_text(
                "vault:\n"
                "  path: ./vaults/all\n"
                "document_processing:\n"
                "  mineru:\n"
                "    output_dir: ./documents-md\n"
                "connectors:\n"
                "  markdown:\n"
                "    enabled: true\n"
                "    settings:\n"
                "      roots:\n"
                "        - ./notes\n",
                encoding="utf-8",
            )

            config = load_config(path)

        self.assertEqual(config.vault.path, (Path(tmp_dir) / "vaults" / "all").resolve())
        self.assertEqual(config.document_processing.mineru.output_dir, (Path(tmp_dir) / "documents-md").resolve())
        self.assertEqual(config.connectors["markdown"].settings["roots"], [(Path(tmp_dir) / "notes").resolve()])

    def test_prepare_config_data_migrates_before_resolving_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base_dir = Path(tmp_dir)

            prepared = prepare_config_data(
                {
                    "vault": {"path": "./vaults/all"},
                    "connectors": {
                        "markdown": {
                            "enabled": True,
                            "settings": {"roots": ["./notes"], "raw_output_dir": "./vaults/all/raw/inbox/notes"},
                        }
                    },
                },
                base_dir,
            )

        self.assertEqual(prepared["config_version"], 3)
        self.assertEqual(prepared["vault"]["path"], (Path(tmp_dir) / "vaults" / "all").resolve())
        self.assertEqual(prepared["connectors"]["markdown"]["settings"]["roots"], [(Path(tmp_dir) / "notes").resolve()])
        self.assertEqual(
            prepared["connectors"]["markdown"]["settings"]["raw_output_dir"],
            (Path(tmp_dir) / "vaults" / "all" / "raw" / "inbox" / "notes").resolve(),
        )

    def test_migrate_config_data_rejects_newer_versions(self) -> None:
        with self.assertRaisesRegex(ConfigMigrationError, "requires version 3"):
            migrate_config_data({"config_version": 999, "vault": {"path": "./vaults/all"}})

    def test_migrate_config_data_rejects_unpublished_legacy_versions(self) -> None:
        for version in (1, 2):
            with self.subTest(version=version):
                with self.assertRaisesRegex(ConfigMigrationError, "requires version 3"):
                    migrate_config_data({"config_version": version, "vault": {"path": "./vaults/all"}})

    def test_migrate_config_data_rejects_invalid_versions(self) -> None:
        with self.assertRaisesRegex(ConfigMigrationError, "Invalid config_version"):
            migrate_config_data({"config_version": "next", "vault": {"path": "./vaults/all"}})

    def test_default_config_path_prefers_local_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "src" / "knoarbor").mkdir(parents=True)
            (root / "pyproject.toml").write_text("[project]\nname = 'example'\n", encoding="utf-8")
            (root / "config.example.yaml").write_text("vault:\n  path: ./vaults/all\n", encoding="utf-8")
            (root / "config.yaml").write_text("vault:\n  path: ./vaults/all\n", encoding="utf-8")

            path = default_config_path(root / "src" / "knoarbor")

        self.assertEqual(path, (root / "config.yaml").resolve())

    def test_default_config_path_prefers_knoarbor_environment_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            configured = root / "desktop-config.yaml"
            configured.write_text("vault:\n  path: ./vaults/default\n", encoding="utf-8")
            (root / "config.yaml").write_text("vault:\n  path: ./vaults/other\n", encoding="utf-8")
            original = os.environ.get("KNOARBOR_CONFIG_PATH")
            os.environ["KNOARBOR_CONFIG_PATH"] = str(configured)
            try:
                path = default_config_path(root)
            finally:
                if original is None:
                    os.environ.pop("KNOARBOR_CONFIG_PATH", None)
                else:
                    os.environ["KNOARBOR_CONFIG_PATH"] = original

        self.assertEqual(path, configured.resolve())

    def test_bundled_default_config_resolves_paths_against_cwd(self) -> None:
        bundled = Path(files("knoarbor").joinpath("config.example.yaml"))
        with tempfile.TemporaryDirectory() as tmp_dir:
            previous = Path.cwd()
            os.chdir(tmp_dir)
            try:
                config = load_config(bundled)
            finally:
                os.chdir(previous)

        self.assertEqual(config.vault.path, (Path(tmp_dir) / "vaults" / "default").resolve())
        self.assertEqual(config.project.host_project_root, Path(tmp_dir).resolve())

    def test_runtime_path_validation_rejects_missing_vault(self) -> None:
        config = KnoArborConfig.model_validate({"vault": {"path": "/path/that/does/not/exist"}})

        with self.assertRaisesRegex(ValueError, "Vault path does not exist"):
            config.validate_runtime_paths()

    def test_provider_max_output_tokens_overrides_global_default(self) -> None:
        config = KnoArborConfig.model_validate(
            {
                "vault": {"path": "./vaults/all"},
                "models": {
                    "default_provider": "local",
                    "default_max_tokens": 30000,
                    "providers": {
                        "local": {
                            "base_url": "http://127.0.0.1:11434/v1",
                            "model": "qwen",
                            "context_window": 32768,
                            "max_output_tokens": 8000,
                        }
                    },
                },
            }
        )

        self.assertEqual(config.models.providers["local"].context_window, 32768)
        self.assertEqual(config.models.resolve_max_tokens(), 8000)
        self.assertEqual(config.models.resolve_max_tokens("local", requested=4096), 4096)


if __name__ == "__main__":
    unittest.main()
