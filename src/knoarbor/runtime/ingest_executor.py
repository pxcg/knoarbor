from __future__ import annotations

from typing import Any
from uuid import uuid4

from knoarbor.core.errors import StorageConflict, error_info
from knoarbor.core.schemas.ingest_execution import provider_admission_key
from knoarbor.runtime.ingest_exceptions import ProviderRateLimited
from knoarbor.runtime.ingest_session import IngestExecutionSession
from knoarbor.runtime.local_operations import OperationCancellationToken
from knoarbor.runtime.provider_permits import provider_permit_pool
from knoarbor.runtime.result_policy import completion_status_for_result
from knoarbor.runtime.run_monitor import RunCancelled, RunMonitor, run_monitor_context
from knoarbor.runtime.transactional_ingest import AttemptLease, TransactionalIngestStore
from knoarbor.storage.ingest_inputs import read_input_generation
from knoarbor.storage.materialization import VaultMaterializer


MIN_LEASE_SECONDS = 300.0
LEASE_MARGIN_SECONDS = 120.0


class IngestTaskExecutor:
    """Execute exactly one persisted local ingest task; no queue loop is owned."""

    def __init__(self, vault_path, *, service, materializer: VaultMaterializer | None = None) -> None:
        self.store = TransactionalIngestStore(vault_path)
        self.vault_path = self.store.vault_path
        self.service = service
        self.materializer = materializer or VaultMaterializer()
        self.owner_id = f"local-operation:{uuid4().hex}"

    def execute(self, task_id: str, *, cancellation: OperationCancellationToken | None = None) -> dict[str, object]:
        token = cancellation or OperationCancellationToken()
        task = self.store.task(task_id)
        attempt_id = str(task["current_attempt_id"])
        command = self.store.command_for_task(task_id)
        read_input_generation(self.vault_path, command.generation_id)
        validator = getattr(self.service, "validate_generation_command", None)
        if validator is not None:
            validator(command)

        provider = command.execution_contract.get("provider")
        provider_payload = provider if isinstance(provider, dict) else {}
        concurrency = command.execution_contract.get("ingest")
        ingest_payload = concurrency if isinstance(concurrency, dict) else {}
        limits = ingest_payload.get("concurrency")
        limit_payload = limits if isinstance(limits, dict) else {}
        limit = int(limit_payload.get("max_concurrent_provider_requests") or 1)
        lease_seconds = max(
            MIN_LEASE_SECONDS,
            float(command.execution_contract.get("request_timeout_seconds") or 0) + LEASE_MARGIN_SECONDS,
        )
        monitor = RunMonitor(
            vault_path=self.vault_path,
            flow="ingest",
            run_id=attempt_id,
            metadata={
                "ingest_task_id": task_id,
                "input_generation_id": command.generation_id,
                "provider": provider_payload.get("name"),
                "ingest_lease_seconds": lease_seconds,
            },
            cancellation_probe=lambda: self._cancelled(task_id, token),
        )
        try:
            with provider_permit_pool.reserve_attempt(
                provider_admission_key(command),
                limit=limit,
                vault_path=self.vault_path,
                raise_if_cancelled=lambda: self._raise_if_cancelled(task_id, token),
            ) as admission:
                lease = self.store.claim(
                    task_id,
                    attempt_id,
                    owner_id=self.owner_id,
                    lease_seconds=lease_seconds,
                    expected_admission_version=admission.control_version,
                )
                session = IngestExecutionSession(
                    self.store,
                    lease,
                    monitor,
                    lease_seconds=lease_seconds,
                )
                return self._execute_claimed(command, session, monitor, token)
        except RunCancelled as exc:
            self._finish_unclaimed_cancel(task_id, attempt_id, monitor, exc)
        except StorageConflict:
            return self.store.task(task_id)
        except Exception as exc:
            self._fail_unclaimed(task_id, attempt_id, monitor, exc)
        return self.store.task(task_id)

    def _execute_claimed(
        self,
        command,
        session: IngestExecutionSession,
        monitor: RunMonitor,
        cancellation: OperationCancellationToken,
    ) -> dict[str, object]:
        with run_monitor_context(monitor):
            try:
                monitor.start(message="ingest run started.")
                cancellation.raise_if_stopped()
                result = self.service.run_generation_command(command, execution=session)
                cancellation.raise_if_stopped()
                session.renew()
                materialization_error = None
                if self.store.materialization_state()["phase"] != "clean":
                    try:
                        materialization_state = self.materializer.reconcile(self.vault_path)
                        if materialization_state["phase"] != "clean":
                            materialization_error = str(
                                materialization_state.get("last_error")
                                or "Vault changed during materialization; reconciliation remains requested."
                            )
                    except Exception as exc:
                        materialization_error = f"{type(exc).__name__}: {exc}"
                state = completion_status_for_result("ingest", result)
                summary = _result_summary(result)
                if materialization_error:
                    summary["materialization_pending"] = True
                    summary["materialization_error"] = materialization_error
                self.store.finish(session.lease, state=state, result=summary)
                if state == "partially_failed":
                    monitor.partially_fail(message="ingest run partially failed.", result_summary=summary, metrics=_metrics(result))
                else:
                    monitor.complete(message="ingest run completed.", result_summary=summary, metrics=_metrics(result))
            except ProviderRateLimited as exc:
                _finish(self.store, session.lease, "paused_rate_limited", exc)
                monitor.fail(exc, stage="rate_limited")
            except Exception as exc:
                state = "recovery_needed" if isinstance(exc, RunCancelled) else "failed"
                _finish(self.store, session.lease, state, exc)
                monitor.fail(exc)
        return self.store.task(session.lease.task_id)

    def _cancelled(self, task_id: str, token: OperationCancellationToken) -> bool:
        try:
            token.raise_if_stopped()
        except RunCancelled:
            return True
        return bool(self.store.task(task_id).get("cancel_requested"))

    def _raise_if_cancelled(self, task_id: str, token: OperationCancellationToken) -> None:
        token.raise_if_stopped()
        if bool(self.store.task(task_id).get("cancel_requested")):
            raise RunCancelled(f"Ingest task was cancelled before claim: {task_id}")

    def _finish_unclaimed_cancel(self, task_id: str, attempt_id: str, monitor: RunMonitor, exc: BaseException) -> None:
        task = self.store.task(task_id)
        if task["state"] != "queued" or not task.get("cancel_requested"):
            return
        self.store.request_cancel(task_id, expected_attempt_id=attempt_id)
        try:
            monitor.fail(exc)
        except Exception:
            return

    def _fail_unclaimed(self, task_id: str, attempt_id: str, monitor: RunMonitor, exc: BaseException) -> None:
        try:
            self.store.fail_queued_task(
                task_id,
                attempt_id,
                error=f"{type(exc).__name__}: {exc}",
                result={"failure": _failure_payload(exc)},
            )
        except StorageConflict:
            return
        monitor.fail(exc, stage="admission_failed")


