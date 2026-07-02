from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from knoarbor.core.config import PrivacyConfig
from knoarbor.core.markdown import adjacent_duplicate_headings, extract_list_items, extract_section, has_unclosed_fenced_code_blocks, wiki_target_key
from knoarbor.core.redaction import detect_sensitive_text
from knoarbor.core.schemas.wiki_draft_batch import WikiDraftBatchItem
from knoarbor.core.schemas.wiki_write import WikiDraftWriteResponse
from knoarbor.maintenance.operation_verification_models import LintPostFixVerification
from knoarbor.retrieval.wiki_links import canonical_wiki_list_item_identity
from knoarbor.storage import resolve_wiki_page
from knoarbor.storage.wiki_index import relative_wiki_path

LEGAL_PLACEHOLDERS_BY_SECTION = {
    "Evidence": {"暂无证据", "No evidence."},
    "Entities": {"暂无实体", "No entities."},
    "Attachments": {"暂无附件", "No attachments."},
    "Raw Source": {"暂无来源", "No source.", "Raw source: unknown"},
}
CHATTY_SUMMARY_PATTERN = re.compile(
    r"如果(你|您)(还)?需要|可以告诉我|欢迎继续|我可以继续|希望我继续|let me know|if you need",
    flags=re.IGNORECASE,
)


def verify_wiki_operation(
    vault_path: Path,
    operation: dict[str, Any],
    *,
    privacy_config: PrivacyConfig | None = None,
) -> LintPostFixVerification:
    privacy_config = privacy_config or PrivacyConfig()
    action = str(operation.get("action") or "")
    target_page = _optional_str(operation.get("output_page")) or _optional_str(operation.get("target_page"))
    details = _as_dict(operation.get("details"))
    operation_id = _optional_str(operation.get("operation_id"))
    if not target_page:
        return _failed(action, target_page, operation_id, "Operation result does not include an output page.")

    path = _resolve_operation_output_path(vault_path, target_page)
    if not path.exists():
        return _failed(action, target_page, operation_id, "Operation output page does not exist.")
    content = path.read_text(encoding="utf-8")

    if action in {"replace_wikilink", "normalize_wikilink"}:
        old_target = _optional_str(details.get("old_target"))
        new_target = _optional_str(details.get("new_target"))
        return _verify_wikilink_replacement(content, old_target, new_target, action, target_page, operation_id)

    if action == "deduplicate_section_items":
        section = _optional_str(details.get("section")) or "Entities"
        return _verify_deduplicated_section(vault_path, content, section, action, target_page, operation_id)

    if action == "remove_adjacent_duplicate_headings":
        return _verify_adjacent_duplicate_headings_removed(content, action, target_page, operation_id)

    if action == "add_missing_section":
        section = _optional_str(details.get("section"))
        return _verify_added_wiki_operation_section(content, action, target_page, operation_id, section)

    if action == "redact_sensitive_text":
        return _verify_sensitive_text_redacted(content, action, target_page, operation_id, privacy_config)

    if action == "rename_page":
        return _verify_renamed_page(vault_path, operation, action, target_page, operation_id)

    if action == "delete_page":
        return _verify_deleted_page(vault_path, operation, action, target_page, operation_id)

    if action == "merge_pages":
        return _verify_merged_pages(vault_path, content, operation, action, target_page, operation_id)

    if action == "create_source_digest":
        return _verify_created_source_digest(content, operation, action, target_page, operation_id)

    if action == "record_source_digest":
        return _verify_recorded_source_digest(vault_path, content, operation, action, target_page, operation_id)

    return LintPostFixVerification(
        action=action,
        status="skipped",
        target_page=target_page,
        operation_id=operation_id,
        reason="No operation-specific verification rule is defined for this action.",
    )


