from __future__ import annotations

import re
from pathlib import Path

from knoarbor.core.errors import UserInputError
from knoarbor.core.markdown import compact_inline_text
from knoarbor.core.schemas.wiki_query import (
    WikiQueryGapSuggestion,
    WikiContextMatch,
    WikiContextRequest,
    WikiContextResponse,
    WikiSearchExcerpt,
    WikiSearchRequest,
    WikiSearchResponse,
    WikiSearchResult,
)
from knoarbor.pipelines.query import QueryPipeline, QueryPipelineRequest
from knoarbor.retrieval.markdown import (
    ScoredPage,
    SearchPage,
    normalize_text,
    query_terms,
    relevance_label,
)


def search_query(request: WikiSearchRequest) -> WikiSearchResponse:
    vault_path = Path(request.vault_path).expanduser().resolve()
    if not vault_path.exists() or not vault_path.is_dir():
        raise UserInputError(f"vault_path does not exist or is not a directory: {vault_path}")

    terms = query_terms(request.query)
    if not terms:
        raise UserInputError("query does not contain searchable terms")

    pipeline_result = QueryPipeline().run(
        QueryPipelineRequest(
            vault_path=vault_path,
            query=request.query,
            mode=request.mode,
            limit=max(request.max_pages_to_read, request.max_results),
            page_dirs=request.page_dirs,
            include_related=request.include_related,
        )
    )
    results = [
        build_result(item, terms, request)
        for item in pipeline_result.matches[: request.max_results]
        if item.score > 0
    ]

    gap_suggestions = build_gap_suggestions(request.query, results, pipeline_result.gaps)
    answer_guidance = build_answer_guidance(results, gap_suggestions)
    context_pack = build_context_pack(
        request.query,
        results,
        request.max_context_chars,
        answer_guidance,
        gap_suggestions,
        request.context_format,
    )
    stats = {
        **pipeline_result.stats,
        "returned_count": len(results),
        "max_pages_to_read": request.max_pages_to_read,
        "context_format": request.context_format,
        "context_pack_chars": len(context_pack),
        "context_pack_truncated": request.context_format == "compact" and context_pack.endswith("... [truncated]"),
        "gap_count": len(pipeline_result.gaps),
        "gap_suggestion_count": len(gap_suggestions),
    }
    return WikiSearchResponse(
        query=request.query,
        retrieval_mode=pipeline_result.retrieval_mode,
        results=results,
        context_pack=context_pack,
        answer_guidance=answer_guidance,
        gap_suggestions=gap_suggestions,
        gaps=pipeline_result.gaps,
        warnings=pipeline_result.warnings,
        stats=stats,
        trace=build_query_trace(stats, results),
    )


def build_wiki_context(request: WikiContextRequest) -> WikiContextResponse:
    vault_path = Path(request.vault_path).expanduser().resolve()
    if not vault_path.exists() or not vault_path.is_dir():
        raise UserInputError(f"vault_path does not exist or is not a directory: {vault_path}")

    terms = query_terms(request.query)
    if not terms:
        raise UserInputError("query does not contain searchable terms")

    pipeline_result = QueryPipeline().run(
        QueryPipelineRequest(
            vault_path=vault_path,
            query=request.query,
            mode="balanced",
            limit=request.limit,
            page_dirs=request.page_dirs,
            include_related=request.include_related,
        )
    )
    matches = [build_context_match(item, terms, request) for item in pipeline_result.matches]
    warnings = list(pipeline_result.warnings)
    if not matches:
        warnings.append("No relevant wiki context matches were found.")

    return WikiContextResponse(
        query=request.query,
        purpose=request.purpose,
        matches=matches,
        context_pack=build_context_summary(request.query, matches),
        warnings=warnings,
        stats={
            **pipeline_result.stats,
            "returned_count": len(matches),
            "include_content": request.include_content,
        },
    )


def build_result(item: ScoredPage, terms: list[str], request: WikiSearchRequest) -> WikiSearchResult:
    page = item.page
    max_excerpts = 0 if request.mode == "quick" else request.max_excerpts_per_page
    if request.mode == "deep":
        max_excerpts = max(max_excerpts, min(6, request.max_excerpts_per_page + 2))
    excerpts = select_excerpts(page, terms, max_excerpts, request.max_chars_per_excerpt, full=request.context_format == "full")
    score = round(item.score, 3)
    include_content = request.include_content or request.context_format == "full"
    content = page.body if include_content and request.context_format == "full" else compact_inline_text(page.body, request.max_chars_per_page) if include_content else None
    return WikiSearchResult(
        path=page.relative_path,
        title=page.title,
        type=page.page_type,
        status=page.status,
        score=score,
        relevance=relevance_label(score),
        match_kind="related" if item.matched_fields == {"related_graph"} else "direct",
        matched_fields=sorted(item.matched_fields),
        matched_terms={key: sorted(set(value)) for key, value in sorted(item.matched_terms.items())},
        reason=match_reason(item),
        summary=compact_inline_text(page.summary, 500),
        key_points=[compact_inline_text(point, 240) for point in page.key_points[:6]],
        excerpts=excerpts,
        content=content,
        source=page.source,
        tags=page.tags,
        related_pages=page.related_pages[:10],
        content_truncated=request.context_format != "full"
        and (
            bool(content and len(page.body) > request.max_chars_per_page)
            or any(len(excerpt.content) >= request.max_chars_per_excerpt for excerpt in excerpts)
        ),
    )


