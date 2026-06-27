from __future__ import annotations

import difflib
import re
from datetime import datetime
from pathlib import Path

from knoarbor.core.errors import PolicyRejection, StorageConflict
from knoarbor.core.markdown import (
    append_to_section,
    extract_heading,
    extract_list_items,
    extract_section,
    parse_frontmatter,
    remove_adjacent_duplicate_headings,
    replace_section,
    update_heading,
)
from knoarbor.core.config import PrivacyConfig
from knoarbor.core.redaction import redact_public_text
from knoarbor.core.schemas.wiki_operation import WikiOperationApplyResult, WikiOperationInput
from knoarbor.core.hashing import file_content_hash
from knoarbor.storage import append_operation_ledger, append_operation_log, relative_wiki_path, resolve_wiki_page, update_index
from knoarbor.storage.vault_layout import maintenance_archives_root
from knoarbor.core.wiki_lists import prefer_list_item
from knoarbor.retrieval.wiki_links import canonical_wiki_list_item_identity, replace_wikilink_targets


STANDARD_SECTION_ORDER = (
    "Summary",
    "Claims",
    "Relations",
    "Synthesis",
    "Entities",
    "Evidence",
    "Attachments",
)

MAX_OPERATION_DIFF_LINES = 320


def ensure_expected_hash(path: Path, expected_hash: str | None) -> tuple[str, str]:
    content = path.read_text(encoding="utf-8")
    current_hash = file_content_hash(content)
    if expected_hash and expected_hash != current_hash:
        raise StorageConflict(f"before_hash mismatch for {path}: expected {expected_hash}, got {current_hash}")
    return content, current_hash


