from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from pydantic import ValidationError

from knoarbor.connectors.registry import ConnectorRegistry
from knoarbor.connectors.selection import selected_connector_configs
from knoarbor.core.config import KnoArborConfig, ModelProviderConfig, default_config_path, load_config
from knoarbor.core.schemas.doctor import DoctorCheck, DoctorReport, DoctorStatus
from knoarbor.runtime.run_monitor import list_runs
from knoarbor.semantic.llm import ModelGateway, is_local_or_private_model_endpoint


class DoctorService:
    """Read-only environment readiness checks for first-run and support use."""

    def __init__(self, registry: ConnectorRegistry | None = None) -> None:
        self.registry = registry or ConnectorRegistry()

    def run(self, *, config_path: str | Path | None = None, connector_names: list[str] | None = None) -> DoctorReport:
        resolved_config_path = Path(config_path).expanduser().resolve() if config_path else default_config_path()
        checks: list[DoctorCheck] = []
        config = self._load_config(resolved_config_path, checks)
        if config is not None:
            checks.extend(self._config_usage_checks(resolved_config_path))
            checks.extend(self._vault_checks(config))
            checks.extend(self._model_checks(config))
            checks.extend(self._connector_checks(config, connector_names))
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
        if not vault.exists():
            return [
                DoctorCheck(
                    name="vault.exists",
                    status="error",
                    message="Vault directory does not exist. Run `knoar init --vault ...` first.",
                    details={"vault_path": str(vault)},
                )
            ]
        if not vault.is_dir():
            return [
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

    def _model_checks(self, config: KnoArborConfig) -> list[DoctorCheck]:
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
        checks.extend(self._provider_runtime_checks(provider_name, provider))
        return checks

    def _provider_runtime_checks(self, provider_name: str, provider: ModelProviderConfig) -> list[DoctorCheck]:
        if not provider.base_url or not provider.model:
            return []
        gateway = ModelGateway.from_config(provider_name, provider, timeout_seconds=5)
        health = gateway.check()
        return [
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

    def _connector_checks(self, config: KnoArborConfig, connector_names: list[str] | None) -> list[DoctorCheck]:
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


def _report(checks: Iterable[DoctorCheck], *, config_path: str | None) -> DoctorReport:
    items = list(checks)
    summary = {status: sum(1 for check in items if check.status == status) for status in ("ok", "warning", "error")}
    if summary["error"]:
        status: DoctorStatus = "error"
    elif summary["warning"]:
        status = "warning"
    else:
        status = "ok"
    return DoctorReport(status=status, config_path=config_path, checks=items, summary=summary)
