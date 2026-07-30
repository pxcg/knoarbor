from __future__ import annotations

from knoarbor.core.config import KnoArborConfig
from knoarbor.core.errors import UserInputError
from knoarbor.semantic.lint_workflow import LintSemanticWorkflow
from knoarbor.semantic.llm import ModelGateway
from knoarbor.semantic.runner import SemanticRetryPolicy, SemanticRunner


def build_semantic_runner(config: KnoArborConfig, provider_name: str | None = None) -> SemanticRunner:
    selected_provider = provider_name or config.models.default_provider
    if not selected_provider:
        raise UserInputError("No model provider selected. Set models.default_provider or pass a provider.")
    provider_config = config.models.providers.get(selected_provider)
    if provider_config is None:
        raise UserInputError(f"Unknown model provider: {selected_provider}")
    return SemanticRunner(
        ModelGateway.from_config(
            selected_provider,
            provider_config,
            timeout_seconds=config.models.request_timeout_seconds,
        ),
        retry_policy=SemanticRetryPolicy(
            enabled=config.models.retry.enabled,
            max_attempts=config.models.retry.max_attempts,
            backoff_seconds=config.models.retry.backoff_seconds,
            retry_on_invalid_output=config.models.retry.retry_on_invalid_output,
            retryable_error_codes=frozenset(config.models.retry.retryable_error_codes),
        ),
    )


def build_lint_semantic_workflow(config: KnoArborConfig, provider_name: str | None = None) -> LintSemanticWorkflow:
    return LintSemanticWorkflow(build_semantic_runner(config, provider_name))
