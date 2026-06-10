from __future__ import annotations

from pathlib import Path

from knoarbor.core.schemas.wiki_lint import (
    LintRunRequest,
    LintRunResult,
    WikiLintCandidateSelectRequest,
    WikiLintCandidateSelectResponse,
    WikiLintRequest,
    WikiLintResponse,
    WikiScanRequest,
    WikiScanResponse,
)
from knoarbor.core.config import default_config_path, load_config
from knoarbor.core.errors import UserInputError
from knoarbor.core.vaults import select_config_vault
from knoarbor.audit.run_failure import write_run_failure_artifacts
from knoarbor.pipelines import WikiLintPipeline
from knoarbor.pipelines.lint import normalize_lint_run_mode
from knoarbor.runtime import configure_runtime_logging, current_run_monitor, runtime_logger
from knoarbor.semantic import build_lint_semantic_workflow

logger = runtime_logger(__name__)


class WikiLinterService:
    """API adapter for deterministic and semantic lint maintenance."""

    def __init__(self, pipeline: WikiLintPipeline | None = None) -> None:
        self.pipeline = pipeline or WikiLintPipeline()

    def scan(self, request: WikiScanRequest) -> WikiScanResponse:
        return self._pipeline_for_request(None).scan(request)

    def select_candidates(self, request: WikiLintCandidateSelectRequest) -> WikiLintCandidateSelectResponse:
        return self._pipeline_for_request(None).select_candidates(request)

    def lint(self, request: WikiLintRequest) -> WikiLintResponse:
        return self._pipeline_for_request(None).lint(request)

    def run_maintenance(self, request: LintRunRequest) -> LintRunResult:
        mode = normalize_lint_run_mode(request.mode)
        request = request.model_copy(update={"mode": mode})
        try:
            config = load_config(request.config_path or default_config_path())
            config = select_config_vault(config, vault_path=request.obsidian_vault_path, vault_id=request.vault_id)
            request = request.model_copy(update={"obsidian_vault_path": str(config.vault.path)})
            configure_runtime_logging(config.vault.path)
            if mode == "deterministic":
                return WikiLintPipeline(privacy_config=config.privacy).run_maintenance(request)
            try:
                semantic = build_lint_semantic_workflow(config, request.provider)
            except UserInputError:
                if mode != "semantic_structural":
                    raise
                semantic = None
            semantic_pipeline = WikiLintPipeline(semantic, privacy_config=config.privacy)
            request_with_defaults = request.model_copy(
                update={"max_tokens": config.models.resolve_max_tokens(request.provider, request.max_tokens)}
            )
            return semantic_pipeline.run_maintenance(request_with_defaults)
        except Exception as exc:
            self._write_failure_artifacts(request, exc)
            raise

    def _pipeline_for_request(self, config_path: str | None) -> WikiLintPipeline:
        try:
            config = load_config(config_path or default_config_path())
        except Exception:
            return self.pipeline
        return WikiLintPipeline(privacy_config=config.privacy)

    def _write_failure_artifacts(self, request: LintRunRequest, exc: BaseException) -> None:
        if not request.write_report and not request.append_ledger:
            return
        try:
            if request.obsidian_vault_path:
                vault_path = Path(request.obsidian_vault_path).expanduser().resolve()
            else:
                config = load_config(request.config_path or default_config_path())
                vault_path = select_config_vault(config, vault_id=request.vault_id).vault.path
            monitor = current_run_monitor()
            write_run_failure_artifacts(
                vault_path,
                flow="lint",
                request=request,
                exc=exc,
                run_id=monitor.run_id if monitor else None,
                stage=monitor.read().stage if monitor else None,
                append_ledger=request.append_ledger,
                write_report=request.write_report,
                report_path=request.report_path,
                ledger_path=request.ledger_path,
            )
        except Exception as report_exc:
            logger.exception("lint_failure_report_write_failed error=%s original_error=%s", report_exc, exc)
