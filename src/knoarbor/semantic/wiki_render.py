from __future__ import annotations

from datetime import datetime

from knoarbor.core.errors import PolicyRejection
from knoarbor.core.markdown import (
    append_to_section,
    extract_list_items,
    extract_section,
    render_list_section,
    replace_section,
    update_frontmatter_value,
    validate_body_markdown,
)
from knoarbor.core.schemas.wiki_write import WikiDraft, WikiPatchInput
from knoarbor.core.wiki_lists import merge_unique_items


def apply_wiki_patch(content: str, patch: WikiPatchInput) -> str:
    section = patch.section.strip()
    if patch.operation == "append_section":
        return append_to_section(content, section, patch.content or "", patch.heading)
    if patch.operation == "replace_section":
        return replace_section(content, section, patch.content or "")
    if patch.operation == "merge_list":
        incoming = [str(item).strip() for item in patch.items if str(item).strip()]
        merged = merge_unique_items(extract_list_items(extract_section(content, section)), incoming, patch.max_items)
        return replace_section(content, section, render_list_section(merged, f"暂无{section}"))
    return content


def apply_wiki_patches(content: str, patches: list[WikiPatchInput]) -> str:
    patched = content
    for patch in patches:
        patched = apply_wiki_patch(patched, patch)
    return patched


def render_markdown(
    draft: WikiDraft,
    related_links: list[str],
    source_file: str | None,
    digest: str,
    created_at: str | None = None,
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    created = created_at or now
    related = "\n".join(f"- {link}" for link in related_links)
    key_points = "\n".join(f"- {item}" for item in draft.key_points)
    tags = "\n".join(f"- {tag}" for tag in draft.tags)
    if not source_file:
        raise PolicyRejection("source_file is required when creating a wiki page")
    source = source_file
    summary = validate_body_markdown(draft.summary, "summary")
    source_focus = validate_body_markdown(draft.question, "source focus")
    answer = validate_body_markdown(draft.answer, "answer")

    return f"""# {draft.title}

---
created: {created}
updated: {now}
type: {draft.page_type}
status: draft
source: {source}
content_hash: {digest}
confidence: {draft.confidence:.2f}
model_provider: {draft.model_provider}
model_name: {draft.model_name}
---

## Summary

{summary}

## Source Focus

{source_focus}

## Answer

{answer}

## Key Points

{key_points}

## Related Pages

{related}

## Tags

{tags}

## Source

- {source}
"""


def apply_patched_markdown(
    existing_content: str,
    draft: WikiDraft,
    related_links: list[str],
    source_file: str | None,
    digest: str,
    auto_related_links: bool = True,
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    merged = update_frontmatter_value(existing_content, "updated", now)
    merged = update_frontmatter_value(merged, "content_hash", digest)
    merged = update_frontmatter_value(merged, "confidence", f"{draft.confidence:.2f}")
    merged = update_frontmatter_value(merged, "model_provider", draft.model_provider)
    merged = update_frontmatter_value(merged, "model_name", draft.model_name)

    merged = apply_wiki_patches(merged, draft.patches)

    if auto_related_links:
        related = merge_unique_items(extract_list_items(extract_section(merged, "Related Pages")), related_links, 20)
        merged = replace_section(merged, "Related Pages", render_list_section(related, "暂无关联知识"))

    sources = merge_unique_items(extract_list_items(extract_section(merged, "Source")), [source_file] if source_file else [], 20)
    if sources:
        merged = replace_section(merged, "Source", render_list_section(sources, "暂无来源"))

    return merged.rstrip() + "\n"
