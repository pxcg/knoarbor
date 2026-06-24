from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from knoarbor.core.markdown import extract_heading, extract_list_items, extract_section, parse_frontmatter
from knoarbor.core.wiki_schema import INDEX_EXCLUDED_DIRS, INDEX_PAGE_DIRS, UNIFIED_KNOWLEDGE_PAGE_DIR, is_index_excluded_file
from knoarbor.retrieval.bm25 import BM25Document, BM25Field, score_bm25_documents
from knoarbor.retrieval.wiki_links import resolve_wikilink_target
from knoarbor.storage import relative_wiki_path
from knoarbor.storage.wiki_paths import content_root


FIELD_WEIGHTS: dict[str, float] = {
    "title": 5.0,
    "tags": 3.0,
    "summary": 3.0,
    "key_points": 2.5,
    "headings": 2.0,
    "path": 1.0,
    "body": 0.8,
}

QUERY_STOP_TERMS = {
    "about",
    "answer",
    "based",
    "explain",
    "list",
    "please",
    "show",
    "summarize",
    "tell",
    "what",
    "which",
    "why",
    "一下",
    "一些",
    "什么",
    "介绍",
    "列出",
    "哪些",
    "基于",
    "如何",
    "怎么",
    "我想",
    "所有",
    "按照",
    "相关",
    "知识",
    "知识库",
    "给出",
    "这个",
    "这些",
}

QUERY_STOP_SUBSTRINGS = (
    "是什么",
    "是什",
    "什么是",
    "为我",
    "帮我",
    "请",
    "请按",
    "知识库里",
    "和我说",
    "告诉我",
)


@dataclass
class SearchPage:
    path: Path
    relative_path: str
    directory: str
    title: str
    page_type: str
    status: str | None
    source: str | None
    tags: list[str]
    summary: str
    key_points: list[str]
    related_pages: list[str]
    headings: list[str]
    body: str
    canonical_path: str = ""
    legacy_paths: list[str] = field(default_factory=list)
    page_kind: str = ""
    role: str = "knowledge_page"
    facets: list[str] = field(default_factory=list)


@dataclass
class ScoredPage:
    page: SearchPage
    score: float
    matched_fields: set[str] = field(default_factory=set)
    matched_terms: dict[str, list[str]] = field(default_factory=dict)
    graph_boost: float = 0.0
    graph_reasons: list[str] = field(default_factory=list)


def collect_search_pages(vault_path: Path) -> list[SearchPage]:
    pages: list[SearchPage] = []
    root = content_root(vault_path)
    for md_path in _iter_search_page_paths(root):
        page_dir = _page_directory(vault_path, md_path)
        try:
            content = md_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        metadata = parse_frontmatter(content)
        page_type = metadata.get("type") or _default_type_for_directory(page_dir)
        page_kind = metadata.get("page_kind") or _default_page_kind(page_dir, page_type)
        relative_path = relative_wiki_path(vault_path, md_path)
        pages.append(
            SearchPage(
                path=md_path,
                relative_path=relative_path,
                directory=page_dir,
                title=extract_heading(content, md_path.stem),
                page_type=page_type,
                status=metadata.get("status"),
                source=metadata.get("source"),
                tags=extract_tags_from_page(content, metadata) or _extract_entities(content),
                summary=extract_section(content, "Summary"),
                key_points=extract_list_items(extract_section(content, "Key Points")) or extract_list_items(extract_section(content, "Claims")),
                related_pages=extract_related_page_paths(vault_path, extract_section(content, "Related Pages")),
                headings=extract_headings(content),
                body=strip_frontmatter(content),
                canonical_path=metadata.get("canonical_path") or relative_path,
                legacy_paths=_metadata_list(metadata.get("legacy_paths")),
                page_kind=page_kind,
                role=_page_role(page_dir, page_kind),
                facets=_page_facets(metadata, page_dir, page_kind),
            )
        )
    return pages


def _iter_search_page_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    for md_path in sorted(root.glob("*.md")):
        if not is_index_excluded_file(md_path.name):
            paths.append(md_path)
    for page_dir in INDEX_PAGE_DIRS:
        directory_path = root / page_dir
        if not directory_path.exists():
            continue
        for md_path in sorted(directory_path.glob("*.md")):
            if not is_index_excluded_file(md_path.name):
                paths.append(md_path)
    return paths


def _page_directory(vault_path: Path, md_path: Path) -> str:
    root = content_root(vault_path)
    if md_path.parent.resolve() == root.resolve():
        return UNIFIED_KNOWLEDGE_PAGE_DIR
    return md_path.parent.name


def should_skip_page(vault_path: Path, path: Path) -> bool:
    parts = path.relative_to(content_root(vault_path)).parts
    return is_index_excluded_file(path.name) or any(part in INDEX_EXCLUDED_DIRS for part in parts)


