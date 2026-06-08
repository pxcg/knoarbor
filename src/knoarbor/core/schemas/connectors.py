from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from knoarbor.core.schemas.sources import SourceRef


class ConnectorRunConfig(BaseModel):
    enabled: bool = True
    settings: dict[str, object] = Field(default_factory=dict)


class ConnectorRunRequest(BaseModel):
    connector: str = Field(..., min_length=1)
    settings: dict[str, object] = Field(default_factory=dict)


class ConnectorBatchRunRequest(BaseModel):
    connectors: dict[str, ConnectorRunConfig] = Field(default_factory=dict)


class ConnectorDiscoverResponse(BaseModel):
    connector: str
    refs: list[SourceRef]


class SourceConnectorCatalogItem(BaseModel):
    schema_version: Literal["source_connector_catalog_item.v1"] = "source_connector_catalog_item.v1"
    name: str
    version: str
    source_types: list[str] = Field(default_factory=list)
    supports_discovery: bool = True
    supports_checkpoint: bool = True
    supports_segmentation_hint: bool = False
    requires_external_service: bool = False
    configured: bool = False
    enabled: bool = False


class SourceCatalogResponse(BaseModel):
    schema_version: Literal["source_catalog.v1"] = "source_catalog.v1"
    config_path: str | None = None
    connectors: list[SourceConnectorCatalogItem] = Field(default_factory=list)
