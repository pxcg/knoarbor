from __future__ import annotations

import base64
from dataclasses import dataclass, field, replace
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Callable, Literal

from knoarbor.retrieval.evidence_selection import (
    EvidenceSelectionCandidate,
    select_structural_evidence,
)
from knoarbor.retrieval.query_text import normalize_text, query_terms
from knoarbor.runtime.run_monitor import RunCancelled
from knoarbor.runtime.transactional_ingest import TransactionalIngestStore
from knoarbor.storage.index_snapshot import IndexSnapshot, open_index_snapshot
from knoarbor.storage.knowledge_atom_index import KnowledgeAtomRecord
from knoarbor.storage.lexical_snapshot import (
    LexicalMatch,
    RetrievalSafety,
    RetrievalSafetyExceeded,
    read_atom_batch_documents,
    read_raw_locator_metadata_by_evidence_ids,
    search_lexical_snapshot,
)
from knoarbor.storage.source_records import RawEvidenceRecord, raw_evidence_records_from_processing_record
from knoarbor.storage.source_revisions import read_revision_processing_record
from knoarbor.storage.vault_identity import vault_identity_path
from knoarbor.storage.vault_layout import runtime_index_root


QueryStatus = Literal[
    "candidates",
    "no_match",
    "index_unavailable",
    "integrity_error",
    "invalid_query",
    "invalid_scope",
    "resource_exhausted",
    "cancelled",
]
ChannelState = Literal["completed", "no_candidates", "unavailable", "error", "cancelled", "resource_exhausted"]
RecallChannel = Literal[
    "atom_claim",
    "raw_lexical",
]


@dataclass(frozen=True)
class RawIdentity:
    vault_id: str
    raw_revision_id: str
    source_unit_id: str


@dataclass(frozen=True)
class RecallSignal:
    channel: RecallChannel
    channel_rank: int
    channel_score: float
    matched_terms: tuple[str, ...] = ()
    claim_refs: tuple[str, ...] = ()
    locator_atom_refs: tuple[str, ...] = ()
    matched_spans: tuple[tuple[int, int], ...] = ()
    evidence_texts: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvidenceHandle:
    evidence_id: str
    raw_identity: RawIdentity
    raw_record_id: str
    revision_id: str
    processing_record_id: str
    source_record_id: str
    source_path: str
    title: str
    retrieval_generation_id: str
    active_fact_generation: str
    signals: tuple[RecallSignal, ...]
    fused_score: float
    fused_rank: int
    locator_page_paths: tuple[str, ...] = ()
    estimated_content_chars: int = 0
    content_hint: str = ""


@dataclass(frozen=True)
class EvidenceRead:
    handle: EvidenceHandle
    raw_evidence: RawEvidenceRecord


@dataclass(frozen=True)
class AtomCandidate:
    atom: KnowledgeAtomRecord
    atom_ref: str
    score: float
    rank: int
    matched_terms: tuple[str, ...] = ()


@dataclass(frozen=True)
class ClaimCandidate:
    claim: KnowledgeAtomRecord
    claim_ref: str
    score: float
    supporting_atom_refs: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    matched_terms: tuple[str, ...] = ()

    @property
    def supporting_atom_ids(self) -> list[str]:
        return list(self.supporting_atom_refs)


@dataclass(frozen=True)
class ChannelStatus:
    channel: RecallChannel
    status: ChannelState
    match_count: int
    exhausted: bool
    fts_hit_count: int = 0
    ineligible_hit_count: int = 0
    continuation_offset: int | None = None
    detail: str | None = None


@dataclass(frozen=True)
class RetrievalCursor:
    query_fingerprint: str
    vault_id: str
    retrieval_generation_id: str
    active_fact_generation: str
    channel: RecallChannel
    offset: int
    rank: int
    had_candidates: bool = False


@dataclass(frozen=True)
class QueryPlan:
    vault_path: Path
    query: str
    safety: RetrievalSafety = field(default_factory=RetrievalSafety.with_timeout)
    continuation_cursor: str | None = None
    resolve_evidence: bool = True
    source_record_ids: frozenset[str] | None = None
    source_unit_ids: frozenset[str] | None = None
    snapshot: IndexSnapshot | None = None


@dataclass(frozen=True)
class EvidenceCollection:
    status: QueryStatus
    handles: tuple[EvidenceHandle, ...]
    evidence_reads: tuple[EvidenceRead, ...]
    atom_candidates: tuple[AtomCandidate, ...]
    claim_candidates: tuple[ClaimCandidate, ...]
    channel_statuses: tuple[ChannelStatus, ...]
    warnings: tuple[str, ...]
    gaps: tuple[str, ...]
    stats: dict[str, object]
    exhausted: bool = True
    continuation_cursor: str | None = None
    query_fingerprint: str = ""
    snapshot_generation: str = ""


