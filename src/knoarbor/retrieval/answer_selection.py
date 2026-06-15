from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from knoarbor.core.schemas.wiki_query import WikiAnswerScope, WikiAnswerSet, WikiRejectedCandidate, WikiSearchResult
from knoarbor.retrieval.markdown import normalize_text


@dataclass(frozen=True)
class AnswerSelectionResult:
    answer_set: WikiAnswerSet
    rejected_candidates: list[WikiRejectedCandidate]


class AnswerSetSelector:
    """Selects answer-bearing wiki pages from page-level retrieval candidates."""

    def select(self, query: str, results: list[WikiSearchResult], scope: WikiAnswerScope) -> AnswerSelectionResult:
        if not results:
            answer_set = WikiAnswerSet(reason="No candidate pages were found.", stop_reason="no_results")
            return AnswerSelectionResult(answer_set=answer_set, rejected_candidates=[])

        source_intent = query_prefers_source_page(query)
        source_pages = [result for result in results if result.type == "source"]
        knowledge_pages = [result for result in results if result.type != "source"]

        if source_intent or not knowledge_pages:
            selected_sources = source_pages[:2] if source_pages else results[:1]
            rejected = [
                _reject(result, "source_query_focus" if result.type != "source" else "outside_answer_budget", role_hint="further_reading")
                for result in results
                if result.path not in {page.path for page in selected_sources}
            ]
            answer_set = WikiAnswerSet(
                kind="multi_page" if len(selected_sources) > 1 else "single_page",
                primary_paths=[page.path for page in selected_sources[:1]],
                supporting_paths=[],
                source_paths=[page.path for page in selected_sources[1:] if page.type == "source"],
                further_reading_paths=[item.path for item in results if item.path not in {page.path for page in selected_sources}][:3],
                rejected_candidates=rejected,
                reason="The query asks about source or provenance, so source digest pages are answer-bearing.",
                stop_reason="source_intent_selected",
            )
            return AnswerSelectionResult(answer_set=answer_set, rejected_candidates=rejected)

        selected_primary, primary_rejections = self._select_primary_pages(knowledge_pages, scope.kind)
        selected_supporting, supporting_rejections = self._select_supporting_pages(
            knowledge_pages,
            selected_primary,
            scope.kind,
        )
        selected_paths = {page.path for page in [*selected_primary, *selected_supporting]}
        source_limit = 1 if scope.kind == "narrow" else 3
        source_paths = [page.path for page in source_pages[:source_limit]]
        further_reading = [
            result.path
            for result in results
            if result.path not in selected_paths and result.path not in set(source_paths)
        ][:3]
        rejected = [*primary_rejections, *supporting_rejections]
        rejected.extend(
            _reject(result, "source_not_requested", role_hint="source")
            for result in source_pages[source_limit:]
        )
        selected_answer_paths = {page.path for page in [*selected_primary, *selected_supporting]}
        selected_answer_paths.update(source_paths)
        rejected = [item for item in rejected if item.path not in selected_answer_paths]
        rejected = _unique_rejections(rejected)
        answer_set = WikiAnswerSet(
            kind="multi_page" if len(selected_primary) + len(selected_supporting) > 1 and scope.kind in {"broad", "exploratory"} else "single_page",
            primary_paths=[page.path for page in selected_primary],
            supporting_paths=[page.path for page in selected_supporting],
            source_paths=source_paths,
            further_reading_paths=further_reading,
            rejected_candidates=rejected,
            reason=selection_reason(scope.kind, selected_primary, selected_supporting, source_paths),
            stop_reason="answer_set_selected",
        )
        return AnswerSelectionResult(answer_set=answer_set, rejected_candidates=rejected)

    def _select_primary_pages(
        self,
        candidates: list[WikiSearchResult],
        scope_kind: str,
    ) -> tuple[list[WikiSearchResult], list[WikiRejectedCandidate]]:
        selected: list[WikiSearchResult] = []
        rejected: list[WikiRejectedCandidate] = []
        if not candidates:
            return selected, rejected

        strongest = candidates[0]
        selected.append(strongest)
        if scope_kind == "narrow":
            return selected, rejected

        seen_facets = result_facets(strongest)
        max_primary = 3 if scope_kind == "broad" else 4
        for candidate in candidates[1:]:
            if len(selected) >= max_primary:
                rejected.append(_reject(candidate, "outside_answer_budget", role_hint="supporting"))
                continue
            if candidate.score < strongest.score * 0.68:
                rejected.append(_reject(candidate, "weak_score", role_hint="supporting"))
                continue
            if candidate.match_kind != "direct" and candidate.score < strongest.score * 0.9:
                rejected.append(_reject(candidate, "related_not_primary", role_hint="supporting"))
                continue
            facets = result_facets(candidate)
            novelty = facet_novelty(facets, seen_facets)
            if novelty < 0.35:
                rejected.append(_reject(candidate, "redundant_facet", role_hint="supporting"))
                continue
            selected.append(candidate)
            seen_facets.update(facets)
        return selected, rejected

    def _select_supporting_pages(
        self,
        candidates: list[WikiSearchResult],
        primary_pages: list[WikiSearchResult],
        scope_kind: str,
    ) -> tuple[list[WikiSearchResult], list[WikiRejectedCandidate]]:
        selected: list[WikiSearchResult] = []
        rejected: list[WikiRejectedCandidate] = []
        primary_paths = {page.path for page in primary_pages}
        if not primary_pages:
            return selected, rejected
        seen_facets = {facet for page in primary_pages for facet in result_facets(page)}
        max_supporting = {"narrow": 2, "broad": 4, "exploratory": 5}.get(scope_kind, 3)
        for candidate in candidates:
            if candidate.path in primary_paths:
                continue
            if len(selected) >= max_supporting:
                rejected.append(_reject(candidate, "outside_answer_budget", role_hint="further_reading"))
                continue
            facets = result_facets(candidate)
            novelty = facet_novelty(facets, seen_facets)
            relation = candidate.match_kind == "direct" or any(
                reason in candidate.reason for reason in ["shared_source", "outbound_link", "backlink", "type_affinity"]
            )
            minimum_score = 0.8 if scope_kind in {"broad", "exploratory"} else 1.2
            if candidate.score < minimum_score and not relation:
                rejected.append(_reject(candidate, "weak_score", role_hint="further_reading"))
                continue
            if novelty < 0.2:
                rejected.append(_reject(candidate, "redundant_facet", role_hint="further_reading"))
                continue
            selected.append(candidate)
            seen_facets.update(facets)
        return selected, rejected


