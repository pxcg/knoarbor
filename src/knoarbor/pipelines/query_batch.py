from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import os
import time
from typing import Callable

from knoarbor.core.errors import UserInputError
from knoarbor.core.schemas.raw_evidence import RawEvidenceRecord
from knoarbor.core.vault_selection import ResolvedVault
from knoarbor.pipelines.query import QueryPipeline, QueryPipelineRequest, QueryPipelineResult
from knoarbor.retrieval.evidence_selection import (
    EvidenceSelectionCandidate,
    explain_structural_evidence,
    select_structural_evidence,
)
from knoarbor.retrieval.corpus_catalog import (
    NavigationRegionScope,
    resolve_navigation_region_scopes,
)
from knoarbor.retrieval.unified import (
    EvidenceHandle,
    EvidenceRead,
    QueryStatus,
    read_evidence_handles,
)
from knoarbor.storage.lexical_snapshot import RetrievalSafety
from knoarbor.storage.index_snapshot import IndexSnapshot, open_index_snapshot


BM25_RESULT_WINDOW_PER_GROUP = 12
BM25_GLOBAL_RESULT_WINDOW = 16


@dataclass(frozen=True)
class QueryBatchExpression:
    query_id: str
    query: str
    region_id: str | None = None
    group_id: str | None = None


@dataclass(frozen=True)
class QueryBatchRequest:
    vaults: tuple[ResolvedVault, ...]
    expressions: tuple[QueryBatchExpression, ...]
    raise_if_cancelled: Callable[[], None] | None = None


@dataclass(frozen=True)
class QueryBatchEvidence:
    vault: ResolvedVault
    read: EvidenceRead
    query_ids: tuple[str, ...]
    matched_spans: tuple[tuple[int, int], ...] = ()
    segments: tuple["QueryEvidenceSegment", ...] = ()
    selection_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class QueryBatchCandidate:
    vault: ResolvedVault
    handle: EvidenceHandle
    query_ids: tuple[str, ...]
    handles_by_query: tuple[tuple[str, EvidenceHandle], ...]
    reciprocal_rank_score: float
    best_rank: int
    matched_spans: tuple[tuple[int, int], ...] = ()

    @property
    def key(self) -> tuple[str, str]:
        return (_vault_scope(self.vault), self.handle.evidence_id)


@dataclass(frozen=True)
class QueryBatchCandidateSet:
    """BM25/RRF-ordered, deduplicated and auditable batch candidate set."""

    items: tuple[QueryBatchCandidate, ...]
    structural_decisions: dict[
        tuple[str, str],
        tuple[str, ...],
    ]

    @property
    def count(self) -> int:
        return len(self.items)


@dataclass(frozen=True)
class QueryEvidenceSegment:
    """One structure-preserving slice of selected active Raw evidence."""

    text: str
    char_start: int
    char_end: int


@dataclass(frozen=True)
class QueryBatchEvidenceSet:
    """Exact active Raw evidence selected by Query for one answer."""

    items: tuple[QueryBatchEvidence, ...]
    selection_reasons: dict[str, tuple[str, ...]]

    @property
    def selected_evidence_ids(self) -> tuple[str, ...]:
        return tuple(item.read.handle.evidence_id for item in self.items)

    @property
    def evidence_query_ids(self) -> dict[str, list[str]]:
        return {
            item.read.handle.evidence_id: list(item.query_ids)
            for item in self.items
        }


@dataclass(frozen=True)
class QueryBatchResult:
    status: QueryStatus
    expressions: tuple[QueryBatchExpression, ...]
    query_results: tuple[dict[str, object], ...]
    group_results: tuple[dict[str, object], ...]
    candidate_set: QueryBatchCandidateSet
    global_eligible_candidate_count: int
    global_result_window: int
    evidence_set: QueryBatchEvidenceSet
    search_elapsed_ms: dict[str, float]
    raw_read_rounds: int
    raw_read_count: int
    raw_read_elapsed_ms: float
    batch_elapsed_ms: float
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class _ScopedCandidate:
    vault: ResolvedVault
    handle: EvidenceHandle

    @property
    def key(self) -> tuple[str, str]:
        return (_vault_scope(self.vault), self.handle.evidence_id)


