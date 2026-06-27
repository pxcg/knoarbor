from __future__ import annotations

import re
from pathlib import Path

from knoarbor.core.markdown import (
    format_wikilink,
    normalize_list_item,
    wiki_target_key,
)
from knoarbor.retrieval.page_resolver import resolve_page_reference_path


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

