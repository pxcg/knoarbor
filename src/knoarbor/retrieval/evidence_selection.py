from __future__ import annotations

from dataclasses import dataclass
from typing import Hashable, Protocol


class EvidenceSignal(Protocol):
    channel: str
    matched_spans: tuple[tuple[int, int], ...]


class EvidenceHandle(Protocol):
    signals: tuple[EvidenceSignal, ...]


@dataclass(frozen=True)
class EvidenceSelectionCandidate:
    key: Hashable
    handle: EvidenceHandle
    query_ids: tuple[str, ...]
    handles_by_query: tuple[tuple[str, EvidenceHandle], ...] = ()


@dataclass(frozen=True)
class EvidenceSelectionDecision:
    key: Hashable
    reasons: tuple[str, ...]


def select_structural_evidence(
    candidates: tuple[EvidenceSelectionCandidate, ...],
) -> tuple[EvidenceSelectionDecision, ...]:
    """Select every candidate backed by an exact locator or claim span.

    Search providers own lexical eligibility. This boundary validates only the
    structural Raw-evidence contract; it never estimates semantic relevance or
    completeness and never assigns membership authority to rank.
    """

    selected: list[EvidenceSelectionDecision] = []
    for candidate in candidates:
        traces = _candidate_traces(candidate)
        if not traces:
            continue
        selected.append(
            EvidenceSelectionDecision(
                key=candidate.key,
                reasons=tuple(traces),
            )
        )
    return tuple(selected)


def explain_structural_evidence(
    candidates: tuple[EvidenceSelectionCandidate, ...],
) -> dict[Hashable, tuple[str, ...]]:
    output: dict[Hashable, tuple[str, ...]] = {}
    for candidate in candidates:
        traces = _candidate_traces(candidate)
        output[candidate.key] = (
            tuple(traces)
            if traces
            else ("structural_evidence.v1:decision=rejected:reason=no_exact_span",)
        )
    return output


def _candidate_traces(
    candidate: EvidenceSelectionCandidate,
) -> list[str]:
    handles = (
        candidate.handles_by_query
        or tuple((query_id, candidate.handle) for query_id in candidate.query_ids)
    )
    traces: list[str] = []
    for query_id, handle in handles:
        channels = sorted(
            {
                signal.channel
                for signal in handle.signals
                if _valid_spans(signal.matched_spans)
            }
        )
        span_count = sum(
            len(_valid_spans(signal.matched_spans))
            for signal in handle.signals
        )
        if not channels or span_count == 0:
            continue
        traces.append(
            "structural_evidence.v1:"
            f"decision=selected:query={query_id}:"
            f"channels={','.join(channels)}:spans={span_count}"
        )
    return list(dict.fromkeys(traces))


def _valid_spans(
    spans: tuple[tuple[int, int], ...],
) -> tuple[tuple[int, int], ...]:
    return tuple(
        (start, end)
        for start, end in spans
        if isinstance(start, int)
        and isinstance(end, int)
        and 0 <= start < end
    )
