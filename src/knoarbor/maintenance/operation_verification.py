from __future__ import annotations

from pathlib import Path
from typing import Any

from knoarbor.core.config import PrivacyConfig
from knoarbor.core.schemas.lint_candidates import MaintenanceCandidates
from knoarbor.core.schemas.wiki_draft_batch import WikiDraftBatch
from knoarbor.core.schemas.wiki_write import WikiDraftBatchWriteResponse
from knoarbor.maintenance.operation_verification_models import LintPostFixVerification
from knoarbor.maintenance.operation_verifiers import verify_draft_write, verify_wiki_operation


def verify_lint_post_fixes(
    vault_path: Path,
    *,
    applied_operations: list[dict[str, Any]],
    draft_batch: WikiDraftBatch | None = None,
    draft_write_response: WikiDraftBatchWriteResponse | None = None,
    candidates: MaintenanceCandidates | None = None,
    privacy_config: PrivacyConfig | None = None,
) -> list[LintPostFixVerification]:
    """Verify effects that cannot be fully proven by a generic rescan.

    The verifier is intentionally downstream of execution. It does not infer
    missing operation parameters, mutate files, or decide whether an operation
    should have been approved.
    """

    verifications: list[LintPostFixVerification] = []
    for operation in applied_operations:
        verifications.append(verify_wiki_operation(vault_path, operation, privacy_config=privacy_config))

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
            verifications.append(verify_draft_write(vault_path, result, draft, candidate))

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


def _optional_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
