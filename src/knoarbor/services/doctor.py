from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from pydantic import ValidationError

from knoarbor.connectors.registry import ConnectorRegistry
from knoarbor.connectors.selection import selected_connector_configs
from knoarbor.core.config import KnoArborConfig, ModelProviderConfig, default_config_path, load_config
from knoarbor.core.schemas.doctor import DoctorCheck, DoctorReport, DoctorStatus
from knoarbor.core.wiki_schema import CONTENT_PAGE_DIRS
from knoarbor.runtime.run_monitor import list_runs
from knoarbor.semantic.llm import ModelGateway, ProviderHealthCheck, is_local_or_private_model_endpoint


class DoctorService:
    """Read-only environment readiness checks for first-run and support use."""

    def __init__(self, registry: ConnectorRegistry | None = None) -> None:
        self.registry = registry or ConnectorRegistry()

    def run(
        self,
        *,
        config_path: str | Path | None = None,
        connector_names: list[str] | None = None,
        check_model_runtime: bool = True,
        check_connector_runtime: bool = True,
    ) -> DoctorReport:
        resolved_config_path = Path(config_path).expanduser().resolve() if config_path else default_config_path()
        checks: list[DoctorCheck] = []
        config = self._load_config(resolved_config_path, checks)
        if config is not None:
            checks.extend(self._config_usage_checks(resolved_config_path))
            checks.extend(self._vault_checks(config))
            checks.extend(self._wiki_content_checks(config))
            checks.extend(self._model_checks(config, check_model_runtime=check_model_runtime))
            checks.extend(self._connector_checks(config, connector_names, check_connector_runtime=check_connector_runtime))
            checks.extend(self._document_processing_checks(config))
            checks.extend(self._run_checks(config))
        return _report(checks, config_path=str(resolved_config_path))

    def _load_config(self, path: Path, checks: list[DoctorCheck]) -> KnoArborConfig | None:
        if not path.exists():
            checks.append(
                DoctorCheck(
                    name="config.exists",
                    status="error",
                    message="Config file does not exist.",
                    details={"path": str(path)},
                )
            )
            return None
        try:
            config = load_config(path)
        except (ValidationError, ValueError, OSError) as exc:
            checks.append(
                DoctorCheck(
                    name="config.load",
                    status="error",
                    message=f"Config file could not be loaded: {exc}",
                    details={"path": str(path), "error_type": type(exc).__name__},
                )
            )
            return None
        checks.append(DoctorCheck(name="config.load", status="ok", message="Config file loaded.", details={"path": str(path)}))
        return config

    def _config_usage_checks(self, path: Path) -> list[DoctorCheck]:
        if path.name == "config.example.yaml":
            return [
                DoctorCheck(
                    name="config.local_file",
                    status="warning",
                    message="Using config.example.yaml. Copy it to config.yaml for persistent local settings.",
                    details={"path": str(path)},
                )
            ]
        return [DoctorCheck(name="config.local_file", status="ok", message="Using a local config file.", details={"path": str(path)})]

    def _vault_checks(self, config: KnoArborConfig) -> list[DoctorCheck]:
        vault = config.vault.path
        checks: list[DoctorCheck] = []
        active_vault_id = config.active_vault_id()
        profiles = config.vaults.profiles
        checks.append(
            DoctorCheck(
                name="vault.profiles",
                status="ok" if profiles else "warning",
                message=f"{len(profiles)} vault profile(s) configured." if profiles else "No vault profiles are configured.",
                details={"active_vault_id": active_vault_id, "profiles": config.vault_profiles_summary()},
            )
        )
        for vault_id, profile in sorted(profiles.items()):
            profile_path = profile.path
            active = vault_id == active_vault_id
            if not profile_path.exists():
                checks.append(
                    DoctorCheck(
                        name=f"vault.profile.{vault_id}",
                        status="error" if active else "warning",
                        message="Active vault profile directory does not exist." if active else "Vault profile directory does not exist.",
                        details={"vault_id": vault_id, "vault_name": profile.name, "vault_path": str(profile_path), "active": active},
                    )
                )
                continue
            if not profile_path.is_dir():
                checks.append(
                    DoctorCheck(
                        name=f"vault.profile.{vault_id}",
                        status="error" if active else "warning",
                        message="Active vault profile path is not a directory." if active else "Vault profile path is not a directory.",
                        details={"vault_id": vault_id, "vault_name": profile.name, "vault_path": str(profile_path), "active": active},
                    )
                )
                continue
            checks.append(
                DoctorCheck(
                    name=f"vault.profile.{vault_id}",
                    status="ok",
                    message="Vault profile directory exists.",
                    details={"vault_id": vault_id, "vault_name": profile.name, "vault_path": str(profile_path), "active": active},
                )
            )
        if not vault.exists():
            return [
                *checks,
                DoctorCheck(
                    name="vault.exists",
                    status="error",
                    message="Vault directory does not exist. Run `knoar init --vault ...` first.",
                    details={"vault_path": str(vault)},
                )
            ]
        if not vault.is_dir():
            return [
                *checks,
                DoctorCheck(
                    name="vault.exists",
                    status="error",
                    message="Vault path is not a directory.",
                    details={"vault_path": str(vault)},
                )
            ]
        checks.append(DoctorCheck(name="vault.exists", status="ok", message="Vault directory exists.", details={"vault_path": str(vault)}))
        required = ["SCHEMA.md", "index.md", "log.md", ".knoarborignore"]
        missing = [name for name in required if not (vault / name).exists()]
        checks.append(
            DoctorCheck(
                name="vault.structure",
                status="warning" if missing else "ok",
                message="Vault is missing initialization files." if missing else "Vault initialization files are present.",
                details={"missing": missing, "required": required},
            )
        )
        return checks

    def _wiki_content_checks(self, config: KnoArborConfig) -> list[DoctorCheck]:
        vault = config.vault.path
        if not vault.exists() or not vault.is_dir():
            return []
        counts = {
            page_dir: len([path for path in (vault / page_dir).glob("*.md") if path.is_file()]) if (vault / page_dir).exists() else 0
            for page_dir in CONTENT_PAGE_DIRS
        }
        page_count = sum(counts.values())
        return [
            DoctorCheck(
                name="wiki.content",
                status="ok" if page_count else "warning",
                message=f"Found {page_count} maintained wiki page(s)." if page_count else "No maintained wiki pages found yet.",
                details={"page_count": page_count, "directory_counts": counts},
            )
        ]

    def _model_checks(self, config: KnoArborConfig, *, check_model_runtime: bool) -> list[DoctorCheck]:
        checks: list[DoctorCheck] = []
        provider_name = config.models.default_provider
        if not provider_name:
            return [DoctorCheck(name="models.default_provider", status="error", message="No default model provider is configured.")]
        provider = config.models.providers.get(provider_name)
        if provider is None:
            return [
                DoctorCheck(
                    name="models.default_provider",
                    status="error",
                    message="Default model provider is not listed in models.providers.",
                    details={"default_provider": provider_name, "providers": sorted(config.models.providers)},
                )
            ]
        checks.append(
            DoctorCheck(
                name="models.default_provider",
                status="ok",
                message="Default model provider is configured.",
                details={"default_provider": provider_name, "model": provider.model, "base_url": provider.base_url},
            )
        )
        if not provider.model:
            checks.append(DoctorCheck(name="models.model", status="error", message="Default provider has no model name.", details={"provider": provider_name}))
        else:
            checks.append(DoctorCheck(name="models.model", status="ok", message="Default provider has a model name.", details={"provider": provider_name, "model": provider.model}))
        if not provider.api_key_env:
            if is_local_or_private_model_endpoint(provider.base_url):
                checks.append(DoctorCheck(name="models.api_key_env", status="ok", message="Default provider uses a local or private unauthenticated endpoint.", details={"provider": provider_name}))
            else:
                checks.append(DoctorCheck(name="models.api_key_env", status="warning", message="Default provider has no api_key_env. This is only valid for local or unauthenticated endpoints.", details={"provider": provider_name}))
        elif os.environ.get(provider.api_key_env):
            checks.append(DoctorCheck(name="models.api_key_env", status="ok", message="API key environment variable is set.", details={"provider": provider_name, "api_key_env": provider.api_key_env}))
        else:
            checks.append(DoctorCheck(name="models.api_key_env", status="error", message="API key environment variable is not set.", details={"provider": provider_name, "api_key_env": provider.api_key_env}))
        if check_model_runtime:
            checks.extend(self._provider_runtime_checks(provider_name, provider))
        return checks

    def _provider_runtime_checks(self, provider_name: str, provider: ModelProviderConfig) -> list[DoctorCheck]:
        if not provider.base_url or not provider.model:
            return []
        gateway = ModelGateway.from_config(provider_name, provider, timeout_seconds=5)
        health = gateway.check()
        checks = [
            DoctorCheck(
                name="models.endpoint",
                status="ok" if health.available else "warning",
                message=health.message,
                details={"provider": provider_name, "model": provider.model, **health.details},
            ),
            DoctorCheck(
                name="models.structured_output",
                status="ok" if health.structured_output else "warning",
                message="Provider is configured to request JSON object output." if health.structured_output else "Provider JSON mode is disabled; structured agent outputs may be less reliable.",
                details={"provider": provider_name, "json_mode": bool(health.structured_output)},
            ),
        ]
        if health.available:
            checks.append(_configured_model_check(provider_name, provider, health))
        return checks

    def _connector_checks(self, config: KnoArborConfig, connector_names: list[str] | None, *, check_connector_runtime: bool) -> list[DoctorCheck]:
        checks: list[DoctorCheck] = []
        try:
            selected = selected_connector_configs(config, connector_names)
        except ValueError as exc:
            return [DoctorCheck(name="connectors.selection", status="error", message=str(exc))]
        if not selected:
            return [
                DoctorCheck(
                    name="connectors.enabled",
                    status="warning",
                    message="No enabled connector matched the requested selection.",
                    details={"requested": connector_names or [], "configured": sorted(config.connectors)},
                )
            ]
        checks.append(
            DoctorCheck(
                name="connectors.enabled",
                status="ok",
                message=f"{len(selected)} connector(s) selected.",
                details={"connectors": sorted(selected)},
            )
        )
        if not check_connector_runtime:
            return checks
        for name, connector_config in selected.items():
            try:
                connector = self.registry.get(name)
                refs = connector.discover(connector_config)
            except Exception as exc:
                checks.append(
                    DoctorCheck(
                        name=f"connectors.{name}",
                        status="error",
                        message=f"Connector discovery failed: {exc}",
                        details={"connector": name, "error_type": type(exc).__name__},
                    )
                )
                continue
            checks.append(
                DoctorCheck(
                    name=f"connectors.{name}",
                    status="ok" if refs else "warning",
                    message=f"Discovered {len(refs)} source(s)." if refs else "Connector is enabled but discovered no sources.",
                    details={"connector": name, "source_count": len(refs)},
                )
            )
        return checks

    def _document_processing_checks(self, config: KnoArborConfig) -> list[DoctorCheck]:
        mineru = config.document_processing.mineru
        if not mineru.enabled:
            return [DoctorCheck(name="document_processing.mineru", status="ok", message="MinerU adapter is disabled; Markdown-only ingest is available.")]
        checks: list[DoctorCheck] = []
        checks.append(
            DoctorCheck(
                name="document_processing.mineru.endpoint",
                status="ok" if mineru.endpoint else "error",
                message="MinerU endpoint is configured." if mineru.endpoint else "MinerU is enabled but endpoint is missing.",
                details={"endpoint": mineru.endpoint},
            )
        )
        for name, path, required in [
            ("input_dir", mineru.input_dir, False),
            ("output_dir", mineru.output_dir, True),
        ]:
            if path is None:
                checks.append(DoctorCheck(name=f"document_processing.mineru.{name}", status="warning", message=f"MinerU {name} is not configured."))
                continue
            exists = path.exists()
            checks.append(
                DoctorCheck(
                    name=f"document_processing.mineru.{name}",
                    status="ok" if exists or not required else "warning",
                    message=f"MinerU {name} exists." if exists else f"MinerU {name} does not exist yet.",
                    details={"path": str(path), "required": required},
                )
            )
        return checks

    def _run_checks(self, config: KnoArborConfig) -> list[DoctorCheck]:
        if not config.vault.path.exists() or not config.vault.path.is_dir():
            return []
        try:
            recent = list_runs(config.vault.path, limit=10)
        except Exception as exc:
            return [DoctorCheck(name="runs.recent", status="warning", message=f"Recent run records could not be read: {exc}", details={"error_type": type(exc).__name__})]
        active = [run for run in recent.runs if run.status not in {"completed", "failed", "cancelled", "partially_failed"}]
        failed = [run for run in recent.runs if run.status in {"failed", "partially_failed"}]
        status: DoctorStatus = "warning" if active or failed else "ok"
        return [
            DoctorCheck(
                name="runs.recent",
                status=status,
                message="Recent run records checked.",
                details={"recent_count": len(recent.runs), "active_count": len(active), "failed_count": len(failed)},
            )
        ]