class UnifiedActiveRawRetriever:
    def retrieve(self, request: QueryPlan) -> EvidenceCollection:
        try:
            _raise_if_cancelled(request.safety)
        except RunCancelled:
            return _terminal("cancelled")
        vault = request.vault_path.expanduser().resolve()
        terms = query_terms(request.query)
        if not terms:
            return _terminal("invalid_query", gaps=("Query has no searchable terms.",))
        snapshot = request.snapshot
        if snapshot is None:
            try:
                snapshot = open_index_snapshot(
                    vault,
                    raise_if_cancelled=request.safety.raise_if_cancelled,
                )
            except RunCancelled:
                return _terminal("cancelled")
            except RuntimeError as exc:
                return _terminal("index_unavailable", warnings=(str(exc),))
        elif snapshot.path.parent != runtime_index_root(vault) / "generations":
            return _terminal(
                "index_unavailable",
                warnings=("Prepared retrieval snapshot belongs to another vault.",),
            )
        if snapshot is None:
            return _terminal("index_unavailable", warnings=("No verified lexical retrieval snapshot is published.",))

        vault_id = _read_vault_id(vault)
        query_fingerprint = _query_fingerprint(
            request.query,
            vault_id,
            source_record_ids=request.source_record_ids,
            source_unit_ids=request.source_unit_ids,
        )
        cursor: RetrievalCursor | None = None
        if request.continuation_cursor:
            try:
                cursor = _decode_cursor(request.continuation_cursor)
            except ValueError as exc:
                return _terminal(
                    "invalid_query",
                    warnings=(f"invalid_retrieval_cursor:{exc}",),
                    query_fingerprint=query_fingerprint,
                    snapshot_generation=snapshot.retrieval_generation_id,
                )
            if cursor.query_fingerprint != query_fingerprint:
                return _terminal(
                    "invalid_query",
                    warnings=("retrieval_cursor_query_mismatch",),
                    query_fingerprint=query_fingerprint,
                    snapshot_generation=snapshot.retrieval_generation_id,
                )
            if cursor.vault_id != vault_id:
                return _terminal(
                    "invalid_scope",
                    warnings=("retrieval_cursor_vault_mismatch",),
                    query_fingerprint=query_fingerprint,
                    snapshot_generation=snapshot.retrieval_generation_id,
                )
            if (
                cursor.retrieval_generation_id != snapshot.retrieval_generation_id
                or cursor.active_fact_generation != snapshot.active_fact_generation
            ):
                return _terminal(
                    "index_unavailable",
                    warnings=("retrieval_cursor_generation_mismatch",),
                    query_fingerprint=query_fingerprint,
                    snapshot_generation=snapshot.retrieval_generation_id,
                )

        store = TransactionalIngestStore(vault)
        state = store.materialization_state()
        current_fact_generation = str(state.get("requested_fact_generation") or "")
        if current_fact_generation != snapshot.active_fact_generation:
            return _terminal(
                "index_unavailable",
                warnings=("Published lexical retrieval snapshot does not match active facts.",),
                stats={
                    "retrieval_generation_id": snapshot.retrieval_generation_id,
                    "snapshot_fact_generation": snapshot.active_fact_generation,
                    "active_fact_generation": current_fact_generation,
                },
            )

        matches: dict[str, list[LexicalMatch]] = {"atom_claim": [], "raw_lexical": []}
        lexical_counts: dict[str, tuple[int, int]] = {"atom_claim": (0, 0), "raw_lexical": (0, 0)}
        statuses: list[ChannelStatus] = []

        channels: tuple[RecallChannel, ...] = ("atom_claim", "raw_lexical")
        if cursor is not None and cursor.channel not in channels:
            return _terminal(
                "invalid_query",
                warnings=("retrieval_cursor_channel_not_required",),
                query_fingerprint=query_fingerprint,
                snapshot_generation=snapshot.retrieval_generation_id,
            )
        start_index = (
            channels.index(cursor.channel)
            if cursor is not None
            else 0
        )
        for completed_channel in channels[:start_index]:
            statuses.append(
                ChannelStatus(
                    channel=completed_channel,
                    status="completed",
                    match_count=0,
                    exhausted=True,
                    detail="completed_before_continuation",
                )
            )
        safety_exceeded: tuple[
            RecallChannel,
            RetrievalSafetyExceeded,
        ] | None = None
        for channel in channels[start_index:]:
            offset = (
                cursor.offset
                if cursor is not None
                and cursor.channel == channel
                else 0
            )
            rank_offset = (
                cursor.rank
                if cursor is not None
                and cursor.channel == channel
                else 0
            )
            try:
                _raise_if_cancelled(request.safety)
                search_result = search_lexical_snapshot(
                    snapshot.retrieval_path,
                    request.query,
                    channel=channel,
                    safety=request.safety,
                    offset=offset,
                    rank_offset=rank_offset,
                    source_record_ids=request.source_record_ids,
                    source_unit_ids=request.source_unit_ids,
                )
                channel_matches = list(search_result.matches)
            except RunCancelled:
                statuses.append(ChannelStatus(channel=channel, status="cancelled", match_count=0, exhausted=False))
                return _terminal("cancelled", channel_statuses=tuple(statuses))
            except RetrievalSafetyExceeded as exc:
                channel_matches = list(exc.partial_matches)
                matches[channel] = channel_matches
                statuses.append(
                    ChannelStatus(
                        channel=channel,
                        status="resource_exhausted",
                        match_count=len(exc.partial_matches),
                        exhausted=False,
                        continuation_offset=exc.continuation_offset,
                        detail=exc.reason,
                    )
                )
                safety_exceeded = (channel, exc)
                break
            except RuntimeError as exc:
                statuses.append(ChannelStatus(channel=channel, status="error", match_count=0, exhausted=False, detail=str(exc)))
                return _terminal(
                    "index_unavailable",
                    channel_statuses=tuple(statuses),
                    warnings=(str(exc),),
                    stats={"retrieval_generation_id": snapshot.retrieval_generation_id},
                )
            matches[channel] = channel_matches
            lexical_counts[channel] = (search_result.fts_hit_count, search_result.ineligible_hit_count)
            statuses.append(
                ChannelStatus(
                    channel=channel,
                    status="completed" if channel_matches else "no_candidates",
                    match_count=len(channel_matches),
                    exhausted=True,
                    fts_hit_count=search_result.fts_hit_count,
                    ineligible_hit_count=search_result.ineligible_hit_count,
                )
            )

        try:
            _raise_if_cancelled(request.safety)
        except RunCancelled:
            return _terminal("cancelled", channel_statuses=tuple(statuses))
        try:
            atom_candidates = _atom_candidates(matches["atom_claim"])
            claim_candidates = _resolve_claim_candidates(
                snapshot.retrieval_path,
                atom_candidates,
                raise_if_cancelled=request.safety.raise_if_cancelled,
            )
            handles = _fuse_handles(
                snapshot_path=snapshot.retrieval_path,
                vault_id=vault_id,
                atom_claims=claim_candidates,
                raw_matches=matches["raw_lexical"],
                retrieval_generation_id=snapshot.retrieval_generation_id,
                active_fact_generation=snapshot.active_fact_generation,
                raise_if_cancelled=request.safety.raise_if_cancelled,
            )
            selection_reasons: dict[str, tuple[str, ...]] = {}
            if request.resolve_evidence:
                decisions = select_structural_evidence(
                    tuple(
                        EvidenceSelectionCandidate(
                            key=handle.evidence_id,
                            handle=handle,
                            query_ids=("query",),
                            handles_by_query=(("query", handle),),
                        )
                        for handle in handles
                    ),
                )
                handles_by_id = {
                    handle.evidence_id: handle for handle in handles
                }
                selected_handles = tuple(
                    handles_by_id[str(decision.key)]
                    for decision in decisions
                )
                selection_reasons = {
                    str(decision.key): decision.reasons
                    for decision in decisions
                }
                reads, integrity_warnings = _resolve_active_evidence(
                    vault,
                    selected_handles,
                    raise_if_cancelled=request.safety.raise_if_cancelled,
                )
            else:
                reads = []
                integrity_warnings = []
        except RunCancelled:
            return _terminal("cancelled", channel_statuses=tuple(statuses))
        if safety_exceeded is not None:
            status: QueryStatus = "resource_exhausted"
        elif integrity_warnings and not reads and handles and request.resolve_evidence:
            status: QueryStatus = "integrity_error"
        elif request.resolve_evidence:
            status = "candidates" if reads else "no_match"
        elif handles or (cursor is not None and cursor.had_candidates):
            status = "candidates"
        else:
            status = "no_match"
        has_usable_result = bool(reads) if request.resolve_evidence else bool(handles)
        gaps = (
            ()
            if has_usable_result or status == "resource_exhausted"
            else (
                "No eligible active Raw evidence matched the completed query plan.",
            )
        )
        continuation_cursor = None
        safety_stats: dict[str, object] = {}
        if safety_exceeded is not None:
            channel, exc = safety_exceeded
            base_offset = (
                cursor.offset
                if cursor is not None and cursor.channel == channel
                else 0
            )
            base_rank = (
                cursor.rank
                if cursor is not None and cursor.channel == channel
                else 0
            )
            if (
                exc.continuation_offset > base_offset
                or exc.continuation_rank > base_rank
            ):
                continuation_cursor = _encode_cursor(
                    RetrievalCursor(
                        query_fingerprint=query_fingerprint,
                        vault_id=vault_id,
                        retrieval_generation_id=snapshot.retrieval_generation_id,
                        active_fact_generation=snapshot.active_fact_generation,
                        channel=channel,
                        offset=exc.continuation_offset,
                        rank=exc.continuation_rank,
                        had_candidates=bool(handles)
                        or bool(cursor and cursor.had_candidates),
                    )
                )
            safety_stats = {
                "partial_match_count": len(exc.partial_matches),
                "continuation_rank": exc.continuation_rank,
            }
        return EvidenceCollection(
            status=status,
            handles=handles,
            evidence_reads=tuple(reads),
            atom_candidates=tuple(atom_candidates),
            claim_candidates=tuple(claim_candidates),
            channel_statuses=tuple(statuses),
            warnings=tuple([
                *integrity_warnings,
                *(
                    [f"retrieval_safety:{safety_exceeded[0]}:{safety_exceeded[1].reason}"]
                    if safety_exceeded is not None
                    else []
                ),
            ]),
            gaps=gaps,
            stats={
                "retrieval_strategy": "unified_active_raw_lexical_v1",
                "scoring_model": "fts5_bm25_weighted_rrf",
                "retrieval_generation_id": snapshot.retrieval_generation_id,
                "active_fact_generation": snapshot.active_fact_generation,
                "atom_match_count": len(atom_candidates),
                "claim_candidate_count": len(claim_candidates),
                "raw_window_match_count": len(matches["raw_lexical"]),
                "atom_fts_hit_count": lexical_counts["atom_claim"][0],
                "atom_ineligible_hit_count": lexical_counts["atom_claim"][1],
                "raw_fts_hit_count": lexical_counts["raw_lexical"][0],
                "raw_ineligible_hit_count": lexical_counts["raw_lexical"][1],
                "evidence_handle_count": len(handles),
                "evidence_selected_count": len(reads),
                "evidence_selection_reasons": {
                    evidence_id: list(reasons)
                    for evidence_id, reasons in selection_reasons.items()
                },
                "query_terms": terms,
                **safety_stats,
            },
            exhausted=safety_exceeded is None,
            continuation_cursor=continuation_cursor,
            query_fingerprint=query_fingerprint,
            snapshot_generation=snapshot.retrieval_generation_id,
        )


