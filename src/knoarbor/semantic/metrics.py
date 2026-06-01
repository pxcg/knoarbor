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
    by_contract = _summarize_by_contract(calls)
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
        "prompt_cache_rate": _ratio(prompt_cached_tokens, prompt_tokens),
        "by_contract": by_contract,
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


def _summarize_by_contract(calls: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, object]] = {}
    order: list[str] = []
    for call in calls:
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
                "completion_tokens": 0,
                "total_tokens": 0,
                "elapsed_seconds": 0.0,
                "tokens_per_second": None,
                "prompt_cache_rate": None,
            }
        item = grouped[name]
        item["semantic_call_count"] = _int(item.get("semantic_call_count")) + 1
        for key in (
            "prompt_tokens",
            "prompt_cached_tokens",
            "prompt_cache_hit_tokens",
            "prompt_cache_miss_tokens",
            "completion_tokens",
            "total_tokens",
        ):
            item[key] = _int(item.get(key)) + _int(call.get(key))
        item["elapsed_seconds"] = _float(item.get("elapsed_seconds")) + _float(call.get("elapsed_seconds"))
    for item in grouped.values():
        item["tokens_per_second"] = _tokens_per_second(_int(item.get("completion_tokens")), _float(item.get("elapsed_seconds")))
        item["prompt_cache_rate"] = _ratio(_int(item.get("prompt_cached_tokens")), _int(item.get("prompt_tokens")))
    return [grouped[name] for name in order]


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _int(value: object) -> int:
    return value if isinstance(value, int) else 0


def _float(value: object) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0
