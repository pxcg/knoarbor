from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from knoarbor.core.markdown import extract_heading, extract_list_items, extract_section, parse_frontmatter
from knoarbor.core.schemas.page_identity import PageIdentity, normalize_facet
from knoarbor.core.schemas.wiki_lint import WikiLintIssue
from knoarbor.core.wiki_schema import FRONTMATTER_TYPES, INDEX_PAGE_DIRS, UNIFIED_KNOWLEDGE_PAGE_DIR, is_index_excluded_file
from knoarbor.maintenance.lint_models import LintPage
from knoarbor.storage.wiki_paths import SOURCE_DIGEST_ROOT_DIR, content_relative_path, content_root, source_digest_root


def collect_pages(vault_path: Path) -> list[LintPage]:
    pages: list[LintPage] = []
    root = content_root(vault_path)
    source_root = source_digest_root(vault_path)
    seen_relative_paths: set[str] = set()
    for md_path in _iter_lint_page_paths(root, source_root):
        try:
            content = md_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = ""
        relative_path = content_relative_path(vault_path, md_path)
        if relative_path in seen_relative_paths:
            continue
        seen_relative_paths.add(relative_path)
        directory = _page_directory(root, source_root, md_path)
        metadata = parse_frontmatter(content) if content else {}
        title = extract_heading(content, md_path.stem) if content else md_path.stem
        identity = _page_identity(relative_path, directory, metadata, title, content)
        pages.append(
            LintPage(
                path=md_path,
                relative_path=relative_path,
                directory=directory,
                stem=md_path.stem,
                title=title,
                content=content,
                metadata=metadata,
                links=extract_wiki_links(content),
                entities=extract_entities(content),
                relation_nodes=extract_relation_nodes(content),
                sources=extract_page_sources(content, metadata),
                canonical_path=identity.canonical_path,
                legacy_paths=identity.legacy_paths,
                page_kind=identity.page_kind,
                role=identity.role,
                facets=identity.facets,
            )
        )
    return pages


def _iter_lint_page_paths(root: Path, source_root: Path) -> list[Path]:
    paths: list[Path] = []
    if root.exists():
        for md_path in sorted(root.glob("*.md")):
            if not is_index_excluded_file(md_path.name):
                paths.append(md_path)
    for directory in INDEX_PAGE_DIRS:
        page_dir = root / directory
        if not page_dir.exists():
            continue
        for md_path in sorted(page_dir.glob("*.md")):
            if not is_index_excluded_file(md_path.name):
                paths.append(md_path)
    if source_root.exists():
        for md_path in sorted(source_root.glob("*.md")):
            if not is_index_excluded_file(md_path.name):
                paths.append(md_path)
    return paths


def _page_directory(root: Path, source_root: Path, md_path: Path) -> str:
    try:
        md_path.resolve().relative_to(source_root.resolve())
        return SOURCE_DIGEST_ROOT_DIR
    except ValueError:
        pass
    if md_path.parent.resolve() == root.resolve():
        return UNIFIED_KNOWLEDGE_PAGE_DIR
    return md_path.parent.name


def _page_identity(relative_path: str, directory: str, metadata: dict[str, str], title: str, content: str) -> PageIdentity:
    page_kind = _infer_page_kind(directory, metadata)
    role = "source_digest" if directory == "sources" or page_kind == "source_digest" else "knowledge_page"
    return PageIdentity(
        canonical_path=metadata.get("canonical_path") or relative_path,
        legacy_paths=_metadata_list(metadata.get("legacy_paths")),
        title=title,
        page_kind=page_kind,
        subject_kind=metadata.get("subject_kind", ""),
        role=role,
        facets=_lint_facets(directory, page_kind, metadata, content),
        atom_ids=_metadata_list(metadata.get("atom_ids")) + _metadata_list(metadata.get("claim_ids")),
        relation_ids=_metadata_list(metadata.get("relation_ids")),
        source_digest_ids=_metadata_list(metadata.get("source_digest_ids")),
    )


def _infer_page_kind(directory: str, metadata: dict[str, str]) -> str:
    raw_kind = metadata.get("page_kind") or metadata.get("kind")
    if raw_kind:
        return _normalize_page_kind(raw_kind)
    raw_type = metadata.get("type") or FRONTMATTER_TYPES.get(directory, "unknown")
    if directory == "sources" or raw_type == "source":
        return "source_digest"
    if raw_type == "page":
        return "unknown"
    return _normalize_page_kind(raw_type)


def _normalize_page_kind(value: str) -> str:
    normalized = normalize_facet(value)
    aliases = {"source": "source_digest", "question": "query", "qa": "query", "page": "unknown"}
    allowed = {"concept", "entity", "workflow", "comparison", "timeline", "query", "note", "source_digest", "generated_view", "unknown"}
    normalized = aliases.get(normalized, normalized or "unknown")
    return normalized if normalized in allowed else "unknown"


