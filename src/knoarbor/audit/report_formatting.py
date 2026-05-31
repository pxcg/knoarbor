from __future__ import annotations

from typing import Any


def as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: object) -> list[Any]:
    return value if isinstance(value, list) else []


def fmt_number(value: object) -> str:
    if isinstance(value, (int, float)):
        return f"{float(value):.2f}"
    return "n/a"


def format_list(items: list[Any]) -> str:
    values = [str(item) for item in items if str(item)]
    return ", ".join(values) if values else "none"


def cache_metric_lines(semantic_metrics: dict[str, object]) -> list[str]:
    if not any(
        int(semantic_metrics.get(key) or 0)
        for key in ("prompt_cached_tokens", "prompt_cache_hit_tokens", "prompt_cache_miss_tokens")
    ):
        return []
    return [
        f"- prompt_cached_tokens: {semantic_metrics.get('prompt_cached_tokens', 0)}",
        f"- prompt_cache_hit_tokens: {semantic_metrics.get('prompt_cache_hit_tokens', 0)}",
        f"- prompt_cache_miss_tokens: {semantic_metrics.get('prompt_cache_miss_tokens', 0)}",
    ]