def _configured_model_check(provider_name: str, provider: ModelProviderConfig, health: ProviderHealthCheck) -> DoctorCheck:
    details: dict[str, object] = {
        "provider": provider_name,
        "model": provider.model,
        "models_list_valid": health.details.get("models_list_valid"),
        "model_count": health.details.get("model_count", 0),
        "configured_model_found": health.details.get("configured_model_found"),
    }
    model_ids = health.details.get("model_ids")
    if isinstance(model_ids, list):
        details["model_ids_preview"] = model_ids[:20]
    if health.details.get("models_list_valid") is not True:
        return DoctorCheck(
            name="models.configured_model",
            status="warning",
            message="Provider endpoint is reachable, but /models did not return a standard model list.",
            details=details,
        )
    if int(health.details.get("model_count") or 0) == 0:
        return DoctorCheck(
            name="models.configured_model",
            status="warning",
            message="Provider endpoint is reachable, but no models are installed or exposed.",
            details=details,
        )
    if health.details.get("configured_model_found") is True:
        return DoctorCheck(
            name="models.configured_model",
            status="ok",
            message="Configured model is exposed by the provider endpoint.",
            details=details,
        )
    return DoctorCheck(
        name="models.configured_model",
        status="warning",
        message="Configured model was not found in the provider model list.",
        details=details,
    )


