from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from knoarbor.core.schemas.run_monitor import TERMINAL_RUN_STATUSES, RunRecord
from knoarbor.runtime.transactional_ingest import TransactionalIngestStore


@dataclass(frozen=True)
class RunRecoveryAssessment:
    available: bool
    reason_code: str
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "available": self.available,
            "reason_code": self.reason_code,
            "reason": self.reason,
        }


def assess_run_recovery(record: RunRecord, *, vault_path: Path | None = None) -> RunRecoveryAssessment:
    """Return the explicit recovery contract for a run record."""

    if record.flow != "ingest":
        return RunRecoveryAssessment(False, "not_ingest", "Only ingest runs can be recovered.")
    if record.status not in TERMINAL_RUN_STATUSES:
        return RunRecoveryAssessment(False, "not_terminal", "Only terminal runs can be recovered.")
    if record.metadata.get("recovery_of_run_id"):
        return RunRecoveryAssessment(False, "already_recovery_run", "Recovery runs are not chained automatically.")
    if vault_path is not None and (vault_path / ".knoarbor" / "ingest.sqlite").is_file():
        store = TransactionalIngestStore(vault_path)
        attempt = store.attempt(record.run_id)
        assessment = store.recovery_assessment(str(attempt["task_id"]), expected_attempt_id=record.run_id)
        return RunRecoveryAssessment(
            bool(assessment["available"]),
            str(assessment["reason_code"]),
            str(assessment["reason"]),
        )

    stats = _record(record.result_summary.get("stats"))
    if _int(stats.get("recovery_candidate_count")) > 0:
        return RunRecoveryAssessment(True, "retryable_source_failures", "The run contains retryable failed source items.")
    if record.error_info.get("retryable") is True:
        return RunRecoveryAssessment(True, "retryable_run_error", "The run failed with a retryable runtime error.")
    if record.error_info:
        return RunRecoveryAssessment(False, "non_retryable_run_error", "The run failed with a non-retryable error.")

    failed_items = (
        _int(stats.get("failed_count")) + _int(stats.get("failed_segment_count")) + _int(stats.get("document_processing_failed_count"))
    )
    if failed_items > 0:
        return RunRecoveryAssessment(False, "no_recoverable_items", "The failed items are not marked retryable.")
    if record.status in {"failed", "partially_failed"}:
        return RunRecoveryAssessment(False, "no_failed_items", "No failed source item is available for recovery.")
    return RunRecoveryAssessment(False, "not_failed", "The run did not fail.")


def with_recovery_assessment(record: RunRecord, *, vault_path: Path | None = None) -> RunRecord:
    summary = dict(record.result_summary)
    summary["recovery"] = assess_run_recovery(record, vault_path=vault_path).to_dict()
    return record.model_copy(update={"result_summary": summary})


def _record(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _int(value: object) -> int:
    return value if isinstance(value, int) else 0
