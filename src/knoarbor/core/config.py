from __future__ import annotations

import json
import os
from importlib.resources import files
from pathlib import Path
from typing import Any, Callable, Literal, Mapping

from pydantic import BaseModel, Field, field_validator, model_validator

from knoarbor.core.errors import ConfigNotFound, InvalidConfig, VaultPathError

SUPPORTED_CONFIG_VERSION = 1
MIN_CONFIG_VERSION = 1
DEFAULT_VAULT_PATH = Path("./vaults/default")


class ConfigMigrationError(ValueError):
    """Raised when a config file cannot be migrated to the supported schema."""


class ProjectConfig(BaseModel):
    name: str = "KnoArbor"
    host_project_root: Path = Path(".")

    @field_validator("host_project_root")
    @classmethod
    def expand_project_root(cls, value: Path) -> Path:
        return value.expanduser()


class VaultConfig(BaseModel):
    path: Path

    @field_validator("path")
    @classmethod
    def expand_path(cls, value: Path) -> Path:
        return value.expanduser()


class VaultProfileConfig(BaseModel):
    name: str
    path: Path

    @field_validator("path")
    @classmethod
    def expand_path(cls, value: Path) -> Path:
        return value.expanduser()


class VaultsConfig(BaseModel):
    default: str = "default"
    profiles: dict[str, VaultProfileConfig] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_default_profile(self) -> "VaultsConfig":
        if self.profiles and self.default not in self.profiles:
            raise ValueError("vaults.default must reference an item in vaults.profiles")
        return self


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)


class ModelProviderConfig(BaseModel):
    base_url: str | None = None
    api_key_env: str | None = None
    model: str | None = None
    json_mode: bool = True
    context_window: int | None = Field(default=None, ge=1)
    max_output_tokens: int | None = Field(default=None, ge=1)

    def api_key(self, env: Mapping[str, str] | None = None) -> str | None:
        if not self.api_key_env:
            return None
        return (env or os.environ).get(self.api_key_env)


class ModelRetryConfig(BaseModel):
    enabled: bool = True
    max_attempts: int = Field(default=3, ge=1, le=5)
    backoff_seconds: float = Field(default=2.0, ge=0, le=120)
    retry_on_invalid_output: bool = True
    retryable_error_codes: list[str] = Field(
        default_factory=lambda: ["KA-EXT-001", "KA-MODEL-001", "KA-SEM-001", "KA-STORAGE-001"]
    )


class ModelsConfig(BaseModel):
    default_provider: str | None = None
    providers: dict[str, ModelProviderConfig] = Field(default_factory=dict)
    default_max_tokens: int | None = Field(default=30000, ge=1)
    request_timeout_seconds: float = Field(default=600.0, ge=1)
    retry: ModelRetryConfig = Field(default_factory=ModelRetryConfig)

    def resolve_max_tokens(self, provider_name: str | None = None, requested: int | None = None) -> int | None:
        if requested is not None:
            return requested
        selected = provider_name or self.default_provider
        provider = self.providers.get(selected) if selected else None
        if provider and provider.max_output_tokens is not None:
            return provider.max_output_tokens
        return self.default_max_tokens


class ConnectorConfig(BaseModel):
    enabled: bool = False
    settings: dict[str, Any] = Field(default_factory=dict)


class MinerUDocumentProcessingConfig(BaseModel):
    enabled: bool = False
    endpoint: str | None = None
    input_dir: Path | None = None
    output_dir: Path = DEFAULT_VAULT_PATH / "raw/documents/markdown"
    recursive: bool = True
    patterns: list[str] = Field(default_factory=lambda: ["*.pdf", "*.docx", "*.pptx"])
    mode: str | None = "auto"
    timeout_seconds: float = Field(default=600.0, ge=1)
    file_field: str = "files"
    output_dir_field: str | None = None
    mode_field: str | None = "parse_method"
    response_markdown_field: str | None = "markdown"
    response_path_field: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    extra_fields: dict[str, object] = Field(
        default_factory=lambda: {
            "backend": "pipeline",
            "return_md": True,
            "return_middle_json": False,
            "return_model_output": False,
            "return_content_list": False,
            "return_images": False,
            "response_format_zip": False,
        }
    )

    @field_validator("input_dir", "output_dir")
    @classmethod
    def expand_path(cls, value: Path | None) -> Path | None:
        return value.expanduser() if value is not None else None


