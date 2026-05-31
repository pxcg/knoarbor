from __future__ import annotations

from knoarbor.connectors.base import ConnectorConfig
from knoarbor.core.config import KnoArborConfig


def selected_connector_configs(config: KnoArborConfig, connector_names: list[str] | None = None) -> dict[str, ConnectorConfig]:
    """Return enabled connector configs selected by CLI/API input."""

    allowed = set(connector_names or [])
    configs: dict[str, ConnectorConfig] = {}
    for name, connector_config in config.connectors.items():
        if connector_names is not None and name not in allowed:
            continue
        if not connector_config.enabled:
            continue
        configs[name] = ConnectorConfig(enabled=connector_config.enabled, settings=connector_config.settings)
    return configs
