from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from knoarbor.core.markdown import adjacent_duplicate_headings, extract_list_items, extract_section, parse_frontmatter, wiki_target_key
from knoarbor.core.schemas.lint_candidates import MaintenanceCandidates
from knoarbor.core.schemas.wiki_draft_batch import WikiDraftBatch, WikiDraftBatchItem
from knoarbor.core.schemas.wiki_write import WikiDraftBatchWriteResponse, WikiDraftWriteResponse
from knoarbor.retrieval.wiki_links import canonical_wiki_list_item_identity, resolve_wikilink_target
from knoarbor.storage import resolve_wiki_page
from knoarbor.storage.wiki_index import relative_wiki_path


VerificationStatus = Literal["verified", "failed", "skipped"]
LEGAL_PLACEHOLDERS_BY_SECTION = {
    "Related Pages": {"暂无关联知识", "No related pages."},
    "Tags": {"暂无标签", "No tags."},
    "Source": {"暂无来源", "No source."},
}
CHATTY_SUMMARY_PATTERN = re.compile(
    r"如果(你|您)(还)?需要|可以告诉我|欢迎继续|我可以继续|希望我继续|let me know|if you need",
    flags=re.IGNORECASE,
)


class LintPostFixVerification(BaseModel):
    """Result of verifying one reviewed lint maintenance effect."""

    action: str
    status: VerificationStatus
    target_page: str | None = None
    operation_id: str | None = None
    reason: str
    evidence: dict[str, Any] = Field(default_factory=dict)


def verify_lint_post_fixes(
    vault_path: Path,
    *,
    applied_operations: list[dict[str, Any]],
    draft_batch: WikiDraftBatch | None = None,
    draft_write_response: WikiDraftBatchWriteResponse | None = None,
    candidates: MaintenanceCandidates | None = None,
) -> list[LintPostFixVerification]:
    """Verify effects that cannot be fully proven by a generic rescan.

    The verifier is intentionally downstream of execution. It does not infer
    missing operation parameters, mutate files, or decide whether an operation
    should have been approved.
    """

    verifications: list[LintPostFixVerification] = []
    for operation in applied_operations:
        verifications.append(_verify_wiki_operation(vault_path, operation))

    if draft_batch and draft_write_response:
        candidate_by_index = {
            index: candidate
            for index, candidate in enumerate(candidates.candidates if candidates else [])
        }
        draft_by_index = {draft.operation_index: draft for draft in draft_batch.drafts}
        for result in draft_write_response.results:
            operation_index = _optional_int(result.stats.get("operation_index"))
            draft = draft_by_index.get(operation_index) if operation_index is not None else None
            candidate = candidate_by_index.get(operation_index) if operation_index is not None else None
            verifications.append(_verify_draft_write(vault_path, result, draft, candidate))

    return verifications


def summarize_verifications(verifications: list[LintPostFixVerification]) -> dict[str, object]:
    counts = {"verified": 0, "failed": 0, "skipped": 0}
    for item in verifications:
        counts[item.status] += 1
    return {
        "total": len(verifications),
        **counts,
        "follow_up_required": counts["failed"] > 0,
    }


def _verify_wiki_operation(vault_path: Path, operation: dict[str, Any]) -> LintPostFixVerification:
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

    if action in {"attach_related_pages", "attach_source_digest"}:
        expected = _string_list(details.get("related_pages")) or _string_list(operation.get("related_pages"))
        return _verify_related_links(vault_path, content, expected, action, target_page, operation_id)

    if action == "remove_related_links":
        expected = _string_list(details.get("related_pages")) or _string_list(operation.get("related_pages"))
        return _verify_related_links_removed(vault_path, content, expected, action, target_page, operation_id)

    if action in {"replace_wikilink", "normalize_wikilink"}:
        old_target = _optional_str(details.get("old_target"))
        new_target = _optional_str(details.get("new_target"))
        return _verify_wikilink_replacement(content, old_target, new_target, action, target_page, operation_id)

    if action == "update_frontmatter":
        return _verify_frontmatter_updates(content, _as_dict(details.get("frontmatter")), action, target_page, operation_id)

    if action == "deduplicate_section_items":
        section = _optional_str(details.get("section")) or "Related Pages"
        return _verify_deduplicated_section(vault_path, content, section, action, target_page, operation_id)

    if action == "remove_adjacent_duplicate_headings":
        return _verify_adjacent_duplicate_headings_removed(content, action, target_page, operation_id)

    if action == "add_missing_section":
        section = _optional_str(details.get("section"))
        return _verify_added_wiki_operation_section(content, action, target_page, operation_id, section)

    if action == "update_source_field":
        source_file = _optional_str(details.get("source_file"))
        return _verify_source_field(content, source_file, action, target_page, operation_id)

    if action == "rename_page":
        return _verify_renamed_page(vault_path, operation, action, target_page, operation_id)

    if action == "delete_page":
        return _verify_deleted_page(vault_path, operation, action, target_page, operation_id)

    if action == "merge_pages":
        return _verify_merged_pages(vault_path, content, operation, action, target_page, operation_id)

    return LintPostFixVerification(
        action=action,
        status="skipped",
        target_page=target_page,
        operation_id=operation_id,
        reason="No operation-specific verification rule is defined for this action.",
    )