def verify_draft_write(
    vault_path: Path,
    result: WikiDraftWriteResponse,
    draft: WikiDraftBatchItem | None,
    candidate: Any,
) -> LintPostFixVerification:
    path = Path(result.wiki_file_path)
    target_page = relative_wiki_path(vault_path, path)
    if not path.exists():
        return _failed("draft_write", target_page, None, "Written draft page does not exist.")
    content = path.read_text(encoding="utf-8")
    action = _candidate_action(candidate) or str(result.stats.get("write_action") or "draft_write")
    action_params = _candidate_action_params(candidate)

    pollution = _markdown_pollution(content)
    if pollution:
        return _failed(action, target_page, None, "Draft write introduced markdown structure pollution.", {"pollution": pollution})

    if action == "create_source_digest":
        source_file = _optional_str(result.stats.get("source_file")) or _optional_str(getattr(draft, "source_file", None))
        return _verify_source_digest_page(content, source_file, action, target_page)

    if draft and draft.write_action in {"update", "merge"}:
        patch_sections = {patch.section.strip() for patch in draft.patches if patch.section.strip()}
        changed_sections = set(_string_list(_as_dict(result.stats.get("write_details")).get("patched_sections")))
        unexpected = sorted(changed_sections - patch_sections)
        if unexpected:
            return _failed(
                action,
                target_page,
                None,
                "Draft write changed sections outside the approved patch set.",
                {"patch_sections": sorted(patch_sections), "changed_sections": sorted(changed_sections), "unexpected": unexpected},
            )
        if action == "improve_summary":
            return _verify_summary_quality(content, action, target_page, patch_sections, changed_sections)
        if action == "rewrite_section":
            section = _draft_target_section(action_params, draft)
            return _verify_rewritten_section(content, action, target_page, section, patch_sections, changed_sections)
        if action == "add_missing_section":
            section = _draft_target_section(action_params, draft)
            return _verify_added_section(content, action, target_page, section, patch_sections, changed_sections)
        return LintPostFixVerification(
            action=action,
            status="verified",
            target_page=target_page,
            reason="Draft write changed only approved patch sections and passed markdown pollution checks.",
            evidence={"patch_sections": sorted(patch_sections), "changed_sections": sorted(changed_sections)},
        )

    return LintPostFixVerification(
        action=action,
        status="verified",
        target_page=target_page,
        reason="Draft write output exists and passed markdown pollution checks.",
    )


def _resolve_operation_output_path(vault_path: Path, target_page: str) -> Path:
    if target_page.startswith("maintenance/"):
        vault = vault_path.resolve()
        path = (vault / target_page).resolve()
        path.relative_to(vault)
        return path
    return resolve_wiki_page(vault_path, target_page)


def _verify_summary_quality(
    content: str,
    action: str,
    target_page: str,
    patch_sections: set[str],
    changed_sections: set[str],
) -> LintPostFixVerification:
    if "Summary" not in patch_sections:
        return _failed(action, target_page, None, "Summary improvement must patch the Summary section.", {"patch_sections": sorted(patch_sections)})
    summary = extract_section(content, "Summary").strip()
    if not _has_meaningful_section_body("Summary", summary):
        return _failed(action, target_page, None, "Summary section is missing or empty after draft write.")
    if CHATTY_SUMMARY_PATTERN.search(summary):
        return _failed(action, target_page, None, "Summary still contains chat-style follow-up wording.", {"summary": summary[:240]})
    return LintPostFixVerification(
        action=action,
        status="verified",
        target_page=target_page,
        reason="Summary was patched, is non-empty, and does not contain chat-style follow-up wording.",
        evidence={"patch_sections": sorted(patch_sections), "changed_sections": sorted(changed_sections)},
    )


def _verify_rewritten_section(
    content: str,
    action: str,
    target_page: str,
    section: str | None,
    patch_sections: set[str],
    changed_sections: set[str],
) -> LintPostFixVerification:
    if not section:
        return _failed(action, target_page, None, "Section rewrite verification requires a target section.")
    if section not in patch_sections:
        return _failed(action, target_page, None, "Section rewrite must patch the declared target section.", {"section": section, "patch_sections": sorted(patch_sections)})
    body = extract_section(content, section).strip()
    if not _has_meaningful_section_body(section, body):
        return _failed(action, target_page, None, "Rewritten section is missing or empty.", {"section": section})
    if _section_body_has_page_shell(body):
        return _failed(action, target_page, None, "Rewritten section appears to contain a nested page shell.", {"section": section})
    return LintPostFixVerification(
        action=action,
        status="verified",
        target_page=target_page,
        reason="Declared section was rewritten with local section content only.",
        evidence={"section": section, "patch_sections": sorted(patch_sections), "changed_sections": sorted(changed_sections)},
    )


