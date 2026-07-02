from __future__ import annotations

from knoarbor.core.schemas.wiki_lint import (
    LintRunRequest,
    LintRunResult,
)
from knoarbor.core.config import default_config_path, load_config
from knoarbor.core.vaults import select_config_vault
from knoarbor.pipelines import WikiLintPipeline
from knoarbor.runtime import configure_runtime_logging, runtime_logger
from knoarbor.semantic import build_lint_semantic_workflow
from knoarbor.services.workflow_failures import write_workflow_failure_artifacts

logger = runtime_logger(__name__)


class WikiLinterService:
    """API adapter for deterministic and semantic lint maintenance."""

    def run_maintenance(self, request: LintRunRequest) -> LintRunResult:
        try:
            config = load_config(request.config_path or default_config_path())
            config = select_config_vault(config, vault_path=request.vault_path, vault_id=request.vault_id)
            request = request.model_copy(update={"vault_path": str(config.vault.path)})
            configure_runtime_logging(config.vault.path)
            if request.mode == "deterministic":
                return WikiLintPipeline(privacy_config=config.privacy).run_maintenance(request)
            semantic = build_lint_semantic_workflow(config, request.provider)
            semantic_pipeline = WikiLintPipeline(semantic, privacy_config=config.privacy)
            request_with_defaults = request.model_copy(
                update={"max_tokens": config.models.resolve_max_tokens(request.provider, request.max_tokens)}
            )
            return semantic_pipeline.run_maintenance(request_with_defaults)
        except Exception as exc:
            self._write_failure_artifacts(request, exc)
            raise

    def _write_failure_artifacts(self, request: LintRunRequest, exc: BaseException) -> None:
        write_workflow_failure_artifacts(flow="lint", request=request, exc=exc, logger=logger)
