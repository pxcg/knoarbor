from __future__ import annotations

import difflib
from pathlib import Path

from knoarbor.maintenance.wiki_links import reconcile_expected_related_pages
from knoarbor.storage.wiki_index import relative_wiki_path


MAX_RELATED_PAGES_DIFF_LINES = 220


def reconcile_related_pages(
    vault_path: Path,
    page_path: Path,
    expected_pages: list[str],
    issue_type: str,
    *,
    max_diff_lines: int = MAX_RELATED_PAGES_DIFF_LINES,
) -> dict[str, object] | None:
    before = page_path.read_text(encoding="utf-8")
    stats = reconcile_expected_related_pages(vault_path, page_path, expected_pages)
    after = page_path.read_text(encoding="utf-8")
    if before == after:
        return None

    relative_path = relative_wiki_path(vault_path, page_path)
    diff_lines = list(
        difflib.unified_diff(
            before.splitlines(),
            after.splitlines(),
            fromfile=relative_path,
            tofile=relative_path,
            lineterm="",
        )
    )
    return {
        "status": "applied",
        "issue_type": issue_type,
        "related_pages": expected_pages,
        "write_details": {
            "patched_sections": ["Related Pages"],
            "semantic_related_links": stats,
            "diff": "\n".join(diff_lines[:max_diff_lines]),
            "diff_truncated": len(diff_lines) > max_diff_lines,
        },
    }
