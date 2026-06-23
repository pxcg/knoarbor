from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from threading import RLock
from typing import Literal

from pydantic import BaseModel, Field

from knoarbor.core.markdown import compact_inline_text, extract_heading, extract_list_items, extract_section, extract_tags, parse_frontmatter
from knoarbor.core.schemas.knowledge_extract import KnowledgeExtract
from knoarbor.core.schemas.wiki_page_plan import WikiPagePlan
from knoarbor.pipelines.query import QueryPipeline, QueryPipelineRequest
from knoarbor.retrieval.markdown import ScoredPage, extract_headings, query_terms, strip_frontmatter
from knoarbor.storage.vault import VaultStore


MaterializedContextRole = Literal["target", "related", "candidate"]
MaterializedContentKind = Literal["full", "excerpt", "profile", "missing"]


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
    context_role: MaterializedContextRole = "candidate"
    content_kind: MaterializedContentKind = "missing"
    title: str = ""
    summary: str = ""
    key_points: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    headings: list[str] = Field(default_factory=list)
    source: str | None = None
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
        self._lock = RLock()
        self._query_cache: dict[tuple[object, ...], object] = {}
        self._materialize_cache: dict[tuple[object, ...], IngestCandidatePageContext] = {}

    def clear_cache(self) -> None:
        with self._lock:
            self._query_cache.clear()
            self._materialize_cache.clear()

    def build(self, vault_path: Path, extract: KnowledgeExtract) -> IngestWikiContext:
        query = build_ingest_query(extract)
        if not query:
            return IngestWikiContext(
                retrieval_mode="none",
                query="",
                warnings=["No searchable terms could be derived from the source extract."],
                stats={"candidate_count": 0},
            )

        query_request = QueryPipelineRequest(
            vault_path=vault_path,
            query=query,
            mode="balanced",
            limit=self.candidate_limit,
            include_related=True,
        )
        result = self._cached_query(query_request)
        matches = rerank_ingest_candidates(extract, result.matches)
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
                summary=_inline_text(item.page.summary),
                key_points=[_inline_text(point) for point in item.page.key_points],
                tags=item.page.tags,
                related_pages=item.page.related_pages,
            )
            for item in matches
        ]
        profile_chars = _candidate_profile_chars(candidates)
        return IngestWikiContext(
            retrieval_mode=result.retrieval_mode,
            query=query,
            candidates=candidates,
            warnings=result.warnings + result.gaps,
            stats={
                **result.stats,
                "pre_rerank_candidate_count": len(result.matches),
                "candidate_count": len(candidates),
                "page_plan_profile_chars": profile_chars,
                "page_plan_candidate_body_included": False,
                "page_plan_context_policy": "lightweight_page_profiles_without_page_body",
            },
        )

    def materialize(self, vault_path: Path, page_plan: WikiPagePlan) -> IngestCandidatePageContext:
        path_roles = selected_page_plan_path_roles(page_plan)
        paths = [item[0] for item in path_roles]
        cache_key = _materialize_cache_key(
            vault_path,
            path_roles,
            self.materialized_page_limit,
            self.max_chars_per_page,
        )
        with self._lock:
            cached = self._materialize_cache.get(cache_key)
            if cached is not None:
                return cached.model_copy(deep=True)
        pages = VaultStore(vault_path).read_pages(paths, self.materialized_page_limit, self.max_chars_per_page)
        role_by_path = {path: role for path, role in path_roles}
        context = IngestCandidatePageContext(
            pages=[
                _materialized_page_content(
                    page.path,
                    exists=page.exists,
                    content=page.content,
                    original_content_length=page.original_content_length,
                    truncated=page.truncated,
                    error=page.error,
                    role=role_by_path.get(page.path, "candidate"),
                )
                for page in pages
            ],
            stats={
                "requested_count": len(paths),
                "returned_count": len(pages),
                "existing_count": sum(1 for page in pages if page.exists),
                "max_chars_per_page": self.max_chars_per_page,
                "context_policy": "target_full_related_excerpt_candidate_profile",
                "full_body_pages": sum(1 for page in pages if page.exists and role_by_path.get(page.path) == "target"),
                "excerpt_pages": sum(1 for page in pages if page.exists and role_by_path.get(page.path) == "related"),
                "profile_only_pages": sum(1 for page in pages if page.exists and role_by_path.get(page.path) == "candidate"),
            },
        )
        context.stats["materialized_context_chars"] = sum(len(page.content) for page in context.pages)
        with self._lock:
            self._materialize_cache[cache_key] = context.model_copy(deep=True)
        return context

    def _cached_query(self, request: QueryPipelineRequest):
        cache_key = _query_cache_key(request, self.query_pipeline.index_provider.name)
        with self._lock:
            cached = self._query_cache.get(cache_key)
            if cached is not None:
                return deepcopy(cached)
        result = self.query_pipeline.run(request)
        with self._lock:
            self._query_cache[cache_key] = deepcopy(result)
        return result


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


def _inline_text(value: str) -> str:
    return " ".join(value.split())


def _candidate_profile_chars(candidates: list[IngestCandidatePage]) -> int:
    return sum(len(candidate.model_dump_json(exclude_none=True)) for candidate in candidates)


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


def selected_page_plan_paths(page_plan: WikiPagePlan) -> list[str]:
    return [path for path, _role in selected_page_plan_path_roles(page_plan)]


