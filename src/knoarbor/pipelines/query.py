from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from knoarbor.core.errors import UserInputError
from knoarbor.retrieval.query_text import query_terms
from knoarbor.retrieval.unified import (
    AtomCandidate,
    ChannelStatus,
    ClaimCandidate,
    EvidenceHandle,
    EvidenceRead,
    QueryStatus,
    UnifiedActiveRawRetriever,
    QueryPlan,
)
from knoarbor.storage.lexical_snapshot import RetrievalSafety
from knoarbor.storage.index_snapshot import IndexSnapshot
from knoarbor.runtime import current_run_monitor


@dataclass
class QueryPipelineRequest:
    vault_path: Path
    query: str
    safety: RetrievalSafety | None = None
    continuation_cursor: str | None = None
    resolve_evidence: bool = True
    source_record_ids: frozenset[str] | None = None
    source_unit_ids: frozenset[str] | None = None
    snapshot: IndexSnapshot | None = None


@dataclass
class QueryPipelineResult:
    query: str
    retrieval_mode: str
    status: QueryStatus
    handles: list[EvidenceHandle]
    matches: list[EvidenceRead]
    atom_candidates: list[AtomCandidate]
    claim_candidates: list[ClaimCandidate]
    channel_statuses: list[ChannelStatus]
    gaps: list[str]
    warnings: list[str]
    stats: dict[str, object]
    exhausted: bool
    continuation_cursor: str | None
    query_fingerprint: str
    snapshot_generation: str


class QueryPipeline:
    """Runs unified lexical recall and active Raw evidence resolution."""

    def __init__(self) -> None:
        self.retriever = UnifiedActiveRawRetriever()

    def run(self, request: QueryPipelineRequest) -> QueryPipelineResult:
        monitor = current_run_monitor()
        vault_path = request.vault_path.expanduser().resolve()
        if not vault_path.exists() or not vault_path.is_dir():
            raise UserInputError(f"vault_path does not exist or is not a directory: {vault_path}")
        if not query_terms(request.query):
            raise UserInputError("query does not contain searchable terms")
        if monitor:
            monitor.event("query_started", stage="query", message="Searching the verified active lexical snapshot.", current_item=request.query)

        retrieval = self.retriever.retrieve(
            QueryPlan(
                vault_path=vault_path,
                query=request.query,
                safety=request.safety or RetrievalSafety.with_timeout(),
                continuation_cursor=request.continuation_cursor,
                resolve_evidence=request.resolve_evidence,
                source_record_ids=request.source_record_ids,
                source_unit_ids=request.source_unit_ids,
                snapshot=request.snapshot,
            )
        )

        if monitor:
            monitor.event(
                "query_finished",
                stage="query",
                message=(
                    f"Resolved {len(retrieval.evidence_reads)} active raw evidence unit(s)."
                    if request.resolve_evidence
                    else f"Recalled {len(retrieval.handles)} active raw evidence handle(s)."
                ),
                progress={"total": len(retrieval.handles), "completed": len(retrieval.evidence_reads), "current": request.query},
                payload={"status": retrieval.status, "claim_count": len(retrieval.claim_candidates), "evidence_count": len(retrieval.evidence_reads)},
            )
        return QueryPipelineResult(
            query=request.query,
            retrieval_mode="unified_active_raw_lexical",
            status=retrieval.status,
            handles=list(retrieval.handles),
            matches=list(retrieval.evidence_reads),
            atom_candidates=list(retrieval.atom_candidates),
            claim_candidates=list(retrieval.claim_candidates),
            channel_statuses=list(retrieval.channel_statuses),
            gaps=list(retrieval.gaps),
            warnings=list(retrieval.warnings),
            stats={**retrieval.stats, "returned_count": len(retrieval.evidence_reads)},
            exhausted=retrieval.exhausted,
            continuation_cursor=retrieval.continuation_cursor,
            query_fingerprint=retrieval.query_fingerprint,
            snapshot_generation=retrieval.snapshot_generation,
        )