class DocumentProcessingConfig(BaseModel):
    mineru: MinerUDocumentProcessingConfig = Field(default_factory=MinerUDocumentProcessingConfig)


class QueryConfig(BaseModel):
    mode: Literal["quick", "balanced", "deep"] = "balanced"
    max_results: int = Field(default=6, ge=1, le=20)
    max_pages_to_read: int = Field(default=10, ge=1, le=30)
    max_excerpts_per_page: int = Field(default=3, ge=0, le=8)
    max_chars_per_excerpt: int = Field(default=800, ge=120, le=3000)
    max_context_chars: int = Field(default=8000, ge=1000, le=30000)
    page_dirs: list[str] = Field(default_factory=list)
    include_related: bool = True


class MemoryConfig(BaseModel):
    enabled: bool = True
    auto_write_explicit_low_risk: bool = True
    max_recalled_records: int = Field(default=12, ge=1, le=100)


class IngestSegmentationConfig(BaseModel):
    enabled: bool = True
    max_chars_per_segment: int = Field(default=18000, ge=2000, le=100000)
    soft_chars_per_segment: int = Field(default=12000, ge=1000, le=100000)
    overlap_chars: int = Field(default=1200, ge=0, le=10000)
    max_segments_per_source: int = Field(default=20, ge=1, le=200)
    min_segment_chars: int = Field(default=1000, ge=0, le=50000)

    @model_validator(mode="after")
    def validate_segment_budget(self) -> "IngestSegmentationConfig":
        if self.soft_chars_per_segment > self.max_chars_per_segment:
            raise ValueError("ingest.segmentation.soft_chars_per_segment must be <= max_chars_per_segment")
        if self.min_segment_chars > self.max_chars_per_segment:
            raise ValueError("ingest.segmentation.min_segment_chars must be <= max_chars_per_segment")
        return self


class IngestRecoveryConfig(BaseModel):
    enabled: bool = True
    execution_ledger_path: str = "maintenance/ingest_execution_ledger.jsonl"


class IngestConcurrencyConfig(BaseModel):
    max_concurrent_sources: int = Field(default=1, ge=1, le=8)


class IngestConfig(BaseModel):
    candidate_limit: int = Field(default=8, ge=1, le=50)
    materialized_page_limit: int = Field(default=8, ge=1, le=50)
    max_chars_per_materialized_page: int = Field(default=6000, ge=500, le=100000)
    auto_scoped_lint: bool = True
    auto_apply_safe_lint_fixes: bool = True
    segmentation: IngestSegmentationConfig = Field(default_factory=IngestSegmentationConfig)
    recovery: IngestRecoveryConfig = Field(default_factory=IngestRecoveryConfig)
    concurrency: IngestConcurrencyConfig = Field(default_factory=IngestConcurrencyConfig)


class LintConfig(BaseModel):
    default_scope: str = "latest-ingest"
    scoped_include_related: bool = True
    include_neighbors: bool = True
    include_global_checks: bool = True


class PrivacyConfig(BaseModel):
    redaction_enabled: bool = True
    redact_emails: bool = True
    redact_phone_numbers: bool = True
    redact_api_keys: bool = True
    redact_private_keys: bool = True
    redact_platform_ids: bool = True
    redact_local_paths: bool = True
    redact_source_paths_in_pages: bool = True
    redact_private_ips: bool = False
    custom_terms: list[str] = Field(default_factory=list)