def _report(checks: Iterable[DoctorCheck], *, config_path: str | None) -> DoctorReport:
    items = list(checks)
    summary = {status: sum(1 for check in items if check.status == status) for status in ("ok", "warning", "error")}
    if summary["error"]:
        status: DoctorStatus = "error"
    elif summary["warning"]:
        status = "warning"
    else:
        status = "ok"
    return DoctorReport(status=status, config_path=config_path, checks=items, summary=summary, next_steps=_next_steps(items))


def _next_steps(checks: list[DoctorCheck]) -> list[str]:
    by_name = {check.name: check for check in checks}
    steps: list[str] = []

    def add(step: str) -> None:
        if step not in steps:
            steps.append(step)

    def status_of(name: str) -> DoctorStatus:
        check = by_name.get(name)
        return check.status if check else "ok"

    if status_of("config.exists") == "error":
        add("Run `uv run knoar first-run --vault ./wiki` to create config.yaml and initialize a local vault.")
        return steps

    if status_of("config.local_file") == "warning":
        add("Copy config.example.yaml to config.yaml before editing persistent local settings.")

    if status_of("vault.exists") == "error":
        add("Run `uv run knoar init --vault ./wiki` or `uv run knoar first-run --vault ./wiki` to create the vault.")
    elif status_of("vault.structure") == "warning":
        add("Run `uv run knoar init --vault <vault-path>` to restore missing vault initialization files.")

    if status_of("models.api_key_env") == "error":
        check = by_name["models.api_key_env"]
        api_key_env = check.details.get("api_key_env")
        if api_key_env:
            add(f"Set `{api_key_env}` in .env, then reload the environment before running semantic workflows.")
        else:
            add("Set the configured model API key environment variable before running semantic workflows.")
    if status_of("models.configured_model") == "warning":
        check = by_name["models.configured_model"]
        model = check.details.get("model")
        provider = check.details.get("provider")
        if model:
            add(f"Install or expose model `{model}` on provider `{provider}` before running semantic workflows.")
        else:
            add("Install or expose the configured model before running semantic workflows.")
    if status_of("models.structured_output") == "warning":
        add("Enable JSON mode for the model provider when available to make structured agent outputs more reliable.")

    if status_of("connectors.enabled") == "warning":
        add("Enable at least one connector or pass `--connector <name>` for the source you want to compile.")

    connector_warnings = [check for check in checks if check.name.startswith("connectors.") and check.status == "warning"]
    if connector_warnings:
        add("Add source files under a configured input path, then run `uv run knoar ingest --write`.")

    wiki_content = by_name.get("wiki.content")
    if wiki_content and wiki_content.status == "warning":
        add("Run `uv run knoar ingest --connector markdown --write` to compile the bundled example or your Markdown notes.")
    elif wiki_content and wiki_content.status == "ok":
        add("Run `uv run knoar query \"Agent Loop 是什么？\"` or open the local UI to query maintained pages.")

    runs = by_name.get("runs.recent")
    if runs and runs.status == "warning":
        active_count = int(runs.details.get("active_count") or 0)
        failed_count = int(runs.details.get("failed_count") or 0)
        if active_count:
            add("Open `uv run knoar serve` and check Run Monitor for active workflow progress.")
        if failed_count:
            add("Review recent run reports, then retry failed ingest or lint work from the Run page or CLI.")

    if not steps:
        add("Run `uv run knoar serve` to open the local console, or use `uv run knoar ingest`, `lint`, and `query` from the CLI.")
    return steps
