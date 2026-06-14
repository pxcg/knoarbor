from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from knoarbor.core.markdown import extract_heading, extract_list_items, extract_section, parse_frontmatter
from knoarbor.core.wiki_schema import INDEX_EXCLUDED_DIRS, PAGE_TYPE_ORDER, is_index_excluded_file
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
    for page_dir in PAGE_TYPE_ORDER:
        directory_path = root / page_dir
        if not directory_path.exists():
            continue
        for md_path in sorted(directory_path.glob("*.md")):
            if should_skip_page(vault_path, md_path):
                continue
            try:
                content = md_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            metadata = parse_frontmatter(content)
            page_type = metadata.get("type") or page_dir.rstrip("s")
            pages.append(
                SearchPage(
                    path=md_path,
                    relative_path=relative_wiki_path(vault_path, md_path),
                    directory=page_dir,
                    title=extract_heading(content, md_path.stem),
                    page_type=page_type,
                    status=metadata.get("status"),
                    source=metadata.get("source"),
                    tags=extract_tags_from_page(content, metadata),
                    summary=extract_section(content, "Summary"),
                    key_points=extract_list_items(extract_section(content, "Key Points")),
                    related_pages=extract_related_page_paths(vault_path, extract_section(content, "Related Pages")),
                    headings=extract_headings(content),
                    body=strip_frontmatter(content),
                )
            )
    return pages


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


def expand_related_pages(
    scored: dict[str, ScoredPage],
    pages: list[SearchPage],
    mode: str,
) -> dict[str, ScoredPage]:
    page_by_path = {page.relative_path: page for page in pages}
    inbound_paths = build_inbound_paths(pages)
    initial = sorted(scored.values(), key=lambda item: item.score, reverse=True)
    seed_count = 3 if mode == "balanced" else 5
    max_related = 5 if mode == "balanced" else 10
    added = 0
    for item in initial[:seed_count]:
        candidate_paths = graph_candidate_paths(item.page, inbound_paths)
        for related_path in candidate_paths:
            if added >= max_related:
                return scored
            page = page_by_path.get(related_path)
            if not page:
                continue
            boost, reasons = graph_relevance_boost(item.page, page, item.score)
            if boost <= 0:
                continue
            if related_path in scored:
                scored[related_path].score += boost
                scored[related_path].graph_boost += boost
                scored[related_path].matched_fields.add("related_graph")
                scored[related_path].matched_terms.setdefault("related_graph", []).append(item.page.relative_path)
                scored[related_path].matched_terms.setdefault("graph_reasons", []).extend(reasons)
                scored[related_path].graph_reasons.extend(reason for reason in reasons if reason not in scored[related_path].graph_reasons)
            else:
                scored[related_path] = ScoredPage(
                    page=page,
                    score=boost,
                    matched_fields={"related_graph"},
                    matched_terms={"related_graph": [item.page.relative_path], "graph_reasons": reasons},
                    graph_boost=boost,
                    graph_reasons=reasons,
                )
                added += 1
    return scored


def build_inbound_paths(pages: list[SearchPage]) -> dict[str, list[str]]:
    inbound: dict[str, list[str]] = {}
    for page in pages:
        for related_path in page.related_pages:
            inbound.setdefault(related_path, [])
            if page.relative_path not in inbound[related_path]:
                inbound[related_path].append(page.relative_path)
    return inbound


def graph_candidate_paths(seed: SearchPage, inbound_paths: dict[str, list[str]]) -> list[str]:
    candidates: list[str] = []
    for path in [*seed.related_pages, *inbound_paths.get(seed.relative_path, [])]:
        if path == seed.relative_path or path in candidates:
            continue
        candidates.append(path)
    return candidates


def graph_relevance_boost(seed: SearchPage, candidate: SearchPage, seed_score: float) -> tuple[float, list[str]]:
    reasons: list[str] = []
    boost = 0.0

    if candidate.relative_path in seed.related_pages:
        boost += min(seed_score * 0.18, 2.4)
        reasons.append("outbound_link")

    if seed.relative_path in candidate.related_pages:
        boost += min(seed_score * 0.14, 1.8)
        reasons.append("backlink")

    if seed.source and candidate.source and seed.source == candidate.source:
        boost += 1.2
        reasons.append("shared_source")

    if seed.directory == candidate.directory or seed.page_type == candidate.page_type:
        boost += 0.6
        reasons.append("type_affinity")

    return boost, reasons


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