def _atom_candidates(matches: list[LexicalMatch]) -> list[AtomCandidate]:
    output: list[AtomCandidate] = []
    for match in matches:
        atom = KnowledgeAtomRecord.model_validate(match.metadata)
        output.append(
            AtomCandidate(
                atom=atom,
                atom_ref=_atom_ref(atom),
                score=match.score,
                rank=match.rank,
                matched_terms=tuple(match.matched_terms),
            )
        )
    return output


def _resolve_claim_candidates(
    snapshot_path: Path,
    matches: list[AtomCandidate],
    *,
    raise_if_cancelled: Callable[[], None] | None = None,
) -> list[ClaimCandidate]:
    claim_cache: dict[
        tuple[str, str],
        tuple[
            dict[str, KnowledgeAtomRecord],
            dict[str, tuple[KnowledgeAtomRecord, ...]],
        ],
    ] = {}
    accumulated: dict[str, dict[str, Any]] = {}
    for match in matches:
        if raise_if_cancelled is not None:
            raise_if_cancelled()
        atom = match.atom
        if atom.atom_type == "claim":
            _add_claim(accumulated, atom, match, "direct_claim")
            continue

        batch_key = (atom.revision_id or "", atom.source_record_id)
        cached = claim_cache.get(batch_key)
        if cached is None:
            claims = {
                item.atom_id: item
                for item in (
                    KnowledgeAtomRecord.model_validate(payload)
                    for payload in read_atom_batch_documents(
                        snapshot_path,
                        revision_id=batch_key[0],
                        source_record_id=batch_key[1],
                    )
                )
                if item.atom_type == "claim"
            }
            claims_by_entity: dict[
                str,
                list[KnowledgeAtomRecord],
            ] = {}
            for claim in claims.values():
                for value in [
                    *_strings(claim.payload.get("entity_ids")),
                    *_strings(claim.payload.get("entity_names")),
                ]:
                    claims_by_entity.setdefault(_key(value), []).append(
                        claim
                    )
            cached = (
                claims,
                {
                    key: tuple(value)
                    for key, value in claims_by_entity.items()
                },
            )
            claim_cache[batch_key] = cached
        claims, claims_by_entity = cached

        if atom.atom_type == "entity":
            keys = {
                _key(atom.atom_id),
                _key(atom.text),
                *(
                    _key(item)
                    for item in _strings(atom.payload.get("aliases"))
                ),
            }
            related_claims = {
                claim.atom_id: claim
                for key in keys
                for claim in claims_by_entity.get(key, ())
            }
            for claim in related_claims.values():
                _add_claim(
                    accumulated,
                    claim,
                    match,
                    "entity_reference",
                )
        elif atom.atom_type == "relation":
            for local_claim_id in _strings(atom.payload.get("source_claim_ids")):
                claim = claims.get(local_claim_id)
                if claim is not None:
                    _add_claim(accumulated, claim, match, "relation_source_claim")
    output = [
        ClaimCandidate(
            claim=item["claim"],
            claim_ref=claim_ref,
            score=float(item["score"]),
            supporting_atom_refs=tuple(item["atom_refs"]),
            reasons=tuple(item["reasons"]),
            matched_terms=tuple(item["matched_terms"]),
        )
        for claim_ref, item in accumulated.items()
    ]
    output.sort(key=lambda item: (-item.score, item.claim_ref))
    return output