def selected_page_plan_path_roles(page_plan: WikiPagePlan) -> list[tuple[str, MaterializedContextRole]]:
    paths: list[str] = []
    seen: set[str] = set()
    for operation in page_plan.operations:
        for raw_path, role in _operation_path_roles(operation):
            path = VaultStore.normalize_page_path(raw_path)
            if not path:
                continue
            if path in seen:
                continue
            seen.add(path)
            paths.append(path)
    return [(path, _highest_page_plan_role(path, page_plan)) for path in paths]


def _query_cache_key(request: QueryPipelineRequest, index_provider_name: str) -> tuple[object, ...]:
    return (
        "query",
        request.vault_path.expanduser().resolve().as_posix(),
        index_provider_name,
        request.query,
        request.mode,
        request.limit,
        tuple(request.page_dirs),
        request.include_related,
    )


def _materialize_cache_key(
    vault_path: Path,
    path_roles: list[tuple[str, MaterializedContextRole]],
    materialized_page_limit: int,
    max_chars_per_page: int,
) -> tuple[object, ...]:
    return (
        "materialize",
        vault_path.expanduser().resolve().as_posix(),
        tuple(path_roles),
        materialized_page_limit,
        max_chars_per_page,
    )


def _operation_paths(operation: object) -> list[str]:
    return [path for path, _role in _operation_path_roles(operation)]


def _operation_path_roles(operation: object) -> list[tuple[str, MaterializedContextRole]]:
    paths: list[tuple[str, MaterializedContextRole]] = []
    target_page = getattr(operation, "target_page", None)
    if target_page:
        paths.append((target_page, "target"))
    for related in getattr(operation, "related_pages", []):
        path = getattr(related, "path", "")
        if path:
            paths.append((path, "related"))
    for candidate in getattr(operation, "candidate_pages", []):
        path = getattr(candidate, "path", "")
        if path:
            paths.append((path, "candidate"))
    return paths


def _highest_page_plan_role(path: str, page_plan: WikiPagePlan) -> MaterializedContextRole:
    rank: dict[MaterializedContextRole, int] = {"candidate": 0, "related": 1, "target": 2}
    selected: MaterializedContextRole = "candidate"
    for operation in page_plan.operations:
        for raw_path, role in _operation_path_roles(operation):
            current_path = VaultStore.normalize_page_path(raw_path)
            if current_path == path and rank[role] > rank[selected]:
                selected = role
    return selected


def _materialized_page_content(
    path: str,
    *,
    exists: bool,
    content: str,
    original_content_length: int,
    truncated: bool,
    error: str | None,
    role: MaterializedContextRole,
) -> IngestCandidatePageContent:
    if not exists:
        return IngestCandidatePageContent(
            path=path,
            exists=False,
            context_role=role,
            content_kind="missing",
            original_content_length=original_content_length,
            error=error,
        )

    metadata = parse_frontmatter(content)
    title = extract_heading(content, Path(path).stem)
    summary = _inline_text(extract_section(content, "Summary"))
    key_points = [_inline_text(item) for item in (extract_list_items(extract_section(content, "Key Points")) or extract_list_items(extract_section(content, "Claims")))]
    tags = extract_tags(content, metadata) or _entities_as_tags(content)
    headings = extract_headings(content)
    source = metadata.get("source")
    if role == "target":
        return IngestCandidatePageContent(
            path=path,
            exists=True,
            context_role="target",
            content_kind="full",
            title=title,
            summary=summary,
            key_points=key_points,
            tags=tags,
            headings=headings,
            source=source,
            content=content,
            truncated=truncated,
            original_content_length=original_content_length,
        )
    if role == "related":
        excerpt = _related_page_excerpt(content, summary=summary, key_points=key_points, headings=headings)
        return IngestCandidatePageContent(
            path=path,
            exists=True,
            context_role="related",
            content_kind="excerpt",
            title=title,
            summary=summary,
            key_points=key_points,
            tags=tags,
            headings=headings,
            source=source,
            content=excerpt,
            truncated=truncated,
            original_content_length=original_content_length,
        )
    return IngestCandidatePageContent(
        path=path,
        exists=True,
        context_role="candidate",
        content_kind="profile",
        title=title,
        summary=summary,
        key_points=key_points,
        tags=tags,
        headings=headings,
        source=source,
        content="",
        truncated=truncated,
        original_content_length=original_content_length,
    )


def _related_page_excerpt(content: str, *, summary: str, key_points: list[str], headings: list[str]) -> str:
    parts: list[str] = []
    if summary:
        parts.append("Summary:\n" + summary)
    if key_points:
        parts.append("Key Points:\n" + "\n".join(f"- {point}" for point in key_points))
    if headings:
        parts.append("Headings:\n" + "\n".join(f"- {heading}" for heading in headings))
    body = strip_frontmatter(content)
    if body and not parts:
        parts.append(compact_inline_text(body, 1200))
    return "\n\n".join(parts)


def _entities_as_tags(content: str) -> list[str]:
    tags: list[str] = []
    for item in extract_list_items(extract_section(content, "Entities")):
        text = item.strip()
        if not text or text.startswith("暂无"):
            continue
        text = text.removeprefix("[[").removesuffix("]]")
        if "|" in text:
            text = text.split("|", 1)[-1]
        if text and text not in tags:
            tags.append(text)
    return tags[:24]


def _relevance_label(score: float) -> str:
    if score >= 8:
        return "high"
    if score >= 3:
        return "medium"
    return "low"
