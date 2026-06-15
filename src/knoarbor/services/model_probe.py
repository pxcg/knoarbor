from __future__ import annotations

import json
import time

import yaml

from knoarbor.core.config import ModelProviderConfig, default_config_path, load_config
from knoarbor.core.errors import ExternalServiceError, ModelOutputError, UserInputError
from knoarbor.core.schemas.model_probe import (
    ModelApplyCapabilitiesRequest,
    ModelApplyCapabilitiesResponse,
    ModelCapabilitySuggestion,
    ModelDiscoveryRequest,
    ModelDiscoveryResponse,
    ModelProbeRequest,
    ModelProbeResponse,
    ModelProvidersResponse,
    ModelProviderSummary,
)
from knoarbor.semantic.llm import (
    ChatCompletionRequest,
    ChatMessage,
    ModelGateway,
    is_local_or_private_model_endpoint,
)
from knoarbor.services.ui_config import resolve_ui_config_path


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
                api_key_env=provider.api_key_env,
                api_key_configured=_provider_credentials_ready(provider),
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
        configured_model_found = _bool_or_none(details.get("configured_model_found"))
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

    def probe(self, request: ModelProbeRequest) -> ModelProbeResponse:
        config = load_config(request.config_path or default_config_path())
        provider_name, provider = _resolve_provider(config.models.providers, request.provider or config.models.default_provider)
        probe_provider = provider.model_copy(update={"json_mode": request.level == "structured"})
        gateway = ModelGateway.from_config(provider_name, probe_provider, timeout_seconds=min(config.models.request_timeout_seconds, 30.0))
        discovery = gateway.discover_models()
        details = dict(discovery.details)
        detected_context = _int_or_none(details.get("detected_context_window"))
        effective_context = detected_context or provider.context_window
        if not discovery.available:
            return ModelProbeResponse(
                provider=provider_name,
                model=provider.model or "",
                level=request.level,
                status="error",
                available=False,
                message=discovery.message,
                detected_context_window=detected_context,
                configured_context_window=provider.context_window,
                effective_context_window=effective_context,
                configured_max_output_tokens=provider.max_output_tokens,
                suggested_config=_suggest_config(effective_context, structured_json=None),
                details=_public_details(details),
            )

        started = time.perf_counter()
        try:
            response = gateway.complete(_probe_completion_request(request.level))
        except (ExternalServiceError, ModelOutputError, UserInputError) as exc:
            return ModelProbeResponse(
                provider=provider_name,
                model=provider.model or "",
                level=request.level,
                status="error",
                available=False,
                message=_classify_probe_error(str(exc)),
                latency_ms=round((time.perf_counter() - started) * 1000),
                detected_context_window=detected_context,
                configured_context_window=provider.context_window,
                effective_context_window=effective_context,
                configured_max_output_tokens=provider.max_output_tokens,
                suggested_config=_suggest_config(effective_context, structured_json=False if request.level == "structured" else None),
                details={"error": str(exc), **_public_details(details)},
            )

        output_valid = _validate_probe_output(request.level, response.content)
        structured = output_valid if request.level == "structured" else None
        status = "ok" if output_valid else "warning"
        return ModelProbeResponse(
            provider=provider_name,
            model=response.model,
            level=request.level,
            status=status,
            available=True,
            message="Model probe succeeded." if output_valid else "Model responded, but the probe output did not match the expected contract.",
            latency_ms=round(response.elapsed_seconds * 1000),
            output_valid=output_valid,
            structured_output=structured,
            detected_context_window=detected_context,
            configured_context_window=provider.context_window,
            effective_context_window=effective_context,
            configured_max_output_tokens=provider.max_output_tokens,
            suggested_config=_suggest_config(effective_context, structured_json=structured),
            usage=response.usage,
            details={"response_preview": response.content[:300], **_public_details(details)},
        )

    def apply_capabilities(self, request: ModelApplyCapabilitiesRequest) -> ModelApplyCapabilitiesResponse:
        path = resolve_ui_config_path(request.config_path, for_write=True)
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
        path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
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


def _provider_credentials_ready(provider: ModelProviderConfig) -> bool:
    if not provider.api_key_env:
        return is_local_or_private_model_endpoint(provider.base_url)
    return bool(provider.api_key())


def _probe_completion_request(level: str) -> ChatCompletionRequest:
    if level == "structured":
        return ChatCompletionRequest(
            messages=[
                ChatMessage(role="system", content="Return only one JSON object. No markdown fences."),
                ChatMessage(role="user", content='Return exactly {"ok": true, "value": 1}.'),
            ],
            temperature=0,
            max_tokens=128,
        )
    return ChatCompletionRequest(
        messages=[
            ChatMessage(role="system", content="You are a connectivity probe. Follow the user instruction exactly."),
            ChatMessage(role="user", content="Reply with exactly: OK"),
        ],
        temperature=0,
        max_tokens=64,
    )


def _validate_probe_output(level: str, content: str) -> bool:
    if level == "structured":
        try:
            payload = json.loads(content.strip())
        except json.JSONDecodeError:
            return False
        return isinstance(payload, dict) and payload.get("ok") is True and payload.get("value") == 1
    return content.strip() == "OK"


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


def _classify_probe_error(message: str) -> str:
    lower = message.lower()
    if "401" in lower or "403" in lower or "auth" in lower or "api key" in lower:
        return "Model provider authentication failed."
    if "404" in lower or "405" in lower:
        return "Model provider endpoint does not support the requested OpenAI-compatible API."
    if "timed out" in lower or "timeout" in lower:
        return "Model provider request timed out."
    if "connection" in lower or "refused" in lower or "unreachable" in lower:
        return "Model provider endpoint is unreachable."
    return "Model provider probe failed."


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    return None


def _bool_or_none(value: object) -> bool | None:
    return value if isinstance(value, bool) else None
