from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from knoarbor.audit.reports import write_maintenance_report
from knoarbor.core.schemas.wiki_lint import (
    WikiLintCandidatePage,
    WikiLintCandidateReason,
    WikiLintCandidateSeverity,
    WikiLintCandidateSource,
    WikiLintFix,
    WikiLintIssue,
    WikiScanPage,
)
from knoarbor.core.markdown import adjacent_duplicate_headings, extract_heading, extract_list_items, extract_section, parse_frontmatter
from knoarbor.core.wiki_schema import (
    FRONTMATTER_TYPES,
    INDEX_EXCLUDED_DIRS,
    PAGE_TYPE_ORDER,
    SYSTEM_PAGE_DIRS,
    is_index_excluded_file,
)
from knoarbor.maintenance.lint_models import LintPage
from knoarbor.maintenance.lint_rules import (
    IGNORED_LINK_PREFIXES,
    KNOWLEDGE_DIRS,
    OVERDENSE_LINK_THRESHOLD,
    OVERDENSE_RELATED_THRESHOLD,
    REQUIRED_FRONTMATTER_KEYS,
    REQUIRED_SECTIONS_BY_DIR,
    WEAK_GRAPH_DIRS,
)
from knoarbor.storage import update_index


def lint_vault(
    vault_path: Path,
    scope_pages: list[str] | None = None,
    include_related: bool = True,
) -> tuple[list[WikiLintIssue], dict[str, Any]]:
    pages = _collect_pages(vault_path)
    issues, stats = _lint_collected_pages(vault_path, pages)
    _scoped_pages, scoped_issues, scoped_stats = _filter_lint_scope(pages, issues, stats, scope_pages or [], include_related)
    return scoped_issues, scoped_stats


def scan_vault(
    vault_path: Path,
    max_chars_per_page: int,
    scope_pages: list[str] | None = None,
    include_related: bool = True,
) -> tuple[list[WikiScanPage], list[WikiLintIssue], dict[str, Any]]:
    pages = _collect_pages(vault_path)
    issues, stats = _lint_collected_pages(vault_path, pages)
    pages, issues, stats = _filter_lint_scope(pages, issues, stats, scope_pages or [], include_related)
    stats = {
        **stats,
        "scan_max_chars_per_page": max_chars_per_page,
    }
    return [_scan_page(page, max_chars_per_page) for page in pages], issues, stats


def select_lint_candidates(
    vault_path: Path,
    mode: str,
    max_candidates: int,
    max_chars_per_page: int,
) -> tuple[list[WikiLintCandidatePage], dict[str, Any], list[str]]:
    pages, issues, scan_stats = scan_vault(vault_path, max_chars_per_page)
    issues_by_path: dict[str, list[WikiLintIssue]] = defaultdict(list)
    for issue in issues:
        issues_by_path[issue.path].append(issue)

    candidates = [
        _score_lint_candidate(page, issues_by_path.get(page.path, []), mode)
        for page in pages
        if page.directory != "maintenance"
    ]
    candidates = [candidate for candidate in candidates if candidate.score > 0]
    candidates.sort(key=lambda item: (-item.score, item.directory, item.path))

    stats = {
        **scan_stats,
        "candidate_count": len(candidates),
        "returned_candidate_count": min(len(candidates), max_candidates),
        "candidate_mode": mode,
    }
    warnings: list[str] = []
    if mode in {"quality", "full"}:
        warnings.append("Quality candidates are deterministic routing hints; semantic judgement belongs to the Quality Diagnose Agent.")
    if mode in {"freshness", "full"}:
        warnings.append("Freshness candidates identify pages that may need review; online verification belongs to a refresh workflow.")
    return candidates[:max_candidates], stats, warnings


def _lint_collected_pages(vault_path: Path, pages: list[LintPage]) -> tuple[list[WikiLintIssue], dict[str, Any]]:
    issues: list[WikiLintIssue] = []

    issues.extend(_lint_unexpected_markdown(vault_path))
    issues.extend(_lint_page_structure(pages))
    issues.extend(_lint_adjacent_duplicate_headings(pages))
    issues.extend(_lint_index_coverage(vault_path, pages))
    issues.extend(_lint_duplicate_identity(pages))
    issues.extend(_lint_links(pages))
    issues.extend(_lint_graph_shape(pages))
    issues.extend(_lint_related_page_lists(pages))
    issues.extend(_lint_repeated_list_sections(pages))
    issues.extend(_lint_specialized_page_contracts(pages))
    issues.extend(_lint_source_pages(vault_path, pages))

    severity_counts = Counter(issue.severity for issue in issues)
    graph_health = _graph_health_stats(pages)
    stats = {
        "page_count": len(pages),
        "issue_count": len(issues),
        "error_count": severity_counts.get("error", 0),
        "warning_count": severity_counts.get("warning", 0),
        "info_count": severity_counts.get("info", 0),
        "directories": dict(Counter(page.directory for page in pages)),
        "graph_health": graph_health,
    }
    return issues, stats


