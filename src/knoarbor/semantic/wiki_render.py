from __future__ import annotations

import re
from datetime import datetime

from knoarbor.core.errors import PolicyRejection
from knoarbor.core.markdown import append_to_section, extract_list_items, extract_section, parse_frontmatter, render_list_section, replace_section, update_frontmatter_value, validate_body_markdown
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
    attachments = _render_attachments(draft.attachments)

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

## Attachments

{attachments}
"""


def _render_source_digest_markdown(draft: WikiDraft, source_file: str, digest: str, created: str, updated: str) -> str:
    summary = validate_body_markdown(draft.summary, "summary")
    source_units = _render_source_units(draft.evidence, source_file)
    attachments = _render_source_digest_attachments(draft.attachments)
    contribution_map = _render_contribution_map(draft)
    unresolved = _render_source_unresolved(draft.unresolved_items)
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

## Attachments

{attachments}

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


def _render_attachments(items: list[dict[str, object]]) -> str:
    return _render_knowledge_page_attachments(items)


def _render_knowledge_page_attachments(items: list[dict[str, object]]) -> str:
    values = [item for item in items if isinstance(item, dict)]
    if not values:
        return "- No attachments recorded."
    rows = ["| Topic | Description |", "|---|---|"]
    for index, item in enumerate(values, start=1):
        topic = _attachment_topic_label(item, index, allow_generic=False)
        description = _attachment_description_label(item)
        if not topic and not description:
            continue
        rows.append(f"| {_escape_table_cell(topic or f'Attachment {index}')} | {_escape_table_cell(description)} |")
    if len(rows) == 2:
        return "- No readable attachments recorded."
    return "\n".join(rows)


def _render_source_digest_attachments(items: list[dict[str, object]]) -> str:
    values = [item for item in items if isinstance(item, dict)]
    if not values:
        return "- No source attachments recorded."
    rows = ["| Attachment | Type | Topic | Description | Source Range | Status |", "|---|---|---|---|---|---|"]
    for index, item in enumerate(values, start=1):
        attachment_id = str(item.get("attachment_id") or f"A{index}").strip() or f"A{index}"
        attachment_type = str(item.get("attachment_type") or "file").strip() or "file"
        topic = _attachment_topic_label(item, index, allow_generic=True)
        description = _attachment_description_label(item)
        source_range = _attachment_source_range_label(item)
        status = str(item.get("status") or "candidate").strip() or "candidate"
        rows.append(
            f"| {_escape_table_cell(attachment_id)} | {_escape_table_cell(attachment_type)} | "
            f"{_escape_table_cell(topic)} | {_escape_table_cell(description)} | "
            f"{_escape_table_cell(source_range)} | {_escape_table_cell(status)} |"
        )
    return "\n".join(rows)


def _attachment_source_range_label(item: dict[str, object]) -> str:
    value = str(item.get("source_range") or "").strip()
    if value:
        return value
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    parts: list[str] = []
    page_idx = metadata.get("page_idx")
    if page_idx is not None and str(page_idx).strip():
        parts.append(f"page_idx:{page_idx}")
    bbox = metadata.get("bbox")
    if isinstance(bbox, list) and bbox:
        parts.append("bbox:" + ",".join(str(part) for part in bbox[:4]))
    return " ".join(parts) or "source-level"


def _attachment_topic_label(item: dict[str, object], index: int, *, allow_generic: bool) -> str:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    for key in ("topic", "title", "caption", "image_caption", "table_caption", "description", "alt", "name"):
        value = item.get(key)
        if value is None and key in metadata:
            value = metadata.get(key)
        value = _clean_attachment_text(value)
        if value and not _looks_like_hash_filename(value):
            return value
    attachment_type = str(item.get("attachment_type") or "attachment").strip()
    if allow_generic and attachment_type == "image":
        return f"Image {index}"
    if allow_generic:
        return f"Attachment {index}"
    return ""


def _attachment_description_label(item: dict[str, object]) -> str:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    for key in ("description", "mineru_description", "caption", "image_caption", "table_caption", "alt"):
        value = item.get(key)
        if value is None and key in metadata:
            value = metadata.get(key)
        text = _clean_attachment_text(value)
        if text and not _looks_like_hash_filename(text):
            return text
    return ""


def _clean_attachment_text(value: object, *, limit: int = 180) -> str:
    if isinstance(value, list):
        text = " ".join(str(part).strip() for part in value if str(part).strip())
    else:
        text = str(value or "").strip()
    if not text:
        return ""
    if re.search(r"<\s*(table|tr|td|th)\b", text, flags=re.IGNORECASE):
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if _looks_like_hash_filename(text):
        return ""
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def _looks_like_hash_filename(value: str) -> bool:
    path_name = value.strip().rsplit("/", 1)[-1]
    stem = path_name.rsplit(".", 1)[0]
    return bool(re.fullmatch(r"[0-9a-fA-F]{24,}", stem))


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
    source_file: str | None,
    digest: str,
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    created = parse_frontmatter(existing_content).get("created") or now
    if draft.page_dir == "sources":
        if not source_file:
            raise PolicyRejection("source_file is required when updating a source digest")
        return _render_source_digest_markdown(draft, source_file, digest, created, now)

    merged = update_frontmatter_value(existing_content, "updated", now)
    merged = update_frontmatter_value(merged, "content_hash", digest)

    merged = apply_wiki_patches(merged, draft.patches)

    return merged.rstrip() + "\n"
