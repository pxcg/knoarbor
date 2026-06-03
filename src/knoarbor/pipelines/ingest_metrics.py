from __future__ import annotations

from knoarbor.core.schemas.ingest_pipeline import IngestSourceResult


def combine_redactions(redactions: list[dict[str, object]]) -> dict[str, object]:
    counts: dict[str, int] = {}
    enabled = any(bool(redaction.get("enabled")) for redaction in redactions)
    for redaction in redactions:
        for key, value in as_dict(redaction.get("counts")).items():
            counts[key] = counts.get(key, 0) + metric_int(value)
    return {
        "enabled": enabled,
        "counts": counts,
        "redacted_count": sum(counts.values()),
    }


def combine_semantic_metrics(metrics: list[dict[str, object]]) -> dict[str, object]:
    prompt_tokens = sum(metric_int(metric.get("prompt_tokens")) for metric in metrics)
    prompt_cached_tokens = sum(metric_int(metric.get("prompt_cached_tokens")) for metric in metrics)
    prompt_cache_hit_tokens = sum(metric_int(metric.get("prompt_cache_hit_tokens")) for metric in metrics)
    prompt_cache_miss_tokens = sum(metric_int(metric.get("prompt_cache_miss_tokens")) for metric in metrics)
    prompt_stable_chars = sum(metric_int(metric.get("prompt_stable_chars")) for metric in metrics)
    prompt_dynamic_chars = sum(metric_int(metric.get("prompt_dynamic_chars")) for metric in metrics)
    completion_tokens = sum(metric_int(metric.get("completion_tokens")) for metric in metrics)
    total_tokens = sum(metric_int(metric.get("total_tokens")) for metric in metrics)
    elapsed_seconds = sum(metric_float(metric.get("elapsed_seconds")) for metric in metrics)
    semantic_call_count = sum(metric_int(metric.get("semantic_call_count")) for metric in metrics)
    calls = [call for metric in metrics for call in as_list(metric.get("calls"))]
    return {
        "semantic_call_count": semantic_call_count,
        "prompt_tokens": prompt_tokens,
        "prompt_cached_tokens": prompt_cached_tokens,
        "prompt_cache_hit_tokens": prompt_cache_hit_tokens,
        "prompt_cache_miss_tokens": prompt_cache_miss_tokens,
        "prompt_stable_chars": prompt_stable_chars,
        "prompt_dynamic_chars": prompt_dynamic_chars,
        "dynamic_to_stable_ratio": ratio(prompt_dynamic_chars, prompt_stable_chars),
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "elapsed_seconds": elapsed_seconds,
        "tokens_per_second": tokens_per_second(completion_tokens, elapsed_seconds),
        "prompt_cache_rate": ratio(prompt_cached_tokens, prompt_tokens),
        "by_contract": summarize_by_contract(calls),
        "calls": calls,
    }


def segment_count(results: list[IngestSourceResult]) -> int:
    return sum(len(result.segments) for result in results)


def segment_status_count(results: list[IngestSourceResult], statuses: set[str]) -> int:
    return sum(1 for result in results for segment in result.segments if str(segment.get("status")) in statuses)


def max_segment_chars(results: list[IngestSourceResult]) -> int:
    chars = [
        int(segment.get("chars") or 0)
        for result in results
        for segment in result.segments
        if isinstance(segment, dict)
    ]
    return max(chars) if chars else 0


def recovery_candidate_count(results: list[IngestSourceResult]) -> int:
    return sum(
        1
        for result in results
        if result.status == "failed"
        and (
            result.error_retryable
            or any(bool(segment.get("error_retryable")) for segment in result.segments)
        )
    )