def _add_claim(accumulated: dict[str, dict[str, Any]], claim: KnowledgeAtomRecord, match: AtomCandidate, reason: str) -> None:
    claim_ref = _atom_ref(claim)
    item = accumulated.setdefault(
        claim_ref,
        {
            "claim": claim,
            "score": 0.0,
            "atom_refs": [],
            "reasons": [],
            "matched_terms": [],
        },
    )
    item["score"] = max(float(item["score"]), match.score)
    if match.atom_ref not in item["atom_refs"]:
        item["atom_refs"].append(match.atom_ref)
    if reason not in item["reasons"]:
        item["reasons"].append(reason)
    _extend_unique(item["matched_terms"], list(match.matched_terms))


def _fuse_handles(
    *,
    snapshot_path: Path,
    vault_id: str,
    atom_claims: list[ClaimCandidate],
    raw_matches: list[LexicalMatch],
    retrieval_generation_id: str,
    active_fact_generation: str,
    raise_if_cancelled: Callable[[], None] | None = None,
) -> tuple[EvidenceHandle, ...]:
    accumulated: dict[tuple[str, str], dict[str, Any]] = {}
    for rank, candidate in enumerate(atom_claims, start=1):
        if raise_if_cancelled is not None:
            raise_if_cancelled()
        claim = candidate.claim
        for source_unit_id in claim.source_unit_ids:
            key = (claim.raw_revision_id or "", source_unit_id)
            if not all(key):
                continue
            item = accumulated.setdefault(key, _handle_seed(claim.model_dump(mode="json")))
            signal = RecallSignal(
                channel="atom_claim",
                channel_rank=rank,
                channel_score=candidate.score,
                matched_terms=candidate.matched_terms,
                claim_refs=(candidate.claim_ref,),
                locator_atom_refs=candidate.supporting_atom_refs,
                matched_spans=_claim_spans_for_unit(claim, source_unit_id),
                evidence_texts=_claim_texts_for_unit(
                    claim,
                    source_unit_id,
                ),
            )
            if signal not in item["signals"]:
                item["signals"].append(signal)
            _extend_unique(item["page_paths"], claim.page_paths)
    for match in raw_matches:
        if raise_if_cancelled is not None:
            raise_if_cancelled()
        metadata = match.metadata
        key = (str(metadata.get("raw_revision_id") or ""), str(metadata.get("source_unit_id") or ""))
        if not all(key):
            continue
        item = accumulated.setdefault(key, _handle_seed(metadata))
        for metadata_field in (
            "raw_record_id",
            "revision_id",
            "processing_record_id",
            "source_record_id",
            "source_path",
            "title",
        ):
            value = metadata.get(metadata_field)
            if value:
                item[metadata_field] = str(value)
        rerank_text = str(
            metadata.get("rerank_text")
            or metadata.get("text")
            or ""
        )
        if rerank_text:
            item["content_hint"] = rerank_text
        _extend_unique(
            item["page_paths"],
            list(
                metadata.get("page_paths")
                or metadata.get("locator_page_paths")
                or []
            ),
        )
        item["estimated_content_chars"] = max(
            int(item["estimated_content_chars"]),
            len(rerank_text),
        )
        unit_start = int(metadata.get("char_start") or 0)
        start = unit_start + int(metadata.get("window_char_start") or 0)
        end = unit_start + int(metadata.get("window_char_end") or int(metadata.get("window_char_start") or 0))
        signal = RecallSignal(
            channel="raw_lexical",
            channel_rank=match.rank,
            channel_score=match.score,
            matched_terms=tuple(match.matched_terms),
            matched_spans=((start, end),),
        )
        if signal not in item["signals"]:
            item["signals"].append(signal)

    _hydrate_handle_metadata(
        snapshot_path,
        vault_id=vault_id,
        accumulated=accumulated,
    )
    for item in accumulated.values():
        _infer_missing_signal_spans(item)
    ranked: list[tuple[float, tuple[str, str], dict[str, Any]]] = []
    for key, item in accumulated.items():
        if raise_if_cancelled is not None:
            raise_if_cancelled()
        score = _best_channel_rank_score(item["signals"])
        ranked.append((score, key, item))
    ranked.sort(key=lambda value: (-value[0], value[1]))
    output: list[EvidenceHandle] = []
    for rank, (score, key, item) in enumerate(ranked, start=1):
        output.append(
            EvidenceHandle(
                evidence_id="evh:" + _stable_hash(vault_id, key[0], key[1]),
                raw_identity=RawIdentity(vault_id=vault_id, raw_revision_id=key[0], source_unit_id=key[1]),
                raw_record_id=item["raw_record_id"],
                revision_id=item["revision_id"],
                processing_record_id=item["processing_record_id"],
                source_record_id=item["source_record_id"],
                source_path=item["source_path"],
                title=item["title"],
                retrieval_generation_id=retrieval_generation_id,
                active_fact_generation=active_fact_generation,
                signals=tuple(item["signals"]),
                fused_score=score,
                fused_rank=rank,
                locator_page_paths=tuple(item["page_paths"]),
                estimated_content_chars=int(item["estimated_content_chars"]),
                content_hint=item["content_hint"],
            )
        )
    return tuple(output)


