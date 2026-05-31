from __future__ import annotations

from knoarbor.connectors.base import ConnectorCapabilities, ConnectorConfig, ConnectorHealth, SourceConnector, connector_capabilities, connector_health
from knoarbor.connectors.claude_code import ClaudeCodeConnector
from knoarbor.connectors.codex import CodexConnector
from knoarbor.connectors.generic_chat import GenericChatConnector
from knoarbor.connectors.hermes import HermesConnector
from knoarbor.connectors.markdown import MarkdownConnector
from knoarbor.connectors.openclaw import OpenClawConnector
from knoarbor.core.errors import ConnectorConfigError


class ConnectorRegistry:
    def __init__(self, connectors: list[SourceConnector] | None = None) -> None:
        initial = connectors or [ClaudeCodeConnector(), CodexConnector(), GenericChatConnector(), HermesConnector(), OpenClawConnector(), MarkdownConnector()]
        self._connectors = {connector.name: connector for connector in initial}

    def get(self, name: str) -> SourceConnector:
        try:
            return self._connectors[name]
        except KeyError as exc:
            available = ", ".join(sorted(self._connectors))
            raise ConnectorConfigError(f"Unknown connector: {name}. Available connectors: {available}") from exc

    def names(self) -> list[str]:
        return sorted(self._connectors)

    def capabilities(self) -> list[ConnectorCapabilities]:
        return [connector_capabilities(self._connectors[name]) for name in self.names()]

    def health(self, configs: dict[str, ConnectorConfig]) -> list[ConnectorHealth]:
        items: list[ConnectorHealth] = []
        for name in self.names():
            config = configs.get(name, ConnectorConfig(enabled=False))
            items.append(connector_health(self._connectors[name], config))
        return items
