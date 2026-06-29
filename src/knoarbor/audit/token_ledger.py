from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from knoarbor.audit.contracts import LEDGER_PATHS, LEDGER_SCHEMA_VERSIONS
from knoarbor.audit.report_formatting import as_dict, as_list
from knoarbor.storage.ledger import append_jsonl_records, read_jsonl_ledger


TOKEN_LEDGER_PATH = LEDGER_PATHS["token"]
TOKEN_LEDGER_SCHEMA_VERSION = LEDGER_SCHEMA_VERSIONS["token"]
TOKEN_ANALYSIS_SCHEMA_VERSION = LEDGER_SCHEMA_VERSIONS["token_analysis"]
LOW_CACHE_RATE_THRESHOLD = 0.2
HIGH_DYNAMIC_TO_STABLE_RATIO = 3.0


def append_ingest_token_records(vault_path: Path, record: dict[str, object]) -> None:
    append_jsonl_records(vault_path, TOKEN_LEDGER_PATH, build_ingest_token_records(record))


def append_lint_token_records(vault_path: Path, record: dict[str, object]) -> None:
    append_jsonl_records(vault_path, TOKEN_LEDGER_PATH, build_lint_token_records(record))


def append_chat_token_records(vault_path: Path, record: dict[str, object]) -> None:
    append_jsonl_records(vault_path, TOKEN_LEDGER_PATH, build_chat_token_records(record))


def read_token_analysis(vault_path: Path, *, limit: int | None = 5000) -> dict[str, object]:
    records = read_jsonl_ledger(vault_path, TOKEN_LEDGER_PATH, limit=limit)
    if not records:
        records = _historical_records(vault_path, limit=limit)
    return build_token_analysis(records)


def build_ingest_token_records(record: dict[str, object]) -> list[dict[str, object]]:
    run_id = str(record.get("run_id") or "")
    base = {
        "schema_version": TOKEN_LEDGER_SCHEMA_VERSION,
        "flow": "ingest",
        "run_id": run_id,
        "started_at": record.get("started_at"),
        "finished_at": record.get("finished_at"),
    }
    rows: list[dict[str, object]] = []
    for source in as_list(record.get("sources")):
        source_dict = as_dict(source)
        source_base = {
            **base,
            "connector": source_dict.get("connector"),
            "source_id": source_dict.get("source_id"),
            "source_file": source_dict.get("source_file"),
            "source_status": source_dict.get("status"),
            "source_mode": source_dict.get("mode"),
        }
        segments = as_list(source_dict.get("segments"))
        if segments:
            for segment in segments:
                segment_dict = as_dict(segment)
                rows.extend(
                    _call_records(
                        source_base,
                        as_dict(as_dict(segment_dict.get("metrics")).get("semantic")),
                        segment_index=segment_dict.get("index"),
                        segment_title=segment_dict.get("title"),
                        segment_chars=segment_dict.get("chars"),
                        page_paths=_page_paths_from_segment(segment_dict),
                    )
                )
        else:
            rows.extend(
                _call_records(
                    source_base,
                    as_dict(as_dict(source_dict.get("metrics")).get("semantic")),
                    page_paths=_unique_strings(
                        [
                            *[str(page) for page in as_list(source_dict.get("generated_pages"))],
                            *[str(page) for page in as_list(source_dict.get("touched_pages"))],
                        ]
                    ),
                )
            )
    return rows


def build_lint_token_records(record: dict[str, object]) -> list[dict[str, object]]:
    base = {
        "schema_version": TOKEN_LEDGER_SCHEMA_VERSION,
        "flow": "lint",
        "run_id": record.get("run_id"),
        "created_at": record.get("created_at"),
        "mode": record.get("mode"),
        "profile": record.get("profile"),
        "page_paths": _lint_page_paths(record),
    }
    return _call_records(base, as_dict(as_dict(record.get("metrics")).get("semantic")), page_paths=as_list(base.get("page_paths")))