def _verify_added_section(
    content: str,
    action: str,
    target_page: str,
    section: str | None,
    patch_sections: set[str],
    changed_sections: set[str],
) -> LintPostFixVerification:
    if not section:
        return _failed(action, target_page, None, "Add section verification requires a target section.")
    if section not in patch_sections:
        return _failed(action, target_page, None, "Add section must patch the declared target section.", {"section": section, "patch_sections": sorted(patch_sections)})
    if changed_sections and section not in changed_sections:
        return _failed(action, target_page, None, "Declared section was not reported as changed.", {"section": section, "changed_sections": sorted(changed_sections)})
    body = extract_section(content, section).strip()
    if not _has_meaningful_section_body(section, body):
        return _failed(action, target_page, None, "Added section is missing or empty.", {"section": section})
    return LintPostFixVerification(
        action=action,
        status="verified",
        target_page=target_page,
        reason="Declared missing section now exists and contains allowed local content.",
        evidence={"section": section, "patch_sections": sorted(patch_sections), "changed_sections": sorted(changed_sections)},
    )


def _verify_added_wiki_operation_section(
    content: str,
    action: str,
    target_page: str,
    operation_id: str | None,
    section: str | None,
) -> LintPostFixVerification:
    if not section:
        return _failed(action, target_page, operation_id, "Add section verification requires a target section.")
    body = extract_section(content, section).strip()
    if not _has_meaningful_section_body(section, body):
        return _failed(action, target_page, operation_id, "Added section is missing or empty.", {"section": section})
    return LintPostFixVerification(
        action=action,
        status="verified",
        target_page=target_page,
        operation_id=operation_id,
        reason="Declared missing section now exists and contains allowed local content.",
        evidence={"section": section},
    )


def _verify_wikilink_replacement(
    content: str,
    old_target: str | None,
    new_target: str | None,
    action: str,
    target_page: str,
    operation_id: str | None,
) -> LintPostFixVerification:
    if not old_target or not new_target:
        return _failed(action, target_page, operation_id, "Wikilink replacement verification requires old_target and new_target.")
    targets = [match.group(1) for match in re.finditer(r"\[\[([^\]|#]+)", content)]
    old_present = any(wiki_target_key(target) == wiki_target_key(old_target) for target in targets)
    new_present = any(wiki_target_key(target) == wiki_target_key(new_target) for target in targets)
    if old_present or not new_present:
        return _failed(
            action,
            target_page,
            operation_id,
            "Wikilink replacement verification failed.",
            {"old_present": old_present, "new_present": new_present},
        )
    return LintPostFixVerification(
        action=action,
        status="verified",
        target_page=target_page,
        operation_id=operation_id,
        reason="Old wikilink target is absent and new target is present.",
        evidence={"old_target": old_target, "new_target": new_target},
    )


def _verify_renamed_page(
    vault_path: Path,
    operation: dict[str, Any],
    action: str,
    target_page: str,
    operation_id: str | None,
) -> LintPostFixVerification:
    details = _as_dict(operation.get("details"))
    old_path = _optional_str(details.get("old_path")) or _optional_str(operation.get("target_page"))
    new_path = _optional_str(details.get("new_path")) or _optional_str(operation.get("output_page"))
    if not old_path or not new_path:
        return _failed(action, target_page, operation_id, "Rename verification requires old_path and new_path.")
    old_exists = resolve_wiki_page(vault_path, old_path).exists()
    new_exists = resolve_wiki_page(vault_path, new_path).exists()
    if old_exists or not new_exists:
        return _failed(action, target_page, operation_id, "Rename verification failed.", {"old_exists": old_exists, "new_exists": new_exists})
    return LintPostFixVerification(
        action=action,
        status="verified",
        target_page=new_path,
        operation_id=operation_id,
        reason="New page exists and old path is absent.",
        evidence={"old_path": old_path, "new_path": new_path},
    )


