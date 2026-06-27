from __future__ import annotations

from fnmatch import fnmatch

from knoarbor.core.errors import PolicyRejection


# Physical write-location directories for AI-writable wiki content.
# ``sources`` holds source digest audit pages; the unified ``pages`` namespace
# holds flat knowledge pages.
SOURCE_DIGEST_DIR = "sources"
UNIFIED_KNOWLEDGE_PAGE_DIR = "pages"

# Directories that may contain AI-writable content. ``sources`` is the source
# digest root; flat files under ``pages`` are the unified namespace.
CONTENT_PAGE_DIRS = (SOURCE_DIGEST_DIR, UNIFIED_KNOWLEDGE_PAGE_DIR)
SYSTEM_PAGE_DIRS = ("maintenance",)
AI_WRITABLE_DIRS = set(CONTENT_PAGE_DIRS)

INDEX_EXCLUDED_DIRS = {"raw"}
INDEX_EXCLUDED_FILES = {"index.md", "log.md", "SCHEMA.md"}
INDEX_EXCLUDED_FILE_PATTERNS = (
    "ingest_report_*.md",
    "lint_report_*.md",
    "lint_run_report_*.md",
    "quality_report_*.md",
    "freshness_report_*.md",
)


def is_index_excluded_file(filename: str) -> bool:
    return filename in INDEX_EXCLUDED_FILES or any(fnmatch(filename, pattern) for pattern in INDEX_EXCLUDED_FILE_PATTERNS)


def normalize_page_dir(value: str | None) -> str:
    if not value:
        raise PolicyRejection("page_dir is required")
    normalized = value.strip().lower().replace(" ", "_")
    aliases = {
        "source": SOURCE_DIGEST_DIR,
        "page": UNIFIED_KNOWLEDGE_PAGE_DIR,
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in AI_WRITABLE_DIRS:
        allowed = ", ".join(sorted(AI_WRITABLE_DIRS))
        raise PolicyRejection(f"Invalid page_dir: {value}. Allowed values: {allowed}")
    return normalized
