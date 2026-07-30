from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

import yaml

from knoarbor.core.config import (
    SUPPORTED_CONFIG_VERSION,
    KnoArborConfig,
    default_config_path,
    default_config_template_path,
    migrate_config_data,
    normalize_mineru_backend,
    normalize_provider_url,
    prepare_config_data,
)
from knoarbor.core.errors import UserInputError
from knoarbor.core.schemas.connectors import SourceConnectorCatalogItem
from knoarbor.document_processing.mineru import probe_mineru_endpoint
from knoarbor.semantic.llm import is_local_or_private_model_endpoint
from knoarbor.services.source_catalog import SourceCatalogService
from knoarbor.services.ui_config_models import (
    DEFAULT_CHAT_RAW_OUTPUT_DIR,
    DEFAULT_CHAT_SESSION_DIRS,
    DEFAULT_MARKDOWN_RAW_OUTPUT_DIR,
    DEFAULT_MINERU_MARKDOWN_OUTPUT_DIR,
    MINERU_ADVANCED_FIELD_KEYS,
    UiConfigDiagnosticItem,
    UiConfigDiagnostics,
    UiConfigFormResponse,
    UiConfigFormUpdateRequest,
    UiConfigResponse,
    UiConfigUpdateRequest,
    UiConfigUpdateResponse,
    UiImageGenerationProviderForm,
    UiModelProviderForm,
    UiVaultProfileForm,
)
from knoarbor.storage.source_metrics import connector_source_metric_identity, load_source_counts, source_metric_key, update_source_counts
from knoarbor.storage.wiki_init import init_wiki_vault

class UiConfigService:
    """Owns UI-facing config read, validation, diagnostics, and writes."""

    def read_raw(self, config_path: str | None = None) -> UiConfigResponse:
        path = resolve_ui_config_path(config_path)
        exists = path.exists()
        content = path.read_text(encoding="utf-8") if exists else default_config_template_path().read_text(encoding="utf-8")
        return UiConfigResponse(
            config_path=str(path),
            exists=exists,
            content=content,
            summary=summarize_config_content(content, base_dir=path.parent),
        )

    def write_raw(self, request: UiConfigUpdateRequest) -> UiConfigUpdateResponse:
        path = resolve_ui_config_path(request.config_path)
        summary = summarize_config_content(request.content, base_dir=path.parent)
        write_private_text_atomic(path, request.content)
        return UiConfigUpdateResponse(config_path=str(path), saved=True, summary=summary)

    def read_form(self, config_path: str | None = None) -> UiConfigFormResponse:
        path = resolve_ui_config_path(config_path)
        content = path.read_text(encoding="utf-8") if path.exists() else default_config_template_path().read_text(encoding="utf-8")
        return config_to_form(config_from_content(content, base_dir=path.parent))

    def read_diagnostics(self, config_path: str | None = None, *, refresh_source_counts: bool = False) -> UiConfigDiagnostics:
        path = resolve_ui_config_path(config_path)
        content = path.read_text(encoding="utf-8") if path.exists() else default_config_template_path().read_text(encoding="utf-8")
        return config_diagnostics(config_from_content(content, base_dir=path.parent), refresh_source_counts=refresh_source_counts)

    def write_form(self, request: UiConfigFormUpdateRequest) -> UiConfigUpdateResponse:
        path = resolve_ui_config_path(request.config_path)
        source_path = path if path.exists() else default_config_template_path()
        base_data = yaml.safe_load(source_path.read_text(encoding="utf-8")) or {}
        if not isinstance(base_data, dict):
            raise UserInputError("Config root must be a YAML object")
        content = render_config_from_form(request, base_data, base_dir=path.parent)
        summary = summarize_config_content(content, base_dir=path.parent)
        _initialize_configured_vaults(summary)
        write_private_text_atomic(path, content)
        return UiConfigUpdateResponse(config_path=str(path), saved=True, summary=summary)


def resolve_ui_config_path(config_path: str | None) -> Path:
    if config_path:
        path = Path(config_path).expanduser().resolve()
    else:
        detected = default_config_path()
        path = detected.with_name("config.yaml") if detected.name == "config.example.yaml" else detected
    if path.name not in {"config.yaml", "config.yml"}:
        raise UserInputError("UI can only edit config.yaml or config.yml")
    return path


def write_private_text_atomic(path: Path, content: str) -> None:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            os.chmod(temporary_path, 0o600)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        os.chmod(path, 0o600)
        temporary_path = None
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY)
        except OSError:
            directory_fd = None
        if directory_fd is not None:
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def summarize_default_config() -> dict[str, object]:
    path = resolve_ui_config_path(None)
    if path.exists():
        return summarize_config_content(path.read_text(encoding="utf-8"), base_dir=path.parent)
    example_path = default_config_template_path()
    return summarize_config_content(example_path.read_text(encoding="utf-8"), base_dir=example_path.parent)


