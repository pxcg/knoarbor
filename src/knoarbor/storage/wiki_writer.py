from __future__ import annotations

import difflib
from pathlib import Path

from knoarbor.core.errors import PolicyRejection
from knoarbor.core.hashing import content_hash
from knoarbor.core.markdown import extract_list_items, extract_section, normalize_list_item, parse_frontmatter
from knoarbor.core.schemas.wiki_write import VaultWriteResult, WikiDraft
from knoarbor.retrieval.wiki_links import find_related_links
from knoarbor.semantic.wiki_render import apply_patched_markdown, render_markdown
from knoarbor.storage.wiki_paths import (
    available_title_path,
    resolve_existing_by_hash,
    resolve_required_target,
)


TRACKED_WRITE_SECTIONS = (
    "Summary",
    "Source Focus",
    "Answer",
    "Key Points",
    "Related Pages",
    "Tags",
    "Source",
)

MAX_WRITE_DIFF_LINES = 320


def section_changed(before_content: str, after_content: str, heading: str) -> bool:
    return extract_section(before_content, heading) != extract_section(after_content, heading)


def added_list_items(before_content: str, after_content: str, heading: str) -> list[str]:
    before = {normalize_list_item(item) for item in extract_list_items(extract_section(before_content, heading))}
    added: list[str] = []
    seen_added: set[str] = set()
    for item in extract_list_items(extract_section(after_content, heading)):
        normalized = normalize_list_item(item)
        if not normalized or normalized in before or normalized in seen_added:
            continue
        seen_added.add(normalized)
        added.append(item)
    return added


def requested_merge_items(draft: WikiDraft, related_links: list[str], source_file: str | None) -> dict[str, list[str]]:
    requested: dict[str, list[str]] = {
        "Related Pages": related_links,
        "Source": [source_file] if source_file else [],
    }
    for patch in draft.patches:
        if patch.operation != "merge_list":
            continue
        section = patch.section.strip()
        requested.setdefault(section, [])
        requested[section].extend(str(item).strip() for item in patch.items if str(item).strip())
    return requested


def skipped_duplicate_items(
    before_content: str,
    added_by_section: dict[str, list[str]],
    requested_by_section: dict[str, list[str]],
) -> dict[str, list[str]]:
    skipped: dict[str, list[str]] = {}
    for section, requested_items in requested_by_section.items():
        before = {normalize_list_item(item) for item in extract_list_items(extract_section(before_content, section))}
        added = {normalize_list_item(item) for item in added_by_section.get(section, [])}
        duplicates: list[str] = []
        seen_duplicates: set[str] = set()
        for item in requested_items:
            normalized = normalize_list_item(item)
            if normalized and normalized in before and normalized not in added and normalized not in seen_duplicates:
                duplicates.append(item)
                seen_duplicates.add(normalized)
        if duplicates:
            skipped[section] = duplicates
    return skipped


def build_write_details(
    write_action: str,
    target_page: str | None,
    before_content: str | None,
    after_content: str,
    draft: WikiDraft,
    related_links: list[str],
    source_file: str | None,
) -> dict[str, object]:
    if write_action not in {"update", "merge"} or before_content is None:
        return {}

    diff_lines = list(
        difflib.unified_diff(
            before_content.splitlines(),
            after_content.splitlines(),
            fromfile=target_page or "before.md",
            tofile=target_page or "after.md",
            lineterm="",
        )
    )
    changed = [section for section in TRACKED_WRITE_SECTIONS if section_changed(before_content, after_content, section)]
    added_by_section = {
        "Key Points": added_list_items(before_content, after_content, "Key Points"),
        "Related Pages": added_list_items(before_content, after_content, "Related Pages"),
        "Tags": added_list_items(before_content, after_content, "Tags"),
        "Source": added_list_items(before_content, after_content, "Source"),
    }
    requested_by_section = requested_merge_items(draft, related_links, source_file)
    return {
        "write_action": write_action,
        "target_page": target_page,
        "patched_sections": changed,
        "added_key_points": added_by_section["Key Points"],
        "added_related_links": added_by_section["Related Pages"],
        "added_tags": added_by_section["Tags"],
        "added_sources": added_by_section["Source"],
        "skipped_duplicate_items": skipped_duplicate_items(before_content, added_by_section, requested_by_section),
        "diff": "\n".join(diff_lines[:MAX_WRITE_DIFF_LINES]),
        "diff_truncated": len(diff_lines) > MAX_WRITE_DIFF_LINES,
    }


def write_draft(
    vault_path: Path,
    draft: WikiDraft,
    source_file: str | None,
    display_source_file: str | None = None,
    write_action: str = "create",
    target_page: str | None = None,
    auto_related_links: bool = True,
) -> VaultWriteResult:
    if write_action == "create" and target_page:
        raise PolicyRejection("create must not set target_page")
    if write_action == "create" and not source_file:
        raise PolicyRejection("create requires source_file")
    digest = content_hash(draft.question, draft.answer)
    target_path = resolve_required_target(vault_path, target_page, write_action) if write_action in {"update", "merge"} else None
    if target_path:
        wiki_path = target_path
    else:
        output_dir = vault_path / draft.page_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        wiki_path = resolve_existing_by_hash(vault_path, draft.page_dir, digest) or available_title_path(output_dir, draft.title)

    created_at = None
    before_content = None
    if wiki_path.exists():
        before_content = wiki_path.read_text(encoding="utf-8")
        created_at = parse_frontmatter(before_content).get("created")
    related_links = find_related_links(vault_path, draft.question, wiki_path) if auto_related_links else []
    page_source_file = display_source_file or source_file
    if target_path and wiki_path.exists():
        if not draft.patches:
            raise PolicyRejection(f"{write_action} requires patches[] for target_page: {target_page}")
        content = apply_patched_markdown(before_content or "", draft, related_links, page_source_file, digest, auto_related_links)
    else:
        content = render_markdown(draft, related_links, page_source_file, digest, created_at)

    created = not wiki_path.exists()
    if target_path or created:
        wiki_path.write_text(content, encoding="utf-8")
    result = VaultWriteResult(
        path=wiki_path,
        content=content,
        created=created,
        related_links=related_links,
        content_hash=digest,
        write_details=build_write_details(
            write_action,
            target_page,
            before_content,
            content,
            draft,
            related_links,
            page_source_file,
        ),
    )
    return result
