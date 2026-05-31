from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from knoarbor.connectors.base import ConnectorConfig as RuntimeConnectorConfig
from knoarbor.connectors.base import ConnectorCapabilities, ConnectorHealth
from knoarbor.connectors.registry import ConnectorRegistry
from knoarbor.core.config import KnoArborConfig, default_config_path, prepare_config_data
from knoarbor.core.errors import UserInputError
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
    UiModelProviderForm,
)

class UiConfigService:
    """Owns UI-facing config read, validation, diagnostics, and writes."""

    def read_raw(self, config_path: str | None = None) -> UiConfigResponse:
        path = resolve_ui_config_path(config_path, for_write=False)
        exists = path.exists()
        content = path.read_text(encoding="utf-8") if exists else default_config_path().read_text(encoding="utf-8")
        return UiConfigResponse(
            config_path=str(path),
            exists=exists,
            content=content,
            summary=summarize_config_content(content, base_dir=path.parent),
        )

    def write_raw(self, request: UiConfigUpdateRequest) -> UiConfigUpdateResponse:
        _reject_inline_secrets(request.content)
        path = resolve_ui_config_path(request.config_path, for_write=True)
        summary = summarize_config_content(request.content, base_dir=path.parent)
        path.write_text(request.content, encoding="utf-8")
        return UiConfigUpdateResponse(config_path=str(path), saved=True, summary=summary)

    def read_form(self, config_path: str | None = None) -> UiConfigFormResponse:
        path = resolve_ui_config_path(config_path, for_write=False)
        content = path.read_text(encoding="utf-8") if path.exists() else default_config_path().read_text(encoding="utf-8")
        return config_to_form(config_from_content(content, base_dir=path.parent))

    def read_diagnostics(self, config_path: str | None = None) -> UiConfigDiagnostics:
        path = resolve_ui_config_path(config_path, for_write=False)
        content = path.read_text(encoding="utf-8") if path.exists() else default_config_path().read_text(encoding="utf-8")
        return config_diagnostics(config_from_content(content, base_dir=path.parent))

    def write_form(self, request: UiConfigFormUpdateRequest) -> UiConfigUpdateResponse:
        path = resolve_ui_config_path(request.config_path, for_write=True)
        source_path = path if path.exists() else default_config_path()
        base_data = yaml.safe_load(source_path.read_text(encoding="utf-8")) or {}
        if not isinstance(base_data, dict):
            raise UserInputError("Config root must be a YAML object")
        content = render_config_from_form(request, base_data, base_dir=path.parent)
        summary = summarize_config_content(content, base_dir=path.parent)
        path.write_text(content, encoding="utf-8")
        return UiConfigUpdateResponse(config_path=str(path), saved=True, summary=summary)


def resolve_ui_config_path(config_path: str | None, *, for_write: bool) -> Path:
    if config_path:
        path = Path(config_path).expanduser().resolve()
    else:
        detected = default_config_path()
        path = detected.with_name("config.yaml") if detected.name == "config.example.yaml" else detected
    if path.name not in {"config.yaml", "config.yml"}:
        raise UserInputError("UI can only edit config.yaml or config.yml")
    return path


def summarize_default_config() -> dict[str, object]:
    path = resolve_ui_config_path(None, for_write=False)
    if path.exists():
        return summarize_config_content(path.read_text(encoding="utf-8"), base_dir=path.parent)
    example_path = default_config_path()
    return summarize_config_content(example_path.read_text(encoding="utf-8"), base_dir=example_path.parent)