def _lint_facets(directory: str, page_kind: str, metadata: dict[str, str], content: str) -> list[str]:
    values = [directory, page_kind]
    values.extend(_metadata_list(metadata.get("facets")))
    values.extend(_metadata_list(metadata.get("tags")))
    for heading, facet in {
        "Claims": "claims",
        "Relations": "relations",
        "Synthesis": "synthesis",
        "Definition": "definition",
    }.items():
        if has_section(content, heading):
            values.append(facet)
    return [facet for facet in (normalize_facet(value) for value in values) if facet]


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


def filter_lint_scope(
    pages: list[LintPage],
    issues: list[WikiLintIssue],
    stats: dict[str, Any],
    scope_pages: list[str],
    include_related: bool,
) -> tuple[list[LintPage], list[WikiLintIssue], dict[str, Any]]:
    normalized_scope = {normalize_scope_path(path) for path in scope_pages if normalize_scope_path(path)}
    if not normalized_scope:
        return pages, issues, {**stats, "scope": "global", "scoped": False}

    pages_by_relative, pages_by_stem, pages_by_title = page_lookup_maps(pages)
    selected = resolve_scope_paths(normalized_scope, pages_by_relative, pages_by_stem, pages_by_title)
    if include_related:
        selected = expand_related_scope(selected, pages, pages_by_relative, pages_by_stem, pages_by_title)

    selected_pages = [page for page in pages if page.relative_path in selected]
    selected_issues = [issue for issue in issues if issue.path in selected or issue.path in {"index.md", ".knoarbor/index"}]
    severity_counts = Counter(issue.severity for issue in selected_issues)
    scoped_stats = {
        **stats,
        "scope": "pages",
        "scoped": True,
        "requested_scope_pages": sorted(normalized_scope),
        "scope_pages": sorted(selected),
        "scope_page_count": len(selected_pages),
        "scope_include_related": include_related,
        "page_count": len(selected_pages),
        "issue_count": len(selected_issues),
        "error_count": severity_counts.get("error", 0),
        "warning_count": severity_counts.get("warning", 0),
        "info_count": severity_counts.get("info", 0),
        "directories": dict(Counter(page.directory for page in selected_pages)),
        "graph_health": graph_health_stats(selected_pages),
    }
    return selected_pages, selected_issues, scoped_stats


def normalize_scope_path(path: str) -> str:
    value = str(path).strip().lstrip("/")
    if not value:
        return ""
    return value if value.endswith(".md") else f"{value}.md"


def resolve_scope_paths(
    scope_pages: set[str],
    pages_by_relative: dict[str, LintPage],
    pages_by_stem: dict[str, list[LintPage]],
    pages_by_title: dict[str, list[LintPage]],
) -> set[str]:
    resolved_paths: set[str] = set()
    for raw_path in scope_pages:
        target = normalize_link_target(raw_path)
        resolved = resolve_link(target, pages_by_relative, pages_by_stem, pages_by_title)
        if len(resolved) == 1:
            resolved_paths.add(resolved[0].relative_path)
        elif raw_path in {f"{key}.md" for key in pages_by_relative}:
            resolved_paths.add(raw_path)
    return resolved_paths


def expand_related_scope(
    selected: set[str],
    pages: list[LintPage],
    pages_by_relative: dict[str, LintPage],
    pages_by_stem: dict[str, list[LintPage]],
    pages_by_title: dict[str, list[LintPage]],
) -> set[str]:
    expanded = set(selected)
    adjacency = provenance_adjacency(pages, pages_by_relative, pages_by_stem, pages_by_title)
    for page in pages:
        resolved_links = resolved_paths_from_links(page.links, pages_by_relative, pages_by_stem, pages_by_title) | adjacency.get(page.relative_path, set())
        if page.relative_path in selected:
            expanded.update(resolved_links)
        if selected.intersection(resolved_links):
            expanded.add(page.relative_path)
    return expanded


def extract_wiki_links(content: str) -> list[str]:
    from knoarbor.maintenance.lint_rules import IGNORED_LINK_PREFIXES

    links: list[str] = []
    for match in re.finditer(r"\[\[([^\]]+)\]\]", content):
        target = match.group(1).split("|", 1)[0].strip()
        if not target or target.startswith(IGNORED_LINK_PREFIXES):
            continue
        links.append(target)
    return links


def extract_entities(content: str) -> list[str]:
    entities: list[str] = []
    for line in extract_section(content, "Entities").splitlines():
        text = line.strip()
        if not text.startswith("- "):
            continue
        value = _clean_relation_node(text[2:])
        if value and value not in entities:
            entities.append(value)
    return entities