def _verify_deleted_page(
    vault_path: Path,
    operation: dict[str, Any],
    action: str,
    target_page: str,
    operation_id: str | None,
) -> LintPostFixVerification:
    original = _optional_str(operation.get("target_page"))
    archive = _optional_str(operation.get("output_page"))
    if not original or not archive:
        return _failed(action, target_page, operation_id, "Delete verification requires original target and archive output.")
    original_exists = resolve_wiki_page(vault_path, original).exists()
    archive_exists = _resolve_operation_output_path(vault_path, archive).exists()
    if original_exists or not archive_exists:
        return _failed(action, target_page, operation_id, "Delete/archive verification failed.", {"original_exists": original_exists, "archive_exists": archive_exists})
    return LintPostFixVerification(
        action=action,
        status="verified",
        target_page=archive,
        operation_id=operation_id,
        reason="Original page is absent and archived page exists.",
        evidence={"original": original, "archive": archive},
    )


def _verify_merged_pages(
    vault_path: Path,
    content: str,
    operation: dict[str, Any],
    action: str,
    target_page: str,
    operation_id: str | None,
) -> LintPostFixVerification:
    details = _as_dict(operation.get("details"))
    sources = _string_list(details.get("merged_sources"))
    archived_sources = bool(details.get("archived_sources", True))
    if not sources:
        return _failed(action, target_page, operation_id, "Merge verification requires merged_sources.")
    merged_notes = extract_section(content, "Merged Notes")
    missing_blocks = [
        source
        for source in sources
        if source not in merged_notes and Path(source).with_suffix("").as_posix() not in merged_notes
    ]
    still_present = [source for source in sources if archived_sources and resolve_wiki_page(vault_path, source).exists()]
    if missing_blocks or still_present:
        return _failed(
            action,
            target_page,
            operation_id,
            "Merge verification failed.",
            {"missing_merged_note_sources": missing_blocks, "unarchived_sources": still_present},
        )
    return LintPostFixVerification(
        action=action,
        status="verified",
        target_page=target_page,
        operation_id=operation_id,
        reason="Merged Notes references all source pages and archived source pages are absent from active wiki paths.",
        evidence={"merged_sources": sources, "archived_sources": archived_sources},
    )


def _verify_deduplicated_section(
    vault_path: Path,
    content: str,
    section: str,
    action: str,
    target_page: str,
    operation_id: str | None,
) -> LintPostFixVerification:
    items = extract_list_items(extract_section(content, section))
    identities = [canonical_wiki_list_item_identity(vault_path, item) for item in items]
    duplicates = sorted({identity for identity in identities if identities.count(identity) > 1})
    if duplicates:
        return _failed(action, target_page, operation_id, "Section still contains duplicate canonical items.", {"section": section, "duplicates": duplicates})
    return LintPostFixVerification(
        action=action,
        status="verified",
        target_page=target_page,
        operation_id=operation_id,
        reason="Target section contains unique canonical list items.",
        evidence={"section": section, "item_count": len(items)},
    )


def _verify_adjacent_duplicate_headings_removed(
    content: str,
    action: str,
    target_page: str,
    operation_id: str | None,
) -> LintPostFixVerification:
    duplicates = adjacent_duplicate_headings(content)
    if duplicates:
        return _failed(
            action,
            target_page,
            operation_id,
            "Page still contains adjacent duplicate headings.",
            {"duplicates": duplicates[:10], "duplicate_count": len(duplicates)},
        )
    return LintPostFixVerification(
        action=action,
        status="verified",
        target_page=target_page,
        operation_id=operation_id,
        reason="Page no longer contains adjacent duplicate Markdown headings.",
    )


def _verify_source_trace(
    content: str,
    source_file: str | None,
    action: str,
    target_page: str,
    operation_id: str | None,
) -> LintPostFixVerification:
    if not source_file:
        return _failed(action, target_page, operation_id, "Source trace verification requires source_file.")
    raw_source = extract_section(content, "Raw Source")
    source_identity = extract_section(content, "Source Identity")
    evidence = extract_section(content, "Evidence")
    trace_text = "\n".join([raw_source, source_identity, evidence])
    if source_file not in trace_text:
        return _failed(
            action,
            target_page,
            operation_id,
            "Source trace does not contain expected raw source reference.",
            {"expected_source": source_file},
        )
    return LintPostFixVerification(
        action=action,
        status="verified",
        target_page=target_page,
        operation_id=operation_id,
        reason="Source trace contains expected raw source reference.",
        evidence={"source_file": source_file},
    )