class QueryBatchPipeline:
    """Owns model-free batch recall, fusion, and active Raw resolution."""

    def run(self, request: QueryBatchRequest) -> QueryBatchResult:
        batch_started = time.perf_counter()
        expressions = _normalize_expressions(request.expressions)
        if not expressions:
            raise UserInputError("query batch requires at least one query expression")
        if not request.vaults:
            raise UserInputError("query batch requires at least one vault")
        snapshots: dict[str, IndexSnapshot] = {}
        for vault in request.vaults:
            try:
                snapshot = open_index_snapshot(
                    vault.path,
                    raise_if_cancelled=request.raise_if_cancelled,
                )
            except RuntimeError:
                # Preserve the normal Query-owned typed unavailable state.
                # Failed opens are intentionally retried by the expression
                # path so its warning and status remain unchanged.
                continue
            if snapshot is not None:
                snapshots[_vault_scope(vault)] = snapshot
        navigation_scopes = _navigation_scopes(
            request.vaults,
            expressions,
        )

        def run_expression(expression: QueryBatchExpression):
            started = time.perf_counter()
            def run_vault(
                vault: ResolvedVault,
            ) -> tuple[ResolvedVault, QueryPipelineResult]:
                scope = navigation_scopes.get(
                    (expression.query_id, _vault_scope(vault))
                )
                missing_scope = bool(expression.region_id and scope is None)
                return (
                    vault,
                    QueryPipeline().run(
                        QueryPipelineRequest(
                            vault_path=vault.path,
                            query=expression.query,
                            safety=RetrievalSafety.with_timeout(
                                raise_if_cancelled=request.raise_if_cancelled
                            ),
                            resolve_evidence=False,
                            source_record_ids=(
                                scope.source_record_ids
                                if scope is not None
                                else frozenset() if missing_scope else None
                            ),
                            source_unit_ids=(
                                scope.source_unit_ids
                                if scope is not None
                                else frozenset() if missing_scope else None
                            ),
                            snapshot=snapshots.get(_vault_scope(vault)),
                        )
                    ),
                )
            results = tuple(run_vault(vault) for vault in request.vaults)
            return expression, results, (time.perf_counter() - started) * 1000

        worker_count = min(
            len(expressions),
            max(2, os.cpu_count() or 2),
        )
        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            expression_results = list(pool.map(run_expression, expressions))

        query_results: list[dict[str, object]] = []
        group_results: list[dict[str, object]] = []
        terminal_statuses: list[QueryStatus] = []
        expression_candidates: dict[str, list[_ScopedCandidate]] = {}
        search_elapsed_ms: dict[str, float] = {}
        warnings: list[str] = []

        for expression, vault_results, elapsed_ms in expression_results:
            search_elapsed_ms[expression.query_id] = round(elapsed_ms, 3)
            status = _expression_status([result for _vault, result in vault_results])
            candidates: list[_ScopedCandidate] = []
            outcomes: list[dict[str, object]] = []
            for vault, result in vault_results:
                outcomes.append(_outcome(vault, result))
                warnings.extend(result.warnings)
                candidates.extend(
                    _ScopedCandidate(vault=vault, handle=handle)
                    for handle in result.handles
                    if _candidate_matches_navigation_scope(
                        handle,
                        query_id=expression.query_id,
                        vault=vault,
                        scopes=navigation_scopes,
                    )
                )
            candidates.sort(
                key=lambda item: (
                    -item.handle.fused_score,
                    item.handle.fused_rank,
                    item.key,
                )
            )
            eligible_candidate_count = len(candidates)
            if status == "candidates" and not candidates:
                status = "no_match"
            terminal_statuses.append(status)
            expression_candidates[expression.query_id] = candidates
            query_results.append(
                {
                    "query_id": expression.query_id,
                    "query": expression.query,
                    "region_id": expression.region_id,
                    "group_id": expression.group_id,
                    "status": status,
                    "candidate_count": len(candidates),
                    "eligible_candidate_count": eligible_candidate_count,
                    "outcomes": outcomes,
                }
            )

        grouped_expressions: dict[str, list[QueryBatchExpression]] = {}
        for expression in expressions:
            grouped_expressions.setdefault(
                expression.group_id or expression.query_id,
                [],
            ).append(expression)

        group_candidate_lists: dict[str, tuple[QueryBatchCandidate, ...]] = {}
        for group_id, group_expressions in grouped_expressions.items():
            group_metadata: dict[tuple[str, str], _ScopedCandidate] = {}
            group_scores: dict[tuple[str, str], float] = {}
            group_best_rank: dict[tuple[str, str], int] = {}
            group_query_ids: dict[tuple[str, str], list[str]] = {}
            group_spans: dict[tuple[str, str], set[tuple[int, int]]] = {}
            group_handles: dict[
                tuple[str, str],
                dict[str, EvidenceHandle],
            ] = {}
            for expression in group_expressions:
                for fallback_rank, candidate in enumerate(
                    expression_candidates.get(expression.query_id, []),
                    start=1,
                ):
                    key = candidate.key
                    rank = candidate.handle.fused_rank or fallback_rank
                    existing = group_metadata.get(key)
                    if (
                        existing is None
                        or candidate.handle.fused_score > existing.handle.fused_score
                    ):
                        group_metadata[key] = candidate
                    group_scores[key] = max(
                        group_scores.get(key, 0.0),
                        1.0 / (60.0 + rank),
                    )
                    group_best_rank[key] = min(
                        group_best_rank.get(key, rank),
                        rank,
                    )
                    group_query_ids[key] = list(
                        dict.fromkeys(
                            [
                                *group_query_ids.get(key, []),
                                expression.query_id,
                            ]
                        )
                    )
                    group_handles.setdefault(key, {})[
                        expression.query_id
                    ] = candidate.handle
                    group_spans.setdefault(key, set()).update(
                        span
                        for signal in candidate.handle.signals
                        for span in signal.matched_spans
                        if len(span) == 2 and span[0] < span[1]
                    )
            ordered_group_keys = sorted(
                group_metadata,
                key=lambda key: (
                    -group_scores.get(key, 0.0),
                    group_best_rank.get(key, 0),
                    -group_metadata[key].handle.fused_score,
                    key,
                ),
            )
            eligible_group_count = len(ordered_group_keys)
            ordered_group_keys = ordered_group_keys[
                :BM25_RESULT_WINDOW_PER_GROUP
            ]
            group_items = tuple(
                QueryBatchCandidate(
                    vault=group_metadata[key].vault,
                    handle=group_metadata[key].handle,
                    query_ids=tuple(group_query_ids.get(key, [])),
                    handles_by_query=tuple(group_handles.get(key, {}).items()),
                    reciprocal_rank_score=group_scores.get(key, 0.0),
                    best_rank=group_best_rank.get(key, 0),
                    matched_spans=tuple(
                        sorted(group_spans.get(key, set()))
                    ),
                )
                for key in ordered_group_keys
            )
            group_candidate_lists[group_id] = group_items
            group_results.append(
                {
                    "group_id": group_id,
                    "region_id": group_expressions[0].region_id,
                    "query_ids": [
                        expression.query_id
                        for expression in group_expressions
                    ],
                    "candidate_count": len(group_items),
                    "eligible_candidate_count": eligible_group_count,
                    "result_window": BM25_RESULT_WINDOW_PER_GROUP,
                }
            )

        candidate_metadata: dict[tuple[str, str], QueryBatchCandidate] = {}
        candidate_scores: dict[tuple[str, str], float] = {}
        candidate_best_rank: dict[tuple[str, str], int] = {}
        candidate_query_ids: dict[tuple[str, str], list[str]] = {}
        candidate_handles_by_query: dict[
            tuple[str, str],
            dict[str, EvidenceHandle],
        ] = {}
        matched_spans: dict[tuple[str, str], set[tuple[int, int]]] = {}
        for group_items in group_candidate_lists.values():
            for group_rank, candidate in enumerate(group_items, start=1):
                key = candidate.key
                existing = candidate_metadata.get(key)
                if (
                    existing is None
                    or candidate.handle.fused_score > existing.handle.fused_score
                ):
                    candidate_metadata[key] = candidate
                candidate_scores[key] = (
                    candidate_scores.get(key, 0.0)
                    + 1.0 / (60.0 + group_rank)
                )
                candidate_best_rank[key] = min(
                    candidate_best_rank.get(key, group_rank),
                    group_rank,
                )
                candidate_query_ids[key] = list(
                    dict.fromkeys(
                        [
                            *candidate_query_ids.get(key, []),
                            *candidate.query_ids,
                        ]
                    )
                )
                candidate_handles_by_query.setdefault(key, {}).update(
                    dict(candidate.handles_by_query)
                )
                matched_spans.setdefault(key, set()).update(
                    candidate.matched_spans
                )

        ordered_keys = sorted(
            candidate_metadata,
            key=lambda key: (
                -candidate_scores.get(key, 0.0),
                candidate_best_rank.get(key, 0),
                -candidate_metadata[key].handle.fused_score,
                key,
            ),
        )
        global_eligible_candidate_count = len(ordered_keys)
        ordered_keys = ordered_keys[:BM25_GLOBAL_RESULT_WINDOW]
        candidate_items = tuple(
            QueryBatchCandidate(
                vault=candidate_metadata[key].vault,
                handle=candidate_metadata[key].handle,
                query_ids=tuple(candidate_query_ids.get(key, [])),
                handles_by_query=tuple(
                    candidate_handles_by_query.get(key, {}).items()
                ),
                reciprocal_rank_score=candidate_scores.get(key, 0.0),
                best_rank=candidate_best_rank.get(key, 0),
                matched_spans=tuple(sorted(matched_spans.get(key, set()))),
            )
            for key in ordered_keys
        )
        candidate_set = QueryBatchCandidateSet(
            items=candidate_items,
            structural_decisions={},
        )
        selected = _select_candidates(candidate_set)
        structural_decisions = _explain_candidates(candidate_set)
        structural_decisions.update(
            {
                candidate.key: reasons
                for candidate, reasons in selected
            }
        )
        candidate_set = QueryBatchCandidateSet(
            items=candidate_items,
            structural_decisions=structural_decisions,
        )
        selected_by_key = {
            candidate.key: (candidate, reasons)
            for candidate, reasons in selected
        }
        selected = tuple(
            selected_by_key[candidate.key]
            for candidate in candidate_items
            if candidate.key in selected_by_key
        )
        selected_keys = [
            candidate.key
            for candidate, _reasons in selected
        ]
        raw_read_started = time.perf_counter()
        found: dict[tuple[str, str], EvidenceRead] = {}
        if selected_keys:
            for vault in request.vaults:
                vault_scope = _vault_scope(vault)
                requested_ids = [
                    evidence_id
                    for scope, evidence_id in selected_keys
                    if scope == vault_scope
                ]
                if not requested_ids:
                    continue
                reads, read_warnings = read_evidence_handles(
                    vault.path,
                    requested_ids,
                    raise_if_cancelled=request.raise_if_cancelled,
                    snapshot=snapshots.get(vault_scope),
                )
                warnings.extend(read_warnings)
                for read in reads:
                    found[(vault_scope, read.handle.evidence_id)] = read
        raw_read_elapsed_ms = (time.perf_counter() - raw_read_started) * 1000
        missing = [key for key in selected_keys if key not in found]
        if missing:
            labels = ", ".join(f"{scope}:{evidence_id}" for scope, evidence_id in missing)
            raise UserInputError(f"Unknown or inactive evidence handles after active resolution: {labels}")

        evidence = tuple(
            QueryBatchEvidence(
                vault=candidate.vault,
                read=found[candidate.key],
                query_ids=candidate.query_ids,
                matched_spans=candidate.matched_spans,
                segments=build_evidence_segments(
                    found[candidate.key].raw_evidence,
                    candidate.matched_spans,
                ),
                selection_reasons=reasons,
            )
            for candidate, reasons in selected
        )
        evidence_set = QueryBatchEvidenceSet(
            items=evidence,
            selection_reasons={
                item.read.handle.evidence_id: item.selection_reasons
                for item in evidence
            },
        )
        status = _batch_status(
            terminal_statuses,
            has_evidence=bool(evidence),
        )
        return QueryBatchResult(
            status=status,
            expressions=expressions,
            query_results=tuple(query_results),
            group_results=tuple(group_results),
            candidate_set=candidate_set,
            global_eligible_candidate_count=global_eligible_candidate_count,
            global_result_window=BM25_GLOBAL_RESULT_WINDOW,
            evidence_set=evidence_set,
            search_elapsed_ms=search_elapsed_ms,
            raw_read_rounds=1 if selected_keys else 0,
            raw_read_count=len(selected_keys),
            raw_read_elapsed_ms=round(raw_read_elapsed_ms, 3),
            batch_elapsed_ms=round((time.perf_counter() - batch_started) * 1000, 3),
            warnings=tuple(dict.fromkeys(warnings)),
        )


