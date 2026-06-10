from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ModelProbeBase(BaseModel):
    model_config = ConfigDict(protected_namespaces=())


ProbeLevel = Literal["minimal", "structured"]
ModelProbeStatus = Literal["ok", "warning", "error"]


class ModelProviderSummary(ModelProbeBase):
    name: str
    base_url: str | None = None
    model: str | None = None
    json_mode: bool = True
    api_key_env: str | None = None
    api_key_configured: bool = False
    local_or_private: bool = False
    context_window: int | None = None
    max_output_tokens: int | None = None
    default: bool = False


class ModelProvidersResponse(ModelProbeBase):
    schema_version: Literal["model_providers.v1"] = "model_providers.v1"
    default_provider: str | None = None
    providers: list[ModelProviderSummary] = Field(default_factory=list)


class ModelDiscoveryRequest(ModelProbeBase):
    config_path: str | None = None
    provider: str | None = None


class ModelCapabilitySuggestion(ModelProbeBase):
    context_window: int | None = None
    max_output_tokens: int | None = None
    json_mode: bool | None = None


class ModelDiscoveryResponse(ModelProbeBase):
    schema_version: Literal["model_discovery.v1"] = "model_discovery.v1"
    provider: str
    model: str
    status: ModelProbeStatus
    available: bool
    message: str
    model_ids: list[str] = Field(default_factory=list)
    model_count: int = 0
    configured_model_found: bool | None = None
    detected_context_window: int | None = None
    configured_context_window: int | None = None
    effective_context_window: int | None = None
    context_window_source: str = "unknown"
    configured_max_output_tokens: int | None = None
    suggested_config: ModelCapabilitySuggestion = Field(default_factory=ModelCapabilitySuggestion)
    details: dict[str, object] = Field(default_factory=dict)


class ModelProbeRequest(ModelProbeBase):
    config_path: str | None = None
    provider: str | None = None
    level: ProbeLevel = "minimal"


class ModelProbeResponse(ModelProbeBase):
    schema_version: Literal["model_probe.v1"] = "model_probe.v1"
    provider: str
    model: str
    level: ProbeLevel
    status: ModelProbeStatus
    available: bool
    message: str
    latency_ms: int | None = None
    output_valid: bool | None = None
    structured_output: bool | None = None
    detected_context_window: int | None = None
    configured_context_window: int | None = None
    effective_context_window: int | None = None
    configured_max_output_tokens: int | None = None
    suggested_config: ModelCapabilitySuggestion = Field(default_factory=ModelCapabilitySuggestion)
    usage: dict[str, int] = Field(default_factory=dict)
    details: dict[str, object] = Field(default_factory=dict)


class ModelApplyCapabilitiesRequest(ModelProbeBase):
    config_path: str | None = None
    provider: str
    context_window: int | None = Field(default=None, ge=1)
    max_output_tokens: int | None = Field(default=None, ge=1)
    json_mode: bool | None = None


class ModelApplyCapabilitiesResponse(ModelProbeBase):
    schema_version: Literal["model_apply_capabilities.v1"] = "model_apply_capabilities.v1"
    provider: str
    config_path: str
    saved: bool
    applied: dict[str, object] = Field(default_factory=dict)
