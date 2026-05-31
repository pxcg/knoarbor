from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from knoarbor.core.markdown import extract_heading, extract_list_items, extract_section, parse_frontmatter
from knoarbor.core.wiki_schema import INDEX_EXCLUDED_DIRS, PAGE_TYPE_ORDER, is_index_excluded_file
from knoarbor.retrieval.wiki_links import resolve_wikilink_target
from knoarbor.storage import relative_wiki_path


FIELD_WEIGHTS: dict[str, float] = {
    "title": 5.0,
    "tags": 3.0,
    "summary": 3.0,
    "key_points": 2.5,
    "headings": 2.0,
    "path": 1.0,
    "body": 0.8,
}


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


def collect_search_pages(vault_path: Path) -> list[SearchPage]:
    pages: list[SearchPage] = []
    for page_dir in PAGE_TYPE_ORDER:
        directory_path = vault_path / page_dir
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
    parts = path.relative_to(vault_path).parts
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
        if term and term not in seen:
            seen.add(term)
            unique.append(term)
    return unique[:80]


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().lower()


def score_pages(pages: list[SearchPage], terms: list[str], query: str) -> dict[str, ScoredPage]:
    scored: dict[str, ScoredPage] = {}
    for page in pages:
        score = 0.0
        matched: set[str] = set()
        matched_terms: dict[str, list[str]] = {}
        score += score_field(page.title, terms, query, FIELD_WEIGHTS["title"], "title", matched, matched_terms)
        score += score_field(" ".join(page.tags), terms, query, FIELD_WEIGHTS["tags"], "tags", matched, matched_terms)
        score += score_field(page.summary, terms, query, FIELD_WEIGHTS["summary"], "summary", matched, matched_terms)
        score += score_field(" ".join(page.key_points), terms, query, FIELD_WEIGHTS["key_points"], "key_points", matched, matched_terms)
        score += score_field(" ".join(page.headings), terms, query, FIELD_WEIGHTS["headings"], "headings", matched, matched_terms)
        score += score_field(page.relative_path, terms, query, FIELD_WEIGHTS["path"], "path", matched, matched_terms)
        score += score_field(page.body, terms, query, FIELD_WEIGHTS["body"], "body", matched, matched_terms)
        if score > 0:
            scored[page.relative_path] = ScoredPage(page=page, score=score, matched_fields=matched, matched_terms=matched_terms)
    return scored


def score_field(
    value: str,
    terms: list[str],
    query: str,
    weight: float,
    field_name: str,
    matched: set[str],
    matched_terms: dict[str, list[str]],
) -> float:
    text = normalize_text(value)
    if not text:
        return 0.0
    field_hits = [term for term in terms if term in text]
    hits = len(field_hits)
    phrase = normalize_text(query)
    phrase_boost = 2 if len(query.strip()) >= 3 and phrase in text else 0
    if hits or phrase_boost:
        matched.add(field_name)
        values = list(dict.fromkeys([*field_hits[:12], *([phrase] if phrase_boost else [])]))
        matched_terms[field_name] = values
    return min(hits, 8) * weight + phrase_boost * weight


def expand_related_pages(
    scored: dict[str, ScoredPage],
    pages: list[SearchPage],
    mode: str,
) -> dict[str, ScoredPage]:
    page_by_path = {page.relative_path: page for page in pages}
    initial = sorted(scored.values(), key=lambda item: item.score, reverse=True)
    seed_count = 3 if mode == "balanced" else 5
    max_related = 5 if mode == "balanced" else 10
    added = 0
    for item in initial[:seed_count]:
        for related_path in item.page.related_pages:
            if added >= max_related:
                return scored
            page = page_by_path.get(related_path)
            if not page:
                continue
            boost = min(item.score * 0.25, 3.0)
            if related_path in scored:
                scored[related_path].score += boost
                scored[related_path].graph_boost += boost
                scored[related_path].matched_fields.add("related_graph")
                scored[related_path].matched_terms.setdefault("related_graph", []).append(item.page.relative_path)
            else:
                scored[related_path] = ScoredPage(
                    page=page,
                    score=boost,
                    matched_fields={"related_graph"},
                    matched_terms={"related_graph": [item.page.relative_path]},
                    graph_boost=boost,
                )
                added += 1
    return scored


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
