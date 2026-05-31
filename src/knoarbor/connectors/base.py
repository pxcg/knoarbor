from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, Field

from knoarbor.core.schemas.sources import RawSource, SourceDocument, SourceRef


class ConnectorConfig(BaseModel):
    enabled: bool = True
    settings: dict[str, object] = Field(default_factory=dict)


class ConnectorCapabilities(BaseModel):
    schema_version: Literal["connector_capabilities.v1"] = "connector_capabilities.v1"
    name: str
    version: str
    source_types: list[str] = Field(default_factory=list)
    supports_discovery: bool = True
    supports_checkpoint: bool = True
    supports_segmentation_hint: bool = False
    requires_external_service: bool = False


class ConnectorHealth(BaseModel):
    schema_version: Literal["connector_health.v1"] = "connector_health.v1"
    name: str
    ok: bool
    code: str = "ok"
    detail: str = ""


class SourceConnector(Protocol):
    """Stable boundary for source-specific discovery and normalization."""

    name: str
    version: str

    def discover(self, config: ConnectorConfig) -> list[SourceRef]:
        """Return stable references for source items without semantic analysis."""

    def fetch(self, ref: SourceRef, config: ConnectorConfig) -> RawSource:
        """Read or sync the referenced source and return immutable raw metadata."""

    def to_document(self, raw: RawSource, config: ConnectorConfig) -> SourceDocument:
        """Convert raw metadata and content into the shared source document contract."""


def connector_capabilities(connector: SourceConnector) -> ConnectorCapabilities:
    if hasattr(connector, "capabilities"):
        value = connector.capabilities()
        if isinstance(value, ConnectorCapabilities):
            return value
        if isinstance(value, dict):
            return ConnectorCapabilities.model_validate(value)
    return ConnectorCapabilities(
        name=connector.name,
        version=connector.version,
        source_types=_default_source_types(connector.name),
        supports_segmentation_hint=connector.name in {"codex", "hermes", "openclaw", "claude_code"},
    )


def connector_health(connector: SourceConnector, config: ConnectorConfig) -> ConnectorHealth:
    if not config.enabled:
        return ConnectorHealth(name=connector.name, ok=True, code="disabled", detail="Connector is disabled.")
    try:
        connector.discover(config)
    except Exception as exc:
        return ConnectorHealth(name=connector.name, ok=False, code=type(exc).__name__, detail=str(exc))
    return ConnectorHealth(name=connector.name, ok=True)


def _default_source_types(name: str) -> list[str]:
    return {
        "markdown": ["markdown"],
        "codex": ["codex_chat"],
        "hermes": ["hermes_chat"],
        "openclaw": ["openclaw_chat"],
        "claude_code": ["claude_code_chat"],
        "generic_chat": ["generic_chat"],
    }.get(name, [])