def build_chat_token_records(record: dict[str, object]) -> list[dict[str, object]]:
    base = {
        "schema_version": TOKEN_LEDGER_SCHEMA_VERSION,
        "flow": "chat",
        "run_id": record.get("chat_id"),
        "created_at": record.get("created_at"),
        "finished_at": record.get("finished_at"),
        "mode": record.get("mode"),
        "connector": "chat",
        "source_id": record.get("source_id") or "chat",
        "source_file": record.get("source_file"),
        "page_paths": _chat_page_paths(record),
    }
    rows: list[dict[str, object]] = []
    for call_index, raw_call in enumerate(as_list(record.get("calls"))):
        call = as_dict(raw_call)
        prompt_tokens = _int(call.get("prompt_tokens"))
        cached_tokens = _int(call.get("prompt_cached_tokens"))
        completion_tokens = _int(call.get("completion_tokens"))
        total_tokens = _int(call.get("total_tokens"))
        elapsed_seconds = _float(call.get("elapsed_seconds"))
        rows.append(
            {
                **base,
                "call_index": call_index,
                "agent": "wiki_chat_agent",
                "agent_schema_version": "chat_agent.v1",
                "provider": call.get("provider") or record.get("provider"),
                "model": call.get("model") or record.get("model"),
                "prompt_tokens": prompt_tokens,
                "prompt_cached_tokens": cached_tokens,
                "prompt_cache_hit_tokens": _int(call.get("prompt_cache_hit_tokens")),
                "prompt_cache_miss_tokens": _int(call.get("prompt_cache_miss_tokens")),
                "prompt_cache_rate": _ratio(cached_tokens, prompt_tokens),
                "prompt_stable_chars": 0,
                "prompt_dynamic_chars": _int(call.get("prompt_chars")),
                "dynamic_to_stable_ratio": None,
                "payload_char_total": _int(call.get("prompt_chars")),
                "payload_top_field": "messages",
                "payload_char_breakdown": {"messages": _int(call.get("prompt_chars"))},
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "elapsed_seconds": elapsed_seconds,
                "tokens_per_second": call.get("tokens_per_second") or _ratio(completion_tokens, elapsed_seconds),
                "turn": call.get("turn"),
                "page_paths": as_list(base.get("page_paths")),
            }
        )
    return rows


def build_token_analysis(records: list[dict[str, object]]) -> dict[str, object]:
    sorted_records = sorted(records, key=lambda item: str(item.get("finished_at") or item.get("created_at") or ""))
    return {
        "schema_version": TOKEN_ANALYSIS_SCHEMA_VERSION,
        "record_count": len(sorted_records),
        "totals": _summarize(sorted_records),
        "by_flow": _group(sorted_records, "flow"),
        "by_agent": _group(sorted_records, "agent"),
        "by_source": _top(_group(sorted_records, "source_file"), limit=20),
        "by_connector": _group(sorted_records, "connector"),
        "by_model": _group(sorted_records, "model"),
        "by_page": _top(_page_groups(sorted_records), limit=20),
        "by_payload_field": _top_payload_fields(sorted_records, limit=30),
        "top_calls": _top_calls(sorted_records, limit=30),
        "cache_diagnostics": _cache_diagnostics(sorted_records),
        "recent_runs": _recent_runs(sorted_records, limit=20),
    }


