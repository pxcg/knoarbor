from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from knoarbor.audit.reports import write_maintenance_report
from knoarbor.core.config import PrivacyConfig
from knoarbor.core.schemas.wiki_lint import WikiLintCandidatePage, WikiLintFix, WikiLintIssue, WikiScanPage
from knoarbor.maintenance.lint_candidates import scan_page, score_lint_candidate
from knoarbor.maintenance.lint_collection import collect_pages, filter_lint_scope
from knoarbor.maintenance.lint_scanners import lint_collected_pages


def lint_vault(
    vault_path: Path,
    scope_pages: list[str] | None = None,
    include_related: bool = True,
    privacy_config: PrivacyConfig | None = None,
) -> tuple[list[WikiLintIssue], dict[str, Any]]:
    pages = collect_pages(vault_path)
    issues, stats = lint_collected_pages(vault_path, pages, privacy_config=privacy_config)
    _scoped_pages, scoped_issues, scoped_stats = filter_lint_scope(pages, issues, stats, scope_pages or [], include_related)
    return scoped_issues, scoped_stats


def scan_vault(
    vault_path: Path,
    max_chars_per_page: int,
    scope_pages: list[str] | None = None,
    include_related: bool = True,
    privacy_config: PrivacyConfig | None = None,
) -> tuple[list[WikiScanPage], list[WikiLintIssue], dict[str, Any]]:
    pages = collect_pages(vault_path)
    issues, stats = lint_collected_pages(vault_path, pages, privacy_config=privacy_config)
    pages, issues, stats = filter_lint_scope(pages, issues, stats, scope_pages or [], include_related)
    stats = {
        **stats,
        "scan_max_chars_per_page": max_chars_per_page,
    }
    return [scan_page(page, max_chars_per_page) for page in pages], issues, stats


def select_lint_candidates(
    vault_path: Path,
    mode: str,
    max_candidates: int,
    max_chars_per_page: int,
    scope_pages: list[str] | None = None,
    include_related: bool = True,
    privacy_config: PrivacyConfig | None = None,
) -> tuple[list[WikiLintCandidatePage], dict[str, Any], list[str]]:
    pages, issues, scan_stats = scan_vault(
        vault_path,
        max_chars_per_page,
        scope_pages=scope_pages or [],
        include_related=include_related,
        privacy_config=privacy_config,
    )
    issues_by_path: dict[str, list[WikiLintIssue]] = defaultdict(list)
    for issue in issues:
        issues_by_path[issue.path].append(issue)

    candidates = [score_lint_candidate(page, issues_by_path.get(page.path, [])) for page in pages if page.directory != "maintenance"]
    candidates = [candidate for candidate in candidates if candidate.score > 0]
    candidates.sort(key=lambda item: (-item.score, item.directory, item.path))

    stats = {
        **scan_stats,
        "candidate_count": len(candidates),
        "returned_candidate_count": min(len(candidates), max_candidates) if max_candidates else len(candidates),
        "candidate_mode": mode,
    }
    warnings: list[str] = []
    warnings.append("Semantic candidates are deterministic routing hints; model review decides whether maintenance is needed.")
    return candidates[:max_candidates] if max_candidates else candidates, stats, warnings


def build_fix_plan(issues: list[WikiLintIssue]) -> list[WikiLintFix]:
    fixes: list[WikiLintFix] = []
    for issue in issues:
        fixes.append(_fix_for_issue(issue))
    return fixes


def render_lint_report(issues: list[WikiLintIssue], stats: dict[str, Any], fixes: list[WikiLintFix] | None = None) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    fixes = fixes or []
    graph_health = stats.get("graph_health") if isinstance(stats.get("graph_health"), dict) else {}
    lines = [
        "# Lint Report",
        "",
        f"- created: {now}",
        f"- pages: {stats['page_count']}",
        f"- issues: {stats['issue_count']}",
        f"- errors: {stats['error_count']}",
        f"- warnings: {stats['warning_count']}",
        f"- info: {stats['info_count']}",
        f"- graph_components: {graph_health.get('component_count', 'n/a')}",
        f"- graph_largest_component: {graph_health.get('largest_component_size', 'n/a')}",
        f"- graph_isolated_pages: {graph_health.get('isolated_page_count', 'n/a')}",
        "",
        "## Directory Counts",
        "",
    ]
    for directory, count in sorted(stats["directories"].items()):
        lines.append(f"- {directory}: {count}")

    lines.extend(["", "## Issues", ""])
    if not issues:
        lines.append("- No issues found.")
    else:
        for issue in sorted(issues, key=lambda item: (item.severity, item.code, item.path)):
            detail_text = _format_details(issue.details)
            suffix = f" ({detail_text})" if detail_text else ""
            lines.append(f"- [{issue.severity}] `{issue.code}` in `{issue.path}`: {issue.message}{suffix}")

    lines.extend(["", "## Suggested Actions", ""])
    if not fixes:
        lines.append("- No suggested actions.")
    else:
        for fix in sorted(fixes, key=lambda item: (item.mode, item.action, item.path)):
            lines.append(f"- [{fix.mode}] `{fix.action}` for `{fix.path}`: {fix.description}")

    return "\n".join(lines).rstrip() + "\n"


