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
        f"- prompt_stable_chars: {semantic_metrics.get('prompt_stable_chars', 0)}",
        f"- prompt_dynamic_chars: {semantic_metrics.get('prompt_dynamic_chars', 0)}",
        f"- dynamic_to_stable_ratio: {fmt_number(semantic_metrics.get('dynamic_to_stable_ratio'))}",
        f"- completion_tokens: {semantic_metrics.get('completion_tokens', 0)}",
        f"- total_tokens: {semantic_metrics.get('total_tokens', 0)}",
        f"- semantic_elapsed_seconds: {fmt_number(semantic_metrics.get('elapsed_seconds'))}",
        f"- tokens_per_second: {fmt_number(semantic_metrics.get('tokens_per_second'))}",
        "",
    ]
    if int(semantic_metrics.get("payload_char_total") or 0) > 0:
        lines.insert(9, f"- payload_char_total: {semantic_metrics.get('payload_char_total', 0)}")
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
                f"dynamic/stable={fmt_number(metric.get('dynamic_to_stable_ratio'))}, "
                f"completion={metric.get('completion_tokens', 0)}, "
                f"total={metric.get('total_tokens', 0)}, "
                f"elapsed={fmt_number(metric.get('elapsed_seconds'))}s"
            )
        lines.append("")
    payload_breakdown = as_dict(semantic_metrics.get("payload_char_breakdown"))
    if payload_breakdown:
        lines.extend(["### Dynamic Payload Fields", ""])
        for key, value in sorted(payload_breakdown.items(), key=lambda item: int(item[1] or 0), reverse=True)[:20]:
            lines.append(f"- `{key}`: {value} chars")
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
                f"dynamic/stable={fmt_number(call.get('dynamic_to_stable_ratio'))}, "
                f"payload={call.get('payload_char_total', 0)} chars"
                f"{_top_payload_suffix(call)}, "
                f"completion={call.get('completion_tokens', 0)}, "
                f"total={call.get('total_tokens', 0)}, "
                f"elapsed={fmt_number(call.get('elapsed_seconds'))}s"
            )
        if len(calls) > max_calls:
            lines.append(f"- ... {len(calls) - max_calls} additional call(s) omitted from report detail.")
        lines.append("")
        diagnostics = _semantic_cache_diagnostics(calls)
        if diagnostics:
            lines.extend(["### Cache Diagnostics", "", *diagnostics, ""])
    return lines


def _top_payload_suffix(call: dict[str, Any]) -> str:
    field = call.get("payload_top_field")
    return f" (top={field})" if field else ""


def _semantic_cache_diagnostics(calls: list[Any]) -> list[str]:
    low_cache: list[str] = []
    high_dynamic: list[str] = []
    for index, raw_call in enumerate(calls):
        call = as_dict(raw_call)
        prompt_tokens = int(call.get("prompt_tokens") or 0)
        if prompt_tokens > 0:
            cached_tokens = int(call.get("prompt_cached_tokens") or 0)
            cache_rate = cached_tokens / prompt_tokens
            if cache_rate < 0.2:
                low_cache.append(f"- low_cache_call [{index}] `{call.get('contract_name')}` cache_rate={fmt_percent(cache_rate)}")
        stable_chars = int(call.get("prompt_stable_chars") or 0)
        dynamic_chars = int(call.get("prompt_dynamic_chars") or 0)
        if stable_chars > 0:
            dynamic_ratio = dynamic_chars / stable_chars
            if dynamic_ratio >= 3.0:
                high_dynamic.append(f"- high_dynamic_call [{index}] `{call.get('contract_name')}` dynamic/stable={fmt_number(dynamic_ratio)}")
    return [*low_cache[:10], *high_dynamic[:10]]