def extract_relation_nodes(content: str) -> list[str]:
    nodes: list[str] = []
    for cells in _markdown_table_rows(extract_section(content, "Relations")):
        if len(cells) < 3:
            continue
        subject, _predicate, obj = cells[:3]
        if subject.lower() == "subject":
            continue
        for value in (_clean_relation_node(subject), _clean_relation_node(obj)):
            if value and value not in nodes:
                nodes.append(value)
    return nodes


def extract_page_sources(content: str, metadata: dict[str, object]) -> list[str]:
    sources: list[str] = []
    for source in [
        *_metadata_sources(metadata.get("source")),
        *_source_identity_values(content),
        *_evidence_sources(content),
        *extract_list_items(extract_section(content, "Source")),
        *extract_list_items(extract_section(content, "Raw Source")),
    ]:
        text = _normalize_source_value(source)
        if text and text not in sources:
            sources.append(text)
    return sources


def extract_headings(content: str) -> list[str]:
    return [match.group(1).strip() for match in re.finditer(r"^#{1,6}\s+(.+)$", content, flags=re.MULTILINE)]


def has_section(content: str, heading: str) -> bool:
    return bool(re.search(rf"^##\s+{re.escape(heading)}\s*$", content, flags=re.MULTILINE))


def normalize_link_target(raw_link: str) -> str:
    target = raw_link.split("#", 1)[0].strip().lstrip("/")
    return target.removesuffix(".md")


def resolve_link(
    target: str,
    pages_by_relative: dict[str, LintPage],
    pages_by_stem: dict[str, list[LintPage]],
    pages_by_title: dict[str, list[LintPage]],
) -> list[LintPage]:
    if target in pages_by_relative:
        return [pages_by_relative[target]]
    target_with_suffix = target if target.endswith(".md") else f"{target}.md"
    if target_with_suffix in pages_by_relative:
        return [pages_by_relative[target_with_suffix]]
    if "/" in target:
        directory, title = target.split("/", 1)
        return [page for page in pages_by_title.get(normalize_title(title), []) if page.directory == directory]
    return pages_by_stem.get(target, []) or pages_by_title.get(normalize_title(target), [])


def page_lookup_maps(
    pages: list[LintPage],
) -> tuple[dict[str, LintPage], dict[str, list[LintPage]], dict[str, list[LintPage]]]:
    pages_by_relative: dict[str, LintPage] = {}
    pages_by_stem: dict[str, list[LintPage]] = defaultdict(list)
    pages_by_title: dict[str, list[LintPage]] = defaultdict(list)
    for page in pages:
        for path in [page.relative_path, page.relative_path.removesuffix(".md"), page.canonical_path, page.canonical_path.removesuffix(".md"), *page.legacy_paths]:
            if path:
                pages_by_relative[path] = page
                pages_by_relative[path.removesuffix(".md")] = page
        pages_by_stem[page.stem].append(page)
        pages_by_title[normalize_title(page.title)].append(page)
    return pages_by_relative, pages_by_stem, pages_by_title


def resolved_paths_from_links(
    links: list[str],
    pages_by_relative: dict[str, LintPage],
    pages_by_stem: dict[str, list[LintPage]],
    pages_by_title: dict[str, list[LintPage]],
) -> set[str]:
    paths: set[str] = set()
    for raw_link in links:
        target = normalize_link_target(raw_link)
        resolved = resolve_link(target, pages_by_relative, pages_by_stem, pages_by_title)
        if len(resolved) == 1:
            paths.add(resolved[0].relative_path)
    return paths


def semantic_adjacency(
    pages: list[LintPage],
    pages_by_relative: dict[str, LintPage],
    pages_by_stem: dict[str, list[LintPage]],
    pages_by_title: dict[str, list[LintPage]],
) -> dict[str, set[str]]:
    return _page_adjacency(
        pages,
        pages_by_relative,
        pages_by_stem,
        pages_by_title,
        include_shared_semantic_nodes=True,
    )


def provenance_adjacency(
    pages: list[LintPage],
    pages_by_relative: dict[str, LintPage],
    pages_by_stem: dict[str, list[LintPage]],
    pages_by_title: dict[str, list[LintPage]],
) -> dict[str, set[str]]:
    return _page_adjacency(
        pages,
        pages_by_relative,
        pages_by_stem,
        pages_by_title,
        include_shared_semantic_nodes=False,
    )