def summarize_config_content(content: str, *, base_dir: Path) -> dict[str, object]:
    config = config_from_content(content, base_dir=base_dir)
    return {
        "project_name": config.active_vault_name(),
        "vault_path": str(config.vault.path),
        "vault_id": config.active_vault_id(),
        "vault_name": config.active_vault_name(),
        "vaults": config.vault_profiles_summary(),
        "server": f"{config.server.host}:{config.server.port}",
        "default_provider": config.models.default_provider,
        "provider_count": len(config.models.providers),
        "image_default_provider": config.image_generation.default_provider,
        "image_provider_count": len(config.image_generation.providers),
        "enabled_connectors": config.enabled_connectors(),
        "enabled_document_processors": enabled_document_processors(config),
        "default_max_tokens": config.models.default_max_tokens,
        "request_timeout_seconds": config.models.request_timeout_seconds,
    }


def _initialize_configured_vaults(summary: dict[str, object]) -> None:
    for item in summary.get("vaults", []):
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        if path:
            init_wiki_vault(Path(path))


def enabled_document_processors(config: KnoArborConfig) -> list[str]:
    enabled: list[str] = []
    if config.document_processing.mineru.enabled:
        enabled.append("mineru")
    return enabled


def config_from_content(content: str, *, base_dir: Path) -> KnoArborConfig:
    try:
        loaded = yaml.safe_load(content) or {}
    except yaml.YAMLError as exc:
        raise UserInputError(f"Invalid YAML: {exc}") from exc
    if not isinstance(loaded, dict):
        raise UserInputError("Config root must be a YAML object")
    try:
        return KnoArborConfig.model_validate(prepare_config_data(loaded, base_dir))
    except Exception as exc:
        raise UserInputError(f"Invalid config: {exc}") from exc


