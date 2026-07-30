from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from knoarbor.audit.contracts import LEDGER_PATHS, LEDGER_SCHEMA_VERSIONS
from knoarbor.core.schemas.wiki_query import WikiQueryFeedbackRequest, WikiSearchRequest, WikiSearchResponse
from knoarbor.storage.ledger import append_jsonl_ledger, read_jsonl_ledger
from knoarbor.storage.vault_layout import ledger_relative_path

QUERY_LEDGER_PATH = LEDGER_PATHS["query"]
QUERY_FEEDBACK_LEDGER_PATH = ledger_relative_path("query_feedback")
QUERY_RECORD_SCHEMA_VERSION = LEDGER_SCHEMA_VERSIONS["query"]
QUERY_FEEDBACK_SCHEMA_VERSION = LEDGER_SCHEMA_VERSIONS["query_feedback"]


def append_query_record(vault_path: Path, request: WikiSearchRequest, response: WikiSearchResponse) -> Path:
    record = {
        "schema_version": QUERY_RECORD_SCHEMA_VERSION,
        "timestamp": current_timestamp(),
        "caller": request.caller or "unknown",
        "query": request.query,
        "status": response.status,
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
        "warnings": response.warnings,
        "context_pack_chars": response.stats.get("context_pack_chars", 0),
        "context_pack_truncated": response.stats.get("context_pack_truncated", False),
    }
    return append_jsonl_ledger(vault_path, QUERY_LEDGER_PATH, record)


def append_query_feedback(vault_path: Path, request: WikiQueryFeedbackRequest) -> Path:
    record = {
        "schema_version": QUERY_FEEDBACK_SCHEMA_VERSION,
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
        query = str(record.get("query") or "").strip()
        if not query:
            continue
        if record.get("status") == "no_match":
            no_result_queries.append(query)

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