def build_context_match(item: ScoredPage, terms: list[str], request: WikiContextRequest) -> WikiContextMatch:
    page = item.page
    content = compact_inline_text(page.body, request.max_chars_per_page) if request.include_content else None
    return WikiContextMatch(
        path=page.relative_path,
        title=page.title,
        page_dir=page.directory,
        type=page.page_type,
        status=page.status,
        source=page.source,
        summary=compact_inline_text(page.summary, 500),
        tags=page.tags,
        key_points=[compact_inline_text(point, 240) for point in page.key_points[:6]],
        related_pages=page.related_pages[:10],
        score=round(item.score, 3),
        relevance=relevance_label(item.score),
        matched_fields=sorted(item.matched_fields),
        reason=match_reason(item),
        content=content,
        content_truncated=bool(content and len(page.body) > request.max_chars_per_page),
    )


def match_reason(item: ScoredPage) -> str:
    fields = ", ".join(sorted(item.matched_fields)) or "content"
    if item.graph_boost:
        reasons = ", ".join(sorted(set(item.graph_reasons)))
        suffix = f" via {reasons}" if reasons else ""
        return f"Matched {fields}; graph relevance boost {round(item.graph_boost, 3)}{suffix}."
    return f"Matched {fields}."


def select_excerpts(page: SearchPage, terms: list[str], max_excerpts: int, max_chars: int, *, full: bool = False) -> list[WikiSearchExcerpt]:
    if max_excerpts == 0:
        return []

    candidates: list[WikiSearchExcerpt] = []
    for heading, body in extract_sections(page.body):
        if heading in {"Tags", "Related Pages", "Source"}:
            continue
        score = section_score(f"{heading}\n{body}", terms)
        if score <= 0:
            continue
        candidates.append(
            WikiSearchExcerpt(
                path=page.relative_path,
                page_title=page.title,
                heading=heading,
                section=heading,
                content=body if full else compact_inline_text(body, max_chars),
                score=round(score, 3),
            )
        )

    if not candidates and page.summary:
        candidates.append(
            WikiSearchExcerpt(
                path=page.relative_path,
                page_title=page.title,
                heading="Summary",
                section="Summary",
                content=page.summary if full else compact_inline_text(page.summary, max_chars),
                score=1.0,
            )
        )

    return sorted(candidates, key=lambda item: item.score, reverse=True)[:max_excerpts]


def section_score(value: str, terms: list[str]) -> float:
    text = normalize_text(value)
    return float(sum(1 for term in terms if term in text))


