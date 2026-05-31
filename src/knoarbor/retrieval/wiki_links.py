from __future__ import annotations

import re
from pathlib import Path

from knoarbor.core.markdown import (
    extract_heading,
    extract_list_items,
    extract_section,
    format_wikilink,
    normalize_list_item,
    render_list_section,
    replace_section,
    wiki_target_key,
)
from knoarbor.core.wiki_lists import merge_unique_items
from knoarbor.core.wiki_schema import INDEX_EXCLUDED_DIRS, PAGE_TYPE_ORDER, is_index_excluded_file
from knoarbor.storage.wiki_index import relative_wiki_path, wiki_link_for_path
from knoarbor.storage.wiki_paths import resolve_existing_target


def normalize_title_key(value: str) -> str:
    normalized = re.sub(r"[\u2010-\u2015\u2212]", "-", value)
    return re.sub(r"\s+", " ", normalized).strip().lower()


def canonical_wiki_list_item_identity(vault_path: Path, value: str) -> str:
    match = re.search(r"\[\[([^\]|#]+)", value)
    if not match:
        return normalize_list_item(value)

    target = wiki_target_key(match.group(1))
    resolved = resolve_wikilink_target(vault_path, target)
    return resolved or target


def resolve_wikilink_target(vault_path: Path, target: str) -> str | None:
    normalized = wiki_target_key(target)
    if not normalized:
        return None

    relative_path = resolve_relative_wiki_path(vault_path, normalized)
    if relative_path:
        return relative_path

    if "/" in normalized:
        directory, title = normalized.split("/", 1)
        return resolve_wikilink_by_title(vault_path, title, directory)
    return resolve_wikilink_by_title(vault_path, normalized, None)


def resolve_relative_wiki_path(vault_path: Path, target: str) -> str | None:
    wanted = f"{target.removesuffix('.md')}.md".lower()
    for page_dir in PAGE_TYPE_ORDER:
        directory_path = vault_path / page_dir
        if not directory_path.exists():
            continue
        for md_path in directory_path.glob("*.md"):
            if is_index_excluded_file(md_path.name):
                continue
            relative = relative_wiki_path(vault_path, md_path)
            if relative.lower() == wanted:
                return relative
    return None


def resolve_wikilink_by_title(vault_path: Path, title: str, directory: str | None) -> str | None:
    matches: list[str] = []
    target_title = normalize_title_key(title)
    for page_dir in PAGE_TYPE_ORDER:
        if directory and page_dir != directory:
            continue
        directory_path = vault_path / page_dir
        if not directory_path.exists():
            continue
        for md_path in directory_path.glob("*.md"):
            if is_index_excluded_file(md_path.name):
                continue
            stem_matches = normalize_title_key(md_path.stem) == target_title
            try:
                heading = extract_heading(md_path.read_text(encoding="utf-8"), md_path.stem)
            except UnicodeDecodeError:
                heading = md_path.stem
            title_matches = normalize_title_key(heading) == target_title
            if stem_matches or title_matches:
                matches.append(relative_wiki_path(vault_path, md_path))
    return matches[0] if len(matches) == 1 else None


def replace_wikilink_targets(content: str, old_target: str, new_target: str, link_text: str | None = None) -> tuple[str, int]:
    old_key = wiki_target_key(old_target)
    replacements = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal replacements
        target = match.group("target").strip()
        alias = match.group("alias")
        if wiki_target_key(target) != old_key:
            return match.group(0)
        replacements += 1
        suffix = "#" + target.split("#", 1)[1].strip() if "#" in target else ""
        return format_wikilink(new_target.strip() + suffix, link_text or alias)

    updated = re.sub(r"\[\[(?P<target>[^\]|]+)(?:\|(?P<alias>[^\]]+))?\]\]", replace, content)
    return updated, replacements


def sanitize_unresolved_wikilinks(vault_path: Path, content: str) -> tuple[str, list[str]]:
    """Convert unresolved internal links to plain text after all writes finish."""

    removed: list[str] = []

    def replace(match: re.Match[str]) -> str:
        target = match.group("target").strip()
        alias = match.group("alias")
        if resolve_wikilink_target(vault_path, target):
            return match.group(0)
        removed.append(target)
        if alias and alias.strip():
            return alias.strip()
        target_without_anchor = target.split("#", 1)[0].strip()
        return Path(target_without_anchor).stem if "/" in target_without_anchor else target_without_anchor

    updated = re.sub(r"\[\[(?P<target>[^\]|]+)(?:\|(?P<alias>[^\]]+))?\]\]", replace, content)
    return updated, removed


def find_related_links(vault_path: Path, source_focus: str, current_path: Path | None = None) -> list[str]:
    words = {word for word in re.findall(r"[\w\u4e00-\u9fff]{2,}", source_focus) if len(word) >= 2}
    related: list[str] = []

    for md_path in vault_path.rglob("*.md"):
        relative_parts = md_path.relative_to(vault_path).parts
        if current_path and md_path.resolve() == current_path.resolve():
            continue
        if any(part in INDEX_EXCLUDED_DIRS for part in relative_parts):
            continue
        if is_index_excluded_file(md_path.name):
            continue
        try:
            content = md_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        score = sum(1 for word in words if word in content or word in md_path.stem)
        if score > 0:
            title = extract_heading(content, md_path.stem)
            related.append(wiki_link_for_path(vault_path, md_path, title))
        if len(related) >= 5:
            break

    return related


def add_related_links(content: str, links: list[str]) -> tuple[str, bool]:
    existing = extract_list_items(extract_section(content, "Related Pages"))
    merged = merge_unique_items(existing, links, 30)
    if merged == existing:
        return content, False
    return replace_section(content, "Related Pages", render_list_section(merged, "暂无关联知识")).rstrip() + "\n", True


def related_links_for_page_paths(vault_path: Path, page_paths: list[str]) -> tuple[list[str], list[str]]:
    links: list[str] = []
    missing: list[str] = []
    for raw_path in page_paths:
        target_path = resolve_existing_target(vault_path, raw_path)
        if not target_path:
            missing.append(raw_path)
            continue
        title = extract_heading(target_path.read_text(encoding="utf-8"), target_path.stem)
        links.append(wiki_link_for_path(vault_path, target_path, title))
    return links, missing
