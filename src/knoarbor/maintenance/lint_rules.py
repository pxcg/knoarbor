from __future__ import annotations


REQUIRED_FRONTMATTER_KEYS = ("created", "updated", "content_hash")
IGNORED_LINK_PREFIXES = ("http://", "https://", "mailto:", "#")
OVERDENSE_LINK_THRESHOLD = 30
KNOWLEDGE_PAGE_SECTIONS = (
    "Summary",
    "Claims",
    "Entities",
    "Relations",
    "Evidence",
    "Synthesis",
)
SOURCE_DIGEST_SECTIONS = (
    "Source Identity",
    "Audit Summary",
    "Source Units",
    "Contribution Map",
    "Unresolved / Rejected",
    "Raw Source",
)
REQUIRED_SECTIONS_BY_ROLE = {
    "source_digest": SOURCE_DIGEST_SECTIONS,
}


# Lint issue execution classes define which layer is responsible for a fix.
# Deterministic-only issues are precise scanner findings and should be handled
# by rule-based fixes or reports, not by semantic diagnose agents.
DETERMINISTIC_ONLY_ISSUE_CODES = frozenset(
    {
        "ambiguous_wikilink",
        "broken_wikilink",
        "duplicate_section_item",
        "missing_frontmatter",
        "missing_frontmatter_keys",
        "missing_index",
        "missing_raw_source",
        "missing_required_section",
        "page_missing_from_index",
        "privacy_sensitive_content",
        "unexpected_markdown_location",
    }
)

SEMANTIC_STRUCTURAL_ISSUE_CODES = frozenset(
    {
        "knowledge_missing_source_digest_link",
        "knowledge_without_source_digest",
        "source_without_knowledge_links",
    }
)

GOVERNANCE_QUEUE_ISSUE_CODES = frozenset(
    {
        "duplicate_content_hash",
        "duplicate_title",
        "overdense_link_graph",
        "path_alias_conflict",
        "weak_link_graph",
    }
)

QUALITY_SEMANTIC_ISSUE_CODES = frozenset()


def lint_issue_execution_class(code: str) -> str:
    if code in DETERMINISTIC_ONLY_ISSUE_CODES:
        return "deterministic_only"
    if code in SEMANTIC_STRUCTURAL_ISSUE_CODES:
        return "semantic_structural"
    if code in GOVERNANCE_QUEUE_ISSUE_CODES:
        return "governance_queue"
    if code in QUALITY_SEMANTIC_ISSUE_CODES:
        return "quality_semantic"
    return "report_only"


def is_structural_semantic_issue(code: str) -> bool:
    return lint_issue_execution_class(code) in {"semantic_structural", "governance_queue"}


def is_deterministic_only_issue(code: str) -> bool:
    return lint_issue_execution_class(code) == "deterministic_only"