def extract_sections(content: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    matches = list(re.finditer(r"^##+\s+(.+?)\s*$", content, flags=re.MULTILINE))
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        sections.append((match.group(1).strip(), content[start:end].strip()))
    return sections


def build_answer_guidance(results: list[WikiSearchResult], gaps: list[WikiQueryGapSuggestion]) -> list[str]:
    if not results:
        return [
            "No maintained wiki page matched strongly enough; tell the user the local KnoArbor vault has no reliable answer yet.",
            "Use other tools or ask a follow-up question before making factual claims.",
        ]
    guidance = [
        "Use the returned wiki pages as local evidence, not as the only possible source of truth.",
        "Cite page paths when making claims, especially for specific facts or recommendations.",
        "Prefer high-relevance results and quoted excerpts; use low-relevance pages only as supporting context.",
    ]
    if gaps:
        guidance.append("Mention the local knowledge gap if the answer depends on missing or weak wiki coverage.")
    return guidance


def build_gap_suggestions(query: str, results: list[WikiSearchResult], gaps: list[str]) -> list[WikiQueryGapSuggestion]:
    if not results:
        return [
            WikiQueryGapSuggestion(
                kind="no_result",
                query=query,
                reason="No maintained wiki pages matched the query.",
                recommended_action="ingest_more_sources",
            )
        ]
    top = results[0]
    if top.relevance == "low" or any("weak" in gap.lower() for gap in gaps):
        return [
            WikiQueryGapSuggestion(
                kind="low_confidence",
                query=query,
                reason=f"Top match {top.path} has low confidence for this query.",
                recommended_action="review_query_terms",
            )
        ]
    return []


def build_context_pack(
    query: str,
    results: list[WikiSearchResult],
    max_chars: int,
    answer_guidance: list[str],
    gap_suggestions: list[WikiQueryGapSuggestion],
    context_format: str = "compact",
) -> str:
    lines = [
        "Relevant KnoArbor context for the host AI.",
        f"Query: {query}",
        "",
    ]
    if answer_guidance:
        lines.append("Answer guidance:")
        lines.extend(f"- {item}" for item in answer_guidance)
        lines.append("")
    if gap_suggestions:
        lines.append("Query gap signals:")
        lines.extend(f"- {item.kind}: {item.reason} ({item.recommended_action})" for item in gap_suggestions)
        lines.append("")
    if not results:
        lines.append("No relevant wiki pages found.")
        return "\n".join(lines)

    if context_format == "full":
        for index, result in enumerate(results, start=1):
            lines.extend(build_result_context_block(index, result, full=True))
        return "\n".join(lines).strip()

    omitted = 0
    for index, result in enumerate(results, start=1):
        block = build_result_context_block(index, result)
        candidate = "\n".join([*lines, *block])
        if len(candidate) > max_chars:
            omitted = len(results) - index + 1
            break
        lines.extend(block)

    if omitted:
        omission = f"... [{omitted} result(s) omitted due to context budget]"
        candidate = "\n".join([*lines, omission])
        if len(candidate) <= max_chars:
            lines.append(omission)
        else:
            return ("\n".join(lines))[: max_chars - 20].rstrip() + "\n... [truncated]"
    return "\n".join(lines).strip()


def build_query_trace(stats: dict[str, object], results: list[WikiSearchResult]) -> dict[str, object]:
    origin_counts = {
        "direct": sum(1 for result in results if result.match_kind == "direct"),
        "related": sum(1 for result in results if result.match_kind == "related"),
    }
    return {
        "schema_version": "query_trace.v1",
        "query_terms": stats.get("query_terms", []),
        "page_count": stats.get("page_count", 0),
        "direct_page_count": stats.get("direct_page_count", 0),
        "graph_page_count": stats.get("graph_page_count", 0),
        "initial_scope_dirs": stats.get("initial_scope_dirs", []),
        "expanded_scope_dirs": stats.get("expanded_scope_dirs", []),
        "direct_match_count": stats.get("direct_match_count", 0),
        "related_expansion_count": stats.get("related_expansion_count", 0),
        "related_seed_pages": stats.get("related_seed_pages", []),
        "related_result_paths": stats.get("related_result_paths", []),
        "candidate_count": stats.get("candidate_count", 0),
        "returned_count": stats.get("returned_count", 0),
        "context_pack_chars": stats.get("context_pack_chars", 0),
        "context_pack_truncated": stats.get("context_pack_truncated", False),
        "gap_count": stats.get("gap_count", 0),
        "gap_suggestion_count": stats.get("gap_suggestion_count", 0),
        "origin_counts": origin_counts,
        "returned_paths": [result.path for result in results],
        "top_matches": [
            {
                "path": result.path,
                "score": result.score,
                "relevance": result.relevance,
                "matched_fields": result.matched_fields,
                "reason": result.reason,
            }
            for result in results[:5]
        ],
    }


def build_result_context_block(index: int, result: WikiSearchResult, *, full: bool = False) -> list[str]:
    lines = [
        f"{index}. {result.title} ({result.path}, relevance: {result.relevance}, score: {result.score})",
        f"Match origin: {result.match_kind}",
        f"Summary: {result.summary or 'No summary.'}",
    ]
    if result.key_points:
        lines.append("Key points:")
        lines.extend(f"- {point}" for point in result.key_points[:4])
    if result.excerpts:
        lines.append("Relevant excerpts:")
        for excerpt in result.excerpts if full else result.excerpts[:2]:
            lines.append(f"- {excerpt.path}#{excerpt.section}: {excerpt.content}")
    if full and result.content:
        lines.append("Full page body:")
        lines.append(result.content)
    if result.source:
        lines.append(f"Source: {result.source}")
    lines.append(f"Why matched: {result.reason}")
    lines.append("")
    return lines


def build_context_summary(query: str, matches: list[WikiContextMatch]) -> str:
    lines = ["Relevant KnoArbor pages for workflow context.", f"Query: {query}", ""]
    if not matches:
        lines.append("No relevant pages found.")
        return "\n".join(lines)

    for index, match in enumerate(matches, start=1):
        lines.append(f"{index}. {match.title} ({match.path}, {match.relevance}, score {match.score})")
        if match.summary:
            lines.append(f"   Summary: {match.summary}")
        if match.tags:
            lines.append(f"   Tags: {', '.join(match.tags[:8])}")
        lines.append(f"   Reason: {match.reason}")
    return "\n".join(lines).strip()
