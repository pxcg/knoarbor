from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from knoarbor.core.schemas.wiki_query import WikiQueryFeedbackRequest, WikiSearchRequest, WikiSearchResponse
from knoarbor.storage.ledger import append_jsonl_ledger, read_jsonl_ledger

QUERY_LEDGER_PATH = "maintenance/query_ledger.jsonl"
QUERY_FEEDBACK_LEDGER_PATH = "maintenance/query_feedback_ledger.jsonl"


def append_query_record(vault_path: Path, request: WikiSearchRequest, response: WikiSearchResponse) -> Path:
    record = {
        "schema_version": "query_record.v1",
        "timestamp": current_timestamp(),
        "caller": request.caller or "unknown",
        "query": request.query,
        "mode": request.mode,
        "page_dirs": request.page_dirs,
        "retrieval_mode": response.retrieval_mode,
        "result_count": len(response.results),
        "top_results": [
            {
                "path": item.path,
                "title": item.title,
                "score": item.score,
                "relevance": item.relevance,
            }
            for item in response.results[:5]
        ],
        "gaps": response.gaps,
        "gap_suggestions": [item.model_dump() for item in response.gap_suggestions],
        "warnings": response.warnings,
        "context_pack_chars": response.stats.get("context_pack_chars", 0),
        "context_pack_truncated": response.stats.get("context_pack_truncated", False),
    }
    return append_jsonl_ledger(vault_path, QUERY_LEDGER_PATH, record)


def append_query_feedback(vault_path: Path, request: WikiQueryFeedbackRequest) -> Path:
    record = {
        "schema_version": "query_feedback.v1",
        "timestamp": current_timestamp(),
        "caller": request.caller or "unknown",
        "query": request.query,
        "useful": request.useful,
        "selected_paths": request.selected_paths,
        "rejected_paths": request.rejected_paths,
        "comment": request.comment.strip(),
    }
    return append_jsonl_ledger(vault_path, QUERY_FEEDBACK_LEDGER_PATH, record)


def build_query_trend(vault_path: Path, *, limit: int = 100) -> dict[str, object]:
    records = read_jsonl_ledger(vault_path, QUERY_LEDGER_PATH, limit=limit)
    no_result_queries: list[str] = []
    low_confidence_queries: list[str] = []
    for record in records:
        suggestions = record.get("gap_suggestions")
        if not isinstance(suggestions, list):
            continue
        for suggestion in suggestions:
            if not isinstance(suggestion, dict):
                continue
            query = str(suggestion.get("query") or record.get("query") or "").strip()
            kind = suggestion.get("kind")
            if not query:
                continue
            if kind == "no_result":
                no_result_queries.append(query)
            elif kind == "low_confidence":
                low_confidence_queries.append(query)

    return {
        "sample_size": len(records),
        "no_result_count": len(no_result_queries),
        "low_confidence_count": len(low_confidence_queries),
        "repeated_gap_queries": top_repeated(no_result_queries + low_confidence_queries),
    }


def top_repeated(values: list[str], *, limit: int = 5) -> list[dict[str, object]]:
    return [
        {"query": query, "count": count}
        for query, count in Counter(values).most_common(limit)
        if count > 1
    ]


def current_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