def summarize_config_content(content: str, *, base_dir: Path) -> dict[str, object]:
    config = config_from_content(content, base_dir=base_dir)
    return {
        "project_name": config.project.name,
        "vault_path": str(config.vault.path),
        "server": f"{config.server.host}:{config.server.port}",
        "default_provider": config.models.default_provider,
        "provider_count": len(config.models.providers),
        "enabled_connectors": config.enabled_connectors(),
        "enabled_document_processors": enabled_document_processors(config),
        "default_max_tokens": config.models.default_max_tokens,
        "request_timeout_seconds": config.models.request_timeout_seconds,
    }


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
    markdown = config.connectors.get("markdown")
    codex_settings = codex.settings if codex else {}
    hermes_settings = hermes.settings if hermes else {}
    openclaw_settings = openclaw.settings if openclaw else {}
    claude_code_settings = claude_code.settings if claude_code else {}
    generic_chat_settings = generic_chat.settings if generic_chat else {}
    markdown_settings = markdown.settings if markdown else {}
    return UiConfigFormResponse(
        project_name=config.project.name,
        vault_path=str(config.vault.path),
        server_host=config.server.host,
        server_port=config.server.port,
        default_provider=config.models.default_provider or "",
        default_max_tokens=config.models.default_max_tokens,
        request_timeout_seconds=config.models.request_timeout_seconds,
        providers=[
            UiModelProviderForm(
                name=name,
                base_url=provider.base_url or "",
                api_key_env=provider.api_key_env or "",
                model=provider.model or "",
                json_mode=provider.json_mode,
                api_key_configured=bool(provider.api_key()),
            )
            for name, provider in sorted(config.models.providers.items())
        ],
        enabled_connectors=config.enabled_connectors(),
        codex_enabled=bool(codex.enabled) if codex else False,
        codex_sessions_dir=str(codex_settings.get("sessions_dir") or ""),
        codex_raw_output_dir=str(codex_settings.get("raw_output_dir") or ""),
        hermes_enabled=bool(hermes.enabled) if hermes else False,
        hermes_sessions_dir=str(hermes_settings.get("sessions_dir") or ""),
        hermes_raw_output_dir=str(hermes_settings.get("raw_output_dir") or ""),
        openclaw_enabled=bool(openclaw.enabled) if openclaw else False,
        openclaw_sessions_dir=str(openclaw_settings.get("sessions_dir") or ""),
        openclaw_raw_output_dir=str(openclaw_settings.get("raw_output_dir") or ""),
        claude_code_enabled=bool(claude_code.enabled) if claude_code else False,
        claude_code_sessions_dir=str(claude_code_settings.get("sessions_dir") or ""),
        claude_code_raw_output_dir=str(claude_code_settings.get("raw_output_dir") or ""),
        generic_chat_enabled=bool(generic_chat.enabled) if generic_chat else False,
        generic_chat_roots=[str(item) for item in generic_chat_settings.get("roots", []) if item],
        generic_chat_raw_output_dir=str(generic_chat_settings.get("raw_output_dir") or ""),
        markdown_enabled=bool(markdown.enabled) if markdown else True,
        markdown_roots=[str(item) for item in markdown_settings.get("roots", []) if item],
        markdown_raw_output_dir=str(markdown_settings.get("raw_output_dir") or ""),
        mineru_enabled=config.document_processing.mineru.enabled,
        mineru_endpoint=config.document_processing.mineru.endpoint or "",
        mineru_input_dir=str(config.document_processing.mineru.input_dir or ""),
        mineru_output_dir=str(config.document_processing.mineru.output_dir or ""),
        mineru_parse_method=config.document_processing.mineru.mode or "",
        mineru_backend=str(config.document_processing.mineru.extra_fields.get("backend") or "pipeline"),
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


def config_diagnostics(config: KnoArborConfig) -> UiConfigDiagnostics:
    connector_items: list[UiConfigDiagnosticItem] = []
    processor_items: list[UiConfigDiagnosticItem] = []
    provider_items: list[UiConfigDiagnosticItem] = []
    path_items: list[UiConfigDiagnosticItem] = []
    connector_capabilities, connector_health = _connector_contracts(config)

    vault = Path(config.vault.path).expanduser()
    path_items.append(_path_diagnostic("vault", "path", vault, enabled=True))

    codex = config.connectors.get("codex")
    codex_settings = codex.settings if codex else {}
    codex_path = Path(str(codex_settings.get("sessions_dir") or "")).expanduser() if codex_settings.get("sessions_dir") else None
    connector_items.append(
        _connector_diagnostic(
            _path_diagnostic(
                "codex",
                "connector",
                codex_path,
                enabled=bool(codex.enabled) if codex else False,
                pattern=str(codex_settings.get("pattern") or "rollout-*.jsonl"),
            ),
            connector_capabilities,
            connector_health,
        )
    )

    hermes = config.connectors.get("hermes")
    hermes_settings = hermes.settings if hermes else {}
    hermes_path = Path(str(hermes_settings.get("sessions_dir") or "")).expanduser() if hermes_settings.get("sessions_dir") else None
    connector_items.append(
        _connector_diagnostic(
            _path_diagnostic(
                "hermes",
                "connector",
                hermes_path,
                enabled=bool(hermes.enabled) if hermes else False,
                pattern=str(hermes_settings.get("pattern") or "session_*.json"),
            ),
            connector_capabilities,
            connector_health,
        )
    )

    openclaw = config.connectors.get("openclaw")
    openclaw_settings = openclaw.settings if openclaw else {}
    openclaw_path = Path(str(openclaw_settings.get("sessions_dir") or "")).expanduser() if openclaw_settings.get("sessions_dir") else None
    connector_items.append(
        _connector_diagnostic(
            _path_diagnostic(
                "openclaw",
                "connector",
                openclaw_path,
                enabled=bool(openclaw.enabled) if openclaw else False,
                pattern=str(openclaw_settings.get("pattern") or "*.jsonl"),
            ),
            connector_capabilities,
            connector_health,
        )
    )

    claude_code = config.connectors.get("claude_code")
    claude_code_settings = claude_code.settings if claude_code else {}
    claude_code_path = Path(str(claude_code_settings.get("sessions_dir") or "")).expanduser() if claude_code_settings.get("sessions_dir") else None
    connector_items.append(
        _connector_diagnostic(
            _path_diagnostic(
                "claude_code",
                "connector",
                claude_code_path,
                enabled=bool(claude_code.enabled) if claude_code else False,
                pattern=str(claude_code_settings.get("pattern") or "*.jsonl"),
            ),
            connector_capabilities,
            connector_health,
        )
    )

    generic_chat = config.connectors.get("generic_chat")
    generic_chat_settings = generic_chat.settings if generic_chat else {}
    generic_chat_roots = [Path(str(root)).expanduser() for root in generic_chat_settings.get("roots", []) if root]
    connector_items.append(
        _connector_diagnostic(
            _multi_path_diagnostic(
                "generic_chat",
                "connector",
                generic_chat_roots,
                enabled=bool(generic_chat.enabled) if generic_chat else False,
                pattern="*",
            ),
            connector_capabilities,
            connector_health,
        )
    )

    markdown = config.connectors.get("markdown")
    markdown_settings = markdown.settings if markdown else {}
    markdown_roots = [Path(str(root)).expanduser() for root in markdown_settings.get("roots", []) if root]
    connector_items.append(
        _connector_diagnostic(
            _multi_path_diagnostic(
                "markdown",
                "connector",
                markdown_roots,
                enabled=bool(markdown.enabled) if markdown else False,
                pattern=str(markdown_settings.get("pattern") or "*.md"),
            ),
            connector_capabilities,
            connector_health,
        )
    )

    mineru = config.document_processing.mineru
    if mineru.enabled and not mineru.endpoint:
        processor_items.append(UiConfigDiagnosticItem(name="mineru", category="processor", enabled=True, ok=False, code="endpoint_missing", path=str(mineru.input_dir) if mineru.input_dir else None))
    else:
        processor_items.append(_path_diagnostic("mineru", "processor", Path(mineru.input_dir).expanduser() if mineru.input_dir else None, enabled=mineru.enabled, pattern="*", detail=mineru.endpoint or ""))

    for name, provider in sorted(config.models.providers.items()):
        missing = []
        if not provider.base_url:
            missing.append("base_url")
        if not provider.model:
            missing.append("model")
        if not provider.api_key_env:
            missing.append("api_key_env")
        elif not provider.api_key():
            missing.append("api_key")
        ok = not missing
        provider_items.append(UiConfigDiagnosticItem(name=name, category="provider", enabled=True, ok=ok, code="ready" if ok else "provider_incomplete", detail=", ".join(missing)))

    return UiConfigDiagnostics(connectors=connector_items, processors=processor_items, providers=provider_items, paths=path_items)


def _connector_contracts(config: KnoArborConfig) -> tuple[dict[str, ConnectorCapabilities], dict[str, ConnectorHealth]]:
    registry = ConnectorRegistry()
    runtime_configs = {
        name: RuntimeConnectorConfig(enabled=connector.enabled, settings=connector.settings)
        for name, connector in config.connectors.items()
    }
    capabilities = {item.name: item for item in registry.capabilities()}
    health = {item.name: item for item in registry.health(runtime_configs)}
    return capabilities, health


def _connector_diagnostic(
    item: UiConfigDiagnosticItem,
    capabilities_by_name: dict[str, ConnectorCapabilities],
    health_by_name: dict[str, ConnectorHealth],
) -> UiConfigDiagnosticItem:
    capability = capabilities_by_name.get(item.name)
    health = health_by_name.get(item.name)
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
    if item.enabled and health and not health.ok:
        data["ok"] = False
        data["code"] = health.code
        data["detail"] = health.detail or item.detail
    elif item.enabled and health and health.detail and not data.get("detail"):
        data["detail"] = health.detail
    return UiConfigDiagnosticItem.model_validate(data)


def render_config_from_form(form: UiConfigFormUpdateRequest, base_data: dict[str, Any], *, base_dir: Path) -> str:
    providers: dict[str, dict[str, object]] = {}
    for provider in form.providers:
        name = provider.name.strip()
        if not name:
            continue
        providers[name] = {
            "base_url": provider.base_url.strip(),
            "api_key_env": provider.api_key_env.strip(),
            "model": provider.model.strip(),
            "json_mode": provider.json_mode,
        }
    data = dict(base_data)
    data["config_version"] = 1
    data["project"] = {**dict(data.get("project") or {}), "name": form.project_name.strip()}
    data["project"].setdefault("host_project_root", ".")
    data["vault"] = {**dict(data.get("vault") or {}), "path": _portable_config_path(form.vault_path, base_dir)}
    data["server"] = {**dict(data.get("server") or {}), "host": form.server_host.strip(), "port": form.server_port}
    data["models"] = {
        **dict(data.get("models") or {}),
        "default_provider": form.default_provider.strip() or None,
        "default_max_tokens": form.default_max_tokens,
        "request_timeout_seconds": form.request_timeout_seconds,
        "providers": providers,
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
    markdown["enabled"] = form.markdown_enabled
    markdown_settings = dict(markdown.get("settings") or {})
    markdown_settings["roots"] = [_portable_config_path(root, base_dir) for root in form.markdown_roots if root.strip()]
    markdown_settings["raw_output_dir"] = _portable_config_path(form.markdown_raw_output_dir or DEFAULT_MARKDOWN_RAW_OUTPUT_DIR, base_dir)
    markdown["settings"] = markdown_settings
    connectors["markdown"] = markdown
    data["connectors"] = connectors

    document_processing = dict(data.get("document_processing") or {})
    mineru = dict(document_processing.get("mineru") or {})
    mineru["enabled"] = form.mineru_enabled
    mineru["endpoint"] = form.mineru_endpoint.strip() or None
    mineru["input_dir"] = _portable_config_path_or_none(form.mineru_input_dir, base_dir)
    mineru["output_dir"] = _portable_config_path(form.mineru_output_dir or DEFAULT_MINERU_MARKDOWN_OUTPUT_DIR, base_dir)
    mineru["mode"] = form.mineru_parse_method.strip() or None
    mineru["timeout_seconds"] = form.mineru_timeout_seconds
    mineru["patterns"] = [pattern.strip() for pattern in form.mineru_patterns if pattern.strip()]
    mineru["recursive"] = form.mineru_recursive
    mineru["extra_fields"] = _mineru_extra_fields_from_form(form)
    document_processing["mineru"] = mineru
    data["document_processing"] = document_processing
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


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
        "backend": form.mineru_backend.strip() or "pipeline",
        "return_md": form.mineru_return_md,
        "return_middle_json": form.mineru_return_middle_json,
        "return_model_output": form.mineru_return_model_output,
        "return_content_list": form.mineru_return_content_list,
        "return_images": form.mineru_return_images,
        "response_format_zip": form.mineru_response_format_zip,
        "lang_list": form.mineru_lang_list.strip() or "ch",
        "formula_enable": form.mineru_formula_enable,
        "table_enable": form.mineru_table_enable,
        "server_url": form.mineru_server_url.strip() or None,
        "start_page_id": form.mineru_start_page_id,
        "end_page_id": form.mineru_end_page_id,
    }
    return {key: value for key, value in fields.items() if value is not None}


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
    next_sessions_dir = sessions_dir.strip() or (default_sessions_dir if enabled else "")
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
) -> UiConfigDiagnosticItem:
    if not enabled:
        return UiConfigDiagnosticItem(name=name, category=category, enabled=False, ok=True, code="disabled", path=str(path) if path else None, detail=detail)
    if path is None:
        return UiConfigDiagnosticItem(name=name, category=category, enabled=True, ok=False, code=missing_code, detail=detail)
    exists = path.exists()
    count = _count_matching_files(path, pattern) if exists and pattern else None
    return UiConfigDiagnosticItem(name=name, category=category, enabled=True, ok=exists, code="path_ready" if exists else missing_code, path=str(path), count=count, detail=detail)


