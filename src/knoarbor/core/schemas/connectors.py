from __future__ import annotations

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
