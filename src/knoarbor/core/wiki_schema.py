from __future__ import annotations

from fnmatch import fnmatch

from knoarbor.core.errors import PolicyRejection


PAGE_TYPE_RULES = {
    "sources": ("来源", "资料", "原文", "source", "reference", "provenance"),
    "comparisons": ("对比", "比较", "区别", "vs", "versus", "compare", "comparison"),
    "queries": ("查询", "问题", "回答", "如何", "为什么", "怎么", "query", "question"),
    "entities": ("公司", "组织", "产品", "人物", "团队", "project", "product", "company"),
    "concepts": ("概念", "原则", "模式", "架构", "方法", "技术", "concept", "pattern", "architecture"),
    "claims": ("断言", "主张", "证据", "claim", "evidence", "argument"),
    "timelines": ("时间线", "历史", "演进", "路线图", "timeline", "history", "roadmap"),
    "workflows": ("流程", "步骤", "操作", "workflow", "playbook", "procedure"),
}

CONTENT_PAGE_DIRS = ("sources", "entities", "concepts", "comparisons", "queries", "claims", "timelines", "workflows")
SYSTEM_PAGE_DIRS = ("maintenance",)
PAGE_TYPE_ORDER = CONTENT_PAGE_DIRS

FRONTMATTER_TYPES = {
    "sources": "source",
    "entities": "entity",
    "concepts": "concept",
    "comparisons": "comparison",
    "queries": "query",
    "claims": "claim",
    "timelines": "timeline",
    "workflows": "workflow",
    "maintenance": "maintenance",
}

INDEX_EXCLUDED_DIRS = {"raw"}
INDEX_EXCLUDED_FILES = {"SCHEMA.md", "index.md", "log.md"}
INDEX_EXCLUDED_FILE_PATTERNS = (
    "ingest_report_*.md",
    "lint_report_*.md",
    "lint_run_report_*.md",
    "quality_report_*.md",
    "freshness_report_*.md",
)
AI_WRITABLE_DIRS = set(CONTENT_PAGE_DIRS)


def frontmatter_type(page_dir: str) -> str:
    return FRONTMATTER_TYPES[page_dir]


def is_index_excluded_file(filename: str) -> bool:
    return filename in INDEX_EXCLUDED_FILES or any(fnmatch(filename, pattern) for pattern in INDEX_EXCLUDED_FILE_PATTERNS)


def normalize_page_dir(value: str | None) -> str:
    if not value:
        raise PolicyRejection("page_dir is required")
    normalized = value.strip().lower().replace(" ", "_")
    aliases = {
        "source": "sources",
        "entity": "entities",
        "concept": "concepts",
        "comparison": "comparisons",
        "query": "queries",
        "claim": "claims",
        "timeline": "timelines",
        "workflow": "workflows",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in AI_WRITABLE_DIRS:
        allowed = ", ".join(sorted(AI_WRITABLE_DIRS))
        raise PolicyRejection(f"Invalid page_dir: {value}. Allowed values: {allowed}")
    return normalized
