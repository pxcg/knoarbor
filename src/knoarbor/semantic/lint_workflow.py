from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from knoarbor.core.schemas.lint_candidates import MaintenanceCandidates
from knoarbor.core.schemas.lint_review import LintMaintenanceReview
from knoarbor.core.schemas.wiki_draft_batch import WikiDraftBatch
from knoarbor.semantic.runner import SemanticRunner


class LintSemanticWorkflow:
    """Run lint semantic model steps without scanning or writing the vault."""

    def __init__(self, runner: SemanticRunner) -> None:
        self.runner = runner

    def diagnose_structural(
        self,
        scan_payload: dict[str, Any],
        *,
        max_tokens: int | None = None,
    ) -> MaintenanceCandidates:
        result = self.runner.run("lint_diagnose", scan_payload, max_tokens=max_tokens)
        return _expect_output(result.output, MaintenanceCandidates)

    def diagnose_quality(
        self,
        quality_payload: dict[str, Any],
        *,
        max_tokens: int | None = None,
    ) -> MaintenanceCandidates:
        result = self.runner.run("lint_quality_diagnose", quality_payload, max_tokens=max_tokens)
        return _expect_output(result.output, MaintenanceCandidates)

    def review(
        self,
        review_payload: dict[str, Any],
        *,
        max_tokens: int | None = None,
    ) -> LintMaintenanceReview:
        result = self.runner.run("lint_maintenance_review", review_payload, max_tokens=max_tokens)
        return _expect_output(result.output, LintMaintenanceReview)

    def compile_drafts(
        self,
        draft_payload: dict[str, Any],
        *,
        max_tokens: int | None = None,
    ) -> WikiDraftBatch:
        result = self.runner.run("lint_draft_compile", draft_payload, max_tokens=max_tokens)
        draft_batch = _expect_output(result.output, WikiDraftBatch)
        return _with_runtime_model_metadata(draft_batch, provider=result.provider, model=result.model)


def _expect_output(value: BaseModel, expected_type: type[Any]) -> Any:
    if not isinstance(value, expected_type):
        raise TypeError(f"Expected {expected_type.__name__}, got {type(value).__name__}")
    return value


def _with_runtime_model_metadata(batch: WikiDraftBatch, *, provider: str, model: str) -> WikiDraftBatch:
    """Model identity is runtime metadata, not an LLM-authored page fact."""
    for draft in batch.drafts:
        draft.model_provider = provider
        draft.model_name = model
    return batch