class KnoArborConfig(BaseModel):
    config_version: Literal[1] = SUPPORTED_CONFIG_VERSION
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    vault: VaultConfig
    vaults: VaultsConfig = Field(default_factory=VaultsConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    document_processing: DocumentProcessingConfig = Field(default_factory=DocumentProcessingConfig)
    connectors: dict[str, ConnectorConfig] = Field(default_factory=dict)
    ingest: IngestConfig = Field(default_factory=IngestConfig)
    query: QueryConfig = Field(default_factory=QueryConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    lint: LintConfig = Field(default_factory=LintConfig)
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)

    @model_validator(mode="after")
    def align_active_vault(self) -> "KnoArborConfig":
        if self.vaults.profiles:
            active = self.vaults.profiles[self.vaults.default]
            self.vault = VaultConfig(path=active.path)
        elif self.vault.path:
            self.vaults = VaultsConfig(
                default="default",
                profiles={
                    "default": VaultProfileConfig(
                        name=self.project.name or "Default",
                        path=self.vault.path,
                    )
                },
            )
        return self

    def enabled_connectors(self) -> list[str]:
        return [name for name, config in self.connectors.items() if config.enabled]

    def active_vault_id(self) -> str:
        return self.vaults.default

    def active_vault_name(self) -> str:
        profile = self.vaults.profiles.get(self.vaults.default)
        return profile.name if profile else self.project.name

    def vault_profiles_summary(self) -> list[dict[str, str]]:
        return [
            {"id": vault_id, "name": profile.name, "path": str(profile.path)}
            for vault_id, profile in sorted(self.vaults.profiles.items())
        ]

    def validate_runtime_paths(self) -> None:
        if not self.vault.path.exists():
            raise VaultPathError(f"Vault path does not exist: {self.vault.path}")
        if not self.vault.path.is_dir():
            raise VaultPathError(f"Vault path is not a directory: {self.vault.path}")


def default_config_path(start: str | Path | None = None) -> Path:
    root = _find_project_root(Path(start or Path.cwd()).resolve())
    local_config = root / "config.yaml"
    if local_config.exists():
        return local_config
    example_config = root / "config.example.yaml"
    if example_config.exists():
        return example_config
    return Path(files("knoarbor").joinpath("config.example.yaml"))


def load_config(path: str | Path) -> KnoArborConfig:
    config_path = Path(path).expanduser()
    base_dir = _config_base_dir(config_path)
    load_env_file(base_dir / ".env")
    data = _load_config_data(config_path)
    data = prepare_config_data(data, base_dir)
    return KnoArborConfig.model_validate(data)


def prepare_config_data(data: dict[str, Any], base_dir: Path) -> dict[str, Any]:
    """Apply schema migration before deterministic path resolution and validation."""
    migrated = migrate_config_data(data)
    return resolve_config_data_paths(migrated, base_dir)


def migrate_config_data(data: dict[str, Any]) -> dict[str, Any]:
    """Migrate raw config data to the currently supported schema version.

    Migration is intentionally structural only: it may move or rename fields in
    future versions, but it must not infer user intent, repair secrets, or guess
    local paths.
    """
    if not isinstance(data, dict):
        raise ConfigMigrationError("Config root must be an object")
    version = _parse_config_version(data.get("config_version", MIN_CONFIG_VERSION))
    if version < MIN_CONFIG_VERSION:
        raise ConfigMigrationError(f"Unsupported config_version: {version}")
    if version > SUPPORTED_CONFIG_VERSION:
        raise ConfigMigrationError(
            f"Config version {version} is newer than this KnoArbor build supports ({SUPPORTED_CONFIG_VERSION})."
        )
    migrated = dict(data)
    while version < SUPPORTED_CONFIG_VERSION:
        migration = _CONFIG_MIGRATIONS.get(version)
        if migration is None:
            raise ConfigMigrationError(f"No migration path from config_version {version} to {SUPPORTED_CONFIG_VERSION}.")
        migrated = migration(migrated)
        version = _parse_config_version(migrated.get("config_version"))
    migrated["config_version"] = SUPPORTED_CONFIG_VERSION
    migrated = _ensure_vault_contract(migrated)
    return migrated


def _parse_config_version(value: object) -> int:
    try:
        version = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ConfigMigrationError(f"Invalid config_version: {value!r}") from exc
    return version


_CONFIG_MIGRATIONS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {}


def load_env_file(path: Path) -> None:
    """Load simple KEY=value pairs without overriding the process environment."""
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = _clean_env_value(value)


def _load_config_data(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigNotFound(f"Config file does not exist: {path}")

    suffix = path.suffix.lower()
    text = path.read_text(encoding="utf-8")
    if suffix == ".json":
        return json.loads(text)
    if suffix in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError as exc:
            raise InvalidConfig("YAML config requires PyYAML. Use JSON or install pyyaml.") from exc
        loaded = yaml.safe_load(text) or {}
        if not isinstance(loaded, dict):
            raise InvalidConfig("Config root must be an object")
        return loaded
    raise InvalidConfig(f"Unsupported config file extension: {path.suffix}")


def _clean_env_value(value: str) -> str:
    cleaned = value.strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {"'", '"'}:
        return cleaned[1:-1]
    return cleaned


def _find_project_root(start: Path) -> Path:
    candidates = [start, *start.parents]
    for candidate in candidates:
        if (candidate / "config.example.yaml").exists() and (candidate / "pyproject.toml").exists():
            return candidate
    return Path(__file__).resolve().parents[3]


def _config_base_dir(config_path: Path) -> Path:
    """Resolve bundled defaults against cwd, not the installed package directory."""
    bundled = Path(files("knoarbor").joinpath("config.example.yaml"))
    try:
        if config_path.resolve() == bundled.resolve():
            return Path.cwd().resolve()
    except FileNotFoundError:
        pass
    return config_path.parent.resolve()


def resolve_config_data_paths(data: dict[str, Any], base_dir: Path) -> dict[str, Any]:
    copied = dict(data)
    if isinstance(copied.get("project"), dict):
        project = dict(copied["project"])
        if "host_project_root" in project:
            project["host_project_root"] = _resolve_path_value(project.get("host_project_root"), base_dir)
        copied["project"] = project
    if isinstance(copied.get("vault"), dict):
        vault = dict(copied["vault"])
        vault["path"] = _resolve_path_value(vault.get("path"), base_dir)
        copied["vault"] = vault
    if isinstance(copied.get("vaults"), dict):
        copied["vaults"] = _resolve_vault_profiles(copied["vaults"], base_dir)
    if isinstance(copied.get("connectors"), dict):
        copied["connectors"] = _resolve_connector_paths(copied["connectors"], base_dir)
    if isinstance(copied.get("document_processing"), dict):
        copied["document_processing"] = _resolve_document_processing_paths(copied["document_processing"], base_dir)
    return copied


def _ensure_vault_contract(data: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(data)
    vault = migrated.get("vault")
    vaults = migrated.get("vaults")
    if isinstance(vaults, dict) and isinstance(vaults.get("profiles"), dict) and vaults["profiles"]:
        default_id = str(vaults.get("default") or "default")
        profiles = vaults["profiles"]
        if default_id not in profiles:
            raise ConfigMigrationError("vaults.default must reference an item in vaults.profiles")
        active_profile = profiles[default_id]
        if isinstance(active_profile, dict) and active_profile.get("path"):
            migrated["vault"] = {"path": active_profile["path"]}
        return migrated
    if isinstance(vault, dict) and vault.get("path"):
        project = migrated.get("project") if isinstance(migrated.get("project"), dict) else {}
        migrated["vaults"] = {
            "default": "default",
            "profiles": {
                "default": {
                    "name": str(project.get("name") or "Default"),
                    "path": vault["path"],
                }
            },
        }
        return migrated
    return migrated


def _resolve_vault_profiles(vaults: dict[str, Any], base_dir: Path) -> dict[str, Any]:
    resolved = dict(vaults)
    profiles = resolved.get("profiles")
    if isinstance(profiles, dict):
        next_profiles: dict[str, Any] = {}
        for vault_id, profile in profiles.items():
            if not isinstance(profile, dict):
                next_profiles[vault_id] = profile
                continue
            item = dict(profile)
            if "path" in item:
                item["path"] = _resolve_path_value(item["path"], base_dir)
            next_profiles[vault_id] = item
        resolved["profiles"] = next_profiles
    return resolved


def _resolve_document_processing_paths(document_processing: dict[str, Any], base_dir: Path) -> dict[str, Any]:
    resolved = dict(document_processing)
    mineru = resolved.get("mineru")
    if isinstance(mineru, dict):
        item = dict(mineru)
        for key in {"input_dir", "output_dir"}:
            if key in item:
                item[key] = _resolve_path_value(item[key], base_dir)
        resolved["mineru"] = item
    return resolved


def _resolve_connector_paths(connectors: dict[str, Any], base_dir: Path) -> dict[str, Any]:
    resolved: dict[str, Any] = {}
    path_keys = {
        "sessions_dir",
        "raw_output_dir",
        "raw_originals_dir",
        "raw_markdown_dir",
    }
    list_path_keys = {"roots"}
    for name, config in connectors.items():
        if not isinstance(config, dict):
            resolved[name] = config
            continue
        item = dict(config)
        settings = dict(item.get("settings", {}))
        for key in path_keys:
            if key in settings:
                settings[key] = _resolve_path_value(settings[key], base_dir)
        for key in list_path_keys:
            if key in settings and isinstance(settings[key], list):
                settings[key] = [_resolve_path_value(value, base_dir) for value in settings[key]]
        item["settings"] = settings
        resolved[name] = item
    return resolved


def _resolve_path_value(value: Any, base_dir: Path) -> Any:
    if not isinstance(value, str) or not value:
        return value
    path = Path(value).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (base_dir / path).resolve()
