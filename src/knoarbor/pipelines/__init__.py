"""Core pipeline package.

Pipeline implementations should compose connectors, storage, retrieval,
semantic agents, policies, ledgers, and events without depending on FastAPI or
any external workflow adapter.
"""

from knoarbor.pipelines.source import SourcePipeline, SourcePipelineBatchResult, SourcePipelineItem, SourcePipelineResult
from knoarbor.pipelines.source_segmentation import SourceSegmentBatch, SourceSegmenter
from knoarbor.core.schemas.ingest_pipeline import IngestPipelineResult, IngestSourceResult
from knoarbor.pipelines.ingest import IngestPipeline
from knoarbor.pipelines.ingest_context import IngestContextProvider, IngestWikiContext, IngestCandidatePageContext
from knoarbor.pipelines.ingest_write_gate import IngestWriteGate, IngestWriteGateResult
from knoarbor.pipelines.ingest_write_policy import IngestWritePolicy, IngestWritePolicyResult
from knoarbor.pipelines.lint import WikiLintPipeline
from knoarbor.pipelines.operation import WikiOperationPipeline
from knoarbor.pipelines.query import QueryPipeline, QueryPipelineRequest, QueryPipelineResult
from knoarbor.pipelines.write import WikiWritePipeline

__all__ = [
    "QueryPipeline",
    "QueryPipelineRequest",
    "QueryPipelineResult",
    "IngestPipeline",
    "IngestContextProvider",
    "IngestWriteGate",
    "IngestWriteGateResult",
    "IngestWritePolicy",
    "IngestWritePolicyResult",
    "IngestWikiContext",
    "IngestCandidatePageContext",
    "IngestPipelineResult",
    "IngestSourceResult",
    "SourcePipeline",
    "SourcePipelineBatchResult",
    "SourcePipelineItem",
    "SourcePipelineResult",
    "SourceSegmentBatch",
    "SourceSegmenter",
    "WikiLintPipeline",
    "WikiOperationPipeline",
    "WikiWritePipeline",
]
