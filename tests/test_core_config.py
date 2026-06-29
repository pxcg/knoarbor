from __future__ import annotations

import os
import sys
import tempfile
import unittest
from importlib.resources import files
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.core.config import (
    ConfigMigrationError,
    IngestSegmentationConfig,
    KnoArborConfig,
    default_config_path,
    load_config,
    migrate_config_data,
    prepare_config_data,
)


class ConfigTests(unittest.TestCase):
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
        self.assertEqual(config.config_version, 1)
        self.assertTrue(config.query.include_related)
        self.assertEqual(config.models.default_max_tokens, 30000)
        self.assertEqual(config.models.request_timeout_seconds, 600.0)
        self.assertEqual(config.active_vault_id(), "default")
        self.assertEqual(config.vault_profiles_summary()[0]["path"], "vaults/all")

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

        self.assertEqual(prepared["config_version"], 1)
        self.assertEqual(prepared["vault"]["path"], (Path(tmp_dir) / "vaults" / "all").resolve())
        self.assertEqual(prepared["connectors"]["markdown"]["settings"]["roots"], [(Path(tmp_dir) / "notes").resolve()])
        self.assertEqual(
            prepared["connectors"]["markdown"]["settings"]["raw_output_dir"],
            (Path(tmp_dir) / "vaults" / "all" / "raw" / "inbox" / "notes").resolve(),
        )

    def test_migrate_config_data_rejects_newer_versions(self) -> None:
        with self.assertRaisesRegex(ConfigMigrationError, "newer than this KnoArbor build"):
            migrate_config_data({"config_version": 999, "vault": {"path": "./vaults/all"}})

    def test_migrate_config_data_rejects_invalid_versions(self) -> None:
        with self.assertRaisesRegex(ConfigMigrationError, "Invalid config_version"):
            migrate_config_data({"config_version": "next", "vault": {"path": "./vaults/all"}})

    def test_load_config_reads_dotenv_next_to_config(self) -> None:
        env_name = "KNOARBOR_TEST_API_KEY"
        original = os.environ.pop(env_name, None)
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                root = Path(tmp_dir)
                (root / "vaults" / "all").mkdir(parents=True)
                (root / ".env").write_text(f'{env_name}="local-secret"\n', encoding="utf-8")
                path = root / "config.yaml"
                path.write_text(
                    "vault:\n"
                    "  path: ./vaults/all\n"
                    "models:\n"
                    "  providers:\n"
                    "    test:\n"
                    f"      api_key_env: {env_name}\n",
                    encoding="utf-8",
                )

                config = load_config(path)

            self.assertEqual(config.models.providers["test"].api_key(), "local-secret")
        finally:
            if original is None:
                os.environ.pop(env_name, None)
            else:
                os.environ[env_name] = original

    def test_dotenv_does_not_override_existing_environment(self) -> None:
        env_name = "KNOARBOR_TEST_EXISTING_API_KEY"
        original = os.environ.get(env_name)
        os.environ[env_name] = "from-process"
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                root = Path(tmp_dir)
                (root / "vaults" / "all").mkdir(parents=True)
                (root / ".env").write_text(f"{env_name}=from-dotenv\n", encoding="utf-8")
                path = root / "config.yaml"
                path.write_text(
                    "vault:\n"
                    "  path: ./vaults/all\n"
                    "models:\n"
                    "  providers:\n"
                    "    test:\n"
                    f"      api_key_env: {env_name}\n",
                    encoding="utf-8",
                )

                config = load_config(path)

            self.assertEqual(config.models.providers["test"].api_key(), "from-process")
        finally:
            if original is None:
                os.environ.pop(env_name, None)
            else:
                os.environ[env_name] = original

    def test_default_config_path_prefers_local_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "src" / "knoarbor").mkdir(parents=True)
            (root / "pyproject.toml").write_text("[project]\nname = 'example'\n", encoding="utf-8")
            (root / "config.example.yaml").write_text("vault:\n  path: ./vaults/all\n", encoding="utf-8")
            (root / "config.yaml").write_text("vault:\n  path: ./vaults/all\n", encoding="utf-8")

            path = default_config_path(root / "src" / "knoarbor")

        self.assertEqual(path, (root / "config.yaml").resolve())

    def test_default_config_path_prefers_explicit_environment_path(self) -> None:
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
