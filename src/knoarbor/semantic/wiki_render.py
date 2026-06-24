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
    if draft.page_dir == "sources":
        return _render_source_digest_markdown(draft, source_file, digest, created, now)

    summary = validate_body_markdown(draft.summary, "summary")
    synthesis = validate_body_markdown(draft.synthesis, "synthesis")
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


def _render_source_digest_markdown(draft: WikiDraft, source_file: str, digest: str, created: str, updated: str) -> str:
    summary = validate_body_markdown(draft.summary, "summary")
    source_units = _render_source_units(draft.evidence, source_file)
    contribution_map = _render_contribution_map(draft)
    unresolved = _render_source_unresolved(draft.key_points)
    raw_source = _render_raw_source(source_file, digest)
    digest_ids = ", ".join(draft.source_digest_ids) if draft.source_digest_ids else "not assigned"
    atom_ids = ", ".join(draft.atom_ids) if draft.atom_ids else "none"

    return f"""---
created: {created}
updated: {updated}
content_hash: {digest}
---

# {draft.title}

## Source Identity

- Raw source: {source_file}
- Source digest ids: {digest_ids}
- Atom ids: {atom_ids}
- Content hash: {digest}

## Audit Summary

{summary}

## Source Units

{source_units}

## Contribution Map

{contribution_map}

## Unresolved / Rejected

{unresolved}

## Raw Source

{raw_source}
"""


def _render_source_units(items: list[str], source_file: str) -> str:
    rows = ["| Unit | Source | Range | Basis | Confidence |", "|---|---|---|---|---|"]
    values = [item.strip() for item in items if item.strip()]
    if not values:
        rows.append(f"| U1 | {_escape_table_cell(source_file)} | source-level | source digest compiled from this raw source | medium |")
        return "\n".join(rows)
    for index, item in enumerate(values, start=1):
        parts = [part.strip() for part in item.split("|")]
        if len(parts) >= 5:
            unit, source, source_range, basis, confidence = parts[:5]
        else:
            unit, source, source_range, basis, confidence = f"U{index}", source_file, "source-level", item, "medium"
        unit = re.sub(r"^C(\d+)$", r"U\1", unit) or f"U{index}"
        rows.append(
            f"| {_escape_table_cell(unit)} | {_escape_table_cell(source)} | {_escape_table_cell(source_range)} | "
            f"{_escape_table_cell(basis)} | {_escape_table_cell(confidence)} |"
        )
    return "\n".join(rows)


def _render_contribution_map(draft: WikiDraft) -> str:
    rows = ["| Item | Contribution | Evidence Units | Target Page |", "|---|---|---|---|"]
    claims = [item.strip() for item in draft.claims if item.strip()]
    relations = [item.strip() for item in draft.relations if item.strip()]
    if not claims and not relations:
        return "- No accepted contribution map was generated."
    for index, claim in enumerate(claims, start=1):
        text = re.sub(r"^(?:C)?\d+[\.:：]\s*", "", claim).strip()
        rows.append(f"| C{index} | {_escape_table_cell(text)} | U{index} | source digest |")
    for index, relation in enumerate(relations, start=1):
        rows.append(f"| R{index} | {_escape_table_cell(relation)} | source-level | source digest |")
    return "\n".join(rows)


def _render_source_unresolved(items: list[str]) -> str:
    values = [item.strip() for item in items if item.strip()]
    if not values:
        return "- No unresolved or rejected material recorded."
    return "\n".join(f"- {item}" for item in values)


def _render_raw_source(source_file: str, digest: str) -> str:
    return f"- Raw source: {source_file}\n- Content hash: {digest}"


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
        rows.append("| 暂无显式关系 | coordinates | 暂无显式对象 | C1 |")
        return "\n".join(rows)
    for item in values:
        parts = [part.strip() for part in item.split("|")]
        if len(parts) >= 4:
            subject, predicate, obj, based_on = parts[:4]
        else:
            subject, predicate, obj, based_on = item, "coordinates", "未结构化对象", "C1"
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