def operation_archive_path(vault_path: Path, category: str, source_path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_dir = maintenance_archives_root(vault_path) / category
    archive_dir.mkdir(parents=True, exist_ok=True)
    return archive_dir / f"{timestamp}_{source_path.name}"


def operation_diff(before_content: str, after_content: str, target_page: str) -> dict[str, object]:
    diff_lines = list(
        difflib.unified_diff(
            before_content.splitlines(),
            after_content.splitlines(),
            fromfile=target_page,
            tofile=target_page,
            lineterm="",
        )
    )
    return {
        "diff": "\n".join(diff_lines[:MAX_OPERATION_DIFF_LINES]),
        "diff_truncated": len(diff_lines) > MAX_OPERATION_DIFF_LINES,
    }


def operation_result(
    vault_path: Path,
    ledger_path: Path,
    operation: WikiOperationInput,
    output_path: Path,
    archived_pages: list[Path],
    before_hash: str,
    after_hash: str,
    details: dict[str, object],
) -> WikiOperationApplyResult:
    return WikiOperationApplyResult(
        operation_id=operation.operation_id,
        action=operation.action,
        status="applied",
        target_page=operation.target_page,
        output_page=relative_wiki_path(vault_path, output_path),
        archived_pages=[relative_wiki_path(vault_path, path) for path in archived_pages],
        before_hash=before_hash,
        after_hash=after_hash,
        ledger_path=relative_wiki_path(vault_path, ledger_path),
        details=details,
    )


def apply_rename_page(vault_path: Path, operation: WikiOperationInput) -> tuple[Path, list[Path], str, str, dict[str, object]]:
    if not operation.new_path:
        raise PolicyRejection("rename_page requires new_path")
    target_path = resolve_wiki_page(vault_path, operation.target_page)
    new_path = resolve_wiki_page(vault_path, operation.new_path)
    if not target_path.exists():
        raise PolicyRejection(f"Target page does not exist: {operation.target_page}")
    if new_path.exists():
        raise PolicyRejection(f"Rename destination already exists: {operation.new_path}")
    before_content, before_hash = ensure_expected_hash(target_path, operation.before_hash)
    new_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.rename(new_path)
    if operation.new_title:
        renamed_content = update_heading(new_path.read_text(encoding="utf-8"), operation.new_title)
        new_path.write_text(renamed_content, encoding="utf-8")
    after_content = new_path.read_text(encoding="utf-8")
    after_hash = file_content_hash(after_content)
    return new_path, [], before_hash, after_hash, {
        "old_path": operation.target_page,
        "new_path": operation.new_path,
        "new_title": operation.new_title,
        "bytes_moved": len(before_content),
        **operation_diff(before_content, after_content, operation.target_page),
    }


def apply_delete_page(vault_path: Path, operation: WikiOperationInput) -> tuple[Path, list[Path], str, str, dict[str, object]]:
    target_path = resolve_wiki_page(vault_path, operation.target_page)
    if not target_path.exists():
        raise PolicyRejection(f"Target page does not exist: {operation.target_page}")
    content, before_hash = ensure_expected_hash(target_path, operation.before_hash)
    archive_path = operation_archive_path(vault_path, "deleted_pages", target_path)
    target_path.rename(archive_path)
    after_hash = file_content_hash(archive_path.read_text(encoding="utf-8"))
    return archive_path, [archive_path], before_hash, after_hash, {"archived_instead_of_removed": True, "bytes_archived": len(content)}


def apply_merge_pages(vault_path: Path, operation: WikiOperationInput) -> tuple[Path, list[Path], str, str, dict[str, object]]:
    target_path = resolve_wiki_page(vault_path, operation.target_page)
    if not target_path.exists():
        raise PolicyRejection(f"Target page does not exist: {operation.target_page}")
    if not operation.source_pages:
        raise PolicyRejection("merge_pages requires source_pages")
    target_content, before_hash = ensure_expected_hash(target_path, operation.before_hash)
    merged_content = target_content
    archived: list[Path] = []
    merged_sources: list[str] = []

    for raw_source in operation.source_pages:
        source_path = resolve_wiki_page(vault_path, raw_source)
        if source_path.resolve() == target_path.resolve():
            continue
        if not source_path.exists():
            raise PolicyRejection(f"Merge source page does not exist: {raw_source}")
        source_content = source_path.read_text(encoding="utf-8")
        source_title = extract_heading(source_content, source_path.stem)
        merged_sources.append(raw_source)
        merged_block = (
            f"Source page: [[{Path(raw_source).with_suffix('').as_posix()}|{source_title}]]\n\n"
            f"{source_content.strip()}"
        )
        merged_content = append_to_section(merged_content, "Merged Notes", merged_block, source_title)
        if operation.archive_sources:
            archive_path = operation_archive_path(vault_path, "merged_pages", source_path)
            source_path.rename(archive_path)
            archived.append(archive_path)

    after_hash = file_content_hash(merged_content)
    if after_hash != before_hash:
        target_path.write_text(merged_content.rstrip() + "\n", encoding="utf-8")
    return target_path, archived, before_hash, after_hash, {
        "merged_sources": merged_sources,
        "archived_sources": operation.archive_sources,
        **operation_diff(target_content, merged_content.rstrip() + "\n", operation.target_page),
    }


def apply_replace_wikilink(vault_path: Path, operation: WikiOperationInput) -> tuple[Path, list[Path], str, str, dict[str, object]]:
    if not operation.old_target or not operation.new_target:
        raise PolicyRejection("replace_wikilink requires old_target and new_target")
    target_path = resolve_wiki_page(vault_path, operation.target_page)
    if not target_path.exists():
        raise PolicyRejection(f"Target page does not exist: {operation.target_page}")
    content, before_hash = ensure_expected_hash(target_path, operation.before_hash)
    updated, replacements = replace_wikilink_targets(content, operation.old_target, operation.new_target, operation.link_text)
    if replacements == 0:
        raise PolicyRejection(f"No wikilinks matched old_target: {operation.old_target}")
    after_hash = file_content_hash(updated)
    if after_hash != before_hash:
        target_path.write_text(updated, encoding="utf-8")
    return target_path, [], before_hash, after_hash, {
        "old_target": operation.old_target,
        "new_target": operation.new_target,
        "link_text": operation.link_text,
        "replacements": replacements,
        **operation_diff(content, updated, operation.target_page),
    }


def apply_deduplicate_section_items(vault_path: Path, operation: WikiOperationInput) -> tuple[Path, list[Path], str, str, dict[str, object]]:
    section = (operation.section or "Entities").strip()
    target_path = resolve_wiki_page(vault_path, operation.target_page)
    if not target_path.exists():
        raise PolicyRejection(f"Target page does not exist: {operation.target_page}")
    content, before_hash = ensure_expected_hash(target_path, operation.before_hash)
    unique: list[str] = []
    index_by_key: dict[str, int] = {}
    removed_count = 0
    for item in extract_list_items(extract_section(content, section)):
        key = canonical_wiki_list_item_identity(vault_path, item)
        if key in index_by_key:
            existing_index = index_by_key[key]
            unique[existing_index] = prefer_list_item(item, unique[existing_index])
            removed_count += 1
            continue
        index_by_key[key] = len(unique)
        unique.append(item)
    updated = replace_section(content, section, "\n".join(f"- {item}" for item in unique) if unique else "- 暂无内容")
    after_hash = file_content_hash(updated)
    if after_hash != before_hash:
        target_path.write_text(updated, encoding="utf-8")
    return target_path, [], before_hash, after_hash, {
        "section": section,
        "removed_count": removed_count,
        **operation_diff(content, updated, operation.target_page),
    }


def apply_remove_adjacent_duplicate_headings(vault_path: Path, operation: WikiOperationInput) -> tuple[Path, list[Path], str, str, dict[str, object]]:
    target_path = resolve_wiki_page(vault_path, operation.target_page)
    if not target_path.exists():
        raise PolicyRejection(f"Target page does not exist: {operation.target_page}")
    content, before_hash = ensure_expected_hash(target_path, operation.before_hash)
    updated, removed_headings = remove_adjacent_duplicate_headings(content)
    after_hash = file_content_hash(updated)
    if after_hash != before_hash:
        target_path.write_text(updated, encoding="utf-8")
    return target_path, [], before_hash, after_hash, {
        "removed_count": len(removed_headings),
        "removed_headings": removed_headings,
        **operation_diff(content, updated, operation.target_page),
    }


def apply_add_missing_section(vault_path: Path, operation: WikiOperationInput) -> tuple[Path, list[Path], str, str, dict[str, object]]:
    section = (operation.section or "").strip()
    if not section:
        raise PolicyRejection("add_missing_section requires section")
    target_path = resolve_wiki_page(vault_path, operation.target_page)
    if not target_path.exists():
        raise PolicyRejection(f"Target page does not exist: {operation.target_page}")
    content, before_hash = ensure_expected_hash(target_path, operation.before_hash)
    if extract_section(content, section).strip():
        return target_path, [], before_hash, before_hash, {"section": section, "already_present": True}

    section_content = operation.section_content or _default_missing_section_content(content, section)
    updated = _insert_missing_section(content, section, section_content)
    after_hash = file_content_hash(updated)
    if after_hash != before_hash:
        target_path.write_text(updated, encoding="utf-8")
    return target_path, [], before_hash, after_hash, {
        "section": section,
        "already_present": False,
        **operation_diff(content, updated, operation.target_page),
    }


def _default_missing_section_content(content: str, section: str) -> str:
    metadata = parse_frontmatter(content)
    source = _first_structured_source(content)
    if section == "Source Identity":
        rows = [
            f"- Raw source: {source or 'unknown'}",
            f"- Content hash: {metadata.get('content_hash', 'unknown')}",
        ]
        return "\n".join(rows)
    if section == "Audit Summary":
        title = extract_heading(content, "Untitled")
        return f"Audit record for {title}. Raw pointer: {source}."
    if section == "Source Units":
        unit_source = source or "unknown"
        return "\n".join(
            [
                "| Unit | Source | Range | Basis | Confidence |",
                "|---|---|---|---|---|",
                f"| U1 | {unit_source} | source-level | source digest placeholder | low |",
            ]
        )
    if section == "Contribution Map":
        return "- No accepted contribution map was generated."
    if section == "Unresolved / Rejected":
        return "- No unresolved or rejected material recorded."
    if section == "Raw Source":
        return f"- Raw source: {source}" if source else "- Raw source: unknown"
    if section == "Summary":
        return extract_heading(content, "Untitled")
    if section == "Claims":
        return "- C1: 暂无可验证断言。"
    if section == "Relations":
        return "| Subject | Predicate | Object | Based on |\n|---|---|---|---|\n| 暂无 | relates_to | 暂无 | C1 |"
    if section == "Synthesis":
        return extract_section(content, "Summary") or extract_heading(content, "Untitled")
    if section == "Entities":
        return "- 暂无实体"
    if section == "Evidence":
        return "- 暂无证据"
    if section == "Attachments":
        return "- 暂无附件"
    return "暂无内容"


def _first_structured_source(content: str) -> str:
    for item in extract_list_items(extract_section(content, "Raw Source")):
        source = item.strip().strip("`")
        if source.lower().startswith("raw source:"):
            source = source.split(":", 1)[1].strip().strip("`")
        if source and not source.startswith("暂无"):
            return source
    for item in extract_list_items(extract_section(content, "Source Identity")):
        source = item.strip().strip("`")
        if source.lower().startswith("raw source:"):
            source = source.split(":", 1)[1].strip().strip("`")
        if source and not source.startswith("暂无"):
            return source
    for cells in _markdown_table_rows(extract_section(content, "Evidence")):
        if len(cells) < 2 or cells[0].strip().lower() == "claim":
            continue
        source = cells[1].strip().strip("`")
        if source:
            return source
    return ""


def _markdown_table_rows(section: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in section.splitlines():
        text = line.strip()
        if not text.startswith("|") or text.startswith("|---"):
            continue
        cells = [cell.strip() for cell in text.strip("|").split("|")]
        if cells:
            rows.append(cells)
    return rows


def _insert_missing_section(content: str, section: str, section_content: str) -> str:
    section_block = f"## {section}\n\n{section_content.strip()}\n"
    if section not in STANDARD_SECTION_ORDER:
        return replace_section(content, section, section_content)

    wanted_index = STANDARD_SECTION_ORDER.index(section)
    following = STANDARD_SECTION_ORDER[wanted_index + 1 :]
    for next_section in following:
        pattern = rf"^##\s+{re.escape(next_section)}\s*$"
        match = re.search(pattern, content, flags=re.MULTILINE)
        if match:
            return content[: match.start()].rstrip() + "\n\n" + section_block + "\n" + content[match.start() :].lstrip()

    return content.rstrip() + "\n\n" + section_block


def apply_redact_sensitive_text(
    vault_path: Path,
    operation: WikiOperationInput,
    privacy_config: PrivacyConfig,
) -> tuple[Path, list[Path], str, str, dict[str, object]]:
    target_path = resolve_wiki_page(vault_path, operation.target_page)
    if not target_path.exists():
        raise PolicyRejection(f"Target page does not exist: {operation.target_page}")
    content, before_hash = ensure_expected_hash(target_path, operation.before_hash)
    result = redact_public_text(content, privacy_config)
    if not result.counts:
        return target_path, [], before_hash, before_hash, {"redaction_counts": {}, "already_redacted": True}
    updated = result.text
    after_hash = file_content_hash(updated)
    if after_hash != before_hash:
        target_path.write_text(updated, encoding="utf-8")
    return target_path, [], before_hash, after_hash, {
        "redaction_counts": result.counts,
        "already_redacted": False,
        **operation_diff(content, updated, operation.target_page),
    }


def apply_wiki_operation(
    vault_path: Path,
    operation: WikiOperationInput,
    ledger_path: str,
    *,
    privacy_config: PrivacyConfig | None = None,
) -> WikiOperationApplyResult:
    privacy_config = privacy_config or PrivacyConfig()
    if operation.action == "rename_page":
        output_path, archived, before_hash, after_hash, details = apply_rename_page(vault_path, operation)
    elif operation.action == "delete_page":
        output_path, archived, before_hash, after_hash, details = apply_delete_page(vault_path, operation)
    elif operation.action == "merge_pages":
        output_path, archived, before_hash, after_hash, details = apply_merge_pages(vault_path, operation)
    elif operation.action in {"replace_wikilink", "normalize_wikilink"}:
        output_path, archived, before_hash, after_hash, details = apply_replace_wikilink(vault_path, operation)
    elif operation.action == "deduplicate_section_items":
        output_path, archived, before_hash, after_hash, details = apply_deduplicate_section_items(vault_path, operation)
    elif operation.action == "remove_adjacent_duplicate_headings":
        output_path, archived, before_hash, after_hash, details = apply_remove_adjacent_duplicate_headings(vault_path, operation)
    elif operation.action == "add_missing_section":
        output_path, archived, before_hash, after_hash, details = apply_add_missing_section(vault_path, operation)
    elif operation.action == "redact_sensitive_text":
        output_path, archived, before_hash, after_hash, details = apply_redact_sensitive_text(vault_path, operation, privacy_config)
    else:
        raise PolicyRejection(f"Unsupported wiki operation action: {operation.action}")

    update_index(vault_path)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ledger_record = {
        "operation_id": operation.operation_id,
        "action": operation.action,
        "status": "applied",
        "target_page": operation.target_page,
        "output_page": relative_wiki_path(vault_path, output_path),
        "archived_pages": [relative_wiki_path(vault_path, path) for path in archived],
        "reason": operation.reason,
        "risk_level": operation.risk_level,
        "confidence": operation.confidence,
        "expected_effect": operation.expected_effect,
        "before_hash": before_hash,
        "after_hash": after_hash,
        "details": details,
        "created_at": now,
    }
    ledger = append_operation_ledger(vault_path, ledger_path, ledger_record)
    append_operation_log(vault_path, f"\n## {now}\n\n- operation: wiki_operation_lint\n- action: {operation.action}\n- operation_id: {operation.operation_id}\n- target: {operation.target_page}\n- output: {ledger_record['output_page']}\n- ledger: {relative_wiki_path(vault_path, ledger)}\n")
    return operation_result(vault_path, ledger, operation, output_path, archived, before_hash, after_hash, details)
