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
    settings_schema: dict[str, object] = Field(default_factory=dict)
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
            return _with_default_settings_schema(value)
        if isinstance(value, dict):
            return _with_default_settings_schema(ConnectorCapabilities.model_validate(value))
    return _with_default_settings_schema(ConnectorCapabilities(
        name=connector.name,
        version=connector.version,
        source_types=_default_source_types(connector.name),
        supports_segmentation_hint=connector.name in {"codex", "hermes", "openclaw", "claude_code"},
    ))


def _with_default_settings_schema(capability: ConnectorCapabilities) -> ConnectorCapabilities:
    if capability.settings_schema:
        return capability
    return capability.model_copy(update={"settings_schema": _default_settings_schema(capability.name)})


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


def _default_settings_schema(name: str) -> dict[str, object]:
    chat_schema = _chat_settings_schema()
    return {
        "markdown": {
            "type": "object",
            "required": ["roots"],
            "properties": {
                "roots": {"type": "array", "items": {"type": "string"}, "description": "Markdown file or folder roots."},
                "pattern": {"type": "string", "default": "*.md"},
                "recursive": {"type": "boolean", "default": True},
                "raw_output_dir": {"type": "string", "description": "Optional raw output directory used by config tooling."},
            },
        },
        "codex": _chat_settings_schema(default_pattern="rollout-*.jsonl", default_recursive=True),
        "hermes": _chat_settings_schema(default_pattern="session_*.json", default_recursive=False),
        "openclaw": _chat_settings_schema(default_pattern="*.jsonl", default_recursive=False),
        "claude_code": _chat_settings_schema(default_pattern="*.jsonl", default_recursive=True),
        "generic_chat": {
            **chat_schema,
            "properties": {
                **chat_schema["properties"],  # type: ignore[index]
                "roots": {"type": "array", "items": {"type": "string"}, "description": "Generic chat file or folder roots."},
                "patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": ["*.jsonl", "*.sqlite", "*.db"],
                },
            },
        },
    }.get(name, {})


def _chat_settings_schema(*, default_pattern: str = "*.jsonl", default_recursive: bool = True) -> dict[str, object]:
    return {
        "type": "object",
        "properties": {
            "sessions_dir": {"type": "string", "description": "Folder containing chat session files."},
            "root": {"type": "string", "description": "Alias for sessions_dir."},
            "session_files": {"type": "array", "items": {"type": "string"}, "description": "Explicit chat session files."},
            "pattern": {"type": "string", "default": default_pattern},
            "recursive": {"type": "boolean", "default": default_recursive},
            "raw_output_dir": {"type": "string", "description": "Optional raw output directory used by config tooling."},
        },
    }
