from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from knoarbor.core.markdown import extract_heading, parse_frontmatter
from knoarbor.core.schemas.wiki_lint import WikiLintIssue
from knoarbor.core.wiki_schema import PAGE_TYPE_ORDER, is_index_excluded_file
from knoarbor.maintenance.lint_models import LintPage
from knoarbor.maintenance.lint_rules import KNOWLEDGE_DIRS


def collect_pages(vault_path: Path) -> list[LintPage]:
    pages: list[LintPage] = []
    for directory in PAGE_TYPE_ORDER:
        page_dir = vault_path / directory
        if not page_dir.exists():
            continue
        for md_path in sorted(page_dir.glob("*.md")):
            if is_index_excluded_file(md_path.name):
                continue
            try:
                content = md_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                content = ""
            relative_path = md_path.relative_to(vault_path).as_posix()
            metadata = parse_frontmatter(content) if content else {}
            pages.append(
                LintPage(
                    path=md_path,
                    relative_path=relative_path,
                    directory=directory,
                    stem=md_path.stem,
                    title=extract_heading(content, md_path.stem) if content else md_path.stem,
                    content=content,
                    metadata=metadata,
                    links=extract_wiki_links(content),
                )
            )
    return pages


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
    selected_issues = [issue for issue in issues if issue.path in selected or issue.path == "index.md"]
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
    for page in pages:
        resolved_links = resolved_paths_from_links(page.links, pages_by_relative, pages_by_stem, pages_by_title)
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
    if "/" in target:
        directory, title = target.split("/", 1)
        return [page for page in pages_by_title.get(normalize_title(title), []) if page.directory == directory]
    return pages_by_stem.get(target, []) or pages_by_title.get(normalize_title(target), [])


def page_lookup_maps(
    pages: list[LintPage],
) -> tuple[dict[str, LintPage], dict[str, list[LintPage]], dict[str, list[LintPage]]]:
    pages_by_relative = {page.relative_path.removesuffix(".md"): page for page in pages}
    pages_by_stem: dict[str, list[LintPage]] = defaultdict(list)
    pages_by_title: dict[str, list[LintPage]] = defaultdict(list)
    for page in pages:
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


def graph_health_stats(pages: list[LintPage]) -> dict[str, object]:
    pages_by_relative, pages_by_stem, pages_by_title = page_lookup_maps(pages)
    knowledge_paths = {page.relative_path for page in pages if page.directory in KNOWLEDGE_DIRS | {"sources"}}
    adjacency: dict[str, set[str]] = {path: set() for path in knowledge_paths}
    degrees: Counter[str] = Counter()

    for page in pages:
        if page.relative_path not in knowledge_paths:
            continue
        resolved_paths = resolved_paths_from_links(page.links, pages_by_relative, pages_by_stem, pages_by_title)
        for target_path in resolved_paths:
            if target_path not in knowledge_paths or target_path == page.relative_path:
                continue
            adjacency[page.relative_path].add(target_path)
            adjacency[target_path].add(page.relative_path)
            degrees[page.relative_path] += 1
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
