from __future__ import annotations

from datetime import datetime
from pathlib import Path

from knoarbor.core.schemas.wiki_query import WikiSearchRequest, WikiSearchResponse
from knoarbor.storage.wiki_index import relative_wiki_path
from knoarbor.audit.reports import write_maintenance_report


def write_query_report(vault_path: Path, request: WikiSearchRequest, response: WikiSearchResponse) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    report_path = write_maintenance_report(
        vault_path,
        "query",
        render_query_report(request, response, timestamp),
        f"maintenance/reports/query/query_report_{timestamp}.md",
    )
    return relative_wiki_path(vault_path, report_path)


def render_query_report(request: WikiSearchRequest, response: WikiSearchResponse, run_id: str) -> str:
    lines = [
        "# Query Report",
        "",
        f"- run_id: {run_id}",
        f"- created_at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- query: {response.query}",
        f"- mode: {request.mode}",
        f"- retrieval_mode: {response.retrieval_mode}",
        f"- returned_count: {len(response.results)}",
        f"- context_pack_chars: {response.stats.get('context_pack_chars', 0)}",
        f"- context_pack_truncated: {response.stats.get('context_pack_truncated', False)}",
        "",
        "## Results",
        "",
    ]
    if not response.results:
        lines.append("- No results returned.")
    for index, item in enumerate(response.results, start=1):
        lines.extend(
            [
                f"### {index}. {item.title}",
                "",
                f"- path: {item.path}",
                f"- match_kind: {item.match_kind}",
                f"- relevance: {item.relevance}",
                f"- score: {item.score}",
                f"- matched_fields: {', '.join(item.matched_fields) if item.matched_fields else 'none'}",
                f"- reason: {item.reason}",
                "",
            ]
        )
        if item.summary:
            lines.extend(["Summary:", "", item.summary, ""])
        if item.excerpts:
            lines.append("Excerpts:")
            for excerpt in item.excerpts[:3]:
                lines.append(f"- {excerpt.section}: {excerpt.content}")
            lines.append("")

    lines.extend(["## Response Guidance", ""])
    if response.response_guidance:
        lines.extend(f"- {item}" for item in response.response_guidance)
    else:
        lines.append("- No response guidance.")
    lines.append("")

    lines.extend(["## Gap Signals", ""])
    if response.gap_suggestions:
        for gap in response.gap_suggestions:
            lines.append(f"- {gap.kind}: {gap.reason} ({gap.recommended_action})")
    elif response.gaps:
        lines.extend(f"- {gap}" for gap in response.gaps)
    else:
        lines.append("- No gap signals.")

    lines.extend(["", "## Trace", ""])
    for key, value in sorted(response.trace.items()):
        lines.append(f"- {key}: {value}")

    lines.extend(["", "## Context Pack", "", "```text", response.context_pack, "```"])
    return "\n".join(lines).strip() + "\n"
