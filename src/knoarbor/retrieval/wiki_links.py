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
from knoarbor.core.wiki_schema import INDEX_EXCLUDED_DIRS, is_index_excluded_file
from knoarbor.retrieval.page_resolver import resolve_page_reference_path
from knoarbor.storage.wiki_index import wiki_link_for_path
from knoarbor.storage.wiki_paths import content_root, resolve_existing_target


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

    direct = resolve_page_reference_path(vault_path, target)
    if direct:
        return direct
    if "/" in normalized:
        directory, title = normalized.split("/", 1)
        return resolve_page_reference_path(vault_path, normalized) or resolve_page_reference_path(vault_path, title, directory=directory)
    return resolve_page_reference_path(vault_path, normalized)


def resolve_relative_wiki_path(vault_path: Path, target: str) -> str | None:
    return resolve_page_reference_path(vault_path, target)


def resolve_wikilink_by_title(vault_path: Path, title: str, directory: str | None) -> str | None:
    return resolve_page_reference_path(vault_path, title, directory=directory)


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

    root = content_root(vault_path)
    for md_path in root.rglob("*.md"):
        relative_parts = md_path.relative_to(root).parts
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