def _filter_lint_scope(
    pages: list[LintPage],
    issues: list[WikiLintIssue],
    stats: dict[str, Any],
    scope_pages: list[str],
    include_related: bool,
) -> tuple[list[LintPage], list[WikiLintIssue], dict[str, Any]]:
    normalized_scope = {_normalize_scope_path(path) for path in scope_pages if _normalize_scope_path(path)}
    if not normalized_scope:
        return pages, issues, {**stats, "scope": "global", "scoped": False}

    pages_by_relative, pages_by_stem, pages_by_title = _page_lookup_maps(pages)
    selected = _resolve_scope_paths(normalized_scope, pages_by_relative, pages_by_stem, pages_by_title)
    if include_related:
        selected = _expand_related_scope(selected, pages, pages_by_relative, pages_by_stem, pages_by_title)

    selected_pages = [page for page in pages if page.relative_path in selected]
    selected_issues = [issue for issue in issues if issue.path in selected or issue.path == "index.md"]
    severity_counts = Counter(issue.severity for issue in selected_issues)
    scoped_stats = {
        **stats,
        "scope": "pages",
        "scoped": True,
        "requested_scope_pages": sorted(normalized_scope),
        "scope_pages": sorted(selected),
        "scope_page_count": len(selected_pages),
        "scope_include_related": include_related,
        "page_count": len(selected_pages),
        "issue_count": len(selected_issues),
        "error_count": severity_counts.get("error", 0),
        "warning_count": severity_counts.get("warning", 0),
        "info_count": severity_counts.get("info", 0),
        "directories": dict(Counter(page.directory for page in selected_pages)),
        "graph_health": _graph_health_stats(selected_pages),
    }
    return selected_pages, selected_issues, scoped_stats


def _normalize_scope_path(path: str) -> str:
    value = str(path).strip().lstrip("/")
    if not value:
        return ""
    return value if value.endswith(".md") else f"{value}.md"


def _resolve_scope_paths(
    scope_pages: set[str],
    pages_by_relative: dict[str, LintPage],
    pages_by_stem: dict[str, list[LintPage]],
    pages_by_title: dict[str, list[LintPage]],
) -> set[str]:
    resolved_paths: set[str] = set()
    for raw_path in scope_pages:
        target = _normalize_link_target(raw_path)
        resolved = _resolve_link(target, pages_by_relative, pages_by_stem, pages_by_title)
        if len(resolved) == 1:
            resolved_paths.add(resolved[0].relative_path)
        elif raw_path in {f"{key}.md" for key in pages_by_relative}:
            resolved_paths.add(raw_path)
    return resolved_paths


def _expand_related_scope(
    selected: set[str],
    pages: list[LintPage],
    pages_by_relative: dict[str, LintPage],
    pages_by_stem: dict[str, list[LintPage]],
    pages_by_title: dict[str, list[LintPage]],
) -> set[str]:
    expanded = set(selected)
    for page in pages:
        resolved_links = _resolved_paths_from_links(page.links, pages_by_relative, pages_by_stem, pages_by_title)
        if page.relative_path in selected:
            expanded.update(resolved_links)
        if selected.intersection(resolved_links):
            expanded.add(page.relative_path)
    return expanded


def build_fix_plan(issues: list[WikiLintIssue]) -> list[WikiLintFix]:
    fixes: list[WikiLintFix] = []
    for issue in issues:
        fixes.append(_fix_for_issue(issue))
    return fixes


def apply_safe_fixes(vault_path: Path, issues: list[WikiLintIssue]) -> list[WikiLintFix]:
    fixes = build_fix_plan(issues)
    needs_index_rebuild = any(fix.action == "rebuild_index" and fix.mode == "safe_auto" for fix in fixes)
    applied: list[WikiLintFix] = []
    if needs_index_rebuild:
        update_index(vault_path)
        applied.append(
            WikiLintFix(
                issue_code="index_coverage",
                path="index.md",
                action="rebuild_index",
                mode="auto_applied",
                description="Rebuilt index.md from current schema directories.",
            )
        )
    return applied


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


def _scan_page(page: LintPage, max_chars_per_page: int) -> WikiScanPage:
    # scan 输出给 lint planning 使用，只暴露页面结构和有限正文预览，避免一次性塞入整个 vault。
    preview = page.content[:max_chars_per_page] if max_chars_per_page else ""
    metadata = page.metadata
    return WikiScanPage(
        path=page.relative_path,
        directory=page.directory,
        title=page.title,
        page_type=metadata.get("type"),
        status=metadata.get("status"),
        updated=metadata.get("updated") or metadata.get("created"),
        source=metadata.get("source"),
        content_hash=metadata.get("content_hash"),
        tags=_extract_tags_for_scan(page.content, metadata),
        summary=extract_section(page.content, "Summary"),
        headings=_extract_headings(page.content),
        outgoing_links=page.links,
        content_preview=preview,
        content_truncated=len(page.content) > len(preview),
        original_content_length=len(page.content),
    )


def _score_lint_candidate(page: WikiScanPage, issues: list[WikiLintIssue], mode: str) -> WikiLintCandidatePage:
    reasons: list[WikiLintCandidateReason] = []
    if mode in {"quality", "full"}:
        reasons.extend(_quality_candidate_reasons(page, issues))
    if mode in {"freshness", "full"}:
        reasons.extend(_freshness_candidate_reasons(page))

    score = round(sum(reason.score for reason in reasons), 3)
    return WikiLintCandidatePage(
        path=page.path,
        directory=page.directory,
        title=page.title,
        page_type=page.page_type,
        updated=page.updated,
        source=page.source,
        summary=page.summary,
        tags=page.tags,
        headings=page.headings,
        outgoing_links=page.outgoing_links,
        content_preview=page.content_preview,
        content_truncated=page.content_truncated,
        original_content_length=page.original_content_length,
        score=score,
        reasons=reasons,
    )


