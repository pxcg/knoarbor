from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from knoarbor.core.errors import UserInputError
from knoarbor.retrieval import GraphLedRetrievalRequest, GraphLedRetriever, IndexProvider, MachineIndexProvider
from knoarbor.retrieval.markdown import FIELD_WEIGHTS, ScoredPage, query_terms
from knoarbor.runtime import current_run_monitor


@dataclass
class QueryPipelineRequest:
    vault_path: Path
    query: str
    mode: str = "balanced"
    limit: int = 8
    page_dirs: list[str] = field(default_factory=list)
    page_kinds: list[str] = field(default_factory=list)
    page_roles: list[str] = field(default_factory=list)
    facets: list[str] = field(default_factory=list)
    include_related: bool = True


@dataclass
class QueryPipelineResult:
    query: str
    retrieval_mode: str
    matches: list[ScoredPage]
    gaps: list[str]
    warnings: list[str]
    stats: dict[str, object]


class QueryPipeline:
    """Runs deterministic wiki retrieval for API, CLI, UI, or skill callers."""

    def __init__(self, index_provider: IndexProvider | None = None) -> None:
        self.index_provider = index_provider or MachineIndexProvider()
        self.retriever = GraphLedRetriever(self.index_provider)

    def run(self, request: QueryPipelineRequest) -> QueryPipelineResult:
        monitor = current_run_monitor()
        if monitor:
            monitor.event("query_started", stage="query", message="Starting wiki context retrieval.", current_item=request.query)
        vault_path = request.vault_path.expanduser().resolve()
        if not vault_path.exists() or not vault_path.is_dir():
            raise UserInputError(f"vault_path does not exist or is not a directory: {vault_path}")

        terms = query_terms(request.query)
        if not terms:
            raise UserInputError("query does not contain searchable terms")

        retrieval = self.retriever.retrieve(
            GraphLedRetrievalRequest(
                vault_path=vault_path,
                query=request.query,
                limit=request.limit,
                page_dirs=request.page_dirs,
                page_kinds=request.page_kinds,
                page_roles=request.page_roles,
                facets=request.facets,
                include_related=request.include_related,
            )
        )
        matches = retrieval.matches
        if monitor:
            monitor.event(
                "query_index_loaded",
                stage="query",
                message=f"Loaded {retrieval.stats.get('page_count', 0)} scoped page(s).",
                payload={"page_count": retrieval.stats.get("page_count", 0)},
            )
        if monitor:
            monitor.event(
                "query_finished",
                stage="query",
                message=f"Query returned {len(matches)} result(s).",
                progress={"total": retrieval.stats.get("candidate_count", 0), "completed": len(matches), "current": request.query},
                payload={"candidate_count": retrieval.stats.get("candidate_count", 0), "returned_count": len(matches)},
            )
        gaps: list[str] = []
        if not matches:
            gaps.append("No relevant wiki pages were found for this query.")
        elif matches[0].score < 2.5:
            gaps.append("Top wiki match is weak; caller should consider other tools or a follow-up question.")

        return QueryPipelineResult(
            query=request.query,
            retrieval_mode=f"{self.index_provider.name}_graph_led_bm25_{request.mode}",
            matches=matches,
            gaps=gaps,
            warnings=retrieval.warnings,
            stats={
                **retrieval.stats,
                "field_weights": FIELD_WEIGHTS,
                "returned_count": len(matches),
            },
        )
