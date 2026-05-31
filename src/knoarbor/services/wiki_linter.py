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
        return self.pipeline.scan(request)

    def select_candidates(self, request: WikiLintCandidateSelectRequest) -> WikiLintCandidateSelectResponse:
        return self.pipeline.select_candidates(request)

    def lint(self, request: WikiLintRequest) -> WikiLintResponse:
        return self.pipeline.lint(request)

    def run_maintenance(self, request: LintRunRequest) -> LintRunResult:
        mode = normalize_lint_run_mode(request.mode)
        request = request.model_copy(update={"mode": mode})
        configure_runtime_logging(Path(request.obsidian_vault_path))
        try:
            if mode == "deterministic":
                return self.pipeline.run_maintenance(request)
            config = load_config(request.config_path or default_config_path())
            configure_runtime_logging(config.vault.path)
            try:
                semantic = build_lint_semantic_workflow(config, request.provider)
            except UserInputError:
                if mode != "semantic_structural":
                    raise
                semantic = None
            semantic_pipeline = WikiLintPipeline(semantic)
            request_with_defaults = request.model_copy(
                update={"max_tokens": request.max_tokens or config.models.default_max_tokens}
            )
            return semantic_pipeline.run_maintenance(request_with_defaults)
        except Exception as exc:
            self._write_failure_artifacts(request, exc)
            raise

    def _write_failure_artifacts(self, request: LintRunRequest, exc: BaseException) -> None:
        if not request.write_report and not request.append_ledger:
            return
        try:
            vault_path = Path(request.obsidian_vault_path).expanduser().resolve()
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