def _call_records(
    base: dict[str, object],
    semantic_metrics: dict[str, object],
    *,
    segment_index: object = None,
    segment_title: object = None,
    segment_chars: object = None,
    page_paths: list[str] | None = None,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for call_index, raw_call in enumerate(as_list(semantic_metrics.get("calls"))):
        call = as_dict(raw_call)
        prompt_tokens = _int(call.get("prompt_tokens"))
        cached_tokens = _int(call.get("prompt_cached_tokens"))
        stable_chars = _int(call.get("prompt_stable_chars"))
        dynamic_chars = _int(call.get("prompt_dynamic_chars"))
        completion_tokens = _int(call.get("completion_tokens"))
        total_tokens = _int(call.get("total_tokens"))
        payload_breakdown = _payload_breakdown(call.get("payload_char_breakdown"))
        rows.append(
            {
                **base,
                "call_index": call_index,
                "agent": call.get("contract_name") or "unknown",
                "agent_schema_version": call.get("schema_version"),
                "provider": call.get("provider"),
                "model": call.get("model"),
                "prompt_tokens": prompt_tokens,
                "prompt_cached_tokens": cached_tokens,
                "prompt_cache_hit_tokens": _int(call.get("prompt_cache_hit_tokens")),
                "prompt_cache_miss_tokens": _int(call.get("prompt_cache_miss_tokens")),
                "prompt_cache_rate": _ratio(cached_tokens, prompt_tokens),
                "prompt_stable_chars": stable_chars,
                "prompt_dynamic_chars": dynamic_chars,
                "dynamic_to_stable_ratio": _ratio(dynamic_chars, stable_chars),
                "payload_char_total": _int(call.get("payload_char_total")),
                "payload_top_field": call.get("payload_top_field"),
                "payload_char_breakdown": payload_breakdown,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "elapsed_seconds": _float(call.get("elapsed_seconds")),
                "tokens_per_second": call.get("tokens_per_second"),
                "segment_index": segment_index,
                "segment_title": segment_title,
                "segment_chars": segment_chars,
                "page_paths": page_paths or [],
            }
        )
    return rows


def _historical_records(vault_path: Path, *, limit: int | None) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for record in read_jsonl_ledger(vault_path, LEDGER_PATHS["ingest"], limit=limit):
        records.extend(build_ingest_token_records(record))
    for record in read_jsonl_ledger(vault_path, LEDGER_PATHS["lint"], limit=limit):
        records.extend(build_lint_token_records(record))
    return records[-limit:] if limit is not None else records


def _page_paths_from_segment(segment: dict[str, object]) -> list[str]:
    paths = [str(page) for page in as_list(segment.get("generated_pages"))]
    for detail in as_list(segment.get("written_page_details")):
        path = as_dict(detail).get("path")
        if isinstance(path, str):
            paths.append(path)
    return _unique_strings(paths)


def _lint_page_paths(record: dict[str, object]) -> list[str]:
    paths = [str(path) for path in as_list(record.get("written_pages"))]
    for operation in as_list(record.get("applied_operations")):
        operation_dict = as_dict(operation)
        for key in ("output_page", "target_page"):
            value = operation_dict.get(key)
            if isinstance(value, str) and value:
                paths.append(value)
    for detail in as_list(record.get("written_page_details")):
        value = as_dict(detail).get("path")
        if isinstance(value, str) and value:
            paths.append(value)
    return _unique_strings(paths)


def _chat_page_paths(record: dict[str, object]) -> list[str]:
    paths: list[str] = []
    for citation in as_list(record.get("citations")):
        path = as_dict(citation).get("path")
        if isinstance(path, str) and path:
            paths.append(path)
    for trace in as_list(record.get("tool_trace")):
        for citation in as_list(as_dict(trace).get("citations")):
            path = as_dict(citation).get("path")
            if isinstance(path, str) and path:
                paths.append(path)
    return _unique_strings(paths)


def current_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _group(records: list[dict[str, object]], key: str) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for record in records:
        value = record.get(key)
        name = str(value) if value not in (None, "") else "unknown"
        grouped.setdefault(name, []).append(record)
    return _top(
        [
            {
                "name": name,
                **_summarize(items),
            }
            for name, items in grouped.items()
        ],
        limit=len(grouped),
    )


def _page_groups(records: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for record in records:
        for page in as_list(record.get("page_paths")):
            if isinstance(page, str) and page:
                grouped.setdefault(page, []).append(record)
    return [{"name": page, **_summarize(items)} for page, items in grouped.items()]


def _top_payload_fields(records: list[dict[str, object]], *, limit: int) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, object]] = {}
    for record in records:
        for field, chars in _payload_breakdown(record.get("payload_char_breakdown")).items():
            if field not in grouped:
                grouped[field] = {
                    "name": field,
                    "call_count": 0,
                    "payload_chars": 0,
                    "top_call_count": 0,
                }
            item = grouped[field]
            item["call_count"] = _int(item.get("call_count")) + 1
            item["payload_chars"] = _int(item.get("payload_chars")) + chars
            if record.get("payload_top_field") == field:
                item["top_call_count"] = _int(item.get("top_call_count")) + 1
    return sorted(grouped.values(), key=lambda item: _int(item.get("payload_chars")), reverse=True)[:limit]