def _best_channel_rank_score(signals: list[RecallSignal]) -> float:
    """Fuse independent channels without rewarding duplicate locator volume."""

    channel_weights = {
        "atom_claim": 1.2,
        "raw_lexical": 1.0,
    }
    best_ranks: dict[str, int] = {}
    for signal in signals:
        current = best_ranks.get(signal.channel)
        if current is None or signal.channel_rank < current:
            best_ranks[signal.channel] = signal.channel_rank
    ranked_scores = sorted((
        channel_weights[channel] / (20 + rank)
        for channel, rank in best_ranks.items()
        if channel in channel_weights
    ), reverse=True)
    if not ranked_scores:
        return 0.0
    return ranked_scores[0] + 0.1 * sum(ranked_scores[1:])


def _handle_seed(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "signals": [],
        "page_paths": list(metadata.get("page_paths") or metadata.get("locator_page_paths") or []),
        "raw_record_id": str(metadata.get("raw_record_id") or ""),
        "revision_id": str(metadata.get("revision_id") or ""),
        "processing_record_id": str(metadata.get("processing_record_id") or ""),
        "source_record_id": str(metadata.get("source_record_id") or ""),
        "source_path": str(metadata.get("source_path") or ""),
        "title": str(metadata.get("title") or ""),
        "content_hint": str(metadata.get("rerank_text") or metadata.get("text") or ""),
        "estimated_content_chars": len(str(metadata.get("rerank_text") or "")),
        "unit_char_start": int(metadata.get("char_start") or 0),
    }