def _multi_path_diagnostic(name: str, category: str, paths: list[Path], *, enabled: bool, pattern: str | None = None) -> UiConfigDiagnosticItem:
    if not enabled:
        return UiConfigDiagnosticItem(name=name, category=category, enabled=False, ok=True, code="disabled")
    if not paths:
        return UiConfigDiagnosticItem(name=name, category=category, enabled=True, ok=False, code="no_paths")
    existing = [path for path in paths if path.exists()]
    count = sum(_count_matching_files(path, pattern) for path in existing) if pattern else None
    return UiConfigDiagnosticItem(name=name, category=category, enabled=True, ok=bool(existing), code="path_ready" if existing else "path_missing", path=", ".join(str(path) for path in paths), count=count)


def _count_matching_files(path: Path, pattern: str | None) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return 1 if pattern is None or path.match(pattern) else 0
    if pattern == "*":
        return sum(1 for item in path.rglob("*") if item.is_file())
    return sum(1 for item in path.rglob(pattern or "*") if item.is_file())


def _reject_inline_secrets(content: str) -> None:
    secret_patterns = [
        re.compile(r"\bsk-[A-Za-z0-9_\-]{12,}"),
        re.compile(r"(?im)^\s*(api_key|token|secret|password)\s*:\s*['\"]?[^'\"\n]+"),
    ]
    for pattern in secret_patterns:
        if pattern.search(content):
            raise UserInputError("config.yaml must not contain inline secrets. Use *_env fields and .env environment variables.")
