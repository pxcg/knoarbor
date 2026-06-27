from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from knoarbor.core.schemas.wiki_query import WikiAnswerScope, WikiAnswerSet, WikiRejectedCandidate, WikiSearchResult
from knoarbor.retrieval.markdown import normalize_text


@dataclass(frozen=True)
class AnswerSelectionResult:
    answer_set: WikiAnswerSet
    rejected_candidates: list[WikiRejectedCandidate]


@dataclass(frozen=True)
class AnswerSelectionPolicy:
    """Tunable page-level answer selection policy.

    The selector still returns deterministic results, but thresholds live in one
    named policy instead of being scattered through the selection code.
    """

    source_answer_limit: int = 2
    narrow_source_limit: int = 1
    broad_source_limit: int = 3
    further_reading_limit: int = 3
    broad_primary_limit: int = 3
    exploratory_primary_limit: int = 4
    narrow_supporting_limit: int = 2
    broad_supporting_limit: int = 4
    exploratory_supporting_limit: int = 5
    primary_min_relative_score: float = 0.68
    related_primary_min_relative_score: float = 0.9
    primary_min_dimension_novelty: float = 0.35
    supporting_min_dimension_novelty: float = 0.2
    broad_supporting_min_score: float = 0.8
    narrow_supporting_min_score: float = 1.2

    def primary_limit(self, scope_kind: str) -> int:
        return self.broad_primary_limit if scope_kind == "broad" else self.exploratory_primary_limit

    def supporting_limit(self, scope_kind: str) -> int:
        return {
            "narrow": self.narrow_supporting_limit,
            "broad": self.broad_supporting_limit,
            "exploratory": self.exploratory_supporting_limit,
        }.get(scope_kind, self.broad_supporting_limit)

    def source_limit(self, scope_kind: str) -> int:
        return self.narrow_source_limit if scope_kind == "narrow" else self.broad_source_limit

    def supporting_min_score(self, scope_kind: str) -> float:
        return self.broad_supporting_min_score if scope_kind in {"broad", "exploratory"} else self.narrow_supporting_min_score