def _verify_created_source_digest(
    content: str,
    operation: dict[str, Any],
    action: str,
    target_page: str,
    operation_id: str | None,
) -> LintPostFixVerification:
    source_file = _optional_str(operation.get("source_file"))
    target_pages = _string_list(operation.get("target_pages"))
    if not source_file:
        return _failed(action, target_page, operation_id, "Source digest creation verification requires source_file.")
    recorded_sources = {
        *_source_values_from_section(content, "Source Identity"),
        *_source_values_from_section(content, "Raw Source"),
        *_source_values_from_evidence(content),
    }
    if source_file not in recorded_sources:
        return _failed(
            action,
            target_page,
            operation_id,
            "Created source digest does not record the refreshed raw source.",
            {"source_file": source_file, "recorded_sources": sorted(recorded_sources)},
        )
    contribution_pages = _contribution_map_pages(content)
    missing_pages = sorted(page for page in target_pages if page not in contribution_pages)
    if missing_pages:
        return _failed(
            action,
            target_page,
            operation_id,
            "Created source digest contribution map does not cover all refreshed target pages.",
            {"missing_pages": missing_pages, "contribution_pages": sorted(contribution_pages)},
        )
    return LintPostFixVerification(
        action=action,
        status="verified",
        target_page=target_page,
        operation_id=operation_id,
        reason="Source digest exists, records the raw source, and covers refreshed target pages.",
        evidence={"source_file": source_file, "target_pages": target_pages},
    )


def _verify_recorded_source_digest(
    vault_path: Path,
    target_content: str,
    operation: dict[str, Any],
    action: str,
    target_page: str,
    operation_id: str | None,
) -> LintPostFixVerification:
    digest_page = _optional_str(operation.get("source_digest_page"))
    source_file = _optional_str(operation.get("source_file"))
    if not digest_page:
        return _failed(action, target_page, operation_id, "Source digest association verification requires source_digest_page.")
    digest_path = _resolve_operation_output_path(vault_path, digest_page)
    if not digest_path.exists():
        return _failed(action, target_page, operation_id, "Associated source digest page does not exist.", {"source_digest_page": digest_page})
    digest_content = digest_path.read_text(encoding="utf-8")
    contribution_pages = _contribution_map_pages(digest_content)
    if target_page not in contribution_pages:
        return _failed(
            action,
            target_page,
            operation_id,
            "Associated source digest contribution map does not contain the target page.",
            {"source_digest_page": digest_page, "contribution_pages": sorted(contribution_pages)},
        )
    if source_file:
        target_sources = {
            *_source_values_from_section(target_content, "Source"),
            *_source_values_from_evidence(target_content),
            *_source_values_from_section(target_content, "Raw Source"),
        }
        if source_file not in target_sources:
            return _failed(
                action,
                target_page,
                operation_id,
                "Target page does not reference the refreshed raw source.",
                {"source_file": source_file, "target_sources": sorted(target_sources)},
            )
    return LintPostFixVerification(
        action=action,
        status="verified",
        target_page=target_page,
        operation_id=operation_id,
        reason="Source digest association is recorded in the digest contribution map.",
        evidence={"source_digest_page": digest_page, "source_file": source_file},
    )


def _verify_sensitive_text_redacted(
    content: str,
    action: str,
    target_page: str,
    operation_id: str | None,
    privacy_config: PrivacyConfig,
) -> LintPostFixVerification:
    remaining = detect_sensitive_text(content, privacy_config)
    if remaining:
        return _failed(
            action,
            target_page,
            operation_id,
            "Sensitive text still matches configured redaction patterns after operation.",
            {"remaining_counts": remaining},
        )
    return LintPostFixVerification(
        action=action,
        status="verified",
        target_page=target_page,
        operation_id=operation_id,
        reason="Generated page no longer matches configured sensitive text patterns.",
    )


