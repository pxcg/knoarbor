from __future__ import annotations

import difflib
import re
from pathlib import Path

from knoarbor.core.errors import PolicyRejection
from knoarbor.core.hashing import content_hash
from knoarbor.core.markdown import extract_list_items, extract_section, normalize_list_item, parse_frontmatter
from knoarbor.core.schemas.wiki_write import VaultWriteResult, WikiDraft
from knoarbor.retrieval.wiki_links import find_related_links
from knoarbor.semantic.wiki_render import apply_patched_markdown, render_markdown
from knoarbor.storage.wiki_paths import (
    available_title_path,
    content_relative_path,
    content_root,
    resolve_existing_by_hash,
    resolve_required_target,
    source_digest_root,
)


TRACKED_WRITE_SECTIONS = (
    "Summary",
    "Claims",
    "Entities",
    "Relations",
    "Evidence",
    "Synthesis",
    "Source Identity",
    "Audit Summary",
    "Source Units",
    "Attachments",
    "Contribution Map",
    "Unresolved / Rejected",
    "Raw Source",
)

MAX_WRITE_DIFF_LINES = 320
STRUCTURED_KNOWLEDGE_SECTIONS = ("Summary", "Claims", "Entities", "Relations", "Evidence", "Synthesis")
LEGACY_BODY_PATCH_SECTIONS = {"Answer", "Definition", "Source Focus"}


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
    digest = _draft_content_hash(draft)
    target_path = resolve_required_target(vault_path, target_page, write_action) if write_action in {"update", "merge"} else None
    if target_path:
        wiki_path = target_path
    else:
        output_dir = _draft_output_dir(vault_path, draft)
        output_dir.mkdir(parents=True, exist_ok=True)
        wiki_path = resolve_existing_by_hash(vault_path, draft.page_dir, digest) or available_title_path(output_dir, draft.title)
    draft = _draft_with_resolved_identity(vault_path, draft, wiki_path)

    created_at = None
    before_content = None
    if wiki_path.exists():
        before_content = wiki_path.read_text(encoding="utf-8")
        created_at = parse_frontmatter(before_content).get("created")
    related_links = find_related_links(vault_path, draft.question, wiki_path) if auto_related_links else []
    page_source_file = display_source_file or source_file
    if target_path and wiki_path.exists():
        structured_rewrite = _structured_rewrite_required(before_content or "", draft, source_file=page_source_file)
        if not draft.patches and not structured_rewrite:
            raise PolicyRejection(f"{write_action} requires patches[] for target_page: {target_page}")
        if structured_rewrite:
            content = render_markdown(draft, related_links, page_source_file, digest, created_at=created_at)
        else:
            content = apply_patched_markdown(before_content or "", draft, related_links, page_source_file, digest, auto_related_links)
    else:
        content = render_markdown(draft, related_links, page_source_file, digest, created_at)

    _validate_rendered_structured_page(content, draft)

    created = not wiki_path.exists()
    if target_path or created:
        wiki_path.write_text(content, encoding="utf-8")
    result = VaultWriteResult(
        path=wiki_path,
        content=content,
        created=created,
        related_links=related_links,
        content_hash=digest,
        canonical_path=draft.canonical_path,
        legacy_paths=list(draft.legacy_paths),
        page_kind=draft.page_kind,
        subject_kind=draft.subject_kind,
        role=draft.role,
        facets=list(draft.facets),
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


def _draft_output_dir(vault_path: Path, draft: WikiDraft) -> Path:
    root = content_root(vault_path)
    if draft.role == "source_digest" or draft.page_kind == "source_digest" or draft.page_dir == "sources":
        return source_digest_root(vault_path)
    return root


def _draft_content_hash(draft: WikiDraft) -> str:
    payload = "\n\n".join(
        [
            f"summary:\n{draft.summary}",
            "claims:\n" + "\n".join(draft.claims),
            "entities:\n" + "\n".join(draft.entities),
            "relations:\n" + "\n".join(draft.relations),
            "evidence:\n" + "\n".join(draft.evidence),
            f"synthesis:\n{draft.synthesis}",
        ]
    )
    return content_hash("wiki_draft_v2", payload)


def _structured_rewrite_required(before_content: str, draft: WikiDraft, *, source_file: str | None) -> bool:
    if draft.page_dir == "sources":
        return True
    if draft.page_dir not in {"entities", "concepts", "comparisons", "queries", "timelines", "workflows"}:
        return False
    if not source_file:
        return False
    if _has_complete_structured_draft(draft):
        return True
    if not draft.patches:
        return True
    return any(patch.section in LEGACY_BODY_PATCH_SECTIONS for patch in draft.patches)


def _has_complete_structured_draft(draft: WikiDraft) -> bool:
    return bool(
        draft.summary.strip()
        and draft.synthesis.strip()
        and any(item.strip() for item in draft.claims)
        and any(item.strip() for item in draft.evidence)
    )


def _validate_rendered_structured_page(content: str, draft: WikiDraft) -> None:
    if draft.page_dir == "sources" or draft.role == "source_digest" or draft.page_kind == "source_digest":
        return
    if draft.page_dir not in {"entities", "concepts", "comparisons", "queries", "timelines", "workflows"}:
        return
    if not _has_rendered_structured_body(content):
        return
    claim_ids = _rendered_claim_ids(content)
    if not claim_ids:
        raise PolicyRejection("structured knowledge page must render at least one claim")
    evidence_claims = _rendered_table_claim_ids(content, "Evidence", first_column_only=True)
    if not evidence_claims:
        raise PolicyRejection("structured knowledge page must render at least one evidence row")
    missing_evidence_claims = sorted(evidence_claims.difference(claim_ids), key=_claim_sort_key)
    if missing_evidence_claims:
        raise PolicyRejection(
            "structured knowledge page evidence references missing claims: "
            + ", ".join(missing_evidence_claims)
        )
    relation_claims = _rendered_table_claim_ids(content, "Relations", first_column_only=False)
    missing_relation_claims = sorted(relation_claims.difference(claim_ids), key=_claim_sort_key)
    if missing_relation_claims:
        raise PolicyRejection(
            "structured knowledge page relations reference missing claims: "
            + ", ".join(missing_relation_claims)
        )


def _rendered_claim_ids(content: str) -> set[str]:
    section = extract_section(content, "Claims")
    return {
        f"C{int(match.group(1))}"
        for match in re.finditer(r"^\s*-\s*C(\d+)\s*:", section, flags=re.MULTILINE)
    }


def _has_rendered_structured_body(content: str) -> bool:
    return any(extract_section(content, section).strip() for section in ("Claims", "Relations", "Evidence"))


def _rendered_table_claim_ids(content: str, heading: str, *, first_column_only: bool) -> set[str]:
    section = extract_section(content, heading)
    ids: set[str] = set()
    for line in section.splitlines():
        text = line.strip()
        if not text.startswith("|") or "---" in text or text.lower().startswith("| claim"):
            continue
        cells = [cell.strip() for cell in text.strip("|").split("|")]
        fields = cells[:1] if first_column_only else cells
        for field in fields:
            for claim_id in re.findall(r"\bC(\d+)\b", field, flags=re.IGNORECASE):
                ids.add(f"C{int(claim_id)}")
    return ids


def _claim_sort_key(claim_id: str) -> int:
    return int(claim_id[1:]) if claim_id.startswith("C") and claim_id[1:].isdigit() else 0


def _draft_with_resolved_identity(vault_path: Path, draft: WikiDraft, wiki_path: Path) -> WikiDraft:
    canonical_path = content_relative_path(vault_path, wiki_path)
    legacy_paths = list(draft.legacy_paths)
    for alias in _draft_canonical_path_aliases(draft.canonical_path):
        if alias != canonical_path and alias not in legacy_paths:
            legacy_paths.append(alias)
    if draft.role != "source_digest" and draft.page_dir != "sources":
        legacy_path = f"{draft.page_dir}/{wiki_path.name}"
        if legacy_path != canonical_path and legacy_path not in legacy_paths:
            legacy_paths.append(legacy_path)
    return draft.model_copy(
        update={
            "canonical_path": canonical_path,
            "legacy_paths": legacy_paths,
        }
    )


def _draft_canonical_path_aliases(value: str | None) -> list[str]:
    text = str(value or "").strip().replace("\\", "/").lstrip("/")
    if not text:
        return []
    aliases = [text]
    if text.startswith("pages/"):
        aliases.append(text.removeprefix("pages/"))
    result: list[str] = []
    for alias in aliases:
        if alias and alias not in result:
            result.append(alias)
    return result