def _hydrate_handle_metadata(
    snapshot_path: Path,
    *,
    vault_id: str,
    accumulated: dict[tuple[str, str], dict[str, Any]],
) -> None:
    """Hydrate every Claim/Graph parent independently from Raw lexical recall."""

    evidence_ids = [
        "evh:" + _stable_hash(vault_id, raw_revision_id, source_unit_id)
        for raw_revision_id, source_unit_id in accumulated
    ]
    metadata_items = read_raw_locator_metadata_by_evidence_ids(
        snapshot_path,
        evidence_ids,
    )
    by_identity = {
        (
            str(metadata.get("raw_revision_id") or ""),
            str(metadata.get("source_unit_id") or ""),
        ): metadata
        for metadata in metadata_items
    }
    for identity, item in accumulated.items():
        metadata = by_identity.get(identity)
        if metadata is None:
            continue
        for metadata_field in (
            "raw_record_id",
            "revision_id",
            "processing_record_id",
            "source_record_id",
            "source_path",
            "title",
        ):
            value = metadata.get(metadata_field)
            if value:
                item[metadata_field] = str(value)
        rerank_text = str(
            metadata.get("rerank_text")
            or metadata.get("text")
            or ""
        )
        if rerank_text:
            item["content_hint"] = rerank_text
            item["estimated_content_chars"] = max(
                int(item["estimated_content_chars"]),
                len(rerank_text),
            )
        item["unit_char_start"] = int(metadata.get("char_start") or 0)
        _extend_unique(
            item["page_paths"],
            list(
                metadata.get("page_paths")
                or metadata.get("locator_page_paths")
                or []
            ),
        )


def _infer_missing_signal_spans(item: dict[str, Any]) -> None:
    content = str(item.get("content_hint") or "")
    if not content:
        return
    unit_start = int(item.get("unit_char_start") or 0)
    signals: list[RecallSignal] = []
    for signal in item["signals"]:
        if signal.matched_spans or not signal.evidence_texts:
            signals.append(signal)
            continue
        spans: list[tuple[int, int]] = []
        for text in signal.evidence_texts:
            start = content.find(text)
            if start >= 0:
                spans.append(
                    (unit_start + start, unit_start + start + len(text))
                )
        signals.append(
            replace(
                signal,
                matched_spans=tuple(dict.fromkeys(spans)),
            )
        )
    item["signals"] = signals


def _resolve_active_evidence(
    vault: Path,
    handles: tuple[EvidenceHandle, ...],
    *,
    raise_if_cancelled: Callable[[], None] | None = None,
) -> tuple[list[EvidenceRead], list[str]]:
    store = TransactionalIngestStore(vault)
    active_revisions = {str(item["revision_id"]) for item in store.active_revision_manifests()}
    raw_by_revision: dict[str, dict[tuple[str, str], RawEvidenceRecord]] = {}
    reads: list[EvidenceRead] = []
    warnings: list[str] = []
    for handle in handles:
        if raise_if_cancelled is not None:
            raise_if_cancelled()
        if handle.revision_id not in active_revisions:
            warnings.append(f"stale_evidence_handle:{handle.evidence_id}")
            continue
        try:
            revision_units = raw_by_revision.get(handle.revision_id)
            if revision_units is None:
                processing_record = read_revision_processing_record(vault, handle.revision_id, store=store)
                revision_units = {
                    (raw.raw_revision_id, raw.source_unit_id): raw
                    for raw in raw_evidence_records_from_processing_record(processing_record)
                }
                raw_by_revision[handle.revision_id] = revision_units
            raw = revision_units.get(
                (handle.raw_identity.raw_revision_id, handle.raw_identity.source_unit_id)
            )
        except (RuntimeError, ValueError) as exc:
            warnings.append(f"evidence_integrity_error:{handle.evidence_id}:{exc}")
            continue
        if raw is None:
            warnings.append(f"evidence_integrity_error:{handle.evidence_id}:identity_mismatch")
            continue
        if (
            raw.raw_record_id != handle.raw_record_id
            or raw.raw_revision_id != handle.raw_identity.raw_revision_id
            or raw.source_unit_id != handle.raw_identity.source_unit_id
            or raw.revision_id != handle.revision_id
            or raw.processing_record_id != handle.processing_record_id
            or raw.source_record_id != handle.source_record_id
        ):
            warnings.append(f"evidence_integrity_error:{handle.evidence_id}:identity_mismatch")
            continue
        if not _claim_spans_valid(handle, raw):
            warnings.append(f"evidence_integrity_error:{handle.evidence_id}:span_mismatch")
            continue
        reads.append(EvidenceRead(handle=handle, raw_evidence=_project_matched_excerpt(handle, raw)))
    return reads, list(dict.fromkeys(warnings))


