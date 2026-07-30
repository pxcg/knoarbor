from __future__ import annotations

from pathlib import Path

from knoarbor.core.errors import UserInputError
from knoarbor.core.schemas.wiki_query import (
    WikiAtomTrace,
    WikiChannelStatus,
    WikiEvidenceHandle,
    WikiRecallSignal,
    WikiRawEvidence,
    WikiSearchRequest,
    WikiSearchResponse,
    WikiSearchResult,
)
from knoarbor.product import PRODUCT
from knoarbor.pipelines.query import QueryPipeline, QueryPipelineRequest
from knoarbor.retrieval.query_text import query_terms
from knoarbor.retrieval.unified import ClaimCandidate, EvidenceHandle, EvidenceRead
from knoarbor.storage.source_records import RawEvidenceRecord


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
            continuation_cursor=request.continuation_cursor,
        )
    )
    results = _locator_results(pipeline_result.claim_candidates)
    raw_evidence = [_candidate_evidence(item) for item in pipeline_result.matches]
    effective_gaps = pipeline_result.gaps
    context_pack = build_context_pack(
        request.query,
        results,
        raw_evidence,
    )
    stats = {
        **pipeline_result.stats,
        "returned_count": len(results),
        "context_strategy": "semantic_indexed_raw_grounded",
        "context_pack_chars": len(context_pack),
        "context_pack_truncated": False,
        "raw_evidence_count": len(raw_evidence),
        "atom_trace_count": sum(len(result.atom_traces) for result in results),
        "gap_count": len(effective_gaps),
        "query_status": pipeline_result.status,
    }
    return WikiSearchResponse(
        query=request.query,
        status=pipeline_result.status,
        retrieval_mode=pipeline_result.retrieval_mode,
        results=results,
        evidence_handles=[_wiki_handle(item) for item in pipeline_result.handles],
        raw_evidence=raw_evidence,
        context_pack=context_pack,
        gaps=effective_gaps,
        warnings=pipeline_result.warnings,
        channel_statuses=[WikiChannelStatus(**item.__dict__) for item in pipeline_result.channel_statuses],
        stats=stats,
        trace={
            **build_query_trace(stats, results, raw_evidence=raw_evidence),
            "atom_candidates": [
                {"atom_id": item.atom.atom_id, "atom_type": item.atom.atom_type, "score": round(item.score, 4)}
                for item in pipeline_result.atom_candidates
            ],
            "claim_candidates": [
                {
                    "claim_ref": item.claim_ref,
                    "local_claim_id": item.claim.atom_id,
                    "score": round(item.score, 4),
                    "supporting_atom_refs": item.supporting_atom_ids,
                    "reasons": list(item.reasons),
                }
                for item in pipeline_result.claim_candidates
            ],
        },
        exhausted=pipeline_result.exhausted,
        continuation_cursor=pipeline_result.continuation_cursor,
        query_fingerprint=pipeline_result.query_fingerprint,
        snapshot_generation=pipeline_result.snapshot_generation,
    )


def _locator_results(claims: list[ClaimCandidate]) -> list[WikiSearchResult]:
    by_path: dict[str, WikiSearchResult] = {}
    for candidate in claims:
        trace = _claim_trace(candidate)
        for path in candidate.claim.page_paths:
            result = by_path.get(path)
            if result is None:
                result = WikiSearchResult(
                    path=path,
                    title=_locator_title(path),
                    score=round(candidate.score, 3),
                    relevance=_score_relevance(candidate.score),
                    matched_fields=["knowledge_atom"],
                    reason="Projection locator derived from a selected claim.",
                    atom_traces=[trace],
                )
                by_path[path] = result
            else:
                result.score = round(result.score + candidate.score, 3)
                if all(item.atom_id != trace.atom_id for item in result.atom_traces):
                    result.atom_traces.append(trace)
    return sorted(by_path.values(), key=lambda item: (-item.score, item.path))


def _locator_title(path: str) -> str:
    return Path(path).stem.replace("-", " ").replace("_", " ").strip()


