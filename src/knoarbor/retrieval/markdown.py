from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from knoarbor.core.markdown import extract_heading, extract_list_items, extract_section
from knoarbor.core.wiki_schema import INDEX_EXCLUDED_DIRS, UNIFIED_KNOWLEDGE_PAGE_DIR, is_index_excluded_file
from knoarbor.retrieval.bm25 import BM25Document, BM25Field, score_bm25_documents
from knoarbor.retrieval.wiki_links import resolve_wikilink_target
from knoarbor.storage import relative_wiki_path
from knoarbor.storage.wiki_paths import SOURCE_DIGEST_ROOT_DIR, content_root, source_digest_root


FIELD_WEIGHTS: dict[str, float] = {
    "title": 5.0,
    "summary": 3.0,
    "entities": 3.0,
    "claims": 2.5,
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
    entities: list[str]
    summary: str
    claim_points: list[str]
    outbound_links: list[str]
    headings: list[str]
    body: str
    canonical_path: str = ""
    role: str = "knowledge_page"
    relations: list[dict[str, str]] = field(default_factory=list)


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
        relative_path = relative_wiki_path(vault_path, md_path)
        entities = _extract_entities(content)
        pages.append(
            SearchPage(
                path=md_path,
                relative_path=relative_path,
                directory=page_dir,
                title=extract_heading(content, md_path.stem),
                entities=entities,
                summary=extract_section(content, "Summary"),
                claim_points=extract_list_items(extract_section(content, "Claims")),
                relations=_extract_relation_rows(extract_section(content, "Relations")),
                outbound_links=_extract_wikilink_paths(vault_path, content),
                headings=extract_headings(content),
                body=strip_frontmatter(content),
                canonical_path=relative_path,
                role=_page_role(page_dir),
            )
        )
    return pages


def _iter_search_page_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    if root.name == "pages" and root.parent.name == "wiki":
        vault = root.parent.parent
    elif root.name == "pages":
        vault = root.parent
    else:
        vault = root
    source_root = source_digest_root(vault)
    for md_path in sorted(root.glob("*.md")):
        if not is_index_excluded_file(md_path.name):
            paths.append(md_path)
    if source_root.exists():
        for md_path in sorted(source_root.glob("*.md")):
            if not is_index_excluded_file(md_path.name):
                paths.append(md_path)
    return paths


def _extract_relation_rows(section: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for cells in _markdown_table_rows(section):
        if len(cells) < 4:
            continue
        subject, predicate, obj, claim = cells[:4]
        if subject.lower() == "subject" or not subject or not predicate or not obj:
            continue
        rows.append(
            {
                "subject": _clean_graph_object(subject),
                "predicate": predicate.strip(),
                "object": _clean_graph_object(obj),
                "claim": claim.strip().upper(),
            }
        )
    return rows


def _markdown_table_rows(section: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if cells and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        rows.append(cells)
    return rows


def _clean_graph_object(value: str) -> str:
    text = value.strip()
    if text.startswith("[[") and text.endswith("]]"):
        text = text[2:-2]
    if "|" in text:
        text = text.split("|", 1)[-1]
    return text.strip()


def _page_directory(vault_path: Path, md_path: Path) -> str:
    root = content_root(vault_path)
    try:
        md_path.resolve().relative_to(source_digest_root(vault_path).resolve())
        return SOURCE_DIGEST_ROOT_DIR
    except ValueError:
        pass
    if md_path.parent.resolve() == root.resolve():
        return UNIFIED_KNOWLEDGE_PAGE_DIR
    return md_path.parent.name


def should_skip_page(vault_path: Path, path: Path) -> bool:
    try:
        parts = path.relative_to(content_root(vault_path)).parts
    except ValueError:
        parts = path.relative_to(source_digest_root(vault_path)).parts
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
            BM25Field("summary", page.summary, FIELD_WEIGHTS["summary"]),
            BM25Field("entities", " ".join(page.entities), FIELD_WEIGHTS["entities"]),
            BM25Field("claims", " ".join(page.claim_points), FIELD_WEIGHTS["claims"]),
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


def _extract_wikilink_paths(vault_path: Path, content: str) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(r"\[\[([^\]|#]+)", content):
        resolved = resolve_wikilink_target(vault_path, match.group(1))
        if not resolved or resolved in seen:
            continue
        seen.add(resolved)
        paths.append(resolved)
    return paths


def _page_role(directory: str) -> str:
    if directory == "sources":
        return "source_digest"
    return "knowledge_page"


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