def query_prefers_source_page(query: str) -> bool:
    text = query.lower()
    source_terms = {
        "source",
        "provenance",
        "raw",
        "digest",
        "来源",
        "原始",
        "溯源",
        "出处",
        "source digest",
    }
    return any(term in text for term in source_terms)


def result_facets(result: WikiSearchResult) -> set[str]:
    facets = {result.type, result.path.split("/", 1)[0]}
    facets.update(result.tags[:8])
    facets.update(result.matched_fields)
    facets.update(result.matched_terms.get("graph_reasons", []))
    facets.update(normalize_text(excerpt.heading)[:40] for excerpt in result.excerpts[:3] if excerpt.heading)
    return {facet for facet in facets if facet}


def facet_novelty(facets: set[str], seen_facets: set[str]) -> float:
    if not facets:
        return 0.0
    return len(facets - seen_facets) / len(facets)


def selection_reason(
    scope_kind: str,
    primary_pages: list[WikiSearchResult],
    supporting_pages: list[WikiSearchResult],
    source_paths: list[str],
) -> str:
    if not primary_pages:
        return "No maintained answer page was selected."
    if scope_kind == "narrow":
        source_note = " Source digest pages are kept for provenance." if source_paths else ""
        return f"The query is narrow enough to anchor on {primary_pages[0].path}.{source_note}"
    return (
        f"The query is {scope_kind}; selected {len(primary_pages)} primary page(s) "
        f"and {len(supporting_pages)} supporting page(s) that add complementary facets."
    )


def _reject(
    result: WikiSearchResult,
    reason: str,
    *,
    role_hint: Literal["primary", "supporting", "source", "further_reading"],
) -> WikiRejectedCandidate:
    return WikiRejectedCandidate(path=result.path, title=result.title, reason=reason, score=result.score, role_hint=role_hint)


def _unique_rejections(items: list[WikiRejectedCandidate]) -> list[WikiRejectedCandidate]:
    seen: set[str] = set()
    output: list[WikiRejectedCandidate] = []
    for item in items:
        if item.path in seen:
            continue
        seen.add(item.path)
        output.append(item)
    return output
