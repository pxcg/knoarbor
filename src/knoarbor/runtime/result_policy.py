from __future__ import annotations

from typing import Any

from knoarbor.core.schemas.run_monitor import RunFlow, RunStatus


def completion_status_for_result(flow: RunFlow, result: Any) -> RunStatus:
    """Decide the terminal run status from a successful workflow return value.

    Exceptions still map to ``failed``/``cancelled`` in the queue. This policy
    only handles workflows that returned a result but report partial source or
    operation failures inside that result.
    """

    data = _result_data(result)
    if flow == "ingest" and _ingest_partially_failed(data):
        return "partially_failed"
    if flow == "lint" and _lint_partially_failed(data):
        return "partially_failed"
    return "completed"


def _result_data(result: Any) -> dict[str, Any]:
    if hasattr(result, "model_dump"):
        payload = result.model_dump()
        return payload if isinstance(payload, dict) else {}
    return result if isinstance(result, dict) else {}


def _ingest_partially_failed(data: dict[str, Any]) -> bool:
    if data.get("status") == "partial":
        return True
    stats = data.get("stats")
    if not isinstance(stats, dict):
        return False
    failure_keys = (
        "failed_count",
        "failed_segment_count",
        "document_processing_failed_count",
        "partial_count",
    )
    return any(_positive_int(stats.get(key)) for key in failure_keys)


def _lint_partially_failed(data: dict[str, Any]) -> bool:
    repair_results = data.get("repair_results")
    if isinstance(repair_results, list):
        incomplete = {"failed", "ineffective", "unresolved"}
        return any(isinstance(item, dict) and item.get("status") in incomplete for item in repair_results)
    return False


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and value > 0