def _quality_candidate_reasons(page: WikiScanPage, issues: list[WikiLintIssue]) -> list[WikiLintCandidateReason]:
    reasons: list[WikiLintCandidateReason] = []
    headings = {heading.strip().lower() for heading in page.headings}

    if not page.summary.strip():
        reasons.append(_candidate_reason("quality", "missing_summary", "medium", "Page has no Summary section content.", 1.4))
    if "key points" not in headings:
        reasons.append(_candidate_reason("quality", "missing_key_points", "low", "Page has no Key Points section.", 0.8))
    if "related pages" not in headings:
        reasons.append(_candidate_reason("graph", "missing_related_pages_section", "low", "Page has no Related Pages section.", 0.7))
    if page.original_content_length < 900 and page.directory != "sources":
        reasons.append(
            _candidate_reason(
                "quality",
                "shallow_page",
                "medium",
                "Generated knowledge page is short enough to warrant completeness review.",
                1.1,
                {"original_content_length": page.original_content_length},
            )
        )
    if page.original_content_length > 12000:
        reasons.append(
            _candidate_reason(
                "quality",
                "long_page",
                "low",
                "Page is long and may need structure or duplication review.",
                0.6,
                {"original_content_length": page.original_content_length},
            )
        )
    if _recently_updated(page.updated):
        reasons.append(
            _candidate_reason(
                "quality",
                "recently_changed_page",
                "low",
                "Recently changed page is a useful low-cost candidate for quality spot review.",
                0.35,
                {"updated": page.updated},
            )
        )
    if _contains_temporal_claim(page.content_preview):
        reasons.append(
            _candidate_reason(
                "freshness",
                "temporal_claim",
                "low",
                "Page preview contains time-sensitive wording or year/version/ranking language.",
                0.45,
            )
        )
    if len(page.outgoing_links) >= 8:
        reasons.append(
            _candidate_reason(
                "graph",
                "central_page",
                "low",
                "Page links to many wiki pages and is worth reviewing as a graph hub.",
                0.35,
                {"outgoing_link_count": len(page.outgoing_links)},
            )
        )
    if not page.outgoing_links and page.directory not in {"sources", "maintenance"}:
        reasons.append(
            _candidate_reason(
                "graph",
                "weak_graph_integration",
                "low",
                "Generated knowledge page has no outgoing wiki links.",
                0.55,
            )
        )

    for issue in issues:
        if issue.code in {"broken_wikilink", "frontmatter_type_mismatch", "missing_frontmatter"}:
            reasons.append(_reason_from_issue(issue, "structural", "high", 2.5))
        elif issue.code in {"knowledge_without_source_digest", "knowledge_missing_source_digest_link", "source_digest_missing_related_pages"}:
            reasons.append(_reason_from_issue(issue, "provenance", "medium", 1.6))
        elif issue.code in {"orphan_page", "duplicate_title", "duplicate_related_target", "duplicate_section_item", "path_alias_conflict", "weak_link_graph", "overdense_link_graph"}:
            reasons.append(_reason_from_issue(issue, "graph", "low", 0.9))
        elif issue.code in {"missing_required_section", "claim_missing_evidence_section", "claim_missing_confidence", "claim_invalid_confidence", "timeline_missing_chronology", "workflow_missing_steps"}:
            reasons.append(_reason_from_issue(issue, "quality", "medium", 1.2))

    return reasons


def _freshness_candidate_reasons(page: WikiScanPage) -> list[WikiLintCandidateReason]:
    reasons: list[WikiLintCandidateReason] = []
    updated = _parse_iso_date(page.updated)
    if updated is None:
        reasons.append(_candidate_reason("freshness", "missing_updated_date", "medium", "Page has no parseable updated or created date.", 1.5))
    else:
        age_days = (datetime.now() - updated).days
        if age_days >= 180:
            reasons.append(
                _candidate_reason(
                    "freshness",
                    "possibly_stale_page",
                    "medium",
                    "Page has not been updated for at least 180 days.",
                    1.3,
                    {"age_days": age_days},
                )
            )

    if _contains_temporal_claim(page.content_preview):
        reasons.append(
            _candidate_reason(
                "freshness",
                "temporal_claim",
                "low",
                "Page preview contains time-sensitive wording or year/version/ranking language.",
                0.8,
            )
        )
    return reasons


def _candidate_reason(
    source: WikiLintCandidateSource,
    issue_type: str,
    severity: WikiLintCandidateSeverity,
    message: str,
    score: float,
    evidence: dict[str, Any] | None = None,
) -> WikiLintCandidateReason:
    return WikiLintCandidateReason(
        source=source,
        issue_type=issue_type,
        severity=severity,
        message=message,
        score=score,
        evidence=evidence or {},
    )


def _reason_from_issue(
    issue: WikiLintIssue,
    source: WikiLintCandidateSource,
    severity: WikiLintCandidateSeverity,
    score: float,
) -> WikiLintCandidateReason:
    return _candidate_reason(
        source,
        issue.code,
        severity,
        issue.message,
        score,
        {"path": issue.path, "details": issue.details},
    )


