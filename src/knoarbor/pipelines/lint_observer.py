from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from knoarbor.runtime import RunReporter


LINT_OBSERVATION_STEPS = (
    "scan",
    "diagnose",
    "review",
    "execute",
    "verify",
    "report",
)

LINT_OBSERVATION_EVENT_TYPES = (
    "lint_step_started",
    "lint_step_finished",
    "lint_step_skipped",
)

LintObservationStep = Literal[
    "scan",
    "diagnose",
    "review",
    "execute",
    "verify",
    "report",
]


@dataclass(frozen=True)
class LintObserver:
    """Lint-specific observation facade over the generic run reporter."""

    reporter: RunReporter

    @classmethod
    def current(cls) -> LintObserver:
        return cls(RunReporter.current())

    def started(
        self,
        step: LintObservationStep,
        *,
        message: str,
        current_item: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.reporter.event(
            "lint_step_started",
            status=_step_status(step),
            stage=step,
            current_item=current_item,
            message=message,
            payload=_payload(step, payload),
        )
        self.reporter.raise_if_cancelled()

    def finished(
        self,
        step: LintObservationStep,
        *,
        message: str,
        current_item: str | None = None,
        metrics: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.reporter.event(
            "lint_step_finished",
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
        step: LintObservationStep,
        *,
        message: str,
        current_item: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.reporter.event(
            "lint_step_skipped",
            status="running",
            stage=step,
            current_item=current_item,
            message=message,
            payload=_payload(step, payload),
        )
        self.reporter.raise_if_cancelled()


def _payload(step: LintObservationStep, payload: dict[str, Any] | None) -> dict[str, Any]:
    return {"lint_step": step, **(payload or {})}


def _step_status(step: LintObservationStep) -> str:
    if step == "execute":
        return "writing"
    return "running"