def build_evidence_segments(
    raw: RawEvidenceRecord,
    matched_spans: tuple[tuple[int, int], ...],
) -> tuple[QueryEvidenceSegment, ...]:
    """Project matched windows to complete local structures without losing offsets."""

    content = raw.content or raw.excerpt
    unit_start = raw.char_start or 0
    local_spans = [
        (start - unit_start, end - unit_start)
        for start, end in matched_spans
        if 0 <= start - unit_start < end - unit_start <= len(content)
    ]
    if not local_spans:
        return (
            QueryEvidenceSegment(
                text=content,
                char_start=unit_start,
                char_end=unit_start + len(content),
            ),
        )

    expanded = [
        _expand_structural_range(content, start, end)
        for start, end in local_spans
    ]
    merged: list[tuple[int, int]] = []
    for start, end in sorted(set(expanded)):
        if merged and _ranges_touch(content, merged[-1][1], start):
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return tuple(
        QueryEvidenceSegment(
            text=content[start:end],
            char_start=unit_start + start,
            char_end=unit_start + end,
        )
        for start, end in merged
        if content[start:end].strip()
    )


def _expand_structural_range(
    content: str,
    start: int,
    end: int,
) -> tuple[int, int]:
    block_start = content.rfind("\n\n", 0, start)
    block_start = 0 if block_start < 0 else block_start + 2
    block_end = content.find("\n\n", end)
    block_end = len(content) if block_end < 0 else block_end
    block = content[block_start:block_end]
    if _requires_complete_block(block):
        return _trim_range(content, block_start, block_end)

    sentence_start = max(
        content.rfind(marker, block_start, start)
        for marker in ("\n", "。", "！", "？", ". ", "! ", "? ")
    )
    sentence_start = block_start if sentence_start < block_start else sentence_start + 1
    sentence_ends = [
        position
        for marker in ("。", "！", "？", ".", "!", "?", "\n")
        if (position := content.find(marker, end, block_end)) >= 0
    ]
    sentence_end = min(sentence_ends) + 1 if sentence_ends else block_end
    return _trim_range(content, sentence_start, sentence_end)