def config_to_form(config: KnoArborConfig) -> UiConfigFormResponse:
    codex = config.connectors.get("codex")
    hermes = config.connectors.get("hermes")
    openclaw = config.connectors.get("openclaw")
    claude_code = config.connectors.get("claude_code")
    generic_chat = config.connectors.get("generic_chat")
    codex_settings = codex.settings if codex else {}
    hermes_settings = hermes.settings if hermes else {}
    openclaw_settings = openclaw.settings if openclaw else {}
    claude_code_settings = claude_code.settings if claude_code else {}
    generic_chat_settings = generic_chat.settings if generic_chat else {}
    return UiConfigFormResponse(
        project_name=config.active_vault_name(),
        vault_path=str(config.vault.path),
        vault_id=config.active_vault_id(),
        vaults=[
            UiVaultProfileForm(
                id=vault_id,
                name=profile.name,
                path=str(profile.path),
                active=vault_id == config.active_vault_id(),
            )
            for vault_id, profile in sorted(config.vaults.profiles.items())
        ],
        server_host=config.server.host,
        server_port=config.server.port,
        default_provider=config.models.default_provider or "",
        default_max_tokens=config.models.default_max_tokens,
        request_timeout_seconds=config.models.request_timeout_seconds,
        providers=[
            UiModelProviderForm(
                name=name,
                adapter=provider.adapter,
                base_url=provider.base_url or "",
                api_key=provider.api_key or "",
                model=provider.model or "",
                json_mode=provider.json_mode,
                tls_ca_file=str(provider.tls_ca_file) if provider.tls_ca_file else "",
                context_window=provider.context_window,
                max_output_tokens=provider.max_output_tokens,
                extra_body=provider.extra_body,
            )
            for name, provider in sorted(config.models.providers.items())
        ],
        image_default_provider=config.image_generation.default_provider or "",
        image_request_timeout_seconds=config.image_generation.request_timeout_seconds,
        image_providers=[
            UiImageGenerationProviderForm(
                name=name,
                adapter=provider.adapter,
                base_url=provider.base_url or "",
                endpoint_path=provider.endpoint_path,
                api_key=provider.api_key or "",
                model=provider.model or "",
                tls_ca_file=str(provider.tls_ca_file) if provider.tls_ca_file else "",
                resolution=provider.resolution or "2720*1536",
                num_inference_steps=provider.num_inference_steps,
                guidance=provider.guidance,
                extra_body=provider.extra_body,
            )
            for name, provider in sorted(config.image_generation.providers.items())
        ],
        enabled_connectors=config.enabled_connectors(),
        detected_chat_source_dirs=_detected_chat_source_dirs(),
        codex_enabled=bool(codex.enabled) if codex else False,
        codex_sessions_dir="",
        codex_raw_output_dir=str(codex_settings.get("raw_output_dir") or ""),
        hermes_enabled=bool(hermes.enabled) if hermes else False,
        hermes_sessions_dir="",
        hermes_raw_output_dir=str(hermes_settings.get("raw_output_dir") or ""),
        openclaw_enabled=bool(openclaw.enabled) if openclaw else False,
        openclaw_sessions_dir="",
        openclaw_raw_output_dir=str(openclaw_settings.get("raw_output_dir") or ""),
        claude_code_enabled=bool(claude_code.enabled) if claude_code else False,
        claude_code_sessions_dir="",
        claude_code_raw_output_dir=str(claude_code_settings.get("raw_output_dir") or ""),
        generic_chat_enabled=bool(generic_chat.enabled) if generic_chat else False,
        generic_chat_roots=[str(item) for item in generic_chat_settings.get("roots", []) if item],
        generic_chat_raw_output_dir=str(generic_chat_settings.get("raw_output_dir") or ""),
        markdown_enabled=False,
        markdown_roots=[],
        markdown_raw_output_dir=DEFAULT_MARKDOWN_RAW_OUTPUT_DIR,
        mineru_enabled=config.document_processing.mineru.enabled,
        mineru_endpoint=config.document_processing.mineru.endpoint or "",
        mineru_input_dir="",
        mineru_output_dir=str(config.document_processing.mineru.output_dir or ""),
        mineru_parse_method=config.document_processing.mineru.mode or "auto",
        mineru_backend=_normalize_mineru_backend(config.document_processing.mineru.extra_fields.get("backend")),
        mineru_timeout_seconds=config.document_processing.mineru.timeout_seconds,
        mineru_patterns=list(config.document_processing.mineru.patterns),
        mineru_recursive=config.document_processing.mineru.recursive,
        mineru_return_md=bool(config.document_processing.mineru.extra_fields.get("return_md", True)),
        mineru_return_middle_json=bool(config.document_processing.mineru.extra_fields.get("return_middle_json")),
        mineru_return_model_output=bool(config.document_processing.mineru.extra_fields.get("return_model_output")),
        mineru_return_content_list=bool(config.document_processing.mineru.extra_fields.get("return_content_list")),
        mineru_return_images=bool(config.document_processing.mineru.extra_fields.get("return_images")),
        mineru_response_format_zip=bool(config.document_processing.mineru.extra_fields.get("response_format_zip")),
        mineru_lang_list=_mineru_lang_list_value(config.document_processing.mineru.extra_fields.get("lang_list", "ch")),
        mineru_formula_enable=bool(config.document_processing.mineru.extra_fields.get("formula_enable", True)),
        mineru_table_enable=bool(config.document_processing.mineru.extra_fields.get("table_enable", True)),
        mineru_server_url=str(config.document_processing.mineru.extra_fields.get("server_url") or ""),
        mineru_start_page_id=int(config.document_processing.mineru.extra_fields.get("start_page_id", 0)),
        mineru_end_page_id=int(config.document_processing.mineru.extra_fields.get("end_page_id", 99999)),
        mineru_extra_fields_json=_mineru_extra_fields_json(config.document_processing.mineru.extra_fields),
    )


def _detected_chat_source_dirs() -> dict[str, list[str]]:
    detected: dict[str, list[str]] = {}
    for name, default_dir in DEFAULT_CHAT_SESSION_DIRS.items():
        path = Path(default_dir).expanduser()
        detected[name] = [str(path)] if path.is_dir() else []
    return detected