def _verify_draft_write(
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
        related_pages = list(getattr(candidate, "related_pages", []) or [])
        return _verify_source_digest_page(content, source_file, related_pages, action, target_page)

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


def _verify_related_links(
    vault_path: Path,
    content: str,
    expected_pages: list[str],
    action: str,
    target_page: str,
    operation_id: str | None,
) -> LintPostFixVerification:
    if not expected_pages:
        return _failed(action, target_page, operation_id, "Related link verification requires expected related_pages.")
    identities = {
        canonical_wiki_list_item_identity(vault_path, item)
        for item in extract_list_items(extract_section(content, "Related Pages"))
    }
    missing = [
        page
        for page in expected_pages
        if _expected_link_identity(vault_path, page) not in identities
    ]
    duplicate_count = len(identities) != len(extract_list_items(extract_section(content, "Related Pages")))
    if missing or duplicate_count:
        return _failed(
            action,
            target_page,
            operation_id,
            "Related Pages verification failed.",
            {"missing": missing, "has_duplicate_related_items": duplicate_count},
        )
    return LintPostFixVerification(
        action=action,
        status="verified",
        target_page=target_page,
        operation_id=operation_id,
        reason="Expected related pages are present and canonical list items are unique.",
        evidence={"expected_pages": expected_pages},
    )


def _verify_related_links_removed(
    vault_path: Path,
    content: str,
    expected_pages: list[str],
    action: str,
    target_page: str,
    operation_id: str | None,
) -> LintPostFixVerification:
    if not expected_pages:
        return _failed(action, target_page, operation_id, "Related link removal verification requires related_pages.")
    identities = {
        canonical_wiki_list_item_identity(vault_path, item)
        for item in extract_list_items(extract_section(content, "Related Pages"))
    }
    still_present = [
        page
        for page in expected_pages
        if _expected_link_identity(vault_path, page) in identities
    ]
    if still_present:
        return _failed(
            action,
            target_page,
            operation_id,
            "Related Pages still contains links that should have been removed.",
            {"still_present": still_present},
        )
    return LintPostFixVerification(
        action=action,
        status="verified",
        target_page=target_page,
        operation_id=operation_id,
        reason="Requested related page links are absent.",
        evidence={"removed_pages": expected_pages},
    )


def _verify_frontmatter_updates(
    content: str,
    expected: dict[str, Any],
    action: str,
    target_page: str,
    operation_id: str | None,
) -> LintPostFixVerification:
    if not expected:
        return _failed(action, target_page, operation_id, "Frontmatter verification requires expected key/value updates.")
    metadata = parse_frontmatter(content)
    mismatches = {
        str(key): {"expected": str(value), "actual": metadata.get(str(key))}
        for key, value in expected.items()
        if metadata.get(str(key)) != str(value)
    }
    if mismatches:
        return _failed(action, target_page, operation_id, "Frontmatter values do not match expected updates.", {"mismatches": mismatches})
    return LintPostFixVerification(
        action=action,
        status="verified",
        target_page=target_page,
        operation_id=operation_id,
        reason="Frontmatter values match the approved updates.",
        evidence={"frontmatter": {str(key): str(value) for key, value in expected.items()}},
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


def _verify_source_field(
    content: str,
    source_file: str | None,
    action: str,
    target_page: str,
    operation_id: str | None,
) -> LintPostFixVerification:
    if not source_file:
        return _failed(action, target_page, operation_id, "Source field verification requires source_file.")
    metadata = parse_frontmatter(content)
    source_section = extract_section(content, "Source")
    ok = metadata.get("source") == source_file and source_file in source_section
    if not ok:
        return _failed(
            action,
            target_page,
            operation_id,
            "Frontmatter source and Source section do not match expected source_file.",
            {"frontmatter_source": metadata.get("source"), "expected_source": source_file},
        )
    return LintPostFixVerification(
        action=action,
        status="verified",
        target_page=target_page,
        operation_id=operation_id,
        reason="Frontmatter source and Source section match expected source_file.",
        evidence={"source_file": source_file},
    )


def _verify_source_digest_page(
    content: str,
    source_file: str | None,
    related_pages: list[str],
    action: str,
    target_page: str,
) -> LintPostFixVerification:
    source_check = _verify_source_field(content, source_file, action, target_page, None)
    if source_check.status != "verified":
        return source_check
    metadata = parse_frontmatter(content)
    if metadata.get("type") != "source":
        return _failed(action, target_page, None, "Created source digest page does not have type: source.", {"frontmatter_type": metadata.get("type")})
    if related_pages and not extract_list_items(extract_section(content, "Related Pages")):
        return _failed(action, target_page, None, "Created source digest page does not link back to related knowledge pages.", {"expected_related_pages": related_pages})
    return LintPostFixVerification(
        action=action,
        status="verified",
        target_page=target_page,
        reason="Created source digest has source frontmatter, Source section, source type, and related page section.",
        evidence={"source_file": source_file, "related_pages": related_pages},
    )


def _markdown_pollution(content: str) -> list[str]:
    pollution: list[str] = []
    if len(re.findall(r"^---\s*$", content, flags=re.MULTILINE)) > 2:
        pollution.append("multiple_frontmatter_delimiters")
    if len(re.findall(r"^#\s+\S+", content, flags=re.MULTILINE)) > 1:
        pollution.append("multiple_h1_headings")
    if len(re.findall(r"^##\s+Source\s*$", content, flags=re.MULTILINE)) > 1:
        pollution.append("multiple_source_sections")
    return pollution


def _expected_link_identity(vault_path: Path, page: str) -> str:
    resolved = resolve_wikilink_target(vault_path, page)
    return resolved or wiki_target_key(page)


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


def _has_meaningful_section_body(section: str, body: str) -> bool:
    if not body:
        return False
    normalized = body.strip()
    if normalized in LEGAL_PLACEHOLDERS_BY_SECTION.get(section, set()):
        return True
    if normalized.startswith("- "):
        items = extract_list_items(normalized)
        return any(item not in LEGAL_PLACEHOLDERS_BY_SECTION.get(section, set()) for item in items)
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
