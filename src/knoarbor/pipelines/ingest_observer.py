from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from knoarbor.runtime import RunReporter


IngestObservationStep = Literal[
    "input",
    "segment",
    "normalize_agent",
    "atom_agent",
    "retrieval",
    "plan_agent",
    "draft_agent",
    "review_agent",
    "write_gate",
    "write",
]


@dataclass(frozen=True)
class IngestObserver:
    """Ingest-specific observation facade over the generic run reporter."""

    reporter: RunReporter

    @classmethod
    def current(cls) -> IngestObserver:
        return cls(RunReporter.current())

    def started(
        self,
        step: IngestObservationStep,
        *,
        message: str,
        current_item: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.reporter.event(
            "ingest_step_started",
            status=_step_status(step),
            stage=step,
            current_item=current_item,
            message=message,
            payload=_payload(step, payload),
        )
        self.reporter.raise_if_cancelled()

    def finished(
        self,
        step: IngestObservationStep,
        *,
        message: str,
        current_item: str | None = None,
        metrics: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.reporter.event(
            "ingest_step_finished",
            status="running",
            stage=step,
            current_item=current_item,
            message=message,
            metrics=metrics,
            payload=_payload(step, payload),
        )
        self.reporter.raise_if_cancelled()

    def skipped(
        self,
        step: IngestObservationStep,
        *,
        message: str,
        current_item: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.reporter.event(
            "ingest_step_skipped",
            status="running",
            stage=step,
            current_item=current_item,
            message=message,
            payload=_payload(step, payload),
        )
        self.reporter.raise_if_cancelled()


def _payload(step: IngestObservationStep, payload: dict[str, Any] | None) -> dict[str, Any]:
    return {"ingest_step": step, **(payload or {})}


def _step_status(step: IngestObservationStep) -> str:
    if step == "write":
        return "writing"
    return "running"
