from __future__ import annotations

from pathlib import Path
from typing import Any

from knoarbor.audit.run_failure import write_run_failure_artifacts
from knoarbor.core.config import KnoArborConfig, default_config_path, load_config
from knoarbor.core.schemas.run_monitor import RunFlow
from knoarbor.core.vaults import select_config_vault
from knoarbor.runtime import current_run_monitor


def write_workflow_failure_artifacts(
    *,
    flow: RunFlow,
    request: Any,
    exc: BaseException,
    logger: Any,
    config: KnoArborConfig | None = None,
    vault_path: Path | None = None,
    append_ledger: bool | None = None,
    write_report: bool | None = None,
    report_path: str | None = None,
    ledger_path: str | None = None,
) -> None:
    """Write failure reports for workflow service boundaries.

    This helper centralizes the only broad exception boundary used by the
    high-level services: if a workflow fails before producing its normal report,
    write a user-visible failure report and ledger entry when requested, then
    let the original exception propagate.
    """

    should_append = _request_bool(request, "append_ledger", _request_bool(request, "record_query", False))
    should_report = _request_bool(request, "write_report", False)
    if append_ledger is not None:
        should_append = append_ledger
    if write_report is not None:
        should_report = write_report
    if not should_report and not should_append:
        return

    effective_vault = _resolve_failure_vault(request, config=config, vault_path=vault_path, logger=logger)
    if effective_vault is None:
        logger.info("%s_failure_report_skipped reason=no_vault_path error=%s", flow, exc)
        return

    try:
        monitor = current_run_monitor()
        write_run_failure_artifacts(
            effective_vault,
            flow=flow,
            request=request,
            exc=exc,
            run_id=monitor.run_id if monitor else None,
            stage=monitor.read().stage if monitor else None,
            append_ledger=should_append,
            write_report=should_report,
            report_path=report_path or _request_str(request, "report_path"),
            ledger_path=ledger_path or _request_str(request, "ledger_path"),
        )
    except Exception as report_exc:  # noqa: BLE001 - secondary reporting failure must not mask the original error.
        logger.exception("%s_failure_report_write_failed error=%s original_error=%s", flow, report_exc, exc)


def _resolve_failure_vault(
    request: Any,
    *,
    config: KnoArborConfig | None,
    vault_path: Path | None,
    logger: Any,
) -> Path | None:
    if vault_path is not None:
        return vault_path.expanduser().resolve()
    if config is not None:
        return config.vault.path
    request_vault = _request_str(request, "vault_path")
    if request_vault:
        return Path(request_vault).expanduser().resolve()
    try:
        loaded = load_config(_request_str(request, "config_path") or default_config_path())
        selected = select_config_vault(loaded, vault_id=_request_str(request, "vault_id"))
        return selected.vault.path
    except Exception as exc:
        logger.info("workflow_failure_vault_resolution_failed error=%s", exc)
        return None


def _request_bool(request: Any, field: str, default: bool) -> bool:
    value = getattr(request, field, default)
    return bool(value)


def _request_str(request: Any, field: str) -> str | None:
    value = getattr(request, field, None)
    text = str(value).strip() if value is not None else ""
    return text or None
