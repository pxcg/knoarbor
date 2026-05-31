from __future__ import annotations


REQUIRED_FRONTMATTER_KEYS = ("created", "updated", "type", "status", "source", "content_hash")
IGNORED_LINK_PREFIXES = ("http://", "https://", "mailto:", "#")
KNOWLEDGE_DIRS = {"entities", "concepts", "comparisons", "queries", "claims", "timelines", "workflows"}
WEAK_GRAPH_DIRS = KNOWLEDGE_DIRS - {"claims"}
OVERDENSE_LINK_THRESHOLD = 30
OVERDENSE_RELATED_THRESHOLD = 20
REQUIRED_SECTIONS_BY_DIR = {
    "sources": ("Summary", "Source Focus", "Answer", "Related Pages", "Tags", "Source"),
    "entities": ("Summary", "Answer", "Key Points", "Related Pages", "Tags", "Source"),
    "concepts": ("Summary", "Answer", "Key Points", "Related Pages", "Tags", "Source"),
    "comparisons": ("Summary", "Answer", "Key Points", "Related Pages", "Tags", "Source"),
    "queries": ("Summary", "Question", "Answer", "Key Points", "Related Pages", "Tags", "Source"),
    "claims": ("Summary", "Evidence", "Related Pages", "Tags", "Source"),
    "timelines": ("Summary", "Answer", "Related Pages", "Tags", "Source"),
    "workflows": ("Summary", "Answer", "Related Pages", "Tags", "Source"),
}