def _claim_trace(candidate: ClaimCandidate) -> WikiAtomTrace:
    claim = candidate.claim
    return WikiAtomTrace(
        atom_id=claim.atom_id,
        atom_type="claim",
        text=claim.text,
        source_record_id=claim.source_record_id,
        raw_record_id=claim.raw_record_id,
        raw_revision_id=claim.raw_revision_id,
        source_unit_ids=claim.source_unit_ids,
        processing_record_id=claim.processing_record_id,
    )


def _candidate_evidence(candidate: EvidenceRead) -> WikiRawEvidence:
    return _wiki_raw_evidence(
        candidate.raw_evidence,
        handle=candidate.handle,
    )


def _score_relevance(score: float) -> str:
    if score >= 8:
        return "high"
    if score >= 2:
        return "medium"
    return "low"


def _wiki_raw_evidence(record: RawEvidenceRecord, *, handle: EvidenceHandle) -> WikiRawEvidence:
    score = handle.fused_score
    relevance = "high" if score >= 0.08 else "medium" if score >= 0.03 else "low"
    locator_atom_ids = _dedupe([
        *(atom_ref for signal in handle.signals for atom_ref in signal.locator_atom_refs),
        *record.locator_atom_ids,
    ])
    locator_page_paths = _dedupe([*handle.locator_page_paths, *record.locator_page_paths])
    return WikiRawEvidence(
        evidence_id=handle.evidence_id,
        vault_id=handle.raw_identity.vault_id,
        raw_record_id=record.raw_record_id,
        raw_revision_id=record.raw_revision_id,
        revision_id=handle.revision_id,
        source_unit_id=record.source_unit_id,
        source_record_id=record.source_record_id,
        processing_record_id=record.processing_record_id,
        source_path=record.source_path,
        unit_index=record.unit_index,
        unit_type=record.unit_type,
        title=record.title,
        excerpt=record.excerpt,
        content=record.content or record.excerpt,
        excerpt_hash=record.excerpt_hash,
        char_start=record.char_start,
        char_end=record.char_end,
        structural_path=list(record.structural_path),
        locator_atom_ids=locator_atom_ids,
        locator_page_paths=locator_page_paths,
        relevance=relevance,
        reason="Resolved from unified active Raw locator signals.",
    )


def _wiki_handle(handle: EvidenceHandle) -> WikiEvidenceHandle:
    return WikiEvidenceHandle(
        evidence_id=handle.evidence_id,
        vault_id=handle.raw_identity.vault_id,
        raw_record_id=handle.raw_record_id,
        raw_revision_id=handle.raw_identity.raw_revision_id,
        revision_id=handle.revision_id,
        source_unit_id=handle.raw_identity.source_unit_id,
        source_record_id=handle.source_record_id,
        processing_record_id=handle.processing_record_id,
        source_path=handle.source_path,
        title=handle.title,
        retrieval_generation_id=handle.retrieval_generation_id,
        active_fact_generation=handle.active_fact_generation,
        fused_score=handle.fused_score,
        fused_rank=handle.fused_rank,
        signals=[
            WikiRecallSignal(
                channel=signal.channel,
                channel_rank=signal.channel_rank,
                channel_score=signal.channel_score,
                matched_terms=list(signal.matched_terms),
                claim_refs=list(signal.claim_refs),
                locator_atom_refs=list(signal.locator_atom_refs),
                matched_spans=list(signal.matched_spans),
            )
            for signal in handle.signals
        ],
    )


def _dedupe(items: list[str]) -> list[str]:
    output: list[str] = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in output:
            output.append(text)
    return output