def query_terms(query: str) -> list[str]:
    normalized = normalize_text(query)
    terms: list[str] = []
    terms.extend(re.findall(r"[a-z0-9][a-z0-9_.+-]{1,}", normalized))
    for group in re.findall(r"[\u4e00-\u9fff]{2,}", query):
        terms.append(group.lower())
        terms.extend(group[index : index + 2].lower() for index in range(0, max(len(group) - 1, 0)))
        if len(group) >= 3:
            terms.extend(group[index : index + 3].lower() for index in range(0, len(group) - 2))
    seen: set[str] = set()
    unique: list[str] = []
    for term in terms:
        if _is_query_signal_term(term) and term not in seen:
            seen.add(term)
            unique.append(term)
    return unique[:80]


def _is_query_signal_term(term: str) -> bool:
    text = term.strip().lower()
    if not text or text in QUERY_STOP_TERMS:
        return False
    return not any(fragment in text for fragment in QUERY_STOP_SUBSTRINGS)


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def score_pages(pages: list[SearchPage], terms: list[str], query: str) -> dict[str, ScoredPage]:
    page_by_path = {page.relative_path: page for page in pages}
    documents = [_page_to_bm25_document(page) for page in pages]
    matches = score_bm25_documents(documents, terms, query)
    return {
        path: ScoredPage(page=page_by_path[path], score=match.score, matched_fields=match.matched_fields, matched_terms=match.matched_terms)
        for path, match in matches.items()
        if path in page_by_path and match.score > 0
    }


def _page_to_bm25_document(page: SearchPage) -> BM25Document:
    return BM25Document(
        id=page.relative_path,
        fields=[
            BM25Field("title", page.title, FIELD_WEIGHTS["title"]),
            BM25Field("tags", " ".join(page.tags), FIELD_WEIGHTS["tags"]),
            BM25Field("summary", page.summary, FIELD_WEIGHTS["summary"]),
            BM25Field("key_points", " ".join(page.key_points), FIELD_WEIGHTS["key_points"]),
            BM25Field("headings", " ".join(page.headings), FIELD_WEIGHTS["headings"]),
            BM25Field("path", page.relative_path, FIELD_WEIGHTS["path"]),
            BM25Field("body", page.body, FIELD_WEIGHTS["body"]),
        ],
    )


def _extract_entities(content: str) -> list[str]:
    entities: list[str] = []
    for item in extract_list_items(extract_section(content, "Entities")):
        text = item.strip()
        if not text or text.startswith("暂无"):
            continue
        text = re.sub(r"^\[\[(?P<link>.+?)\]\]$", r"\g<link>", text)
        if "|" in text:
            text = text.split("|", 1)[-1]
        if text and text not in entities:
            entities.append(text)
    return entities[:24]


def relevance_label(score: float) -> str:
    if score >= 8:
        return "high"
    if score >= 3:
        return "medium"
    return "low"


def extract_headings(content: str) -> list[str]:
    return [match.group(1).strip() for match in re.finditer(r"^#{1,6}\s+(.+?)\s*$", content, flags=re.MULTILINE)]


def strip_frontmatter(content: str) -> str:
    return re.sub(r"^---\s*\n.*?^---\s*$\n?", "", content, count=1, flags=re.MULTILINE | re.DOTALL).strip()


def extract_tags_from_page(content: str, metadata: dict[str, str]) -> list[str]:
    raw_tags = metadata.get("tags", "")
    tags = [tag.strip().strip("[]'\"") for tag in raw_tags.split(",") if tag.strip()]
    if tags:
        return tags[:12]
    return extract_list_items(extract_section(content, "Tags"))[:12]


def extract_related_page_paths(vault_path: Path, related_section: str) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for item in extract_list_items(related_section):
        match = re.search(r"\[\[([^\]|#]+)", item)
        if not match:
            continue
        resolved = resolve_wikilink_target(vault_path, match.group(1))
        if not resolved or resolved in seen:
            continue
        seen.add(resolved)
        paths.append(resolved)
    return paths


def _default_page_kind(directory: str, page_type: str) -> str:
    if directory == "sources" or page_type == "source":
        return "source_digest"
    if page_type == "page":
        return "unknown"
    return page_type


def _default_type_for_directory(directory: str) -> str:
    if directory == UNIFIED_KNOWLEDGE_PAGE_DIR:
        return "page"
    return directory.rstrip("s")


def _page_role(directory: str, page_kind: str) -> str:
    if directory == "sources" or page_kind == "source_digest":
        return "source_digest"
    return "knowledge_page"


def _page_facets(metadata: dict[str, str], directory: str, page_kind: str) -> list[str]:
    values: list[str] = []
    values.extend(_metadata_list(metadata.get("facets")))
    values.extend(_metadata_list(metadata.get("tags")))
    values.extend([directory, page_kind])
    facets: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = value.strip().lower().replace(" ", "_").replace("-", "_")
        if text and text not in seen:
            facets.append(text)
            seen.add(text)
    return facets


def _metadata_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("[") and text.endswith("]"):
            text = text[1:-1]
        return [item.strip().strip("'\"") for item in text.split(",") if item.strip().strip("'\"")]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]