def config_diagnostics(config: KnoArborConfig, *, refresh_source_counts: bool = False) -> UiConfigDiagnostics:
    connector_items: list[UiConfigDiagnosticItem] = []
    processor_items: list[UiConfigDiagnosticItem] = []
    provider_items: list[UiConfigDiagnosticItem] = []
    path_items: list[UiConfigDiagnosticItem] = []
    connector_capabilities = _connector_contracts()
    vault = Path(config.vault.path).expanduser()
    cached_counts = load_source_counts(vault)
    refreshed_counts: dict[str, int] = {}

    path_items.append(_path_diagnostic("vault", "path", vault, enabled=True, detail=f"active:{config.active_vault_id()}"))
    for vault_id, profile in sorted(config.vaults.profiles.items()):
        active = vault_id == config.active_vault_id()
        path_items.append(
            _path_diagnostic(
                f"vault.{vault_id}",
                "path",
                Path(profile.path).expanduser(),
                enabled=True,
                detail=f"{profile.name} ({'active' if active else 'available'})",
            )
        )

    codex = config.connectors.get("codex")
    codex_settings = codex.settings if codex else {}
    codex_identity = connector_source_metric_identity("codex", codex_settings)
    codex_path = Path(str(codex_settings.get("sessions_dir") or "")).expanduser() if codex_settings.get("sessions_dir") else None
    connector_items.append(
        _connector_diagnostic(
            _path_diagnostic(
                "codex",
                "connector",
                codex_path,
                enabled=bool(codex.enabled) if codex else False,
                pattern=str(codex_settings.get("pattern") or "rollout-*.jsonl"),
                metric_path=codex_identity["path"] if codex_identity else None,
                metric_pattern=codex_identity["pattern"] if codex_identity else None,
                cached_counts=cached_counts,
                refreshed_counts=refreshed_counts,
                refresh_count=refresh_source_counts,
            ),
            connector_capabilities,
        )
    )

    hermes = config.connectors.get("hermes")
    hermes_settings = hermes.settings if hermes else {}
    hermes_identity = connector_source_metric_identity("hermes", hermes_settings)
    hermes_path = Path(str(hermes_settings.get("sessions_dir") or "")).expanduser() if hermes_settings.get("sessions_dir") else None
    connector_items.append(
        _connector_diagnostic(
            _path_diagnostic(
                "hermes",
                "connector",
                hermes_path,
                enabled=bool(hermes.enabled) if hermes else False,
                pattern=str(hermes_settings.get("pattern") or "session_*.json"),
                metric_path=hermes_identity["path"] if hermes_identity else None,
                metric_pattern=hermes_identity["pattern"] if hermes_identity else None,
                cached_counts=cached_counts,
                refreshed_counts=refreshed_counts,
                refresh_count=refresh_source_counts,
            ),
            connector_capabilities,
        )
    )

    openclaw = config.connectors.get("openclaw")
    openclaw_settings = openclaw.settings if openclaw else {}
    openclaw_identity = connector_source_metric_identity("openclaw", openclaw_settings)
    openclaw_path = Path(str(openclaw_settings.get("sessions_dir") or "")).expanduser() if openclaw_settings.get("sessions_dir") else None
    connector_items.append(
        _connector_diagnostic(
            _path_diagnostic(
                "openclaw",
                "connector",
                openclaw_path,
                enabled=bool(openclaw.enabled) if openclaw else False,
                pattern=str(openclaw_settings.get("pattern") or "*.jsonl"),
                metric_path=openclaw_identity["path"] if openclaw_identity else None,
                metric_pattern=openclaw_identity["pattern"] if openclaw_identity else None,
                cached_counts=cached_counts,
                refreshed_counts=refreshed_counts,
                refresh_count=refresh_source_counts,
            ),
            connector_capabilities,
        )
    )

    claude_code = config.connectors.get("claude_code")
    claude_code_settings = claude_code.settings if claude_code else {}
    claude_code_identity = connector_source_metric_identity("claude_code", claude_code_settings)
    claude_code_path = Path(str(claude_code_settings.get("sessions_dir") or "")).expanduser() if claude_code_settings.get("sessions_dir") else None
    connector_items.append(
        _connector_diagnostic(
            _path_diagnostic(
                "claude_code",
                "connector",
                claude_code_path,
                enabled=bool(claude_code.enabled) if claude_code else False,
                pattern=str(claude_code_settings.get("pattern") or "*.jsonl"),
                metric_path=claude_code_identity["path"] if claude_code_identity else None,
                metric_pattern=claude_code_identity["pattern"] if claude_code_identity else None,
                cached_counts=cached_counts,
                refreshed_counts=refreshed_counts,
                refresh_count=refresh_source_counts,
            ),
            connector_capabilities,
        )
    )

    generic_chat = config.connectors.get("generic_chat")
    generic_chat_settings = generic_chat.settings if generic_chat else {}
    generic_chat_identity = connector_source_metric_identity("generic_chat", generic_chat_settings)
    generic_chat_roots = [Path(str(root)).expanduser() for root in generic_chat_settings.get("roots", []) if root]
    connector_items.append(
        _connector_diagnostic(
            _multi_path_diagnostic(
                "generic_chat",
                "connector",
                generic_chat_roots,
                enabled=bool(generic_chat.enabled) if generic_chat else False,
                pattern="*",
                metric_path=generic_chat_identity["path"] if generic_chat_identity else None,
                metric_pattern=generic_chat_identity["pattern"] if generic_chat_identity else None,
                cached_counts=cached_counts,
                refreshed_counts=refreshed_counts,
                refresh_count=refresh_source_counts,
            ),
            connector_capabilities,
        )
    )

    markdown = config.connectors.get("markdown")
    markdown_settings = markdown.settings if markdown else {}
    markdown_identity = connector_source_metric_identity("markdown", markdown_settings)
    markdown_roots = [Path(str(root)).expanduser() for root in markdown_settings.get("roots", []) if root]
    connector_items.append(
        _connector_diagnostic(
            _multi_path_diagnostic(
                "markdown",
                "connector",
                markdown_roots,
                enabled=bool(markdown.enabled) if markdown else False,
                pattern=str(markdown_settings.get("pattern") or "*.md"),
                metric_path=markdown_identity["path"] if markdown_identity else None,
                metric_pattern=markdown_identity["pattern"] if markdown_identity else None,
                cached_counts=cached_counts,
                refreshed_counts=refreshed_counts,
                refresh_count=refresh_source_counts,
            ),
            connector_capabilities,
        )
    )

    mineru = config.document_processing.mineru
    if mineru.enabled and not mineru.endpoint:
        processor_items.append(UiConfigDiagnosticItem(name="mineru", category="processor", enabled=True, ok=False, code="endpoint_missing"))
    elif mineru.enabled and mineru.endpoint:
        ok, detail = probe_mineru_endpoint(mineru.endpoint, headers=mineru.headers)
        processor_items.append(
            UiConfigDiagnosticItem(
                name="mineru",
                category="processor",
                enabled=True,
                ok=ok,
                code="ready" if ok else "endpoint_unreachable",
                detail=f"{mineru.endpoint} · {detail}",
            )
        )
    else:
        processor_items.append(
            UiConfigDiagnosticItem(
                name="mineru",
                category="processor",
                enabled=False,
                ok=True,
                code="disabled",
            )
        )

    for name, provider in sorted(config.models.providers.items()):
        missing = []
        if not provider.base_url:
            missing.append("base_url")
        if not provider.model:
            missing.append("model")
        if not provider.resolved_api_key() and not is_local_or_private_model_endpoint(provider.base_url):
            missing.append("api_key")
        ok = not missing
        detail_parts = list(missing)
        if provider.context_window:
            detail_parts.append(f"context_window={provider.context_window}")
        if provider.max_output_tokens:
            detail_parts.append(f"max_output_tokens={provider.max_output_tokens}")
        provider_items.append(UiConfigDiagnosticItem(name=name, category="provider", enabled=True, ok=ok, code="ready" if ok else "provider_incomplete", detail=", ".join(detail_parts)))

    if refreshed_counts:
        update_source_counts(vault, refreshed_counts)
    return UiConfigDiagnostics(connectors=connector_items, processors=processor_items, providers=provider_items, paths=path_items)