def _parse_iso_date(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    for candidate in (text, text.replace("Z", "+00:00")):
        try:
            parsed = datetime.fromisoformat(candidate)
            return parsed.replace(tzinfo=None)
        except ValueError:
            continue
    match = re.search(r"\d{4}-\d{2}-\d{2}", text)
    if not match:
        return None
    try:
        return datetime.fromisoformat(match.group(0))
    except ValueError:
        return None


def _contains_temporal_claim(content: str) -> bool:
    return bool(
        re.search(
            r"(?i)\b(20[1-3][0-9]|latest|current|recent|version|ranking|ranked|price|api|deprecated|today|now)\b|最新|当前|最近|排名|版本|价格|弃用|政策|法规",
            content,
        )
    )


def _recently_updated(value: str | None, *, days: int = 14) -> bool:
    updated = _parse_iso_date(value)
    if updated is None:
        return False
    return 0 <= (datetime.now() - updated).days <= days


def _collect_pages(vault_path: Path) -> list[LintPage]:
    pages: list[LintPage] = []
    for directory in PAGE_TYPE_ORDER:
        page_dir = vault_path / directory
        if not page_dir.exists():
            continue
        for md_path in sorted(page_dir.glob("*.md")):
            if is_index_excluded_file(md_path.name):
                continue
            try:
                content = md_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                content = ""
            relative_path = md_path.relative_to(vault_path).as_posix()
            metadata = parse_frontmatter(content) if content else {}
            pages.append(
                LintPage(
                    path=md_path,
                    relative_path=relative_path,
                    directory=directory,
                    stem=md_path.stem,
                    title=extract_heading(content, md_path.stem) if content else md_path.stem,
                    content=content,
                    metadata=metadata,
                    links=_extract_wiki_links(content),
                )
            )
    return pages


def _lint_unexpected_markdown(vault_path: Path) -> list[WikiLintIssue]:
    allowed_dirs = set(PAGE_TYPE_ORDER) | set(SYSTEM_PAGE_DIRS) | INDEX_EXCLUDED_DIRS
    issues: list[WikiLintIssue] = []
    for md_path in sorted(vault_path.rglob("*.md")):
        relative = md_path.relative_to(vault_path)
        if is_index_excluded_file(md_path.name):
            continue
        if relative.parts and relative.parts[0] in allowed_dirs:
            continue
        issues.append(
            _issue(
                "unexpected_markdown_location",
                "warning",
                relative.as_posix(),
                "Markdown file is outside the schema-defined wiki directories.",
            )
        )
    return issues


def _lint_page_structure(pages: list[LintPage]) -> list[WikiLintIssue]:
    issues: list[WikiLintIssue] = []
    for page in pages:
        if not page.content:
            issues.append(_issue("unreadable_page", "error", page.relative_path, "Page could not be read as UTF-8."))
            continue
        if not page.metadata:
            issues.append(_issue("missing_frontmatter", "error", page.relative_path, "Page is missing YAML frontmatter."))
        missing_keys = [key for key in REQUIRED_FRONTMATTER_KEYS if key not in page.metadata]
        if page.metadata and missing_keys:
            issues.append(
                _issue(
                    "missing_frontmatter_keys",
                    "warning",
                    page.relative_path,
                    "Page frontmatter is missing expected generated-page keys.",
                    {"missing": missing_keys},
                )
            )
        if not re.search(r"^#\s+.+$", page.content, flags=re.MULTILINE):
            issues.append(_issue("missing_h1", "warning", page.relative_path, "Page is missing a top-level title."))
        expected_type = FRONTMATTER_TYPES.get(page.directory)
        actual_type = page.metadata.get("type")
        if expected_type and actual_type and actual_type != expected_type:
            issues.append(
                _issue(
                    "frontmatter_type_mismatch",
                    "error",
                    page.relative_path,
                    "Frontmatter type does not match the containing directory.",
                    {"expected": expected_type, "actual": actual_type},
                )
            )
        for section in REQUIRED_SECTIONS_BY_DIR.get(page.directory, ()):
            if not _has_section(page.content, section):
                issues.append(
                    _issue(
                        "missing_required_section",
                        "info",
                        page.relative_path,
                        f"Page is missing required {page.directory} section: {section}.",
                        {"directory": page.directory, "page_type": expected_type, "section": section},
                    )
                )
    return issues


def _lint_adjacent_duplicate_headings(pages: list[LintPage]) -> list[WikiLintIssue]:
    issues: list[WikiLintIssue] = []
    for page in pages:
        for duplicate in adjacent_duplicate_headings(page.content):
            issues.append(
                _issue(
                    "adjacent_duplicate_heading",
                    "info",
                    page.relative_path,
                    "Page has adjacent duplicate Markdown headings with no content between them.",
                    duplicate,
                )
            )
    return issues


def _lint_index_coverage(vault_path: Path, pages: list[LintPage]) -> list[WikiLintIssue]:
    index_path = vault_path / "index.md"
    if not index_path.exists():
        return [_issue("missing_index", "error", "index.md", "Wiki index.md is missing.")]

    index_content = index_path.read_text(encoding="utf-8")
    indexed_targets = {_normalize_link_target(link) for link in _extract_wiki_links(index_content)}
    issues: list[WikiLintIssue] = []
    for page in pages:
        if page.relative_path.removesuffix(".md") not in indexed_targets:
            issues.append(_issue("page_missing_from_index", "warning", page.relative_path, "Page is not listed in index.md."))
    return issues


def _lint_duplicate_identity(pages: list[LintPage]) -> list[WikiLintIssue]:
    issues: list[WikiLintIssue] = []
    title_groups: dict[str, list[LintPage]] = defaultdict(list)
    hash_groups: dict[str, list[LintPage]] = defaultdict(list)
    stem_groups: dict[str, list[LintPage]] = defaultdict(list)
    for page in pages:
        normalized_title = re.sub(r"\s+", " ", page.title).strip().lower()
        if normalized_title:
            title_groups[normalized_title].append(page)
        content_hash = page.metadata.get("content_hash")
        if content_hash:
            hash_groups[content_hash].append(page)
        normalized_stem = _normalize_title(page.stem)
        if normalized_stem:
            stem_groups[normalized_stem].append(page)

    for group in title_groups.values():
        if len(group) > 1:
            paths = [page.relative_path for page in group]
            for page in group:
                issues.append(_issue("duplicate_title", "info", page.relative_path, "Multiple pages share the same title.", {"pages": paths}))
    for group in hash_groups.values():
        if len(group) > 1:
            paths = [page.relative_path for page in group]
            for page in group:
                issues.append(_issue("duplicate_content_hash", "warning", page.relative_path, "Multiple pages share the same content hash.", {"pages": paths}))
    for group in stem_groups.values():
        directories = {page.directory for page in group}
        if len(group) > 1 and len(directories) > 1:
            paths = [page.relative_path for page in group]
            for page in group:
                issues.append(_issue("path_alias_conflict", "info", page.relative_path, "Multiple pages share the same filename stem across directories, which can make short wikilinks ambiguous.", {"pages": paths}))
    return issues


def _lint_links(pages: list[LintPage]) -> list[WikiLintIssue]:
    pages_by_relative = {page.relative_path.removesuffix(".md"): page for page in pages}
    pages_by_stem: dict[str, list[LintPage]] = defaultdict(list)
    pages_by_title: dict[str, list[LintPage]] = defaultdict(list)
    incoming_links: dict[str, set[str]] = defaultdict(set)
    issues: list[WikiLintIssue] = []

    for page in pages:
        pages_by_stem[page.stem].append(page)
        pages_by_title[_normalize_title(page.title)].append(page)

    for page in pages:
        for raw_link in page.links:
            target = _normalize_link_target(raw_link)
            if not target:
                continue
            resolved = _resolve_link(target, pages_by_relative, pages_by_stem, pages_by_title)
            if len(resolved) == 0:
                issues.append(_issue("broken_wikilink", "error", page.relative_path, "Wiki link target does not exist.", {"target": raw_link}))
            elif len(resolved) > 1:
                issues.append(
                    _issue(
                        "ambiguous_wikilink",
                        "warning",
                        page.relative_path,
                        "Wiki link matches multiple pages by title/stem.",
                        {"target": raw_link, "matches": [item.relative_path for item in resolved]},
                    )
                )
            else:
                incoming_links[resolved[0].relative_path].add(page.relative_path)

    for page in pages:
        if page.directory == "maintenance":
            continue
        if page.relative_path not in incoming_links:
            issues.append(_issue("orphan_page", "info", page.relative_path, "No other wiki page links to this page."))

    return issues


def _lint_graph_shape(pages: list[LintPage]) -> list[WikiLintIssue]:
    pages_by_relative, pages_by_stem, pages_by_title = _page_lookup_maps(pages)
    incoming: dict[str, set[str]] = defaultdict(set)
    outgoing: dict[str, set[str]] = defaultdict(set)
    issues: list[WikiLintIssue] = []

    for page in pages:
        for raw_link in page.links:
            target = _normalize_link_target(raw_link)
            resolved = _resolve_link(target, pages_by_relative, pages_by_stem, pages_by_title)
            if len(resolved) != 1:
                continue
            target_path = resolved[0].relative_path
            if target_path == page.relative_path:
                continue
            outgoing[page.relative_path].add(target_path)
            incoming[target_path].add(page.relative_path)

    for page in pages:
        if page.directory in WEAK_GRAPH_DIRS and not incoming.get(page.relative_path) and not outgoing.get(page.relative_path):
            issues.append(
                _issue(
                    "weak_link_graph",
                    "info",
                    page.relative_path,
                    "Generated knowledge page has no resolved incoming or outgoing wiki links.",
                    {"incoming_count": 0, "outgoing_count": 0},
                )
            )

        related_count = len(_extract_wiki_links(extract_section(page.content, "Related Pages")))
        outgoing_count = len(outgoing.get(page.relative_path, set()))
        if related_count > OVERDENSE_RELATED_THRESHOLD or outgoing_count > OVERDENSE_LINK_THRESHOLD:
            issues.append(
                _issue(
                    "overdense_link_graph",
                    "info",
                    page.relative_path,
                    "Page has a dense link graph that may need relationship pruning or section organization.",
                    {
                        "related_count": related_count,
                        "resolved_outgoing_count": outgoing_count,
                        "related_threshold": OVERDENSE_RELATED_THRESHOLD,
                        "outgoing_threshold": OVERDENSE_LINK_THRESHOLD,
                    },
                )
            )
    return issues


def _lint_source_pages(vault_path: Path, pages: list[LintPage]) -> list[WikiLintIssue]:
    issues: list[WikiLintIssue] = []
    pages_by_relative, pages_by_stem, pages_by_title = _page_lookup_maps(pages)
    source_digest_by_source = {
        page.metadata.get("source", ""): page
        for page in pages
        if page.directory == "sources" and page.metadata.get("source")
    }
    knowledge_pages_by_source: dict[str, list[LintPage]] = defaultdict(list)
    for page in pages:
        source = page.metadata.get("source", "")
        if page.directory in KNOWLEDGE_DIRS and source.startswith("raw/"):
            knowledge_pages_by_source[source].append(page)

    for page in pages:
        source = page.metadata.get("source", "")
        if source.startswith("raw/"):
            section_sources = extract_list_items(extract_section(page.content, "Source"))
            if source not in section_sources:
                issues.append(
                    _issue(
                        "source_section_mismatch",
                        "info",
                        page.relative_path,
                        "Frontmatter source is missing from the Source section.",
                        {"source": source, "section_sources": section_sources},
                    )
                )

        if page.directory == "sources":
            if source.startswith("raw/") and not (vault_path / source).exists():
                issues.append(_issue("missing_raw_source", "warning", page.relative_path, "Source digest points to a missing raw file.", {"source": source}))
            expected_knowledge_pages = knowledge_pages_by_source.get(source, [])
            if expected_knowledge_pages:
                related_paths = _resolved_paths_from_links(
                    _extract_wiki_links(extract_section(page.content, "Related Pages")),
                    pages_by_relative,
                    pages_by_stem,
                    pages_by_title,
                )
                missing_related = [item.relative_path for item in expected_knowledge_pages if item.relative_path not in related_paths]
                if missing_related:
                    issues.append(
                        _issue(
                            "source_digest_missing_related_pages",
                            "info",
                            page.relative_path,
                            "Source digest does not list all generated knowledge pages for the same raw source in Related Pages.",
                            {"source": source, "related_pages": missing_related},
                        )
                    )
            else:
                knowledge_links = [
                    link
                    for link in page.links
                    if _normalize_link_target(link).split("/", 1)[0] in KNOWLEDGE_DIRS
                ]
                if not knowledge_links:
                    issues.append(_issue("source_without_knowledge_links", "info", page.relative_path, "Source digest does not link to any generated knowledge page."))
            continue

        if page.directory in KNOWLEDGE_DIRS and source.startswith("raw/"):
            source_digest = source_digest_by_source.get(source)
            if not source_digest:
                issues.append(
                    _issue(
                        "knowledge_without_source_digest",
                        "info",
                        page.relative_path,
                        "Generated knowledge page points to a raw source without a matching source digest page.",
                        {"source": source},
                    )
                )
                continue
            related_paths = _resolved_paths_from_links(
                _extract_wiki_links(extract_section(page.content, "Related Pages")),
                pages_by_relative,
                pages_by_stem,
                pages_by_title,
            )
            if source_digest.relative_path not in related_paths:
                issues.append(
                    _issue(
                        "knowledge_missing_source_digest_link",
                        "info",
                        page.relative_path,
                        "Generated knowledge page does not link back to its matching source digest.",
                        {"source": source, "source_digest": source_digest.relative_path},
                    )
                )
    return issues


def _lint_related_page_lists(pages: list[LintPage]) -> list[WikiLintIssue]:
    pages_by_relative, pages_by_stem, pages_by_title = _page_lookup_maps(pages)
    issues: list[WikiLintIssue] = []
    for page in pages:
        related_links = _extract_wiki_links(extract_section(page.content, "Related Pages"))
        if not related_links:
            continue
        by_target: dict[str, list[str]] = defaultdict(list)
        for raw_link in related_links:
            target = _normalize_link_target(raw_link)
            resolved = _resolve_link(target, pages_by_relative, pages_by_stem, pages_by_title)
            if len(resolved) == 1:
                key = resolved[0].relative_path
            else:
                key = target
            by_target[key].append(raw_link)
        duplicates = {target: links for target, links in by_target.items() if len(links) > 1}
        for target, links in duplicates.items():
            issues.append(
                _issue(
                    "duplicate_related_target",
                    "info",
                    page.relative_path,
                    "Related Pages contains multiple list items pointing to the same wiki target.",
                    {"section": "Related Pages", "target": target, "links": links},
                )
            )
    return issues


def _lint_repeated_list_sections(pages: list[LintPage]) -> list[WikiLintIssue]:
    issues: list[WikiLintIssue] = []
    for page in pages:
        for section in ("Key Points", "Tags", "Source"):
            items = [
                item
                for item in extract_list_items(extract_section(page.content, section))
                if _is_meaningful_list_item(item)
            ]
            duplicates = _duplicate_items(items)
            if duplicates:
                issues.append(
                    _issue(
                        "duplicate_section_item",
                        "info",
                        page.relative_path,
                        f"{section} contains duplicate list items.",
                        {"section": section, "duplicates": duplicates},
                    )
                )
    return issues


def _lint_specialized_page_contracts(pages: list[LintPage]) -> list[WikiLintIssue]:
    issues: list[WikiLintIssue] = []
    for page in pages:
        headings = {heading.strip().lower() for heading in _extract_headings(page.content)}
        if page.directory == "claims":
            if not extract_section(page.content, "Evidence").strip():
                issues.append(
                    _issue(
                        "claim_missing_evidence_section",
                        "warning",
                        page.relative_path,
                        "Claim page is missing an Evidence section.",
                    )
                )
            if "confidence" not in page.metadata:
                issues.append(
                    _issue(
                        "claim_missing_confidence",
                        "info",
                        page.relative_path,
                        "Claim page is missing frontmatter confidence.",
                    )
                )
            elif not _valid_claim_confidence(page.metadata.get("confidence")):
                issues.append(
                    _issue(
                        "claim_invalid_confidence",
                        "warning",
                        page.relative_path,
                        "Claim page frontmatter confidence must be a number between 0 and 1.",
                        {"confidence": page.metadata.get("confidence")},
                    )
                )
        elif page.directory == "timelines":
            if len(_date_tokens(_markdown_body(page.content))) < 2:
                issues.append(
                    _issue(
                        "timeline_missing_chronology",
                        "info",
                        page.relative_path,
                        "Timeline page does not expose at least two date-like chronology markers.",
                    )
                )
        elif page.directory == "workflows":
            if not _has_workflow_steps(page.content, headings):
                issues.append(
                    _issue(
                        "workflow_missing_steps",
                        "info",
                        page.relative_path,
                        "Workflow page does not expose an ordered or step-oriented procedure.",
                    )
                )
    return issues


def _is_meaningful_list_item(item: str) -> bool:
    text = item.strip()
    if not text:
        return False
    return text not in {"暂无内容", "暂无关联知识", "暂无标签", "暂无来源"}


def _duplicate_items(items: list[str]) -> list[str]:
    seen: dict[str, str] = {}
    duplicates: list[str] = []
    duplicate_keys: set[str] = set()
    for item in items:
        key = _normalize_list_item(item)
        if not key:
            continue
        if key in seen and key not in duplicate_keys:
            duplicates.append(seen[key])
            duplicate_keys.add(key)
            continue
        seen[key] = item
    return duplicates


def _normalize_list_item(item: str) -> str:
    return re.sub(r"\s+", " ", item.strip()).strip("- ").lower()


def _date_tokens(content: str) -> list[str]:
    return re.findall(r"\b(?:19|20)\d{2}(?:[-/年.]\d{1,2}(?:[-/月.]\d{1,2}日?)?)?\b", content)


def _markdown_body(content: str) -> str:
    return re.sub(r"^---\s*\n.*?^---\s*$\n?", "", content, count=1, flags=re.MULTILINE | re.DOTALL).strip()


def _has_workflow_steps(content: str, headings: set[str]) -> bool:
    if {"steps", "procedure", "流程", "步骤", "操作步骤"}.intersection(headings):
        return True
    ordered_items = re.findall(r"^\s*\d+[\.)、]\s+\S+", content, flags=re.MULTILINE)
    task_items = re.findall(r"^\s*-\s+\[[ xX]\]\s+\S+", content, flags=re.MULTILINE)
    return len(ordered_items) >= 2 or len(task_items) >= 2


def _valid_claim_confidence(value: str | None) -> bool:
    if value is None:
        return False
    try:
        number = float(str(value).strip().strip('"\''))
    except ValueError:
        return False
    return 0 <= number <= 1


def _extract_wiki_links(content: str) -> list[str]:
    links: list[str] = []
    for match in re.finditer(r"\[\[([^\]]+)\]\]", content):
        target = match.group(1).split("|", 1)[0].strip()
        if not target or target.startswith(IGNORED_LINK_PREFIXES):
            continue
        links.append(target)
    return links


def _extract_headings(content: str) -> list[str]:
    return [match.group(1).strip() for match in re.finditer(r"^#{1,6}\s+(.+)$", content, flags=re.MULTILINE)]


def _has_section(content: str, heading: str) -> bool:
    return bool(re.search(rf"^##\s+{re.escape(heading)}\s*$", content, flags=re.MULTILINE))


def _extract_tags_for_scan(content: str, metadata: dict[str, str]) -> list[str]:
    raw_tags = metadata.get("tags", "")
    tags = [tag.strip().strip("[]'\"") for tag in raw_tags.split(",") if tag.strip()]
    if tags:
        return tags[:12]
    section_tags = []
    for item in extract_list_items(extract_section(content, "Tags")):
        if item and item != "暂无标签":
            section_tags.append(item)
    return section_tags[:12]


def _normalize_link_target(raw_link: str) -> str:
    target = raw_link.split("#", 1)[0].strip().lstrip("/")
    return target.removesuffix(".md")


def _resolve_link(
    target: str,
    pages_by_relative: dict[str, LintPage],
    pages_by_stem: dict[str, list[LintPage]],
    pages_by_title: dict[str, list[LintPage]],
) -> list[LintPage]:
    if target in pages_by_relative:
        return [pages_by_relative[target]]
    if "/" in target:
        directory, title = target.split("/", 1)
        return [page for page in pages_by_title.get(_normalize_title(title), []) if page.directory == directory]
    return pages_by_stem.get(target, []) or pages_by_title.get(_normalize_title(target), [])


def _page_lookup_maps(
    pages: list[LintPage],
) -> tuple[dict[str, LintPage], dict[str, list[LintPage]], dict[str, list[LintPage]]]:
    pages_by_relative = {page.relative_path.removesuffix(".md"): page for page in pages}
    pages_by_stem: dict[str, list[LintPage]] = defaultdict(list)
    pages_by_title: dict[str, list[LintPage]] = defaultdict(list)
    for page in pages:
        pages_by_stem[page.stem].append(page)
        pages_by_title[_normalize_title(page.title)].append(page)
    return pages_by_relative, pages_by_stem, pages_by_title


def _resolved_paths_from_links(
    links: list[str],
    pages_by_relative: dict[str, LintPage],
    pages_by_stem: dict[str, list[LintPage]],
    pages_by_title: dict[str, list[LintPage]],
) -> set[str]:
    paths: set[str] = set()
    for raw_link in links:
        target = _normalize_link_target(raw_link)
        resolved = _resolve_link(target, pages_by_relative, pages_by_stem, pages_by_title)
        if len(resolved) == 1:
            paths.add(resolved[0].relative_path)
    return paths


def _graph_health_stats(pages: list[LintPage]) -> dict[str, object]:
    pages_by_relative, pages_by_stem, pages_by_title = _page_lookup_maps(pages)
    knowledge_paths = {page.relative_path for page in pages if page.directory in KNOWLEDGE_DIRS | {"sources"}}
    adjacency: dict[str, set[str]] = {path: set() for path in knowledge_paths}
    degrees: Counter[str] = Counter()

    for page in pages:
        if page.relative_path not in knowledge_paths:
            continue
        resolved_paths = _resolved_paths_from_links(page.links, pages_by_relative, pages_by_stem, pages_by_title)
        for target_path in resolved_paths:
            if target_path not in knowledge_paths or target_path == page.relative_path:
                continue
            adjacency[page.relative_path].add(target_path)
            adjacency[target_path].add(page.relative_path)
            degrees[page.relative_path] += 1
            degrees[target_path] += 1

    seen: set[str] = set()
    components: list[list[str]] = []
    for path in sorted(knowledge_paths):
        if path in seen:
            continue
        stack = [path]
        component: list[str] = []
        seen.add(path)
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbor in sorted(adjacency.get(current, set())):
                if neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)
        components.append(sorted(component))

    component_sizes = sorted((len(component) for component in components), reverse=True)
    isolated = sorted(component[0] for component in components if len(component) == 1)
    small_components = [component for component in components if 1 < len(component) <= 3]
    hub_pages = [
        {"path": path, "degree": degree}
        for path, degree in sorted(degrees.items(), key=lambda item: (-item[1], item[0]))[:10]
    ]
    return {
        "node_count": len(knowledge_paths),
        "component_count": len(components),
        "largest_component_size": component_sizes[0] if component_sizes else 0,
        "isolated_page_count": len(isolated),
        "isolated_pages": isolated[:20],
        "small_component_count": len(small_components),
        "small_components": [component for component in small_components[:10]],
        "hub_pages": hub_pages,
    }


