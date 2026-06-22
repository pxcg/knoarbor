from __future__ import annotations


REQUIRED_FRONTMATTER_KEYS = ("created", "updated", "type", "status", "source", "content_hash")
IGNORED_LINK_PREFIXES = ("http://", "https://", "mailto:", "#")
KNOWLEDGE_DIRS = {"entities", "concepts", "comparisons", "queries", "timelines", "workflows"}
WEAK_GRAPH_DIRS = KNOWLEDGE_DIRS
OVERDENSE_LINK_THRESHOLD = 30
OVERDENSE_RELATED_THRESHOLD = 20
KNOWLEDGE_PAGE_SECTIONS = (
    "Summary",
    "Source Focus",
    "Definition",
    "Claims",
    "Relations",
    "Synthesis",
    "Key Points",
    "Related Pages",
    "Tags",
    "Source",
)
REQUIRED_SECTIONS_BY_DIR = {
    "sources": KNOWLEDGE_PAGE_SECTIONS,
    "entities": KNOWLEDGE_PAGE_SECTIONS,
    "concepts": KNOWLEDGE_PAGE_SECTIONS,
    "comparisons": KNOWLEDGE_PAGE_SECTIONS,
    "queries": KNOWLEDGE_PAGE_SECTIONS,
    "timelines": KNOWLEDGE_PAGE_SECTIONS,
    "workflows": KNOWLEDGE_PAGE_SECTIONS,
}

# Lint issue execution classes define which layer is responsible for a fix.
# Deterministic-only issues are precise scanner findings and should be handled
# by rule-based fixes or reports, not by semantic diagnose agents.
DETERMINISTIC_ONLY_ISSUE_CODES = frozenset(
    {
        "ambiguous_wikilink",
        "broken_wikilink",
        "duplicate_related_target",
        "duplicate_section_item",
        "frontmatter_type_mismatch",
        "missing_frontmatter",
        "missing_frontmatter_keys",
        "missing_index",
        "missing_raw_source",
        "missing_required_section",
        "page_missing_from_index",
        "privacy_sensitive_content",
        "source_section_mismatch",
        "unexpected_markdown_location",
    }
)

SEMANTIC_STRUCTURAL_ISSUE_CODES = frozenset(
    {
        "knowledge_missing_source_digest_link",
        "knowledge_without_source_digest",
        "source_digest_missing_related_pages",
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

QUALITY_SEMANTIC_ISSUE_CODES = frozenset(
    {
        "timeline_missing_chronology",
        "workflow_missing_steps",
    }
)


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