def _connector_contracts() -> dict[str, SourceConnectorCatalogItem]:
    catalog = SourceCatalogService().list_catalog()
    return {item.name: item for item in catalog.connectors}


def _connector_diagnostic(
    item: UiConfigDiagnosticItem,
    capabilities_by_name: dict[str, SourceConnectorCatalogItem],
) -> UiConfigDiagnosticItem:
    capability = capabilities_by_name.get(item.name)
    data = item.model_dump()
    if capability:
        data.update(
            {
                "version": capability.version,
                "source_types": capability.source_types,
                "supports_checkpoint": capability.supports_checkpoint,
                "supports_segmentation_hint": capability.supports_segmentation_hint,
                "requires_external_service": capability.requires_external_service,
            }
        )
    return UiConfigDiagnosticItem.model_validate(data)


def render_config_from_form(form: UiConfigFormUpdateRequest, base_data: dict[str, Any], *, base_dir: Path) -> str:
    providers: dict[str, dict[str, object]] = {}
    for provider in form.providers:
        name = provider.name.strip()
        if not name:
            continue
        base_url = provider.base_url.strip()
        if base_url:
            suffixes = ("/chat/completions",) if provider.adapter == "openai_compatible" else ()
            base_url, _ = normalize_provider_url(base_url, endpoint_suffixes=suffixes)
        providers[name] = {
            "adapter": provider.adapter,
            "base_url": base_url,
            "api_key": provider.api_key.strip() or None,
            "model": provider.model.strip(),
            "json_mode": provider.json_mode,
            "tls_ca_file": provider.tls_ca_file.strip() or None,
            "context_window": provider.context_window,
            "max_output_tokens": provider.max_output_tokens,
            "extra_body": provider.extra_body,
        }
    image_providers: dict[str, dict[str, object]] = {}
    for provider in form.image_providers:
        name = provider.name.strip()
        if not name:
            continue
        base_url = provider.base_url.strip()
        endpoint_path = provider.endpoint_path.strip() or _default_image_endpoint_path(provider.adapter)
        if base_url:
            base_url, detected_endpoint = normalize_provider_url(
                base_url,
                endpoint_suffixes=("/images/generations", "/chat/completions"),
            )
            endpoint_path = detected_endpoint or endpoint_path
        if endpoint_path not in {"/images/generations", "/chat/completions"}:
            raise UserInputError("Image endpoint path must be /images/generations or /chat/completions")
        image_providers[name] = {
            "adapter": provider.adapter,
            "base_url": base_url or None,
            "endpoint_path": endpoint_path,
            "api_key": provider.api_key.strip() or None,
            "model": provider.model.strip() or None,
            "tls_ca_file": provider.tls_ca_file.strip() or None,
            "resolution": provider.resolution.strip() or "2720*1536",
            "num_inference_steps": provider.num_inference_steps,
            "guidance": provider.guidance,
            "extra_body": provider.extra_body,
        }
    data = migrate_config_data(base_data)
    default_provider = form.default_provider.strip()
    if default_provider not in providers:
        default_provider = next(iter(providers), "")
    image_default_provider = form.image_default_provider.strip()
    if image_default_provider not in image_providers:
        image_default_provider = next(iter(image_providers), "")
    data["config_version"] = SUPPORTED_CONFIG_VERSION
    vault_profiles, active_vault_id = _vault_profiles_from_form(form, base_dir)
    active_vault = vault_profiles[active_vault_id]
    data["project"] = {**dict(data.get("project") or {}), "name": active_vault["name"]}
    data["project"].setdefault("host_project_root", ".")
    data["vaults"] = {"default": active_vault_id, "profiles": vault_profiles}
    data["vault"] = {**dict(data.get("vault") or {}), "path": active_vault["path"]}
    data["server"] = {**dict(data.get("server") or {}), "host": form.server_host.strip(), "port": form.server_port}
    data["models"] = {
        **dict(data.get("models") or {}),
        "default_provider": default_provider or None,
        "default_max_tokens": form.default_max_tokens,
        "request_timeout_seconds": form.request_timeout_seconds,
        "providers": providers,
    }
    data["image_generation"] = {
        **dict(data.get("image_generation") or {}),
        "default_provider": image_default_provider or None,
        "request_timeout_seconds": form.image_request_timeout_seconds,
        "providers": image_providers,
    }
    connectors = dict(data.get("connectors") or {})
    _upsert_chat_connector(
        connectors,
        "codex",
        form.codex_enabled,
        form.codex_sessions_dir,
        form.codex_raw_output_dir,
        base_dir=base_dir,
        pattern="rollout-*.jsonl",
        recursive=True,
        default_sessions_dir=DEFAULT_CHAT_SESSION_DIRS["codex"],
    )
    _upsert_chat_connector(
        connectors,
        "hermes",
        form.hermes_enabled,
        form.hermes_sessions_dir,
        form.hermes_raw_output_dir,
        base_dir=base_dir,
        default_sessions_dir=DEFAULT_CHAT_SESSION_DIRS["hermes"],
    )
    _upsert_chat_connector(
        connectors,
        "openclaw",
        form.openclaw_enabled,
        form.openclaw_sessions_dir,
        form.openclaw_raw_output_dir,
        base_dir=base_dir,
        pattern="*.jsonl",
        recursive=False,
        default_sessions_dir=DEFAULT_CHAT_SESSION_DIRS["openclaw"],
    )
    _upsert_chat_connector(
        connectors,
        "claude_code",
        form.claude_code_enabled,
        form.claude_code_sessions_dir,
        form.claude_code_raw_output_dir,
        base_dir=base_dir,
        pattern="*.jsonl",
        recursive=True,
        default_sessions_dir=DEFAULT_CHAT_SESSION_DIRS["claude_code"],
    )
    _upsert_generic_chat_connector(connectors, form.generic_chat_enabled, form.generic_chat_roots, form.generic_chat_raw_output_dir, base_dir=base_dir)
    markdown = dict(connectors.get("markdown") or {})
    markdown["enabled"] = False
    markdown_settings = dict(markdown.get("settings") or {})
    markdown_settings["roots"] = []
    markdown_settings["raw_output_dir"] = _portable_config_path(form.markdown_raw_output_dir or DEFAULT_MARKDOWN_RAW_OUTPUT_DIR, base_dir)
    markdown["settings"] = markdown_settings
    connectors["markdown"] = markdown
    data["connectors"] = connectors

    document_processing = dict(data.get("document_processing") or {})
    mineru = dict(document_processing.get("mineru") or {})
    mineru_endpoint = form.mineru_endpoint.strip()
    mineru["enabled"] = form.mineru_enabled or bool(mineru_endpoint)
    mineru["endpoint"] = mineru_endpoint or None
    mineru["input_dir"] = None
    mineru["output_dir"] = _portable_config_path(form.mineru_output_dir or DEFAULT_MINERU_MARKDOWN_OUTPUT_DIR, base_dir)
    mineru["mode"] = form.mineru_parse_method if form.mineru_parse_method in {"auto", "txt", "ocr"} else "auto"
    mineru["timeout_seconds"] = form.mineru_timeout_seconds
    mineru["patterns"] = form.mineru_patterns or ["*.pdf", "*.docx", "*.pptx", "*.ppt", "*.xlsx", "*.xls", "*.png", "*.jpg", "*.jpeg", "*.webp", "*.bmp"]
    mineru["recursive"] = form.mineru_recursive
    mineru["extra_fields"] = _mineru_extra_fields_from_form(form)
    document_processing["mineru"] = mineru
    data["document_processing"] = document_processing
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


