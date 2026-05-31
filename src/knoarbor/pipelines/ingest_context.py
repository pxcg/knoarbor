from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from knoarbor.core.markdown import compact_inline_text
from knoarbor.core.schemas.knowledge_extract import KnowledgeExtract
from knoarbor.core.schemas.wiki_relation_plan import WikiRelationPlan
from knoarbor.pipelines.query import QueryPipeline, QueryPipelineRequest
from knoarbor.retrieval.markdown import ScoredPage, query_terms
from knoarbor.storage.vault import VaultStore


class IngestCandidatePage(BaseModel):
    path: str
    title: str
    page_dir: str
    type: str
    status: str | None = None
    source: str | None = None
    score: float
    relevance: str
    matched_fields: list[str] = Field(default_factory=list)
    summary: str = ""
    key_points: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    related_pages: list[str] = Field(default_factory=list)


class IngestWikiContext(BaseModel):
    retrieval_mode: str
    query: str
    candidates: list[IngestCandidatePage] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    stats: dict[str, object] = Field(default_factory=dict)


class IngestCandidatePageContent(BaseModel):
    path: str
    exists: bool
    content: str = ""
    truncated: bool = False
    original_content_length: int = 0
    error: str | None = None


class IngestCandidatePageContext(BaseModel):
    pages: list[IngestCandidatePageContent] = Field(default_factory=list)
    stats: dict[str, object] = Field(default_factory=dict)


class IngestContextProvider:
    """Builds one lightweight candidate set and materializes selected pages later."""

    def __init__(
        self,
        *,
        query_pipeline: QueryPipeline | None = None,
        candidate_limit: int = 8,
        materialized_page_limit: int = 8,
        max_chars_per_page: int = 6000,
    ) -> None:
        self.query_pipeline = query_pipeline or QueryPipeline()
        self.candidate_limit = candidate_limit
        self.materialized_page_limit = materialized_page_limit
        self.max_chars_per_page = max_chars_per_page

    def build(self, vault_path: Path, extract: KnowledgeExtract) -> IngestWikiContext:
        query = build_ingest_query(extract)
        if not query:
            return IngestWikiContext(
                retrieval_mode="none",
                query="",
                warnings=["No searchable terms could be derived from the source extract."],
                stats={"candidate_count": 0},
            )

        result = self.query_pipeline.run(
            QueryPipelineRequest(
                vault_path=vault_path,
                query=query,
                mode="balanced",
                limit=max(self.candidate_limit * 2, self.candidate_limit),
                include_related=True,
            )
        )
        matches = rerank_ingest_candidates(extract, result.matches)[: self.candidate_limit]
        candidates = [
            IngestCandidatePage(
                path=item.page.relative_path,
                title=item.page.title,
                page_dir=item.page.directory,
                type=item.page.page_type,
                status=item.page.status,
                source=item.page.source,
                score=round(item.score, 3),
                relevance=_relevance_label(item.score),
                matched_fields=sorted(item.matched_fields),
                summary=compact_inline_text(item.page.summary, 500),
                key_points=[compact_inline_text(point, 240) for point in item.page.key_points[:6]],
                tags=item.page.tags[:12],
                related_pages=item.page.related_pages[:10],
            )
            for item in matches
        ]
        return IngestWikiContext(
            retrieval_mode=result.retrieval_mode,
            query=query,
            candidates=candidates,
            warnings=result.warnings + result.gaps,
            stats={
                **result.stats,
                "pre_rerank_candidate_count": len(result.matches),
                "candidate_count": len(candidates),
            },
        )

    def materialize(self, vault_path: Path, relation_plan: WikiRelationPlan) -> IngestCandidatePageContext:
        paths = selected_relation_paths(relation_plan)
        pages = VaultStore(vault_path).read_pages(paths, self.materialized_page_limit, self.max_chars_per_page)
        return IngestCandidatePageContext(
            pages=[
                IngestCandidatePageContent(
                    path=page.path,
                    exists=page.exists,
                    content=page.content,
                    truncated=page.truncated,
                    original_content_length=page.original_content_length,
                    error=page.error,
                )
                for page in pages
            ],
            stats={
                "requested_count": len(paths),
                "returned_count": len(pages),
                "existing_count": sum(1 for page in pages if page.exists),
                "max_chars_per_page": self.max_chars_per_page,
            },
        )


def build_ingest_query(extract: KnowledgeExtract) -> str:
    parts: list[str] = [extract.source.title]
    for unit in extract.content_units[:6]:
        if unit.title:
            parts.append(unit.title)
        if unit.is_primary and unit.content:
            parts.append(unit.content)
    if extract.compile_context.primary_content:
        parts.append(extract.compile_context.primary_content)
    return compact_inline_text("\n".join(part for part in parts if part), 1200)


def rerank_ingest_candidates(extract: KnowledgeExtract, matches: list[ScoredPage]) -> list[ScoredPage]:
    """Prefer exact source/provenance and graph context after broad query retrieval."""

    source_terms = _extract_source_terms(extract)
    for item in matches:
        boost = 0.0
        overlap_hits = _overlap_hits(item, source_terms)
        if overlap_hits:
            boost += min(len(overlap_hits) * 0.75, 3.0)
            item.matched_fields.add("source_overlap")
            item.matched_terms["source_overlap"] = overlap_hits[:12]
        if item.page.source and extract.source.source_path and _same_source(item.page.source, extract.source.source_path):
            boost += 4.0
            item.matched_fields.add("same_source")
            item.matched_terms["same_source"] = [extract.source.source_path]
        if item.page.related_pages:
            boost += min(len(item.page.related_pages) * 0.15, 1.0)
            item.matched_fields.add("graph_context")
        item.score += boost
    return sorted(matches, key=lambda item: item.score, reverse=True)


def _extract_source_terms(extract: KnowledgeExtract) -> list[str]:
    values = [
        extract.source.title,
        extract.source.source_id or "",
        extract.source.source_path or "",
        " ".join(extract.compile_context.links),
        " ".join(unit.title or "" for unit in extract.content_units[:8]),
    ]
    terms: list[str] = []
    seen: set[str] = set()
    for value in values:
        for term in query_terms(value):
            if term not in seen:
                seen.add(term)
                terms.append(term)
    return terms[:80]


def _overlap_hits(item: ScoredPage, terms: list[str]) -> list[str]:
    haystack = " ".join(
        [
            item.page.title,
            item.page.relative_path,
            item.page.source or "",
            " ".join(item.page.tags),
            item.page.summary,
        ]
    ).lower()
    return [term for term in terms if term and term in haystack]


def _same_source(page_source: str, extract_source_path: str) -> bool:
    return page_source.strip().strip("/") == extract_source_path.strip().strip("/")


def selected_relation_paths(relation_plan: WikiRelationPlan) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for operation in relation_plan.operations:
        for path in _operation_paths(operation):
            if path not in seen:
                seen.add(path)
                paths.append(path)
    return paths


def _operation_paths(operation: object) -> list[str]:
    paths: list[str] = []
    target_page = getattr(operation, "target_page", None)
    if target_page:
        paths.append(target_page)
    for related in getattr(operation, "related_pages", []):
        path = getattr(related, "path", "")
        if path:
            paths.append(path)
    for candidate in getattr(operation, "candidate_pages", []):
        path = getattr(candidate, "path", "")
        if path:
            paths.append(path)
    return paths


def _relevance_label(score: float) -> str:
    if score >= 8:
        return "high"
    if score >= 3:
        return "medium"
    return "low"
