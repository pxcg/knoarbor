from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from knoarbor.core.errors import UserInputError
from knoarbor.retrieval import IndexProvider, IndexRequest, MachineIndexProvider
from knoarbor.retrieval.graph_index import expand_graph_index_pages
from knoarbor.retrieval.markdown import FIELD_WEIGHTS, ScoredPage, expand_related_pages, query_terms, score_pages
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

    def run(self, request: QueryPipelineRequest) -> QueryPipelineResult:
        monitor = current_run_monitor()
        if monitor:
            monitor.event("query_started", stage="query", message="Starting wiki context retrieval.", current_item=request.query)
        vault_path = request.vault_path.expanduser().resolve()
        if not vault_path.exists() or not vault_path.is_dir():
            raise UserInputError(f"vault_path does not exist or is not a directory: {vault_path}")

        direct_pages = self.index_provider.collect(
            IndexRequest(
                vault_path=vault_path,
                page_dirs=request.page_dirs,
                page_kinds=request.page_kinds,
                page_roles=request.page_roles,
                facets=request.facets,
            )
        )
        if monitor:
            monitor.event("query_index_loaded", stage="query", message=f"Loaded {len(direct_pages)} direct page(s).", payload={"page_count": len(direct_pages)})
        graph_pages = direct_pages
        if request.include_related and request.mode in {"balanced", "deep"} and request.page_dirs:
            graph_pages = self.index_provider.collect(IndexRequest(vault_path=vault_path))
            if monitor:
                monitor.event("query_graph_scope_loaded", stage="query", message=f"Loaded {len(graph_pages)} graph page(s) for related expansion.")

        terms = query_terms(request.query)
        if not terms:
            raise UserInputError("query does not contain searchable terms")

        scored = score_pages(direct_pages, terms, request.query)
        direct_match_count = len(scored)
        graph_index_expansion_count = 0
        graph_index_seed_pages: list[str] = []
        graph_index_result_paths: list[str] = []
        if request.include_related and request.mode in {"balanced", "deep"}:
            scored = expand_graph_index_pages(scored, graph_pages, vault_path, request.mode)
            graph_index_expansion_count = len([item for item in scored.values() if "graph_index" in item.matched_fields])
            graph_index_seed_pages = sorted(
                {
                    seed
                    for item in scored.values()
                    for seed in item.matched_terms.get("graph_index", [])
                }
            )
            graph_index_result_paths = sorted(
                item.page.relative_path
                for item in scored.values()
                if "graph_index" in item.matched_fields
            )
            scored = expand_related_pages(scored, graph_pages, request.mode)
        related_expansion_count = len([item for item in scored.values() if item.graph_boost > 0])
        related_seed_pages = sorted(
            {
                seed
                for item in scored.values()
                for seed in item.matched_terms.get("related_graph", [])
            }
        )
        related_result_paths = sorted(
            item.page.relative_path
            for item in scored.values()
            if item.graph_boost > 0
        )

        ranked = [item for item in sorted(scored.values(), key=lambda item: item.score, reverse=True) if item.score > 0]
        matches = ranked[: request.limit]
        if monitor:
            monitor.event(
                "query_finished",
                stage="query",
                message=f"Query returned {len(matches)} result(s).",
                progress={"total": len(ranked), "completed": len(matches), "current": request.query},
                payload={"candidate_count": len(ranked), "returned_count": len(matches)},
            )
        gaps: list[str] = []
        if not matches:
            gaps.append("No relevant wiki pages were found for this query.")
        elif matches[0].score < 2.5:
            gaps.append("Top wiki match is weak; caller should consider other tools or a follow-up question.")

        return QueryPipelineResult(
            query=request.query,
            retrieval_mode=f"{self.index_provider.name}_hybrid_{request.mode}",
            matches=matches,
            gaps=gaps,
            warnings=[],
            stats={
                "index_provider": self.index_provider.name,
                "scoring_model": "field_weighted_bm25",
                "page_count": len(direct_pages),
                "direct_page_count": len(direct_pages),
                "graph_page_count": len(graph_pages),
                "page_dirs": request.page_dirs,
                "page_kinds": request.page_kinds,
                "page_roles": request.page_roles,
                "facets": request.facets,
                "initial_scope_dirs": request.page_dirs or sorted({page.directory for page in direct_pages}),
                "expanded_scope_dirs": sorted({page.directory for page in graph_pages}),
                "initial_scope_page_kinds": request.page_kinds or sorted({page.page_kind for page in direct_pages if page.page_kind}),
                "expanded_scope_page_kinds": sorted({page.page_kind for page in graph_pages if page.page_kind}),
                "initial_scope_roles": request.page_roles or sorted({page.role for page in direct_pages if page.role}),
                "expanded_scope_roles": sorted({page.role for page in graph_pages if page.role}),
                "initial_scope_facets": request.facets or sorted({facet for page in direct_pages for facet in page.facets}),
                "expanded_scope_facets": sorted({facet for page in graph_pages for facet in page.facets}),
                "query_terms": terms,
                "field_weights": FIELD_WEIGHTS,
                "direct_match_count": direct_match_count,
                "graph_index_expansion_count": graph_index_expansion_count,
                "graph_index_seed_pages": graph_index_seed_pages,
                "graph_index_result_paths": graph_index_result_paths,
                "related_expansion_count": related_expansion_count,
                "related_seed_pages": related_seed_pages,
                "related_result_paths": related_result_paths,
                "candidate_count": len(ranked),
                "returned_count": len(matches),
            },
        )