def ingest_run_metrics(results: list[IngestSourceResult], elapsed_seconds: float) -> dict[str, object]:
    prompt_tokens = 0
    prompt_cached_tokens = 0
    prompt_cache_hit_tokens = 0
    prompt_cache_miss_tokens = 0
    prompt_stable_chars = 0
    prompt_dynamic_chars = 0
    completion_tokens = 0
    total_tokens = 0
    semantic_elapsed = 0.0
    semantic_call_count = 0
    calls: list[object] = []
    for result in results:
        semantic = semantic_metrics(result)
        prompt_tokens += metric_int(semantic.get("prompt_tokens"))
        prompt_cached_tokens += metric_int(semantic.get("prompt_cached_tokens"))
        prompt_cache_hit_tokens += metric_int(semantic.get("prompt_cache_hit_tokens"))
        prompt_cache_miss_tokens += metric_int(semantic.get("prompt_cache_miss_tokens"))
        prompt_stable_chars += metric_int(semantic.get("prompt_stable_chars"))
        prompt_dynamic_chars += metric_int(semantic.get("prompt_dynamic_chars"))
        completion_tokens += metric_int(semantic.get("completion_tokens"))
        total_tokens += metric_int(semantic.get("total_tokens"))
        semantic_elapsed += metric_float(semantic.get("elapsed_seconds"))
        semantic_call_count += metric_int(semantic.get("semantic_call_count"))
        calls.extend(as_list(semantic.get("calls")))
    return {
        "elapsed_seconds": elapsed_seconds,
        "semantic": {
            "semantic_call_count": semantic_call_count,
            "prompt_tokens": prompt_tokens,
            "prompt_cached_tokens": prompt_cached_tokens,
            "prompt_cache_hit_tokens": prompt_cache_hit_tokens,
            "prompt_cache_miss_tokens": prompt_cache_miss_tokens,
            "prompt_stable_chars": prompt_stable_chars,
            "prompt_dynamic_chars": prompt_dynamic_chars,
            "dynamic_to_stable_ratio": ratio(prompt_dynamic_chars, prompt_stable_chars),
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "elapsed_seconds": semantic_elapsed,
            "tokens_per_second": tokens_per_second(completion_tokens, semantic_elapsed),
            "prompt_cache_rate": ratio(prompt_cached_tokens, prompt_tokens),
            "by_contract": summarize_by_contract(calls),
            "calls": calls,
        },
    }


def semantic_metrics(result: IngestSourceResult) -> dict[str, object]:
    context_semantic = as_dict(result.context.get("semantic_metrics"))
    if context_semantic:
        return context_semantic
    metrics_semantic = as_dict(result.metrics.get("semantic"))
    return metrics_semantic


def source_processed(result: IngestSourceResult) -> bool:
    return result.semantic_result is not None or any(as_dict(segment).get("relation_operations") for segment in result.segments)


def tokens_per_second(completion_tokens: int, elapsed_seconds: float) -> float | None:
    if completion_tokens <= 0 or elapsed_seconds <= 0:
        return None
    return completion_tokens / elapsed_seconds


def summarize_by_contract(calls: list[object]) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, object]] = {}
    order: list[str] = []
    for raw_call in calls:
        call = as_dict(raw_call)
        name = str(call.get("contract_name") or "unknown")
        if name not in grouped:
            order.append(name)
            grouped[name] = {
                "contract_name": name,
                "semantic_call_count": 0,
                "prompt_tokens": 0,
                "prompt_cached_tokens": 0,
                "prompt_cache_hit_tokens": 0,
                "prompt_cache_miss_tokens": 0,
                "prompt_stable_chars": 0,
                "prompt_dynamic_chars": 0,
                "dynamic_to_stable_ratio": None,
                "completion_tokens": 0,
                "total_tokens": 0,
                "elapsed_seconds": 0.0,
                "tokens_per_second": None,
                "prompt_cache_rate": None,
            }
        item = grouped[name]
        item["semantic_call_count"] = metric_int(item.get("semantic_call_count")) + 1
        for key in (
            "prompt_tokens",
            "prompt_cached_tokens",
            "prompt_cache_hit_tokens",
            "prompt_cache_miss_tokens",
            "prompt_stable_chars",
            "prompt_dynamic_chars",
            "completion_tokens",
            "total_tokens",
        ):
            item[key] = metric_int(item.get(key)) + metric_int(call.get(key))
        item["elapsed_seconds"] = metric_float(item.get("elapsed_seconds")) + metric_float(call.get("elapsed_seconds"))
    for item in grouped.values():
        item["tokens_per_second"] = tokens_per_second(metric_int(item.get("completion_tokens")), metric_float(item.get("elapsed_seconds")))
        item["prompt_cache_rate"] = ratio(metric_int(item.get("prompt_cached_tokens")), metric_int(item.get("prompt_tokens")))
        item["dynamic_to_stable_ratio"] = ratio(metric_int(item.get("prompt_dynamic_chars")), metric_int(item.get("prompt_stable_chars")))
    return [grouped[name] for name in order]


def ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def metric_int(value: object) -> int:
    return value if isinstance(value, int) else 0


def metric_float(value: object) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0


def as_dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []
