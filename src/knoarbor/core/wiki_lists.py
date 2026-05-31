from __future__ import annotations

import re

from knoarbor.core.markdown import normalize_list_item, wiki_target_key


def merge_unique_items(existing: list[str], incoming: list[str], max_items: int | None = None) -> list[str]:
    merged: list[str] = []
    index_by_key: dict[str, int] = {}
    for item in [*existing, *incoming]:
        key = list_item_identity(item)
        if not key:
            continue
        if key in index_by_key:
            existing_index = index_by_key[key]
            merged[existing_index] = prefer_list_item(item, merged[existing_index])
            continue
        index_by_key[key] = len(merged)
        merged.append(item)
        if max_items and len(merged) >= max_items:
            break
    return merged


def list_item_identity(value: str) -> str:
    match = re.search(r"\[\[([^\]|#]+)", value)
    if match:
        return wiki_target_key(match.group(1))
    return normalize_list_item(value)


def prefer_list_item(candidate: str, existing: str) -> str:
    candidate_has_alias = bool(re.search(r"\[\[[^\]]+\|[^\]]+\]\]", candidate))
    existing_has_alias = bool(re.search(r"\[\[[^\]]+\|[^\]]+\]\]", existing))
    if candidate_has_alias and not existing_has_alias:
        return candidate
    return existing