def _verify_source_digest_page(
    content: str,
    source_file: str | None,
    action: str,
    target_page: str,
) -> LintPostFixVerification:
    source_check = _verify_source_trace(content, source_file, action, target_page, None)
    if source_check.status != "verified":
        return source_check
    return LintPostFixVerification(
        action=action,
        status="verified",
        target_page=target_page,
        reason="Created source digest has a raw source trace.",
        evidence={"source_file": source_file},
    )


def _markdown_pollution(content: str) -> list[str]:
    pollution: list[str] = []
    if len(re.findall(r"^---\s*$", content, flags=re.MULTILINE)) > 2:
        pollution.append("multiple_frontmatter_delimiters")
    if len(re.findall(r"^#\s+\S+", content, flags=re.MULTILINE)) > 1:
        pollution.append("multiple_h1_headings")
    if has_unclosed_fenced_code_blocks(content):
        pollution.append("unclosed_fenced_code_block")
    return pollution


def _candidate_action(candidate: Any) -> str | None:
    action = getattr(getattr(candidate, "recommended_action", None), "action", None)
    return str(action).strip() if action else None


def _candidate_action_params(candidate: Any) -> dict[str, Any]:
    params = getattr(getattr(candidate, "recommended_action", None), "params", None)
    return params if isinstance(params, dict) else {}


def _draft_target_section(params: dict[str, Any], draft: WikiDraftBatchItem | None) -> str | None:
    section = _optional_str(params.get("section"))
    if section:
        return section
    patch_sections = [patch.section.strip() for patch in draft.patches] if draft else []
    unique_sections = sorted({section for section in patch_sections if section})
    return unique_sections[0] if len(unique_sections) == 1 else None


def _source_values_from_section(content: str, section: str) -> set[str]:
    values: set[str] = set()
    for item in extract_list_items(extract_section(content, section)):
        text = item.strip().strip("`")
        lowered = text.lower().replace("_", " ")
        if lowered.startswith("raw source:"):
            text = text.split(":", 1)[1].strip().strip("`")
        if text:
            values.add(text)
    return values


def _source_values_from_evidence(content: str) -> set[str]:
    sources: set[str] = set()
    for line in extract_section(content, "Evidence").splitlines():
        text = line.strip()
        if not text.startswith("|") or text.startswith("|---") or ("Claim" in text and "Source" in text):
            continue
        cells = [cell.strip() for cell in text.strip("|").split("|")]
        if len(cells) >= 2 and cells[1]:
            sources.add(cells[1])
    return sources


def _contribution_map_pages(content: str) -> set[str]:
    pages: set[str] = set()
    for line in extract_section(content, "Contribution Map").splitlines():
        text = line.strip()
        if not text.startswith("|") or text.startswith("|---"):
            continue
        if re.search(r"\b(Item|Page)\b", text) and re.search(r"\b(Contribution|Claims)\b", text):
            continue
        for cell in [cell.strip() for cell in text.strip("|").split("|")]:
            for match in re.finditer(r"[\w./ ()-]+\.md", cell):
                page = match.group(0).strip()
                if page:
                    pages.add(page)
    return pages


def _has_meaningful_section_body(section: str, body: str) -> bool:
    if not body:
        return False
    normalized = body.strip()
    legal_placeholders = LEGAL_PLACEHOLDERS_BY_SECTION.get(section, set())
    if normalized in legal_placeholders:
        return True
    if normalized.startswith("- "):
        bullet_text = normalized[2:].strip()
        if bullet_text in legal_placeholders:
            return True
        items = extract_list_items(normalized)
        return any(item not in legal_placeholders for item in items)
    return bool(re.search(r"\w|[\u4e00-\u9fff]", normalized))


def _section_body_has_page_shell(body: str) -> bool:
    return bool(
        re.search(r"^---\s*$", body, flags=re.MULTILINE)
        or re.search(r"^#\s+\S+", body, flags=re.MULTILINE)
    )


def _failed(
    action: str,
    target_page: str | None,
    operation_id: str | None,
    reason: str,
    evidence: dict[str, Any] | None = None,
) -> LintPostFixVerification:
    return LintPostFixVerification(
        action=action or "unknown",
        status="failed",
        target_page=target_page,
        operation_id=operation_id,
        reason=reason,
        evidence=evidence or {},
    )


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _as_dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