def _requires_complete_block(block: str) -> bool:
    stripped_lines = [
        line.strip()
        for line in block.splitlines()
        if line.strip()
    ]
    return (
        "```" in block
        or bool(stripped_lines)
        and (
            all(line.startswith("|") for line in stripped_lines)
            or all(
                line.startswith(("- ", "* ", "+ "))
                or (
                    len(line.split(".", 1)) == 2
                    and line.split(".", 1)[0].isdigit()
                )
                for line in stripped_lines
            )
        )
    )


def _trim_range(content: str, start: int, end: int) -> tuple[int, int]:
    while start < end and content[start].isspace():
        start += 1
    while end > start and content[end - 1].isspace():
        end -= 1
    return start, end


def _ranges_touch(content: str, previous_end: int, next_start: int) -> bool:
    return next_start <= previous_end or not content[previous_end:next_start].strip()


def _select_candidates(
    candidate_set: QueryBatchCandidateSet,
) -> tuple[tuple[QueryBatchCandidate, tuple[str, ...]], ...]:
    by_key = {item.key: item for item in candidate_set.items}
    decisions = select_structural_evidence(
        tuple(
            EvidenceSelectionCandidate(
                key=item.key,
                handle=item.handle,
                query_ids=item.query_ids,
                handles_by_query=item.handles_by_query,
            )
            for item in candidate_set.items
        ),
    )
    return tuple((by_key[decision.key], decision.reasons) for decision in decisions)


