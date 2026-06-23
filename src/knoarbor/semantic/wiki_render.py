from __future__ import annotations

import re
from datetime import datetime

from knoarbor.core.errors import PolicyRejection
from knoarbor.core.markdown import append_to_section, extract_list_items, extract_section, render_list_section, replace_section, update_frontmatter_value, validate_body_markdown
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
    if not source_file:
        raise PolicyRejection("source_file is required when creating a wiki page")
    summary = validate_body_markdown(draft.summary, "summary")
    synthesis = validate_body_markdown(draft.synthesis or draft.answer, "synthesis")
    claims = _render_claims(draft.claims)
    entities = _render_list(draft.entities, "暂无显式实体")
    relations = _render_relations(draft.relations)
    evidence = _render_evidence(draft.evidence, draft.claims, source_file, draft.source_digest_ids, draft.page_dir)

    return f"""---
created: {created}
updated: {now}
content_hash: {digest}
---

# {draft.title}

## Summary

{summary}

## Claims

{claims}

## Entities

{entities}

## Relations

{relations}

## Evidence

{evidence}

## Synthesis

{synthesis}
"""


def _render_list(items: list[str], placeholder: str) -> str:
    values = [item.strip() for item in items if item.strip()]
    if not values:
        return f"- {placeholder}"
    return "\n".join(f"- {item}" for item in values)


def _render_claims(items: list[str]) -> str:
    values = [item.strip() for item in items if item.strip()]
    if not values:
        return "- C1: 暂无可审计断言"
    rendered: list[str] = []
    for index, item in enumerate(values, start=1):
        text = re.sub(r"^(?:C)?\d+[\.:：]\s*", "", item).strip()
        rendered.append(f"- C{index}: {text}")
    return "\n".join(rendered)


def _render_relations(items: list[str]) -> str:
    rows = ["| Subject | Predicate | Object | Based on |", "|---|---|---|---|"]
    values = [item.strip() for item in items if item.strip()]
    if not values:
        rows.append("| 暂无显式关系 | relates_to | 暂无显式对象 | C1 |")
        return "\n".join(rows)
    for item in values:
        parts = [part.strip() for part in item.split("|")]
        if len(parts) >= 4:
            subject, predicate, obj, based_on = parts[:4]
        else:
            subject, predicate, obj, based_on = item, "relates_to", "未结构化对象", "C1"
        rows.append(f"| {_escape_table_cell(subject)} | {_escape_table_cell(predicate)} | {_escape_table_cell(obj)} | {_escape_table_cell(based_on)} |")
    return "\n".join(rows)


def _render_evidence(items: list[str], claims: list[str], source_file: str, source_digest_ids: list[str], page_dir: str) -> str:
    rows = ["| Claim | Source | Range | Basis | Confidence |", "|---|---|---|---|---|"]
    values = [item.strip() for item in items if item.strip()]
    if not values:
        if page_dir != "sources":
            raise PolicyRejection("non-source wiki drafts require explicit evidence rows")
        source = source_digest_ids[0] if source_digest_ids else source_file
        claim_count = max(len([claim for claim in claims if claim.strip()]), 1)
        values = [f"C{index} | {source} | source-level | direct source support | medium" for index in range(1, claim_count + 1)]
    for item in values:
        parts = [part.strip() for part in item.split("|")]
        if len(parts) >= 5:
            claim, source, source_range, basis, confidence = parts[:5]
        else:
            claim, source, source_range, basis, confidence = "C1", source_file, "source-level", item, "medium"
        rows.append(
            f"| {_escape_table_cell(claim)} | {_escape_table_cell(source)} | {_escape_table_cell(source_range)} | "
            f"{_escape_table_cell(basis)} | {_escape_table_cell(confidence)} |"
        )
    return "\n".join(rows)


def _escape_table_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


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

    merged = apply_wiki_patches(merged, draft.patches)

    return merged.rstrip() + "\n"