def _page_adjacency(
    pages: list[LintPage],
    pages_by_relative: dict[str, LintPage],
    pages_by_stem: dict[str, list[LintPage]],
    pages_by_title: dict[str, list[LintPage]],
    *,
    include_shared_semantic_nodes: bool,
) -> dict[str, set[str]]:
    adjacency: dict[str, set[str]] = {page.relative_path: set() for page in pages if page.is_knowledge_page or page.is_source_digest}
    for page in pages:
        if page.relative_path not in adjacency:
            continue
        for target_path in resolved_paths_from_links(page.links, pages_by_relative, pages_by_stem, pages_by_title):
            _connect(adjacency, page.relative_path, target_path)

    source_groups: dict[str, list[str]] = defaultdict(list)
    semantic_groups: dict[str, list[str]] = defaultdict(list)
    for page in pages:
        if page.relative_path not in adjacency:
            continue
        for source in page.sources:
            if source.startswith(("raw/", "sd_")) or source.startswith("/"):
                source_groups[source].append(page.relative_path)
        if include_shared_semantic_nodes:
            for node in [*page.entities, *page.relation_nodes]:
                key = normalize_title(node)
                if key:
                    semantic_groups[key].append(page.relative_path)

    for paths in [*source_groups.values(), *semantic_groups.values()]:
        unique_paths = sorted(set(paths))
        if len(unique_paths) < 2:
            continue
        for index, source_path in enumerate(unique_paths):
            for target_path in unique_paths[index + 1 :]:
                _connect(adjacency, source_path, target_path)
    return adjacency


def graph_health_stats(pages: list[LintPage]) -> dict[str, object]:
    pages_by_relative, pages_by_stem, pages_by_title = page_lookup_maps(pages)
    knowledge_paths = {page.relative_path for page in pages if page.is_knowledge_page or page.is_source_digest}
    adjacency = semantic_adjacency(pages, pages_by_relative, pages_by_stem, pages_by_title)
    degrees: Counter[str] = Counter()
    for source_path, targets in adjacency.items():
        for target_path in targets:
            if source_path < target_path:
                degrees[source_path] += 1
                degrees[target_path] += 1

    seen: set[str] = set()
    components: list[list[str]] = []
    for path in sorted(knowledge_paths):
        if path in seen:
            continue
        stack = [path]
        component: list[str] = []
        seen.add(path)
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbor in sorted(adjacency.get(current, set())):
                if neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)
        components.append(sorted(component))

    component_sizes = sorted((len(component) for component in components), reverse=True)
    isolated = sorted(component[0] for component in components if len(component) == 1)
    small_components = [component for component in components if 1 < len(component) <= 3]
    hub_pages = [
        {"path": path, "degree": degree}
        for path, degree in sorted(degrees.items(), key=lambda item: (-item[1], item[0]))[:10]
    ]
    return {
        "node_count": len(knowledge_paths),
        "component_count": len(components),
        "largest_component_size": component_sizes[0] if component_sizes else 0,
        "isolated_page_count": len(isolated),
        "isolated_pages": isolated[:20],
        "small_component_count": len(small_components),
        "small_components": [component for component in small_components[:10]],
        "hub_pages": hub_pages,
    }


def normalize_title(title: str) -> str:
    value = re.sub(r"[\u2010-\u2015\u2212]", "-", title)
    return re.sub(r"\s+", " ", value).strip().lower()


def _connect(adjacency: dict[str, set[str]], source_path: str, target_path: str) -> None:
    if source_path == target_path:
        return
    if source_path not in adjacency or target_path not in adjacency:
        return
    adjacency[source_path].add(target_path)
    adjacency[target_path].add(source_path)


def _metadata_sources(value: object) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _evidence_sources(content: str) -> list[str]:
    sources: list[str] = []
    for cells in _markdown_table_rows(extract_section(content, "Evidence")):
        if len(cells) < 2:
            continue
        claim, source = cells[:2]
        if claim.lower() == "claim":
            continue
        source = source.strip()
        if source and source not in sources:
            sources.append(source)
    return sources


def _source_identity_values(content: str) -> list[str]:
    values: list[str] = []
    for item in extract_list_items(extract_section(content, "Source Identity")):
        text = item.strip().strip("`")
        lowered = text.lower()
        if lowered.startswith("raw source:"):
            values.append(text.split(":", 1)[1].strip().strip("`"))
        elif lowered.startswith("source digest ids:"):
            raw_values = text.split(":", 1)[1]
            values.extend(part.strip().strip("`") for part in re.split(r"[,，]", raw_values) if part.strip())
    return values


def _normalize_source_value(value: str) -> str:
    text = value.strip().strip("`")
    lowered = text.lower()
    if lowered.startswith("raw source:"):
        return text.split(":", 1)[1].strip().strip("`")
    if lowered.startswith(("content hash:", "atom ids:", "source digest ids:")):
        return ""
    return text


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


def _clean_relation_node(value: str) -> str:
    text = re.sub(r"\*\*", "", value).strip()
    if text.startswith("[[") and text.endswith("]]"):
        text = text[2:-2]
    if "|" in text:
        text = text.split("|", 1)[-1]
    return text.strip()
