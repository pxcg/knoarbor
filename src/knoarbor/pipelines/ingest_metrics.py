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
    completion_tokens = sum(metric_int(metric.get("completion_tokens")) for metric in metrics)
    total_tokens = sum(metric_int(metric.get("total_tokens")) for metric in metrics)
    elapsed_seconds = sum(metric_float(metric.get("elapsed_seconds")) for metric in metrics)
    semantic_call_count = sum(metric_int(metric.get("semantic_call_count")) for metric in metrics)
    return {
        "semantic_call_count": semantic_call_count,
        "prompt_tokens": prompt_tokens,
        "prompt_cached_tokens": prompt_cached_tokens,
        "prompt_cache_hit_tokens": prompt_cache_hit_tokens,
        "prompt_cache_miss_tokens": prompt_cache_miss_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "elapsed_seconds": elapsed_seconds,
        "tokens_per_second": tokens_per_second(completion_tokens, elapsed_seconds),
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
    completion_tokens = 0
    total_tokens = 0
    semantic_elapsed = 0.0
    semantic_call_count = 0
    for result in results:
        semantic = semantic_metrics(result)
        prompt_tokens += metric_int(semantic.get("prompt_tokens"))
        prompt_cached_tokens += metric_int(semantic.get("prompt_cached_tokens"))
        prompt_cache_hit_tokens += metric_int(semantic.get("prompt_cache_hit_tokens"))
        prompt_cache_miss_tokens += metric_int(semantic.get("prompt_cache_miss_tokens"))
        completion_tokens += metric_int(semantic.get("completion_tokens"))
        total_tokens += metric_int(semantic.get("total_tokens"))
        semantic_elapsed += metric_float(semantic.get("elapsed_seconds"))
        semantic_call_count += metric_int(semantic.get("semantic_call_count"))
    return {
        "elapsed_seconds": elapsed_seconds,
        "semantic": {
            "semantic_call_count": semantic_call_count,
            "prompt_tokens": prompt_tokens,
            "prompt_cached_tokens": prompt_cached_tokens,
            "prompt_cache_hit_tokens": prompt_cache_hit_tokens,
            "prompt_cache_miss_tokens": prompt_cache_miss_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "elapsed_seconds": semantic_elapsed,
            "tokens_per_second": tokens_per_second(completion_tokens, semantic_elapsed),
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


def metric_int(value: object) -> int:
    return value if isinstance(value, int) else 0


def metric_float(value: object) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0


def as_dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}