def _explain_candidates(
    candidate_set: QueryBatchCandidateSet,
) -> dict[tuple[str, str], tuple[str, ...]]:
    return {
        key: reasons
        for key, reasons in explain_structural_evidence(
            tuple(
                EvidenceSelectionCandidate(
                    key=item.key,
                    handle=item.handle,
                    query_ids=item.query_ids,
                    handles_by_query=item.handles_by_query,
                )
                for item in candidate_set.items
            ),
        ).items()
        if isinstance(key, tuple) and len(key) == 2
    }


def _normalize_expressions(
    expressions: tuple[QueryBatchExpression, ...],
) -> tuple[QueryBatchExpression, ...]:
    output: list[QueryBatchExpression] = []
    seen: set[tuple[str, str, str]] = set()
    for index, expression in enumerate(expressions, start=1):
        query = expression.query.strip()
        normalized = " ".join(query.casefold().split())
        region_id = str(expression.region_id or "").strip()
        group_id = str(expression.group_id or "").strip()
        key = (normalized, region_id, group_id)
        if not query or key in seen:
            continue
        seen.add(key)
        output.append(
            QueryBatchExpression(
                query_id=expression.query_id.strip() or f"q{index}",
                query=query,
                region_id=region_id or None,
                group_id=group_id or None,
            )
        )
    return tuple(output)


def _navigation_scopes(
    vaults: tuple[ResolvedVault, ...],
    expressions: tuple[QueryBatchExpression, ...],
) -> dict[tuple[str, str], NavigationRegionScope | None]:
    output: dict[tuple[str, str], NavigationRegionScope | None] = {}
    scoped_expressions = tuple(
        expression
        for expression in expressions
        if expression.region_id
    )
    for vault in vaults:
        resolved = resolve_navigation_region_scopes(
            vault,
            (
                expression.region_id
                for expression in scoped_expressions
                if expression.region_id is not None
            ),
        )
        for expression in scoped_expressions:
            scope = resolved.get(str(expression.region_id))
            output[(expression.query_id, _vault_scope(vault))] = scope
    return output


def _candidate_matches_navigation_scope(
    handle: EvidenceHandle,
    *,
    query_id: str,
    vault: ResolvedVault,
    scopes: dict[tuple[str, str], NavigationRegionScope | None],
) -> bool:
    key = (query_id, _vault_scope(vault))
    if key not in scopes:
        return True
    scope = scopes[key]
    if scope is None:
        return False
    return (
        handle.source_record_id in scope.source_record_ids
        and handle.raw_identity.source_unit_id in scope.source_unit_ids
    )


def _vault_scope(vault: ResolvedVault) -> str:
    return str(vault.vault_id or vault.path.expanduser().resolve())


def _outcome(vault: ResolvedVault, result: QueryPipelineResult) -> dict[str, object]:
    return {
        "vault_id": vault.vault_id,
        "status": result.status,
        "channel_statuses": [item.__dict__ for item in result.channel_statuses],
        "gaps": result.gaps,
        "warnings": result.warnings,
        "exhausted": result.exhausted,
        "continuation_cursor": result.continuation_cursor,
        "query_fingerprint": result.query_fingerprint,
        "snapshot_generation": result.snapshot_generation,
    }


def _expression_status(results: list[QueryPipelineResult]) -> QueryStatus:
    statuses = [item.status for item in results]
    for status in (
        "cancelled",
        "resource_exhausted",
        "integrity_error",
        "index_unavailable",
        "invalid_scope",
        "invalid_query",
    ):
        if status in statuses:
            return status
    if "candidates" in statuses:
        return "candidates"
    if statuses and all(item == "no_match" for item in statuses) and all(
        _outcome_exhausted(item) for item in results
    ):
        return "no_match"
    if statuses and all(item == "no_match" for item in statuses):
        return "resource_exhausted"
    return "integrity_error"


def _outcome_exhausted(result: QueryPipelineResult) -> bool:
    if not result.exhausted:
        return False
    required = {"atom_claim", "raw_lexical"}
    completed = {
        item.channel
        for item in result.channel_statuses
        if item.status in {"completed", "no_candidates"} and item.exhausted
    }
    return required.issubset(completed)


def _batch_status(
    statuses: list[QueryStatus],
    *,
    has_evidence: bool,
) -> QueryStatus:
    literal_status = statuses[0] if statuses else "integrity_error"
    if literal_status not in {"candidates", "no_match"}:
        return literal_status
    if has_evidence:
        return "candidates"
    if statuses and all(
        item in {"candidates", "no_match"}
        for item in statuses
    ):
        return "no_match"
    for status in (
        "cancelled",
        "resource_exhausted",
        "integrity_error",
        "index_unavailable",
        "invalid_scope",
        "invalid_query",
    ):
        if status in statuses:
            return status
    return "integrity_error"