def read_evidence_handles(
    vault_path: Path,
    evidence_ids: list[str],
    *,
    raise_if_cancelled: Callable[[], None] | None = None,
    snapshot: IndexSnapshot | None = None,
) -> tuple[list[EvidenceRead], list[str]]:
    """Resolve disclosed stable handle IDs through the current snapshot and active facts."""

    if raise_if_cancelled is not None:
        raise_if_cancelled()
    vault = vault_path.expanduser().resolve()
    if (
        snapshot is not None
        and snapshot.path.parent
        != runtime_index_root(vault) / "generations"
    ):
        raise RuntimeError(
            "Prepared retrieval snapshot belongs to another vault."
        )
    snapshot = snapshot or open_index_snapshot(vault)
    if snapshot is None:
        raise RuntimeError("No verified lexical retrieval snapshot is published.")
    state = TransactionalIngestStore(vault).materialization_state()
    if str(state.get("requested_fact_generation") or "") != snapshot.active_fact_generation:
        raise RuntimeError("Published lexical retrieval snapshot does not match active facts.")
    metadata_items = read_raw_locator_metadata_by_evidence_ids(snapshot.retrieval_path, evidence_ids)
    by_id = {str(item.get("evidence_id") or ""): item for item in metadata_items}
    missing = [evidence_id for evidence_id in evidence_ids if evidence_id not in by_id]
    handles: list[EvidenceHandle] = []
    vault_id = _read_vault_id(vault)
    for rank, evidence_id in enumerate(evidence_ids, start=1):
        metadata = by_id.get(evidence_id)
        if metadata is None:
            continue
        handles.append(
            EvidenceHandle(
                evidence_id=evidence_id,
                raw_identity=RawIdentity(
                    vault_id=vault_id,
                    raw_revision_id=str(metadata.get("raw_revision_id") or ""),
                    source_unit_id=str(metadata.get("source_unit_id") or ""),
                ),
                raw_record_id=str(metadata.get("raw_record_id") or ""),
                revision_id=str(metadata.get("revision_id") or ""),
                processing_record_id=str(metadata.get("processing_record_id") or ""),
                source_record_id=str(metadata.get("source_record_id") or ""),
                source_path=str(metadata.get("source_path") or ""),
                title=str(metadata.get("title") or ""),
                retrieval_generation_id=snapshot.retrieval_generation_id,
                active_fact_generation=snapshot.active_fact_generation,
                signals=(),
                fused_score=0.0,
                fused_rank=rank,
                locator_page_paths=tuple(metadata.get("locator_page_paths") or []),
                content_hint=str(
                    metadata.get("rerank_text")
                    or metadata.get("text")
                    or ""
                ),
            )
        )
    reads, warnings = _resolve_active_evidence(
        vault,
        tuple(handles),
        raise_if_cancelled=raise_if_cancelled,
    )
    return reads, [*missing, *warnings]


def build_active_raw_handles(
    vault_path: Path,
    raw_records: list[RawEvidenceRecord],
) -> tuple[EvidenceHandle, ...]:
    """Build lightweight handles for known active Raw units without reading them."""

    if not raw_records:
        return ()
    vault = vault_path.expanduser().resolve()
    snapshot = open_index_snapshot(vault)
    if snapshot is None:
        raise RuntimeError("No verified lexical retrieval snapshot is published.")
    state = TransactionalIngestStore(vault).materialization_state()
    if (
        str(state.get("requested_fact_generation") or "")
        != snapshot.active_fact_generation
    ):
        raise RuntimeError(
            "Published lexical retrieval snapshot does not match active facts."
        )
    vault_id = _read_vault_id(vault)
    return tuple(
        EvidenceHandle(
            evidence_id="evh:"
            + _stable_hash(
                vault_id,
                raw.raw_revision_id,
                raw.source_unit_id,
            ),
            raw_identity=RawIdentity(
                vault_id=vault_id,
                raw_revision_id=raw.raw_revision_id,
                source_unit_id=raw.source_unit_id,
            ),
            raw_record_id=raw.raw_record_id,
            revision_id=raw.revision_id,
            processing_record_id=raw.processing_record_id,
            source_record_id=raw.source_record_id,
            source_path=raw.source_path,
            title=raw.title,
            retrieval_generation_id=snapshot.retrieval_generation_id,
            active_fact_generation=snapshot.active_fact_generation,
            signals=(),
            fused_score=0.0,
            fused_rank=rank,
            locator_page_paths=tuple(raw.locator_page_paths),
            estimated_content_chars=len(raw.content or raw.excerpt),
            content_hint="",
        )
        for rank, raw in enumerate(raw_records, start=1)
    )


def _claim_spans_valid(handle: EvidenceHandle, raw: RawEvidenceRecord) -> bool:
    unit_text = raw.content or raw.excerpt
    unit_start = raw.char_start or 0
    for signal in handle.signals:
        if signal.channel != "atom_claim":
            continue
        # Claim spans were validated during immutable revision publication. The
        # active resolver fences revision, processing record and parent unit;
        # any available locator span must still lie inside the complete unit.
        for start, end in signal.matched_spans:
            local_start = start - unit_start
            local_end = end - unit_start
            if not (0 <= local_start <= local_end <= len(unit_text)):
                return False
    return True


def _claim_spans_for_unit(claim: KnowledgeAtomRecord, source_unit_id: str) -> tuple[tuple[int, int], ...]:
    spans: list[tuple[int, int]] = []
    for evidence in claim.evidence:
        if str(evidence.get("source_unit_id") or "") != source_unit_id:
            continue
        start = evidence.get("char_start")
        end = evidence.get("char_end")
        if isinstance(start, int) and isinstance(end, int) and 0 <= start <= end:
            span = (start, end)
            if span not in spans:
                spans.append(span)
    return tuple(spans)


def _claim_texts_for_unit(
    claim: KnowledgeAtomRecord,
    source_unit_id: str,
) -> tuple[str, ...]:
    excerpts = tuple(
        str(evidence.get("excerpt") or "").strip()
        for evidence in claim.evidence
        if str(evidence.get("source_unit_id") or "") == source_unit_id
        and str(evidence.get("excerpt") or "").strip()
    )
    return tuple(dict.fromkeys(excerpts or (claim.text.strip(),)))


