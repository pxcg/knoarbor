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


def fmt_percent(value: object) -> str:
    if isinstance(value, (int, float)):
        return f"{float(value) * 100:.1f}%"
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
        f"- prompt_cache_rate: {fmt_percent(semantic_metrics.get('prompt_cache_rate'))}",
    ]


def semantic_token_report_lines(semantic_metrics: dict[str, object], *, max_calls: int = 20) -> list[str]:
    lines = [
        "## Semantic Token Usage",
        "",
        f"- semantic_calls: {semantic_metrics.get('semantic_call_count', 0)}",
        f"- prompt_tokens: {semantic_metrics.get('prompt_tokens', 0)}",
        f"- prompt_cached_tokens: {semantic_metrics.get('prompt_cached_tokens', 0)}",
        f"- prompt_cache_rate: {fmt_percent(semantic_metrics.get('prompt_cache_rate'))}",
        f"- completion_tokens: {semantic_metrics.get('completion_tokens', 0)}",
        f"- total_tokens: {semantic_metrics.get('total_tokens', 0)}",
        f"- semantic_elapsed_seconds: {fmt_number(semantic_metrics.get('elapsed_seconds'))}",
        f"- tokens_per_second: {fmt_number(semantic_metrics.get('tokens_per_second'))}",
        "",
    ]
    by_contract = as_list(semantic_metrics.get("by_contract"))
    if by_contract:
        lines.extend(["### By Agent", ""])
        for item in by_contract:
            metric = as_dict(item)
            lines.append(
                f"- `{metric.get('contract_name')}`: "
                f"calls={metric.get('semantic_call_count', 0)}, "
                f"prompt={metric.get('prompt_tokens', 0)}, "
                f"cached={metric.get('prompt_cached_tokens', 0)} ({fmt_percent(metric.get('prompt_cache_rate'))}), "
                f"completion={metric.get('completion_tokens', 0)}, "
                f"total={metric.get('total_tokens', 0)}, "
                f"elapsed={fmt_number(metric.get('elapsed_seconds'))}s"
            )
        lines.append("")
    calls = as_list(semantic_metrics.get("calls"))
    if calls:
        lines.extend(["### Calls", ""])
        for index, raw_call in enumerate(calls[:max_calls]):
            call = as_dict(raw_call)
            lines.append(
                f"- [{index}] `{call.get('contract_name')}` "
                f"{call.get('provider')}/{call.get('model')}: "
                f"prompt={call.get('prompt_tokens', 0)}, "
                f"cached={call.get('prompt_cached_tokens', 0)}, "
                f"completion={call.get('completion_tokens', 0)}, "
                f"total={call.get('total_tokens', 0)}, "
                f"elapsed={fmt_number(call.get('elapsed_seconds'))}s"
            )
        if len(calls) > max_calls:
            lines.append(f"- ... {len(calls) - max_calls} additional call(s) omitted from report detail.")
        lines.append("")
    return lines