def _normalize_title(title: str) -> str:
    value = re.sub(r"[\u2010-\u2015\u2212]", "-", title)
    return re.sub(r"\s+", " ", value).strip().lower()


def _issue(code: str, severity: str, path: str, message: str, details: dict[str, Any] | None = None) -> WikiLintIssue:
    return WikiLintIssue(code=code, severity=severity, path=path, message=message, details=details or {})


def _fix_for_issue(issue: WikiLintIssue) -> WikiLintFix:
    if issue.code in {"missing_index", "page_missing_from_index"}:
        return WikiLintFix(
            issue_code=issue.code,
            path=issue.path,
            action="rebuild_index",
            mode="safe_auto",
            description="Rebuild index.md from generated wiki pages.",
        )
    if issue.code == "unexpected_markdown_location":
        return WikiLintFix(
            issue_code=issue.code,
            path=issue.path,
            action="ingest_or_move_source",
            mode="manual",
            description="Move this file into raw/notes and ingest it, or relocate it to a schema-defined generated-page directory with valid frontmatter.",
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
    if issue.code in {"missing_frontmatter", "missing_frontmatter_keys", "frontmatter_type_mismatch"}:
        return WikiLintFix(
            issue_code=issue.code,
            path=issue.path,
            action="repair_frontmatter",
            mode="manual",
            description="Repair frontmatter from source provenance and page intent before rerunning lint.",
        )
    if issue.code == "missing_required_section":
        return WikiLintFix(
            issue_code=issue.code,
            path=issue.path,
            action="add_missing_section",
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
        "source_digest_missing_related_pages",
        "source_section_mismatch",
        "knowledge_without_source_digest",
        "knowledge_missing_source_digest_link",
    }:
        return WikiLintFix(
            issue_code=issue.code,
            path=issue.path,
            action="repair_source_provenance",
            mode="manual",
            description="Review source provenance and connect the source digest to generated knowledge pages.",
        )
    if issue.code == "duplicate_related_target":
        return WikiLintFix(
            issue_code=issue.code,
            path=issue.path,
            action="deduplicate_related_pages",
            mode="manual",
            description="Remove duplicate Related Pages items that resolve to the same wiki target.",
        )
    if issue.code == "duplicate_section_item":
        return WikiLintFix(
            issue_code=issue.code,
            path=issue.path,
            action="deduplicate_section_items",
            mode="manual",
            description="Remove duplicate list items from the affected section.",
        )
    if issue.code == "adjacent_duplicate_heading":
        return WikiLintFix(
            issue_code=issue.code,
            path=issue.path,
            action="remove_adjacent_duplicate_headings",
            mode="manual",
            description="Remove adjacent duplicate Markdown heading lines that have no content between them.",
        )
    if issue.code in {"claim_missing_evidence_section", "claim_missing_confidence", "claim_invalid_confidence"}:
        return WikiLintFix(
            issue_code=issue.code,
            path=issue.path,
            action="repair_claim_contract",
            mode="manual",
            description="Review the claim page and add explicit evidence and confidence metadata before relying on it.",
        )
    if issue.code == "timeline_missing_chronology":
        return WikiLintFix(
            issue_code=issue.code,
            path=issue.path,
            action="repair_timeline_structure",
            mode="manual",
            description="Review whether this page belongs in timelines and add an explicit chronological structure if it does.",
        )
    if issue.code == "workflow_missing_steps":
        return WikiLintFix(
            issue_code=issue.code,
            path=issue.path,
            action="repair_workflow_structure",
            mode="manual",
            description="Review whether this page belongs in workflows and add ordered or checklist steps if it does.",
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