def write_lint_report(vault_path: Path, content: str, report_path: str | None = None) -> Path:
    return write_maintenance_report(vault_path, "lint", content, report_path)


def _fix_for_issue(issue: WikiLintIssue) -> WikiLintFix:
    if issue.code in {"missing_machine_index", "stale_machine_index"}:
        return WikiLintFix(
            issue_code=issue.code,
            path=issue.path,
            action="rebuild_index",
            mode="safe_auto",
            description="Rebuild the derived machine index through the publication lifecycle.",
        )
    if issue.code == "unexpected_markdown_location":
        return WikiLintFix(
            issue_code=issue.code,
            path=issue.path,
            action="ingest_or_move_source",
            mode="manual",
            description="Move this file into raw/inbox/notes and ingest it, or relocate it to a schema-defined generated-page directory with valid frontmatter.",
        )
    if issue.code == "orphan_page":
        return WikiLintFix(
            issue_code=issue.code,
            path=issue.path,
            action="review_relationships",
            mode="manual",
            description="Review whether this page should be linked from a source, entity, concept, query, or index-facing hub page.",
        )
    if issue.code == "broken_wikilink":
        return WikiLintFix(
            issue_code=issue.code,
            path=issue.path,
            action="repair_wikilink",
            mode="manual",
            description="Update the link target to an existing page or create the missing page through ingest.",
        )
    if issue.code == "ambiguous_wikilink":
        return WikiLintFix(
            issue_code=issue.code,
            path=issue.path,
            action="disambiguate_wikilink",
            mode="manual",
            description="Replace the ambiguous link with a path-qualified wikilink.",
        )
    if issue.code in {"missing_frontmatter", "missing_frontmatter_keys"}:
        return WikiLintFix(
            issue_code=issue.code,
            path=issue.path,
            action="projection_rebuild_request",
            mode="manual",
            description="Repair page identity metadata before rerunning lint.",
        )
    if issue.code == "missing_required_section":
        return WikiLintFix(
            issue_code=issue.code,
            path=issue.path,
            action="projection_rebuild_request",
            mode="manual",
            description="Add the missing standard section through reviewed deterministic wiki operation.",
        )
    if issue.code in {"duplicate_title", "duplicate_content_hash", "path_alias_conflict"}:
        return WikiLintFix(
            issue_code=issue.code,
            path=issue.path,
            action="review_duplicate",
            mode="manual",
            description="Review duplicate pages and decide whether to merge, rename, or keep both.",
        )
    if issue.code in {"weak_link_graph", "overdense_link_graph"}:
        return WikiLintFix(
            issue_code=issue.code,
            path=issue.path,
            action="review_graph_density",
            mode="manual",
            description="Review whether this page needs contextual links, relationship pruning, or a hub page.",
        )
    if issue.code in {
        "missing_raw_source",
        "source_without_knowledge_links",
        "knowledge_without_source_record",
        "knowledge_missing_source_record_link",
    }:
        return WikiLintFix(
            issue_code=issue.code,
            path=issue.path,
            action="reingest_request",
            mode="manual",
            description="Review source provenance and connect the source record to generated knowledge pages.",
        )
    if issue.code == "privacy_sensitive_content":
        return WikiLintFix(
            issue_code=issue.code,
            path=issue.path,
            action="report_only",
            mode="manual",
            description="Report sensitive material to the owning source lifecycle without rewriting a projection.",
        )
    if issue.code == "duplicate_section_item":
        return WikiLintFix(
            issue_code=issue.code,
            path=issue.path,
            action="projection_rebuild_request",
            mode="manual",
            description="Rebuild the generated projection from canonical facts.",
        )
    if issue.code == "adjacent_duplicate_heading":
        return WikiLintFix(
            issue_code=issue.code,
            path=issue.path,
            action="projection_rebuild_request",
            mode="manual",
            description="Rebuild the generated projection from canonical facts.",
        )
    if issue.code.startswith(("atom_", "canonical_", "evidence_")):
        return WikiLintFix(
            issue_code=issue.code,
            path=issue.path,
            action="reingest_request",
            mode="manual",
            description="Rerun ingest or semantic maintenance so page metadata and the atom index agree.",
        )
    if issue.code.startswith("projection_"):
        return WikiLintFix(
            issue_code=issue.code,
            path=issue.path,
            action="projection_rebuild_request",
            mode="manual",
            description="Rebuild the generated projection from the active canonical source revision.",
        )
    return WikiLintFix(
        issue_code=issue.code,
        path=issue.path,
        action="manual_review",
        mode="manual",
        description="Review this lint issue manually.",
    )
def _format_details(details: dict[str, Any]) -> str:
    if not details:
        return ""
    parts = []
    for key, value in sorted(details.items()):
        parts.append(f"{key}: {value}")
    return "; ".join(parts)