def _summarize(records: list[dict[str, object]]) -> dict[str, object]:
    prompt_tokens = sum(_int(record.get("prompt_tokens")) for record in records)
    cached_tokens = sum(_int(record.get("prompt_cached_tokens")) for record in records)
    completion_tokens = sum(_int(record.get("completion_tokens")) for record in records)
    total_tokens = sum(_int(record.get("total_tokens")) for record in records)
    stable_chars = sum(_int(record.get("prompt_stable_chars")) for record in records)
    dynamic_chars = sum(_int(record.get("prompt_dynamic_chars")) for record in records)
    payload_chars = sum(_int(record.get("payload_char_total")) for record in records)
    elapsed_seconds = sum(_float(record.get("elapsed_seconds")) for record in records)
    return {
        "call_count": len(records),
        "prompt_tokens": prompt_tokens,
        "prompt_cached_tokens": cached_tokens,
        "prompt_cache_rate": _ratio(cached_tokens, prompt_tokens),
        "prompt_stable_chars": stable_chars,
        "prompt_dynamic_chars": dynamic_chars,
        "dynamic_to_stable_ratio": _ratio(dynamic_chars, stable_chars),
        "payload_char_total": payload_chars,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "tokens_per_second": _ratio(completion_tokens, elapsed_seconds),
    }


def _top(items: list[dict[str, object]], *, limit: int) -> list[dict[str, object]]:
    return sorted(items, key=lambda item: _int(item.get("total_tokens")), reverse=True)[:limit]


def _top_calls(records: list[dict[str, object]], *, limit: int) -> list[dict[str, object]]:
    return _top(records, limit=limit)


def _recent_runs(records: list[dict[str, object]], *, limit: int) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for record in records:
        run_id = str(record.get("run_id") or "unknown")
        grouped.setdefault(run_id, []).append(record)
    runs = [
        {
            "run_id": run_id,
            "flow": items[0].get("flow"),
            "created_at": items[0].get("created_at") or items[0].get("started_at"),
            "finished_at": items[-1].get("finished_at"),
            **_summarize(items),
        }
        for run_id, items in grouped.items()
    ]
    return sorted(runs, key=lambda item: str(item.get("finished_at") or item.get("created_at") or ""), reverse=True)[:limit]


def _cache_diagnostics(records: list[dict[str, object]]) -> dict[str, object]:
    tokenized = [record for record in records if _int(record.get("prompt_tokens")) > 0]
    low_cache = [
        record
        for record in tokenized
        if (_ratio(_int(record.get("prompt_cached_tokens")), _int(record.get("prompt_tokens"))) or 0.0) < LOW_CACHE_RATE_THRESHOLD
    ]
    high_dynamic = [
        record
        for record in records
        if (_ratio(_int(record.get("prompt_dynamic_chars")), _int(record.get("prompt_stable_chars"))) or 0.0) >= HIGH_DYNAMIC_TO_STABLE_RATIO
    ]
    cache_telemetry_observed = [
        record
        for record in tokenized
        if any(_int(record.get(key)) > 0 for key in ("prompt_cached_tokens", "prompt_cache_hit_tokens", "prompt_cache_miss_tokens"))
    ]
    return {
        "low_cache_rate_threshold": LOW_CACHE_RATE_THRESHOLD,
        "high_dynamic_to_stable_ratio": HIGH_DYNAMIC_TO_STABLE_RATIO,
        "tokenized_call_count": len(tokenized),
        "cache_telemetry_observed_calls": len(cache_telemetry_observed),
        "cache_telemetry_observed_rate": _ratio(len(cache_telemetry_observed), len(tokenized)),
        "low_cache_calls": _top_calls(low_cache, limit=20),
        "high_dynamic_calls": _top_calls(high_dynamic, limit=20),
    }


def _unique_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = value.strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _ratio(numerator: int | float, denominator: int | float) -> float | None:
    if denominator <= 0:
        return None
    return round(float(numerator) / float(denominator), 4)


def _int(value: object) -> int:
    return value if isinstance(value, int) else 0


def _float(value: object) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0


def _payload_breakdown(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {str(key): _int(item) for key, item in value.items()}
