from __future__ import annotations

from typing import Any


def summarize_semantic_runs(runs: list[Any]) -> dict[str, object]:
    prompt_tokens = 0
    prompt_cached_tokens = 0
    prompt_cache_hit_tokens = 0
    prompt_cache_miss_tokens = 0
    prompt_stable_chars = 0
    prompt_dynamic_chars = 0
    payload_char_total = 0
    payload_char_breakdown: dict[str, int] = {}
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
        prompt_stable_chars += _int(metrics.get("prompt_stable_chars"))
        prompt_dynamic_chars += _int(metrics.get("prompt_dynamic_chars"))
        payload_char_total += _int(metrics.get("payload_char_total"))
        for key, value in _dict(metrics.get("payload_char_breakdown")).items():
            payload_char_breakdown[key] = payload_char_breakdown.get(key, 0) + _int(value)
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
                "prompt_stable_chars": _int(metrics.get("prompt_stable_chars")),
                "prompt_dynamic_chars": _int(metrics.get("prompt_dynamic_chars")),
                "dynamic_to_stable_ratio": _ratio(_int(metrics.get("prompt_dynamic_chars")), _int(metrics.get("prompt_stable_chars"))),
                "payload_char_total": _int(metrics.get("payload_char_total")),
                "payload_top_field": metrics.get("payload_top_field"),
                "payload_char_breakdown": _dict(metrics.get("payload_char_breakdown")),
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
        "prompt_stable_chars": prompt_stable_chars,
        "prompt_dynamic_chars": prompt_dynamic_chars,
        "dynamic_to_stable_ratio": _ratio(prompt_dynamic_chars, prompt_stable_chars),
        "payload_char_total": payload_char_total,
        "payload_char_breakdown": payload_char_breakdown,
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
                "prompt_stable_chars": 0,
                "prompt_dynamic_chars": 0,
                "payload_char_total": 0,
                "payload_char_breakdown": {},
                "dynamic_to_stable_ratio": None,
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
            "prompt_stable_chars",
            "prompt_dynamic_chars",
            "completion_tokens",
            "total_tokens",
            "payload_char_total",
        ):
            item[key] = _int(item.get(key)) + _int(call.get(key))
        for field, value in _dict(call.get("payload_char_breakdown")).items():
            breakdown = _dict(item.get("payload_char_breakdown"))
            breakdown[field] = _int(breakdown.get(field)) + _int(value)
            item["payload_char_breakdown"] = breakdown
        item["elapsed_seconds"] = _float(item.get("elapsed_seconds")) + _float(call.get("elapsed_seconds"))
    for item in grouped.values():
        item["tokens_per_second"] = _tokens_per_second(_int(item.get("completion_tokens")), _float(item.get("elapsed_seconds")))
        item["prompt_cache_rate"] = _ratio(_int(item.get("prompt_cached_tokens")), _int(item.get("prompt_tokens")))
        item["dynamic_to_stable_ratio"] = _ratio(_int(item.get("prompt_dynamic_chars")), _int(item.get("prompt_stable_chars")))
    return [grouped[name] for name in order]


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _int(value: object) -> int:
    return value if isinstance(value, int) else 0


def _float(value: object) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0


def _dict(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {str(key): _int(item) for key, item in value.items()}
