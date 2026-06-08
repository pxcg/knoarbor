from __future__ import annotations

from pathlib import Path

from knoarbor.connectors.registry import ConnectorRegistry
from knoarbor.core.config import KnoArborConfig, load_config
from knoarbor.core.schemas.connectors import SourceCatalogResponse, SourceConnectorCatalogItem


class SourceCatalogService:
    """Read-only catalog of source connector contracts.

    This service exposes connector capabilities without running connector
    discovery. Runtime path checks remain part of doctor/source preflight.
    """

    def __init__(self, registry: ConnectorRegistry | None = None) -> None:
        self.registry = registry or ConnectorRegistry()

    def list_catalog(
        self,
        *,
        config_path: str | None = None,
        connector_names: list[str] | None = None,
    ) -> SourceCatalogResponse:
        config = load_config(config_path) if config_path else None
        selected = set(connector_names or [])
        items: list[SourceConnectorCatalogItem] = []
        for capability in self.registry.capabilities():
            if selected and capability.name not in selected:
                continue
            configured, enabled = _configured_state(config, capability.name)
            items.append(
                SourceConnectorCatalogItem(
                    name=capability.name,
                    version=capability.version,
                    source_types=capability.source_types,
                    supports_discovery=capability.supports_discovery,
                    supports_checkpoint=capability.supports_checkpoint,
                    supports_segmentation_hint=capability.supports_segmentation_hint,
                    requires_external_service=capability.requires_external_service,
                    configured=configured,
                    enabled=enabled,
                )
            )
        return SourceCatalogResponse(
            config_path=str(Path(config_path).expanduser().resolve()) if config_path else None,
            connectors=items,
        )


def _configured_state(config: KnoArborConfig | None, connector_name: str) -> tuple[bool, bool]:
    if config is None:
        return False, False
    connector = config.connectors.get(connector_name)
    if connector is None:
        return False, False
    return True, connector.enabled