class AnswerSetSelector:
    """Selects answer-bearing wiki pages from page-level retrieval candidates."""

    def __init__(self, policy: AnswerSelectionPolicy | None = None) -> None:
        self.policy = policy or AnswerSelectionPolicy()

    def select(self, query: str, results: list[WikiSearchResult], scope: WikiAnswerScope) -> AnswerSelectionResult:
        if not results:
            answer_set = WikiAnswerSet(reason="No candidate pages were found.", stop_reason="no_results")
            return AnswerSelectionResult(answer_set=answer_set, rejected_candidates=[])

        source_intent = query_prefers_source_page(query)
        source_pages = [result for result in results if _is_source_result(result)]
        knowledge_pages = [result for result in results if not _is_source_result(result)]

        if source_intent or not knowledge_pages:
            selected_sources = source_pages[: self.policy.source_answer_limit] if source_pages else results[:1]
            rejected = [
                _reject(result, "source_query_focus" if not _is_source_result(result) else "outside_answer_budget", role_hint="further_reading")
                for result in results
                if result.path not in {page.path for page in selected_sources}
            ]
            answer_set = WikiAnswerSet(
                kind="multi_page" if len(selected_sources) > 1 else "single_page",
                primary_paths=[page.path for page in selected_sources[:1]],
                supporting_paths=[],
                source_paths=[page.path for page in selected_sources[1:] if _is_source_result(page)],
                further_reading_paths=[item.path for item in results if item.path not in {page.path for page in selected_sources}][: self.policy.further_reading_limit],
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
        source_limit = self.policy.source_limit(scope.kind)
        provenance_source_paths = [page.path for page in source_pages[:source_limit]]
        further_reading = [
            result.path
            for result in results
            if result.path not in selected_paths and result.path not in set(provenance_source_paths)
        ][: self.policy.further_reading_limit]
        rejected = [*primary_rejections, *supporting_rejections]
        rejected.extend(
            _reject(result, "source_not_requested", role_hint="source")
            for result in source_pages[source_limit:]
        )
        selected_answer_paths = {page.path for page in [*selected_primary, *selected_supporting]}
        rejected = [item for item in rejected if item.path not in selected_answer_paths]
        rejected = _unique_rejections(rejected)
        answer_set = WikiAnswerSet(
            kind="multi_page" if len(selected_primary) + len(selected_supporting) > 1 and scope.kind in {"broad", "exploratory"} else "single_page",
            primary_paths=[page.path for page in selected_primary],
            supporting_paths=[page.path for page in selected_supporting],
            source_paths=provenance_source_paths,
            further_reading_paths=further_reading,
            rejected_candidates=rejected,
            reason=selection_reason(scope.kind, selected_primary, selected_supporting, provenance_source_paths),
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

        seen_dimensions = result_dimensions(strongest)
        max_primary = self.policy.primary_limit(scope_kind)
        for candidate in candidates[1:]:
            if len(selected) >= max_primary:
                rejected.append(_reject(candidate, "outside_answer_budget", role_hint="supporting"))
                continue
            if candidate.score < strongest.score * self.policy.primary_min_relative_score:
                rejected.append(_reject(candidate, "weak_score", role_hint="supporting"))
                continue
            if candidate.match_kind != "direct" and candidate.score < strongest.score * self.policy.related_primary_min_relative_score:
                rejected.append(_reject(candidate, "related_not_primary", role_hint="supporting"))
                continue
            dimensions = result_dimensions(candidate)
            novelty = dimension_novelty(dimensions, seen_dimensions)
            if novelty < self.policy.primary_min_dimension_novelty:
                rejected.append(_reject(candidate, "redundant_dimension", role_hint="supporting"))
                continue
            selected.append(candidate)
            seen_dimensions.update(dimensions)
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
        seen_dimensions = {dimension for page in primary_pages for dimension in result_dimensions(page)}
        max_supporting = self.policy.supporting_limit(scope_kind)
        for candidate in candidates:
            if candidate.path in primary_paths:
                continue
            if len(selected) >= max_supporting:
                rejected.append(_reject(candidate, "outside_answer_budget", role_hint="further_reading"))
                continue
            dimensions = result_dimensions(candidate)
            novelty = dimension_novelty(dimensions, seen_dimensions)
            relation = candidate.match_kind == "direct" or any(
                reason in candidate.reason for reason in ["shared_source", "outbound_link", "backlink", "type_affinity"]
            )
            minimum_score = self.policy.supporting_min_score(scope_kind)
            if candidate.score < minimum_score and not relation:
                rejected.append(_reject(candidate, "weak_score", role_hint="further_reading"))
                continue
            if novelty < self.policy.supporting_min_dimension_novelty:
                rejected.append(_reject(candidate, "redundant_dimension", role_hint="further_reading"))
                continue
            selected.append(candidate)
            seen_dimensions.update(dimensions)
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


def result_dimensions(result: WikiSearchResult) -> set[str]:
    dimensions = {result.page_role or ""}
    if "/" in result.path:
        dimensions.add(result.path.split("/", 1)[0])
    dimensions.update(result.entities[:8])
    dimensions.update(result.matched_fields)
    dimensions.update(result.matched_terms.get("graph_reasons", []))
    dimensions.update(normalize_text(excerpt.heading)[:40] for excerpt in result.excerpts[:3] if excerpt.heading)
    return {dimension for dimension in dimensions if dimension}


def _is_source_result(result: WikiSearchResult) -> bool:
    return (
        result.role == "source"
        or result.page_role == "source_digest"
        or result.path.startswith("sources/")
    )


def dimension_novelty(dimensions: set[str], seen_dimensions: set[str]) -> float:
    if not dimensions:
        return 0.0
    return len(dimensions - seen_dimensions) / len(dimensions)


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
        f"and {len(supporting_pages)} supporting page(s) that add complementary evidence dimensions."
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