def _finish(store: TransactionalIngestStore, lease: AttemptLease, state: str, exc: BaseException) -> None:
    try:
        store.finish(
            lease,
            state=state,
            error=f"{type(exc).__name__}: {exc}",
            result={"failure": _failure_payload(exc)},
        )
    except StorageConflict:
        return


def _result_summary(result: Any) -> dict[str, Any]:
    payload = result.model_dump(mode="json") if hasattr(result, "model_dump") else {}
    summary = {key: payload[key] for key in ("stats", "report_path", "ledger_path") if key in payload}
    if isinstance(payload.get("results"), list):
        summary["result_count"] = len(payload["results"])
        compilations = []
        for item in payload["results"]:
            if not isinstance(item, dict):
                continue
            context = item.get("context")
            index_metadata = context.get("index_metadata") if isinstance(context, dict) else None
            compilation = index_metadata.get("compilation") if isinstance(index_metadata, dict) else None
            if isinstance(compilation, dict):
                compilations.append({"source_id": item.get("source_id"), **compilation})
        if compilations:
            summary["index_metadata_compilations"] = compilations
        failures = [
            {
                key: item.get(key)
                for key in (
                    "source_id",
                    "source_file",
                    "error_stage",
                    "error_code",
                    "error_category",
                    "error_retryable",
                    "error_hint",
                    "error_type",
                    "error_message",
                )
            }
            for item in payload["results"]
            if isinstance(item, dict) and item.get("status") in {"failed", "partial"}
        ]
        if failures:
            summary["failures"] = failures
    return summary


def _metrics(result: Any) -> dict[str, Any]:
    value = getattr(result, "metrics", None)
    return dict(value) if isinstance(value, dict) else {}


def _failure_payload(exc: BaseException) -> dict[str, object]:
    info = error_info(exc)
    return {
        "type": type(exc).__name__,
        "message": str(exc),
        "code": info["code"],
        "category": info["category"],
        "retryable": info["retryable"],
        "hint": info["hint"],
    }
