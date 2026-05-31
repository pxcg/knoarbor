from __future__ import annotations

from typing import Any


def summarize_semantic_runs(runs: list[Any]) -> dict[str, object]:
    prompt_tokens = 0
    prompt_cached_tokens = 0
    prompt_cache_hit_tokens = 0
    prompt_cache_miss_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    elapsed_seconds = 0.0
    calls: list[dict[str, object]] = []
    for run in runs:
        metrics = getattr(run, "metrics", {}) or {}
        prompt_tokens += _int(metrics.get("prompt_tokens"))
        prompt_cached_tokens += _int(metrics.get("prompt_cached_tokens"))
        prompt_cache_hit_tokens += _int(metrics.get("prompt_cache_hit_tokens"))
        prompt_cache_miss_tokens += _int(metrics.get("prompt_cache_miss_tokens"))
        completion_tokens += _int(metrics.get("completion_tokens"))
        total_tokens += _int(metrics.get("total_tokens"))
        elapsed_seconds += _float(metrics.get("elapsed_seconds"))
        calls.append(
            {
                "contract_name": getattr(run, "contract_name", None),
                "schema_version": getattr(run, "schema_version", None),
                "provider": metrics.get("provider"),
                "model": metrics.get("model"),
                "prompt_tokens": _int(metrics.get("prompt_tokens")),
                "prompt_cached_tokens": _int(metrics.get("prompt_cached_tokens")),
                "prompt_cache_hit_tokens": _int(metrics.get("prompt_cache_hit_tokens")),
                "prompt_cache_miss_tokens": _int(metrics.get("prompt_cache_miss_tokens")),
                "completion_tokens": _int(metrics.get("completion_tokens")),
                "total_tokens": _int(metrics.get("total_tokens")),
                "elapsed_seconds": _float(metrics.get("elapsed_seconds")),
                "tokens_per_second": metrics.get("tokens_per_second"),
            }
        )
    return {
        "semantic_call_count": len(calls),
        "prompt_tokens": prompt_tokens,
        "prompt_cached_tokens": prompt_cached_tokens,
        "prompt_cache_hit_tokens": prompt_cache_hit_tokens,
        "prompt_cache_miss_tokens": prompt_cache_miss_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "elapsed_seconds": elapsed_seconds,
        "tokens_per_second": _tokens_per_second(completion_tokens, elapsed_seconds),
        "calls": calls,
    }


def empty_run_metrics(elapsed_seconds: float = 0.0) -> dict[str, object]:
    return {
        "elapsed_seconds": elapsed_seconds,
        "semantic": summarize_semantic_runs([]),
    }


def _tokens_per_second(completion_tokens: int, elapsed_seconds: float) -> float | None:
    if completion_tokens <= 0 or elapsed_seconds <= 0:
        return None
    return completion_tokens / elapsed_seconds


def _int(value: object) -> int:
    return value if isinstance(value, int) else 0


def _float(value: object) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0
