from __future__ import annotations

import re
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
    preview = page.content[:max_chars_per_page] if max_chars_per_page else page.content
    metadata = page.metadata
    return WikiScanPage(
        path=page.relative_path,
        directory=page.directory,
        title=page.title,
        role=page.role,
        updated=metadata.get("updated") or metadata.get("created"),
        content_hash=metadata.get("content_hash"),
        entities=extract_entities_for_scan(page.content),
        summary=extract_section(page.content, "Summary"),
        headings=extract_headings(page.content),
        outgoing_links=page.links,
        content_preview=preview,
        content_truncated=len(page.content) > len(preview),
        original_content_length=len(page.content),
    )


def score_lint_candidate(page: WikiScanPage, issues: list[WikiLintIssue]) -> WikiLintCandidatePage:
    reasons: list[WikiLintCandidateReason] = []
    reasons.extend(_quality_candidate_reasons(page, issues))
    reasons.extend(_freshness_candidate_reasons(page))

    score = _candidate_score(reasons)
    return WikiLintCandidatePage(
        path=page.path,
        directory=page.directory,
        title=page.title,
        role=page.role,
        updated=page.updated,
        summary=page.summary,
        entities=page.entities,
        headings=page.headings,
        outgoing_links=page.outgoing_links,
        content_preview=page.content_preview,
        content_truncated=page.content_truncated,
        original_content_length=page.original_content_length,
        score=score,
        reasons=reasons,
    )


def extract_entities_for_scan(content: str) -> list[str]:
    entities: list[str] = []
    for item in extract_list_items(extract_section(content, "Entities")):
        text = item.strip()
        if not text or text.startswith("暂无"):
            continue
        text = text.removeprefix("[[").removesuffix("]]")
        if "|" in text:
            text = text.split("|", 1)[-1]
        if text not in entities:
            entities.append(text)
    return entities[:24]


def _quality_candidate_reasons(page: WikiScanPage, issues: list[WikiLintIssue]) -> list[WikiLintCandidateReason]:
    reasons: list[WikiLintCandidateReason] = []
    headings = {heading.strip().lower() for heading in page.headings}

    if "claims" in headings and _section_is_placeholder(page.content_preview, "Claims"):
        reasons.append(_candidate_reason("quality", "empty_claims", "high", "Claims projection contains only a placeholder.", 1.5))
    if "synthesis" in headings and _section_is_placeholder(page.content_preview, "Synthesis"):
        reasons.append(_candidate_reason("quality", "empty_synthesis", "medium", "Synthesis projection contains only a placeholder.", 1.0))

    for issue in issues:
        if is_deterministic_only_issue(issue.code):
            continue
        if issue.code in {"knowledge_without_source_record", "knowledge_missing_source_record_link", "source_record_missing_contribution_map"}:
            reasons.append(_reason_from_issue(issue, "provenance", "medium", 1.6))
        elif issue.code in {"orphan_page", "duplicate_title", "duplicate_section_item", "path_alias_conflict", "weak_link_graph", "overdense_link_graph"}:
            reasons.append(_reason_from_issue(issue, "graph", "low", 0.9))
        elif issue.code == "missing_required_section":
            reasons.append(_reason_from_issue(issue, "quality", "medium", 1.2))

    return reasons


def _candidate_score(reasons: list[WikiLintCandidateReason]) -> float:
    return round(sum(reason.score for reason in reasons), 3)


def _freshness_candidate_reasons(page: WikiScanPage) -> list[WikiLintCandidateReason]:
    reasons: list[WikiLintCandidateReason] = []
    if _contains_temporal_claim(page.content_preview):
        reasons.append(_candidate_reason("freshness", "temporal_claim", "low", "Page preview contains time-sensitive wording or year/version/ranking language.", 0.8))
    return reasons


def _section_is_placeholder(content: str, heading: str) -> bool:
    section = extract_section(content, heading).strip().lower()
    return section in {"- 暂无内容", "暂无内容", "- none", "none", "- n/a", "n/a"}


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


def _contains_temporal_claim(content: str) -> bool:
    return bool(
        re.search(
            r"(?i)\b(20[1-3][0-9]|latest|current|recent|version|ranking|ranked|price|api|deprecated|today|now)\b|最新|当前|最近|排名|版本|价格|弃用|政策|法规",
            content,
        )
    )
