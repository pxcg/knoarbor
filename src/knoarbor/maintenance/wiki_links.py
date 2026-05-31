from __future__ import annotations

from pathlib import Path

from knoarbor.core.markdown import extract_list_items, extract_section
from knoarbor.core.schemas.wiki_write import VaultWriteResult, WikiDraft
from knoarbor.retrieval.wiki_links import add_related_links, related_links_for_page_paths
from knoarbor.storage.wiki_index import update_index, wiki_link_for_path


def reconcile_batch_related_links(vault_path: Path, entries: list[tuple[WikiDraft, VaultWriteResult]]) -> set[Path]:
    """Write provenance links between source digests and knowledge pages."""

    source_entries = [(draft, result) for draft, result in entries if draft.page_dir == "sources"]
    knowledge_entries = [(draft, result) for draft, result in entries if draft.page_dir != "sources"]
    if not source_entries or not knowledge_entries:
        return set()

    changed_paths: set[Path] = set()
    knowledge_links = [wiki_link_for_path(vault_path, result.path, draft.title) for draft, result in knowledge_entries]
    source_links = [wiki_link_for_path(vault_path, result.path, draft.title) for draft, result in source_entries]

    for _, result in source_entries:
        changed_paths.update(_add_links_to_page(result.path, knowledge_links))

    for _, result in knowledge_entries:
        changed_paths.update(_add_links_to_page(result.path, source_links))

    if changed_paths:
        update_index(vault_path)
    return changed_paths


def reconcile_expected_related_pages(vault_path: Path, page_path: Path, expected_page_paths: list[str]) -> dict[str, object]:
    """Write expected related-page links after a draft is committed."""

    links, missing = related_links_for_page_paths(vault_path, expected_page_paths)
    if not links and not missing:
        return {"added_count": 0, "missing": []}

    content = page_path.read_text(encoding="utf-8")
    before = set(extract_list_items(extract_section(content, "Related Pages")))
    changed_paths = _add_links_to_page(page_path, links)
    current_content = page_path.read_text(encoding="utf-8") if changed_paths else content
    after = set(extract_list_items(extract_section(current_content, "Related Pages")))
    added = sorted(after - before)
    return {"added_count": len(added), "added": added, "missing": missing}


def _add_links_to_page(page_path: Path, links: list[str]) -> set[Path]:
    content = page_path.read_text(encoding="utf-8")
    updated, changed = add_related_links(content, links)
    if not changed:
        return set()
    page_path.write_text(updated, encoding="utf-8")
    return {page_path}
