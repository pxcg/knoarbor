from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from knoarbor.connectors.base import ConnectorConfig
from knoarbor.connectors.registry import ConnectorRegistry
from knoarbor.connectors.selection import selected_connector_configs
from knoarbor.core.config import KnoArborConfig
from knoarbor.core.errors import error_info
from knoarbor.core.schemas.sources import RawSource, SourceDocument, SourceRef


class SourcePipelineItem(BaseModel):
    ref: SourceRef
    raw: RawSource
    document: SourceDocument


class SourcePipelineFailure(BaseModel):
    connector: str
    stage: Literal["fetch", "to_document"]
    ref: SourceRef
    error_code: str | None = None
    error_category: str | None = None
    error_retryable: bool = False
    error_hint: str | None = None
    error_type: str
    error_message: str


class SourcePipelineResult(BaseModel):
    connector: str
    items: list[SourcePipelineItem] = Field(default_factory=list)
    failures: list[SourcePipelineFailure] = Field(default_factory=list)


class SourcePipelineBatchResult(BaseModel):
    results: list[SourcePipelineResult] = Field(default_factory=list)
    stats: dict[str, int] = Field(default_factory=dict)


class SourcePipeline:
    """Runs deterministic source discovery and document normalization."""

    def __init__(self, registry: ConnectorRegistry | None = None) -> None:
        self.registry = registry or ConnectorRegistry()

    def run(self, connector_name: str, config: ConnectorConfig) -> SourcePipelineResult:
        connector = self.registry.get(connector_name)
        refs = connector.discover(config)
        items: list[SourcePipelineItem] = []
        failures: list[SourcePipelineFailure] = []
        for ref in refs:
            try:
                raw = connector.fetch(ref, config)
            except Exception as exc:
                failures.append(_source_failure(connector_name, "fetch", ref, exc))
                continue
            try:
                document = connector.to_document(raw, config)
            except Exception as exc:
                failures.append(_source_failure(connector_name, "to_document", ref, exc))
                continue
            items.append(SourcePipelineItem(ref=ref, raw=raw, document=document))
        return SourcePipelineResult(connector=connector_name, items=items, failures=failures)

    def run_many(self, configs: dict[str, ConnectorConfig]) -> SourcePipelineBatchResult:
        results = [self.run(name, config) for name, config in configs.items() if config.enabled]
        return SourcePipelineBatchResult(
            results=results,
            stats={
                "connector_count": len(results),
                "item_count": sum(len(result.items) for result in results),
                "failure_count": sum(len(result.failures) for result in results),
            },
        )

    def run_enabled(self, config: KnoArborConfig, connector_names: list[str] | None = None) -> SourcePipelineBatchResult:
        return self.run_many(selected_connector_configs(config, connector_names))


def _source_failure(connector_name: str, stage: Literal["fetch", "to_document"], ref: SourceRef, exc: Exception) -> SourcePipelineFailure:
    info = error_info(exc)
    return SourcePipelineFailure(
        connector=connector_name,
        stage=stage,
        ref=ref,
        error_code=str(info["code"]),
        error_category=str(info["category"]),
        error_retryable=bool(info["retryable"]),
        error_hint=str(info["hint"]),
        error_type=type(exc).__name__,
        error_message=str(exc),
    )