def build_context_pack(
    query: str,
    results: list[WikiSearchResult],
    raw_evidence: list[WikiRawEvidence],
) -> str:
    lines = [
        f"Relevant {PRODUCT.name} context for the host AI.",
        f"Query: {query}",
        "",
    ]
    lines.extend(
        [
            "Fact context contract:",
            "- Allowed factual material: raw_evidence excerpts/source units only.",
            "- Disallowed factual material: wiki page body, wiki synthesis, atom claim text, entity summaries, relation summaries.",
            "- Locator pages explain retrieval only; do not cite them as factual evidence.",
            "",
        ]
    )
    if not results and not raw_evidence:
        lines.append("No relevant locator pages found.")
        return "\n".join(lines)

    if raw_evidence:
        lines.append("Raw evidence:")
        for index, evidence in enumerate(raw_evidence, start=1):
            block = build_raw_evidence_context_block(index, evidence)
            lines.extend(block)
        lines.append("")
    else:
        lines.extend(
            [
                "Raw evidence:",
                "- No raw/source-unit evidence was available for the selected locator metadata.",
                "- The answer should report insufficient raw evidence instead of using wiki prose as fact material.",
                "",
            ]
        )

    lines.append("Locator trace:")
    if not results:
        lines.append("- No locator pages found; raw evidence was selected directly from atom/evidence indexes.")
        return "\n".join(lines).strip()
    for index, result in enumerate(results, start=1):
        block = build_result_context_block(index, result)
        lines.extend(block)
    return "\n".join(lines).strip()


def build_raw_evidence_context_block(index: int, evidence: WikiRawEvidence) -> list[str]:
    title = evidence.title or f"Source unit {evidence.unit_index}"
    content = evidence.content or evidence.excerpt
    locator_pages = ", ".join(evidence.locator_page_paths[:5]) if evidence.locator_page_paths else "none"
    locator_atoms = ", ".join(evidence.locator_atom_ids[:8]) if evidence.locator_atom_ids else "none"
    return [
        f"### Raw Evidence {index}: {title}",
        f"- Evidence id: {evidence.evidence_id}",
        f"- Source path: {evidence.source_path or evidence.source_record_id}",
        f"- Source unit: {evidence.source_unit_id} (index {evidence.unit_index})",
        f"- Range: {evidence.char_start if evidence.char_start is not None else 'n/a'}-{evidence.char_end if evidence.char_end is not None else 'n/a'}",
        f"- Locator pages: {locator_pages}",
        f"- Locator atoms: {locator_atoms}",
        "",
        content,
        "",
    ]


def build_query_trace(
    stats: dict[str, object],
    results: list[WikiSearchResult],
    *,
    raw_evidence: list[WikiRawEvidence],
) -> dict[str, object]:
    return {
        "schema_version": "query_trace.v2",
        "scoring_model": stats.get("scoring_model", "unknown"),
        "query_terms": stats.get("query_terms", []),
        "candidate_count": stats.get("candidate_count", 0),
        "returned_count": stats.get("returned_count", 0),
        "context_pack_chars": stats.get("context_pack_chars", 0),
        "context_pack_truncated": stats.get("context_pack_truncated", False),
        "atom_trace_count": stats.get("atom_trace_count", 0),
        "raw_evidence_count": len(raw_evidence),
        "gap_count": stats.get("gap_count", 0),
        "gap_suggestion_count": stats.get("gap_suggestion_count", 0),
        "returned_paths": [result.path for result in results],
        "atom_trace_counts": {
            result.path: len(result.atom_traces)
            for result in results
            if result.atom_traces
        },
        "raw_evidence": [
            {
                "evidence_id": item.evidence_id,
                "source_unit_id": item.source_unit_id,
                "source_record_id": item.source_record_id,
                "source_path": item.source_path,
                "locator_page_paths": item.locator_page_paths,
                "locator_atom_ids": item.locator_atom_ids,
            }
            for item in raw_evidence
        ],
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


def build_result_context_block(index: int, result: WikiSearchResult) -> list[str]:
    lines = [
        f"{index}. {result.title} ({result.path}, relevance: {result.relevance}, score: {result.score})",
        f"Matched fields: {', '.join(result.matched_fields) or 'none'}",
        f"Why matched: {result.reason}",
    ]
    lines.append("")
    return lines
