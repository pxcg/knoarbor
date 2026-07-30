from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from knoarbor.core.errors import error_info
from knoarbor.core.schemas.run_monitor import RunEvent, RunProgress, RunStatus
from knoarbor.runtime.events import RunEventType
from knoarbor.runtime.run_monitor import RunMonitor, current_run_monitor


@dataclass(frozen=True)
class RunReporter:
    """Typed reporting facade over the current run monitor.

    Pipelines own workflow behavior; this facade owns event vocabulary and
    repetitive monitor calls. It is intentionally optional so core code remains
    usable outside a monitored run.
    """

    monitor: RunMonitor | None

    @classmethod
    def current(cls) -> RunReporter:
        return cls(current_run_monitor())

    def event(
        self,
        event_type: RunEventType,
        *,
        message: str = "",
        status: RunStatus | None = None,
        stage: str | None = None,
        current_item: str | None = None,
        progress: dict[str, Any] | RunProgress | None = None,
        metrics: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> RunEvent | None:
        if not self.monitor:
            return None
        return self.monitor.event(
            event_type,
            message=message,
            status=status,
            stage=stage,
            current_item=current_item,
            progress=progress,
            metrics=metrics,
            payload=payload,
        )

    def raise_if_cancelled(self) -> None:
        if self.monitor:
            self.monitor.raise_if_cancelled()

    def model_call_started(self, *, contract_name: str, schema_version: str, attempt: int, max_attempts: int) -> None:
        self.event(
            "model_call_started",
            status="waiting_model",
            stage="waiting_model",
            current_item=contract_name,
            message=f"Calling model for {contract_name}.",
            payload={
                "contract_name": contract_name,
                "schema_version": schema_version,
                "attempt": attempt,
                "max_attempts": max_attempts,
            },
        )
        self.raise_if_cancelled()

    def model_admission_waiting(self, *, contract_name: str, reason: str, wait_seconds: float, provider_key: str) -> None:
        self.event(
            "provider_admission_waiting",
            status="waiting_model",
            stage="waiting_model",
            current_item=contract_name,
            message=f"Waiting for model admission: {reason}.",
            payload={"reason": reason, "wait_seconds": round(wait_seconds, 3), "provider_key": provider_key},
        )
        self.raise_if_cancelled()

    def model_call_finished(
        self,
        *,
        contract_name: str,
        provider: str,
        model: str,
        usage: dict[str, int],
        elapsed_seconds: float,
        tokens_per_second: float | None,
    ) -> None:
        self.event(
            "model_call_finished",
            status="running",
            stage="semantic",
            current_item=contract_name,
            message=f"Model call finished for {contract_name}.",
            metrics={
                "last_model_elapsed_seconds": elapsed_seconds,
                "last_model_total_tokens": usage.get("total_tokens", 0),
                "last_model_prompt_cached_tokens": usage.get("prompt_cached_tokens", 0),
                "last_model_prompt_cache_hit_tokens": usage.get("prompt_cache_hit_tokens", 0),
                "last_model_prompt_cache_miss_tokens": usage.get("prompt_cache_miss_tokens", 0),
                "last_model_tokens_per_second": tokens_per_second,
            },
            payload={"contract_name": contract_name, "provider": provider, "model": model, "usage": usage},
        )
        self.raise_if_cancelled()

    def model_call_failed(
        self,
        *,
        contract_name: str,
        schema_version: str,
        attempt: int,
        max_attempts: int,
        error: Exception,
        elapsed_seconds: float,
    ) -> None:
        self.event(
            "model_call_failed",
            status="running",
            stage="semantic",
            current_item=contract_name,
            message=f"Model call failed for {contract_name}: {type(error).__name__}.",
            metrics={
                "last_model_elapsed_seconds": elapsed_seconds,
                "last_model_total_tokens": 0,
                "last_model_tokens_per_second": None,
            },
            payload={
                "contract_name": contract_name,
                "schema_version": schema_version,
                "attempt": attempt,
                "max_attempts": max_attempts,
                "error_type": type(error).__name__,
                "error_message": str(error),
                "error": _public_error_info(error),
            },
        )
        self.raise_if_cancelled()

    def model_output_invalid(
        self,
        *,
        contract_name: str,
        schema_version: str,
        attempt: int,
        max_attempts: int,
        error: Exception,
    ) -> None:
        self.event(
            "model_output_invalid",
            status="running",
            stage="semantic",
            current_item=contract_name,
            message=f"Model output failed contract validation for {contract_name}.",
            payload={
                "contract_name": contract_name,
                "schema_version": schema_version,
                "attempt": attempt,
                "max_attempts": max_attempts,
                "error_type": type(error).__name__,
                "error_message": str(error),
                "error": _public_error_info(error),
            },
        )
        self.raise_if_cancelled()

    def model_call_retrying(
        self,
        *,
        contract_name: str,
        schema_version: str,
        attempt: int,
        max_attempts: int,
        previous_error: Exception,
        backoff_seconds: float,
    ) -> None:
        self.event(
            "model_call_retrying",
            status="running",
            stage="semantic",
            current_item=contract_name,
            message=f"Retrying model call for {contract_name} after {type(previous_error).__name__}.",
            payload={
                "contract_name": contract_name,
                "schema_version": schema_version,
                "attempt": attempt,
                "max_attempts": max_attempts,
                "previous_error_type": type(previous_error).__name__,
                "previous_error_message": str(previous_error),
                "previous_error": _public_error_info(previous_error),
                "backoff_seconds": backoff_seconds,
            },
        )
        self.raise_if_cancelled()


def _public_error_info(exc: BaseException) -> dict[str, object]:
    info = error_info(exc)
    info.pop("http_status", None)
    return info
