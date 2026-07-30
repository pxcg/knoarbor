from __future__ import annotations

import yaml

from knoarbor.core.config import KnoArborConfig, ModelProviderConfig, default_config_path, load_config, prepare_config_data
from knoarbor.core.errors import UserInputError
from knoarbor.core.schemas.model_probe import (
    ModelApplyCapabilitiesRequest,
    ModelApplyCapabilitiesResponse,
    ModelCapabilitySuggestion,
    ModelDiscoveryRequest,
    ModelDiscoveryResponse,
    ModelProvidersResponse,
    ModelProviderSummary,
)
from knoarbor.semantic.llm import ModelGateway, is_local_or_private_model_endpoint
from knoarbor.services.ui_config import resolve_ui_config_path, write_private_text_atomic


class ModelProbeService:
    """Owns model discovery, capability probes, and explicit capability writes."""

    def providers(self, config_path: str | None = None) -> ModelProvidersResponse:
        config = load_config(config_path or default_config_path())
        providers = [
            ModelProviderSummary(
                name=name,
                adapter=provider.adapter,
                base_url=provider.base_url,
                model=provider.model,
                json_mode=provider.json_mode,
                tls_ca_file=str(provider.tls_ca_file) if provider.tls_ca_file else None,
                local_or_private=is_local_or_private_model_endpoint(provider.base_url),
                context_window=provider.context_window,
                max_output_tokens=provider.max_output_tokens,
                default=name == config.models.default_provider,
            )
            for name, provider in sorted(config.models.providers.items())
        ]
        return ModelProvidersResponse(default_provider=config.models.default_provider, providers=providers)

    def discover(self, request: ModelDiscoveryRequest) -> ModelDiscoveryResponse:
        config = load_config(request.config_path or default_config_path())
        provider_name, provider = _resolve_provider(config.models.providers, request.provider or config.models.default_provider)
        discovery_provider = _provider_for_discovery(provider)
        gateway = ModelGateway.from_config(provider_name, discovery_provider, timeout_seconds=min(config.models.request_timeout_seconds, 10.0))
        discovery = gateway.discover_models()
        details = dict(discovery.details)
        detected_context = _int_or_none(details.get("detected_context_window"))
        effective_context = detected_context or provider.context_window
        configured_model_found = _bool_or_none(details.get("configured_model_found")) if provider.model else None
        status = "error"
        if discovery.available:
            status = "warning" if provider.model and configured_model_found is False else "ok"
        return ModelDiscoveryResponse(
            provider=provider_name,
            model=provider.model or "",
            status=status,
            available=discovery.available,
            message=_discovery_message(discovery.message, provider.model, configured_model_found),
            model_ids=[str(item) for item in details.get("model_ids", []) if isinstance(item, str)],
            model_count=int(details.get("model_count") or 0),
            configured_model_found=configured_model_found,
            detected_context_window=detected_context,
            configured_context_window=provider.context_window,
            effective_context_window=effective_context,
            context_window_source=str(details.get("context_window_source") or ("runtime" if detected_context else "config" if provider.context_window else "unknown")),
            configured_max_output_tokens=provider.max_output_tokens,
            suggested_config=_suggest_config(effective_context, structured_json=None),
            details=_public_details(details),
        )

    def apply_capabilities(self, request: ModelApplyCapabilitiesRequest) -> ModelApplyCapabilitiesResponse:
        path = resolve_ui_config_path(request.config_path)
        source_path = path if path.exists() else default_config_path()
        data = yaml.safe_load(source_path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise UserInputError("Config root must be a YAML object")
        providers = data.setdefault("models", {}).setdefault("providers", {})
        if not isinstance(providers, dict) or request.provider not in providers or not isinstance(providers[request.provider], dict):
            raise UserInputError(f"Unknown model provider: {request.provider}")
        target = providers[request.provider]
        applied: dict[str, object] = {}
        if request.context_window is not None:
            target["context_window"] = request.context_window
            applied["context_window"] = request.context_window
        if request.max_output_tokens is not None:
            target["max_output_tokens"] = request.max_output_tokens
            applied["max_output_tokens"] = request.max_output_tokens
        if request.json_mode is not None:
            target["json_mode"] = request.json_mode
            applied["json_mode"] = request.json_mode
        content = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
        KnoArborConfig.model_validate(prepare_config_data(data, path.parent))
        write_private_text_atomic(path, content)
        return ModelApplyCapabilitiesResponse(provider=request.provider, config_path=str(path), saved=True, applied=applied)


def _resolve_provider(providers: dict[str, ModelProviderConfig], provider_name: str | None) -> tuple[str, ModelProviderConfig]:
    if not provider_name:
        raise UserInputError("No model provider selected. Set models.default_provider or pass provider.")
    provider = providers.get(provider_name)
    if provider is None:
        raise UserInputError(f"Unknown model provider: {provider_name}")
    return provider_name, provider


def _provider_for_discovery(provider: ModelProviderConfig) -> ModelProviderConfig:
    """Build a provider config suitable for list-model discovery.

    Discovery is the step that lets users choose a model, so it must only
    require provider name/base URL/credentials. A concrete model remains
    mandatory for probe and semantic generation.
    """

    if provider.model:
        return provider
    return provider.model_copy(update={"model": "__knoarbor_discovery__"})


def _discovery_message(base_message: str, configured_model: str | None, configured_model_found: bool | None) -> str:
    if configured_model and configured_model_found is False:
        return f"{base_message} Configured model was not found in the discovered model list."
    return base_message




def _suggest_config(context_window: int | None, *, structured_json: bool | None) -> ModelCapabilitySuggestion:
    max_output = None
    if context_window:
        max_output = min(8000, max(1024, context_window // 4))
    return ModelCapabilitySuggestion(
        context_window=context_window,
        max_output_tokens=max_output,
        json_mode=structured_json if structured_json is not None else None,
    )


def _public_details(details: dict[str, object]) -> dict[str, object]:
    blocked = {"body_preview", "ollama_show_body_preview"}
    return {key: value for key, value in details.items() if key not in blocked}


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    return None


def _bool_or_none(value: object) -> bool | None:
    return value if isinstance(value, bool) else None
