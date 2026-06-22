from __future__ import annotations

import re
from pathlib import Path

from knoarbor.core.errors import UserInputError
from knoarbor.core.markdown import compact_inline_text
from knoarbor.core.schemas.wiki_query import (
    WikiAnswerScope,
    WikiAnswerSet,
    WikiAtomTrace,
    WikiEvidenceCoverage,
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
from knoarbor.retrieval.answer_selection import AnswerSetSelector, query_prefers_source_page, result_facets
from knoarbor.retrieval.markdown import (
    ScoredPage,
    SearchPage,
    normalize_text,
    query_terms,
    relevance_label,
)
from knoarbor.storage.knowledge_atom_index import KnowledgeAtomRecord, read_knowledge_atom_records


MAX_ATOM_TRACES_PER_PAGE = 8


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
            page_kinds=request.page_kinds,
            page_roles=request.page_roles,
            facets=request.facets,
            include_related=request.include_related,
        )
    )
    results = [
        build_result(item, terms, request)
        for item in pipeline_result.matches[: request.max_results]
        if item.score > 0
    ]
    results = attach_atom_traces(results, vault_path)
    answer_scope = build_answer_scope(request, pipeline_result.stats, results)
    selection = AnswerSetSelector().select(request.query, results, answer_scope)
    answer_set = selection.answer_set
    results = assign_result_roles(request.query, results, answer_set=answer_set)
    results = apply_answer_content_strategy(results, pipeline_result.matches)
    primary_pages = [result for result in results if result.role == "primary"]
    supporting_pages = [result for result in results if result.role == "supporting"]
    source_pages = [result for result in results if result.role == "source"]

    gap_suggestions = build_gap_suggestions(request.query, results, pipeline_result.gaps)
    evidence_coverage = build_evidence_coverage(terms, answer_scope, primary_pages, supporting_pages, source_pages, pipeline_result.gaps)
    answer_guidance = build_answer_guidance(results, gap_suggestions, primary_pages=primary_pages)
    context_pack = build_context_pack(
        request.query,
        order_results_for_context(results),
        request.max_context_chars,
        answer_guidance,
        gap_suggestions,
    )
    stats = {
        **pipeline_result.stats,
        "returned_count": len(results),
        "max_pages_to_read": request.max_pages_to_read,
        "context_strategy": "page_first_primary_full",
        "context_pack_chars": len(context_pack),
        "context_pack_truncated": context_pack.endswith("... [truncated]"),
        "atom_trace_count": sum(len(result.atom_traces) for result in results),
        "gap_count": len(pipeline_result.gaps),
        "gap_suggestion_count": len(gap_suggestions),
    }
    return WikiSearchResponse(
        query=request.query,
        retrieval_mode=pipeline_result.retrieval_mode,
        results=results,
        primary_pages=primary_pages,
        supporting_pages=supporting_pages,
        source_pages=source_pages,
        answer_scope=answer_scope,
        answer_set=answer_set,
        evidence_coverage=evidence_coverage,
        rejected_candidates=selection.rejected_candidates,
        context_pack=context_pack,
        answer_guidance=answer_guidance,
        gap_suggestions=gap_suggestions,
        gaps=pipeline_result.gaps,
        warnings=pipeline_result.warnings,
        stats=stats,
        trace=build_query_trace(stats, results, answer_scope=answer_scope, answer_set=answer_set),
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
            page_kinds=request.page_kinds,
            page_roles=request.page_roles,
            facets=request.facets,
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
    excerpts = select_excerpts(page, terms, max_excerpts, request.max_chars_per_excerpt)
    score = round(item.score, 3)
    return WikiSearchResult(
        path=page.relative_path,
        canonical_path=page.canonical_path or page.relative_path,
        legacy_paths=page.legacy_paths,
        title=page.title,
        type=page.page_type,
        page_kind=page.page_kind,
        page_role=page.role,
        facets=page.facets,
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
        content=None,
        source=page.source,
        tags=page.tags,
        related_pages=page.related_pages[:10],
        content_truncated=False,
    )


def attach_atom_traces(results: list[WikiSearchResult], vault_path: Path) -> list[WikiSearchResult]:
    if not results:
        return []
    atoms_by_page = _atom_traces_by_page(vault_path)
    if not atoms_by_page:
        return results
    output: list[WikiSearchResult] = []
    for result in results:
        traces = atoms_by_page.get(result.path, [])
        if not traces:
            output.append(result)
            continue
        output.append(result.model_copy(update={"atom_traces": traces[:MAX_ATOM_TRACES_PER_PAGE]}))
    return output


def _atom_traces_by_page(vault_path: Path) -> dict[str, list[WikiAtomTrace]]:
    records = read_knowledge_atom_records(vault_path)
    traces_by_page: dict[str, list[WikiAtomTrace]] = {}
    for record in records:
        trace = _atom_trace(record)
        for page_path in record.page_paths:
            traces_by_page.setdefault(page_path, [])
            if trace.atom_id not in {item.atom_id for item in traces_by_page[page_path]}:
                traces_by_page[page_path].append(trace)
    return traces_by_page


def _atom_trace(record: KnowledgeAtomRecord) -> WikiAtomTrace:
    return WikiAtomTrace(
        atom_id=record.atom_id,
        atom_type=record.atom_type,
        text=compact_inline_text(record.text, 260),
        source_digest_id=record.source_digest_id,
    )


def apply_answer_content_strategy(
    results: list[WikiSearchResult],
    matches: list[ScoredPage],
) -> list[WikiSearchResult]:
    """Attach model-facing page bodies after answer roles are known.

    KnoArbor retrieves maintained wiki pages, not interchangeable chunks. The
    answer context should therefore preserve answer-bearing wiki pages as whole
    maintained pages. Source pages remain provenance by default unless they are
    selected as answer-bearing pages for a source-oriented query.
    """

    page_by_path = {item.page.relative_path: item.page for item in matches}
    output: list[WikiSearchResult] = []
    for result in results:
        page = page_by_path.get(result.path)
        if not page:
            output.append(result)
            continue
        if result.role in {"primary", "supporting"}:
            output.append(result.model_copy(update={"content": page.body, "content_truncated": False}))
            continue
        output.append(result.model_copy(update={"content": None, "content_truncated": False}))
    return output


def build_context_match(item: ScoredPage, terms: list[str], request: WikiContextRequest) -> WikiContextMatch:
    page = item.page
    content = compact_inline_text(page.body, request.max_chars_per_page) if request.include_content else None
    return WikiContextMatch(
        path=page.relative_path,
        canonical_path=page.canonical_path or page.relative_path,
        legacy_paths=page.legacy_paths,
        title=page.title,
        page_dir=page.directory,
        type=page.page_type,
        page_kind=page.page_kind,
        page_role=page.role,
        facets=page.facets,
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


def build_answer_scope(request: WikiSearchRequest, stats: dict[str, object], results: list[WikiSearchResult]) -> WikiAnswerScope:
    kind, reason = classify_answer_scope(request.query, results)
    return WikiAnswerScope(
        kind=kind,
        vault_ids=_request_vault_ids(request, results),
        initial_page_dirs=[str(item) for item in stats.get("initial_scope_dirs", request.page_dirs) or []],
        expanded_page_dirs=[str(item) for item in stats.get("expanded_scope_dirs", request.page_dirs) or []],
        include_related=request.include_related,
        reason=reason,
    )


def _request_vault_ids(request: WikiSearchRequest, results: list[WikiSearchResult]) -> list[str]:
    ids: list[str] = []
    if request.all_vaults:
        ids.append("all")
    if request.vault_id:
        ids.append(request.vault_id)
    ids.extend(request.vault_ids)
    ids.extend(result.vault_id or "" for result in results)
    seen: set[str] = set()
    output: list[str] = []
    for item in ids:
        text = item.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


def classify_answer_scope(query: str, results: list[WikiSearchResult]) -> tuple[str, str]:
    if not results:
        return "narrow", "No candidate pages were found."
    text = normalize_text(query)
    broad_terms = {
        "architecture",
        "compare",
        "comparison",
        "design",
        "overview",
        "pattern",
        "patterns",
        "strategy",
        "summary",
        "system",
        "体系",
        "全部",
        "区别",
        "如何",
        "对比",
        "怎么",
        "总结",
        "整体",
        "方案",
        "有哪些",
        "机制",
        "架构",
        "模式",
        "设计",
        "风险",
    }
    exploratory_terms = {"guide", "learn", "roadmap", "了解", "介绍", "入门", "学习", "导览"}
    non_source = [result for result in results if not _is_source_result(result)]
    directories = {result.path.split("/", 1)[0] for result in non_source if "/" in result.path}
    top_scores = [result.score for result in non_source[:3]]
    close_top_scores = len(top_scores) >= 2 and top_scores[1] >= top_scores[0] * 0.72
    if any(term in text or term in query for term in exploratory_terms):
        return "exploratory", "Query asks for a guided overview or learning path."
    if any(term in text or term in query for term in broad_terms):
        return "broad", "Query asks for a broad explanation or system-level synthesis."
    if len(directories) >= 2 and len(non_source) >= 3 and close_top_scores:
        return "broad", "Multiple strong pages across directories can jointly answer the query."
    return "narrow", "Top result appears sufficient as the main answer unit."


def build_evidence_coverage(
    terms: list[str],
    scope: WikiAnswerScope,
    primary_pages: list[WikiSearchResult],
    supporting_pages: list[WikiSearchResult],
    source_pages: list[WikiSearchResult],
    gaps: list[str],
) -> WikiEvidenceCoverage:
    selected_pages = [*primary_pages, *supporting_pages]
    covered_terms = sorted(
        {
            term
            for page in selected_pages
            for values in page.matched_terms.values()
            for term in values
            if term in terms
        }
    )
    missing_terms = [term for term in terms if term not in set(covered_terms)]
    if gaps or not primary_pages:
        status = "weak"
    elif scope.kind in {"broad", "exploratory"} and len(supporting_pages) >= 2:
        status = "strong" if len(covered_terms) >= max(1, len(terms) // 2) else "adequate"
    else:
        status = "adequate"
    return WikiEvidenceCoverage(
        status=status,
        primary_count=len(primary_pages),
        supporting_count=len(supporting_pages),
        source_count=len(source_pages),
        gap_count=len(gaps),
        covered_terms=covered_terms[:12],
        covered_facets=sorted({facet for page in selected_pages for facet in result_facets(page)})[:12],
        missing_facets=missing_terms[:8],
    )


def assign_result_roles(query: str, results: list[WikiSearchResult], *, answer_set: WikiAnswerSet | None = None) -> list[WikiSearchResult]:
    if not results:
        return []

    primary_paths = set(answer_set.primary_paths if answer_set else [])
    supporting_paths = set(answer_set.supporting_paths if answer_set else [])
    source_paths = set(answer_set.source_paths if answer_set else [])
    primary_path = next(iter(primary_paths), "") or _primary_result_path(query, results)
    output: list[WikiSearchResult] = []
    for result in results:
        if result.path == primary_path or result.path in primary_paths:
            output.append(result.model_copy(update={"role": "primary"}))
        elif result.path in supporting_paths:
            output.append(result.model_copy(update={"role": "supporting"}))
        elif result.path in source_paths or _is_source_result(result):
            output.append(result.model_copy(update={"role": "source"}))
        else:
            output.append(result.model_copy(update={"role": "supporting"}))
    return output


def _primary_result_path(query: str, results: list[WikiSearchResult]) -> str:
    if query_prefers_source_page(query):
        return results[0].path
    for result in results:
        if not _is_source_result(result):
            return result.path
    return results[0].path


def _is_source_result(result: WikiSearchResult) -> bool:
    return result.page_role == "source_digest" or result.page_kind == "source_digest" or result.type == "source"

def build_answer_guidance(
    results: list[WikiSearchResult],
    gaps: list[WikiQueryGapSuggestion],
    *,
    primary_pages: list[WikiSearchResult] | None = None,
) -> list[str]:
    if not results:
        return [
            "No maintained wiki page matched strongly enough; tell the user the local KnoArbor vault has no reliable answer yet.",
            "Use other tools or ask a follow-up question before making factual claims.",
        ]
    primary_pages = primary_pages or [results[0]]
    guidance = [
        "Use primary_pages as the maintained wiki answer unit when they answer the question directly.",
        "Use supporting_pages and source_pages for context, provenance, and follow-up suggestions.",
        "Use the returned wiki pages as local evidence, not as the only possible source of truth.",
        "Cite page paths when making claims, especially for specific facts or recommendations.",
        f"Primary page candidate: {primary_pages[0].path}.",
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

    ordered_results = order_results_for_context(results)
    omitted = 0
    for index, result in enumerate(ordered_results, start=1):
        include_full_body = result.role in {"primary", "supporting"} and bool(result.content)
        block = build_result_context_block(index, result, full=include_full_body)
        if include_full_body:
            lines.extend(block)
            continue
        candidate = "\n".join([*lines, *block])
        if len(candidate) > max_chars:
            omitted = len(ordered_results) - index + 1
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


def order_results_for_context(results: list[WikiSearchResult]) -> list[WikiSearchResult]:
    role_order = {"primary": 0, "supporting": 1, "source": 2}
    return [result for _, result in sorted(
        enumerate(results),
        key=lambda pair: (
            role_order.get(pair[1].role, 1),
            1 if _is_source_result(pair[1]) and pair[1].role != "source" else 0,
            -pair[1].score,
            pair[0],
        ),
    )]


def build_query_trace(
    stats: dict[str, object],
    results: list[WikiSearchResult],
    *,
    answer_scope: WikiAnswerScope,
    answer_set: WikiAnswerSet,
) -> dict[str, object]:
    origin_counts = {
        "direct": sum(1 for result in results if result.match_kind == "direct"),
        "related": sum(1 for result in results if result.match_kind == "related"),
    }
    role_counts = {
        "primary": sum(1 for result in results if result.role == "primary"),
        "supporting": sum(1 for result in results if result.role == "supporting"),
        "source": sum(1 for result in results if result.role == "source"),
    }
    return {
        "schema_version": "query_trace.v1",
        "scoring_model": stats.get("scoring_model", "unknown"),
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
        "atom_trace_count": stats.get("atom_trace_count", 0),
        "gap_count": stats.get("gap_count", 0),
        "gap_suggestion_count": stats.get("gap_suggestion_count", 0),
        "origin_counts": origin_counts,
        "role_counts": role_counts,
        "answer_scope": answer_scope.model_dump(),
        "answer_set": answer_set.model_dump(),
        "rejected_candidates": [item.model_dump() for item in answer_set.rejected_candidates],
        "returned_paths": [result.path for result in results],
        "atom_trace_counts": {
            result.path: len(result.atom_traces)
            for result in results
            if result.atom_traces
        },
        "top_matches": [
            {
                "path": result.path,
                "score": result.score,
                "relevance": result.relevance,
                "matched_fields": result.matched_fields,
                "atom_trace_count": len(result.atom_traces),
                "reason": result.reason,
            }
            for result in results[:5]
        ],
    }


def build_result_context_block(index: int, result: WikiSearchResult, *, full: bool = False) -> list[str]:
    lines = [
        f"{index}. {result.title} ({result.path}, relevance: {result.relevance}, score: {result.score})",
        f"Answer role: {result.role}",
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