def _project_matched_excerpt(handle: EvidenceHandle, raw: RawEvidenceRecord) -> RawEvidenceRecord:
    unit_text = raw.content or raw.excerpt
    unit_start = raw.char_start or 0
    claim_spans = [
        span
        for signal in handle.signals
        if signal.channel == "atom_claim"
        for span in signal.matched_spans
    ]
    spans = claim_spans or [
        span
        for signal in handle.signals
        if signal.channel == "raw_lexical"
        for span in signal.matched_spans
    ]
    if not spans:
        return raw
    start, end = spans[0]
    local_start = start - unit_start
    local_end = end - unit_start
    if not (0 <= local_start < local_end <= len(unit_text)):
        return raw
    excerpt = unit_text[local_start:local_end]
    return raw.model_copy(update={"excerpt": excerpt, "char_start": start, "char_end": end})


def _read_vault_id(vault: Path) -> str:
    path = vault_identity_path(vault)
    if not path.is_file():
        raise RuntimeError("Vault identity is missing.")
    payload = json.loads(path.read_text(encoding="utf-8"))
    identity = str(payload.get("identity") or "")
    if not identity:
        raise RuntimeError("Vault identity is invalid.")
    return identity


def _atom_ref(atom: KnowledgeAtomRecord) -> str:
    return f"{atom.revision_id or atom.raw_revision_id or '<missing>'}:{atom.source_record_id}:{atom.atom_id}"


def _key(value: str) -> str:
    return normalize_text(value)


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _extend_unique(target: list[str], values: list[str]) -> None:
    for value in values:
        if value and value not in target:
            target.append(value)


def _query_fingerprint(
    query: str,
    vault_id: str,
    *,
    source_record_ids: frozenset[str] | None = None,
    source_unit_ids: frozenset[str] | None = None,
) -> str:
    record_scope = "\x1e".join(sorted(source_record_ids or ()))
    unit_scope = "\x1e".join(sorted(source_unit_ids or ()))
    return sha256(
        (
            f"{vault_id}\x1f{normalize_text(query)}"
            f"\x1f{record_scope}\x1f{unit_scope}"
        ).encode("utf-8")
    ).hexdigest()


def _encode_cursor(cursor: RetrievalCursor) -> str:
    payload = json.dumps(
        {
            "version": 1,
            "query_fingerprint": cursor.query_fingerprint,
            "vault_id": cursor.vault_id,
            "retrieval_generation_id": cursor.retrieval_generation_id,
            "active_fact_generation": cursor.active_fact_generation,
            "channel": cursor.channel,
            "offset": cursor.offset,
            "rank": cursor.rank,
            "had_candidates": cursor.had_candidates,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    encoded = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    checksum = sha256(payload).hexdigest()[:16]
    return f"retrieval_cursor.v1.{encoded}.{checksum}"


def _decode_cursor(value: str) -> RetrievalCursor:
    parts = value.split(".")
    if len(parts) != 4 or parts[:2] != ["retrieval_cursor", "v1"]:
        raise ValueError("unsupported_format")
    encoded, checksum = parts[2:]
    try:
        payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        data = json.loads(payload)
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError("malformed_payload") from exc
    if sha256(payload).hexdigest()[:16] != checksum:
        raise ValueError("checksum_mismatch")
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("unsupported_payload")
    channel = data.get("channel")
    if channel not in {
        "atom_claim",
        "raw_lexical",
    }:
        raise ValueError("invalid_channel")
    offset = data.get("offset")
    rank = data.get("rank")
    if not isinstance(offset, int) or not isinstance(rank, int) or offset < 0 or rank < 0:
        raise ValueError("invalid_position")
    required = (
        "query_fingerprint",
        "vault_id",
        "retrieval_generation_id",
        "active_fact_generation",
    )
    if any(not isinstance(data.get(name), str) or not data[name] for name in required):
        raise ValueError("missing_identity")
    return RetrievalCursor(
        query_fingerprint=data["query_fingerprint"],
        vault_id=data["vault_id"],
        retrieval_generation_id=data["retrieval_generation_id"],
        active_fact_generation=data["active_fact_generation"],
        channel=channel,
        offset=offset,
        rank=rank,
        had_candidates=data.get("had_candidates") is True,
    )


def _stable_hash(*values: str) -> str:
    return sha256("\x1f".join(values).encode("utf-8")).hexdigest()[:24]


def _terminal(
    status: QueryStatus,
    *,
    channel_statuses: tuple[ChannelStatus, ...] = (),
    warnings: tuple[str, ...] = (),
    gaps: tuple[str, ...] = (),
    stats: dict[str, object] | None = None,
    query_fingerprint: str = "",
    snapshot_generation: str = "",
) -> EvidenceCollection:
    return EvidenceCollection(
        status=status,
        handles=(),
        evidence_reads=(),
        atom_candidates=(),
        claim_candidates=(),
        channel_statuses=channel_statuses,
        warnings=warnings,
        gaps=gaps,
        stats=stats or {},
        query_fingerprint=query_fingerprint,
        snapshot_generation=snapshot_generation,
    )


def _raise_if_cancelled(safety: RetrievalSafety) -> None:
    if safety.raise_if_cancelled is not None:
        safety.raise_if_cancelled()
