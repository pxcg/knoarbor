from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from knoarbor.core.markdown import extract_list_items, extract_section
from knoarbor.core.schemas.wiki_lint import (
    WikiLintCandidatePage,
    WikiLintCandidateReason,
    WikiLintCandidateSeverity,
    WikiLintCandidateSource,
    WikiLintIssue,
    WikiScanPage,
)
from knoarbor.maintenance.lint_collection import extract_headings
from knoarbor.maintenance.lint_models import LintPage
from knoarbor.maintenance.lint_rules import is_deterministic_only_issue


def scan_page(page: LintPage, max_chars_per_page: int) -> WikiScanPage:
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
        tags=extract_tags_for_scan(page.content, metadata),
        summary=extract_section(page.content, "Summary"),
        headings=extract_headings(page.content),
        outgoing_links=page.links,
        content_preview=preview,
        content_truncated=len(page.content) > len(preview),
        original_content_length=len(page.content),
    )


def score_lint_candidate(page: WikiScanPage, issues: list[WikiLintIssue], mode: str) -> WikiLintCandidatePage:
    reasons: list[WikiLintCandidateReason] = []
    if mode in {"quality", "full"}:
        reasons.extend(_quality_candidate_reasons(page, issues))
    if mode in {"freshness", "full"}:
        reasons.extend(_freshness_candidate_reasons(page))

    score = _candidate_score(reasons, mode)
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


def extract_tags_for_scan(content: str, metadata: dict[str, str]) -> list[str]:
    raw_tags = metadata.get("tags", "")
    tags = [tag.strip().strip("[]'\"") for tag in raw_tags.split(",") if tag.strip()]
    if tags:
        return tags[:12]
    section_tags = []
    for item in extract_list_items(extract_section(content, "Tags")):
        if item and item != "暂无标签":
            section_tags.append(item)
    return section_tags[:12]


def _quality_candidate_reasons(page: WikiScanPage, issues: list[WikiLintIssue]) -> list[WikiLintCandidateReason]:
    reasons: list[WikiLintCandidateReason] = []
    headings = {heading.strip().lower() for heading in page.headings}

    if not page.summary.strip():
        reasons.append(_candidate_reason("quality", "missing_summary", "medium", "Page has no Summary section content.", 1.4))
    if "claims" not in headings:
        reasons.append(_candidate_reason("quality", "missing_claims", "medium", "Page has no Claims section.", 1.0))
    if "evidence" not in headings:
        reasons.append(_candidate_reason("quality", "missing_evidence", "medium", "Page has no Evidence section.", 1.0))
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
        reasons.append(_candidate_reason("freshness", "temporal_claim", "low", "Page preview contains time-sensitive wording or year/version/ranking language.", 0.45))
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
        reasons.append(_candidate_reason("graph", "weak_graph_integration", "low", "Generated knowledge page has no outgoing wiki links.", 0.55))

    for issue in issues:
        if is_deterministic_only_issue(issue.code):
            continue
        if issue.code in {"knowledge_without_source_digest", "knowledge_missing_source_digest_link", "source_digest_missing_related_pages"}:
            reasons.append(_reason_from_issue(issue, "provenance", "medium", 1.6))
        elif issue.code in {"orphan_page", "duplicate_title", "duplicate_related_target", "duplicate_section_item", "path_alias_conflict", "weak_link_graph", "overdense_link_graph"}:
            reasons.append(_reason_from_issue(issue, "graph", "low", 0.9))
        elif issue.code == "workflow_missing_steps":
            reasons.append(_reason_from_issue(issue, "quality", "medium", 2.0))
        elif issue.code in {"missing_required_section", "timeline_missing_chronology"}:
            reasons.append(_reason_from_issue(issue, "quality", "medium", 1.2))

    return reasons


def _candidate_score(reasons: list[WikiLintCandidateReason], mode: str) -> float:
    if mode == "quality":
        quality_score = sum(reason.score for reason in reasons if reason.source == "quality")
        support_score = sum(reason.score for reason in reasons if reason.source in {"freshness", "graph"}) * 0.25
        return round(quality_score + support_score, 3)
    return round(sum(reason.score for reason in reasons), 3)


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
        reasons.append(_candidate_reason("freshness", "temporal_claim", "low", "Page preview contains time-sensitive wording or year/version/ranking language.", 0.8))
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
    return _candidate_reason(source, issue.code, severity, issue.message, score, {"path": issue.path, "details": issue.details})


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