def _vault_profiles_from_form(form: UiConfigFormUpdateRequest, base_dir: Path) -> tuple[dict[str, dict[str, str]], str]:
    profiles: dict[str, dict[str, str]] = {}
    requested_active = (form.vault_id or "").strip()
    for item in form.vaults:
        vault_id = _normalize_vault_id(item.id)
        name = item.name.strip()
        path = item.path.strip()
        if not vault_id or not name or not path:
            continue
        profiles[vault_id] = {"name": name, "path": _portable_config_path(path, base_dir)}
        if item.active:
            requested_active = vault_id
    if not profiles:
        fallback_id = _normalize_vault_id(form.vault_id) or "default"
        profiles[fallback_id] = {
            "name": form.project_name.strip(),
            "path": _portable_config_path(form.vault_path, base_dir),
        }
        requested_active = fallback_id
    if requested_active not in profiles:
        requested_active = next(iter(profiles))
    return profiles, requested_active


def _default_image_endpoint_path(adapter: str) -> str:
    return "/chat/completions" if adapter == "openai_chat_image" else "/images/generations"


def _normalize_vault_id(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-").lower()
    return normalized


def _mineru_extra_fields_json(extra_fields: dict[str, object]) -> str:
    custom = {key: value for key, value in extra_fields.items() if key not in MINERU_ADVANCED_FIELD_KEYS}
    return json.dumps(custom, ensure_ascii=False, indent=2)


def _mineru_extra_fields_from_form(form: UiConfigFormUpdateRequest) -> dict[str, object]:
    try:
        custom = json.loads(form.mineru_extra_fields_json or "{}")
    except json.JSONDecodeError as exc:
        raise UserInputError(f"MinerU extra fields must be valid JSON: {exc.msg}") from exc
    if not isinstance(custom, dict):
        raise UserInputError("MinerU extra fields must be a JSON object.")
    fields = {
        **custom,
        "backend": _normalize_mineru_backend(form.mineru_backend),
        "return_md": True,
        "return_middle_json": form.mineru_return_middle_json,
        "return_model_output": form.mineru_return_model_output,
        "return_content_list": form.mineru_return_content_list,
        "return_images": form.mineru_return_images,
        "response_format_zip": form.mineru_response_format_zip,
        "lang_list": [part.strip() for part in form.mineru_lang_list.split(",") if part.strip()] or ["ch"],
        "formula_enable": form.mineru_formula_enable,
        "table_enable": form.mineru_table_enable,
        "server_url": form.mineru_server_url.strip() or None,
        "start_page_id": form.mineru_start_page_id,
        "end_page_id": form.mineru_end_page_id,
    }
    return {key: value for key, value in fields.items() if value is not None}


def _normalize_mineru_backend(value: object) -> str:
    try:
        return normalize_mineru_backend(value)
    except ValueError as exc:
        raise UserInputError(str(exc)) from exc


def _mineru_lang_list_value(value: object) -> str:
    if isinstance(value, list):
        return ",".join(str(item) for item in value)
    return str(value)


def _upsert_chat_connector(
    connectors: dict[str, object],
    name: str,
    enabled: bool,
    sessions_dir: str,
    raw_output_dir: str,
    *,
    base_dir: Path,
    pattern: str | None = None,
    recursive: bool | None = None,
    default_sessions_dir: str | None = None,
) -> None:
    connector = dict(connectors.get(name) or {})
    connector["enabled"] = enabled
    settings = dict(connector.get("settings") or {})
    if pattern is not None:
        settings.setdefault("pattern", pattern)
    if recursive is not None:
        settings.setdefault("recursive", recursive)
    next_sessions_dir = sessions_dir.strip()
    if next_sessions_dir:
        settings["sessions_dir"] = _portable_config_path(next_sessions_dir, base_dir)
    elif "sessions_dir" in settings:
        settings["sessions_dir"] = ""
    settings["raw_output_dir"] = _portable_config_path(raw_output_dir or DEFAULT_CHAT_RAW_OUTPUT_DIR, base_dir)
    connector["settings"] = settings
    connectors[name] = connector


def _upsert_generic_chat_connector(
    connectors: dict[str, object],
    enabled: bool,
    roots: list[str],
    raw_output_dir: str,
    *,
    base_dir: Path,
) -> None:
    connector = dict(connectors.get("generic_chat") or {})
    connector["enabled"] = enabled
    settings = dict(connector.get("settings") or {})
    settings["roots"] = [_portable_config_path(root, base_dir) for root in roots if root.strip()]
    settings.setdefault("patterns", ["*.jsonl", "*.sqlite", "*.db"])
    settings.setdefault("recursive", True)
    settings["raw_output_dir"] = _portable_config_path(raw_output_dir or DEFAULT_CHAT_RAW_OUTPUT_DIR, base_dir)
    connector["settings"] = settings
    connectors["generic_chat"] = connector


def _portable_config_path_or_none(value: str, base_dir: Path) -> str | None:
    if not value.strip():
        return None
    return _portable_config_path(value, base_dir)


def _portable_config_path(value: str, base_dir: Path) -> str:
    text = value.strip()
    if not text:
        return ""
    path = Path(text).expanduser()
    if not path.is_absolute():
        return text
    try:
        relative = path.resolve().relative_to(base_dir.resolve())
    except ValueError:
        return text
    if relative == Path("."):
        return "."
    return f"./{relative.as_posix()}"


def _path_diagnostic(
    name: str,
    category: str,
    path: Path | None,
    *,
    enabled: bool,
    pattern: str | None = None,
    detail: str = "",
    missing_code: str = "path_missing",
    metric_path: str | None = None,
    metric_pattern: str | None = None,
    cached_counts: dict[str, int] | None = None,
    refreshed_counts: dict[str, int] | None = None,
    refresh_count: bool = False,
) -> UiConfigDiagnosticItem:
    if not enabled:
        return UiConfigDiagnosticItem(name=name, category=category, enabled=False, ok=True, code="disabled", path=str(path) if path else None, detail=detail)
    if path is None:
        return UiConfigDiagnosticItem(name=name, category=category, enabled=True, ok=False, code=missing_code, detail=detail)
    exists = path.exists()
    count = _diagnostic_count(
        category=category,
        name=name,
        path=metric_path or str(path),
        pattern=metric_pattern or pattern,
        exists=exists,
        scan_paths=[path],
        cached_counts=cached_counts,
        refreshed_counts=refreshed_counts,
        refresh_count=refresh_count,
    )
    return UiConfigDiagnosticItem(name=name, category=category, enabled=True, ok=exists, code="path_ready" if exists else missing_code, path=str(path), count=count, detail=detail)


def _multi_path_diagnostic(
    name: str,
    category: str,
    paths: list[Path],
    *,
    enabled: bool,
    pattern: str | None = None,
    metric_path: str | None = None,
    metric_pattern: str | None = None,
    cached_counts: dict[str, int] | None = None,
    refreshed_counts: dict[str, int] | None = None,
    refresh_count: bool = False,
) -> UiConfigDiagnosticItem:
    if not enabled:
        return UiConfigDiagnosticItem(name=name, category=category, enabled=False, ok=True, code="disabled")
    if not paths:
        return UiConfigDiagnosticItem(name=name, category=category, enabled=True, ok=False, code="no_paths")
    existing = [path for path in paths if path.exists()]
    path_text = ", ".join(str(path) for path in paths)
    count = _diagnostic_count(
        category=category,
        name=name,
        path=metric_path or path_text,
        pattern=metric_pattern or pattern,
        exists=bool(existing),
        scan_paths=existing,
        cached_counts=cached_counts,
        refreshed_counts=refreshed_counts,
        refresh_count=refresh_count,
    )
    return UiConfigDiagnosticItem(name=name, category=category, enabled=True, ok=bool(existing), code="path_ready" if existing else "path_missing", path=path_text, count=count)


def _diagnostic_count(
    *,
    category: str,
    name: str,
    path: str,
    pattern: str | None,
    exists: bool,
    scan_paths: list[Path],
    cached_counts: dict[str, int] | None,
    refreshed_counts: dict[str, int] | None,
    refresh_count: bool,
) -> int | None:
    if not exists or not pattern:
        return None
    key = source_metric_key(category=category, name=name, path=path, pattern=pattern)
    if refresh_count:
        count = sum(_count_matching_files(item, pattern) for item in scan_paths)
        if refreshed_counts is not None:
            refreshed_counts[key] = count
        return count
    return (cached_counts or {}).get(key)


def _count_matching_files(path: Path, pattern: str | None) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return 1 if pattern is None or path.match(pattern) else 0
    count = 0
    iterator = path.rglob("*") if pattern == "*" else path.rglob(pattern or "*")
    for item in iterator:
        if item.is_file():
            count += 1
    if pattern == "*":
        return count
    return count
