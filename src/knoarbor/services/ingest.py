from __future__ import annotations

from pathlib import Path

from knoarbor.connectors.base import ConnectorConfig
from knoarbor.core.config import KnoArborConfig, default_config_path, load_config
from knoarbor.core.schemas.ingest_run import IngestDocumentRunRequest, IngestFileRunRequest, IngestRunRequest, UnifiedIngestRequest
from knoarbor.audit.run_failure import write_run_failure_artifacts
from knoarbor.document_processing import DocumentProcessingPipeline
from knoarbor.pipelines import IngestContextProvider, IngestPipeline, IngestPipelineResult, IngestSourceResult
from knoarbor.runtime import configure_runtime_logging, current_run_monitor, runtime_logger
from knoarbor.semantic import build_ingest_semantic_workflow

logger = runtime_logger(__name__)


class IngestService:
    """Runs the high-level ingest pipeline for API callers."""

    def run_unified(self, request: UnifiedIngestRequest) -> IngestPipelineResult | IngestSourceResult:
        if request.kind == "document":
            return self.run_document(request.to_document_request())
        if request.kind == "file":
            return self.run_file(request.to_file_request())
        return self.run(request.to_connectors_request())

    def run(self, request: IngestRunRequest) -> IngestPipelineResult:
        config: KnoArborConfig | None = None
        try:
            config = _load_runtime_config(request.config_path)
            pipeline = _build_ingest_pipeline(config, request.provider)
            return pipeline.run(
                config,
                connector_names=request.connector_names,
                write=request.write,
                max_tokens=request.max_tokens or config.models.default_max_tokens,
                write_report=request.write_report,
                append_ledger=request.append_ledger,
            )
        except Exception as exc:
            _write_failure_artifacts(request, exc, config=config)
            raise

    def run_document(self, request: IngestDocumentRunRequest) -> IngestSourceResult:
        config: KnoArborConfig | None = None
        try:
            config = _load_runtime_config(request.config_path)
            vault_path = Path(request.obsidian_vault_path).expanduser().resolve() if request.obsidian_vault_path else config.vault.path
            pipeline = _build_ingest_pipeline(config, request.provider)
            return pipeline.run_document(
                request.source_document,
                vault_path=vault_path,
                write=request.write,
                max_tokens=request.max_tokens or config.models.default_max_tokens,
                privacy_config=config.privacy,
                write_report=request.write_report,
                append_ledger=request.append_ledger,
                auto_scoped_lint=request.auto_scoped_lint if request.auto_scoped_lint is not None else config.ingest.auto_scoped_lint,
                auto_apply_safe_lint_fixes=(
                    request.auto_apply_safe_lint_fixes
                    if request.auto_apply_safe_lint_fixes is not None
                    else config.ingest.auto_apply_safe_lint_fixes
                ),
                scoped_lint_include_related=(
                    request.scoped_lint_include_related
                    if request.scoped_lint_include_related is not None
                    else config.lint.scoped_include_related
                ),
                segmentation_config=config.ingest.segmentation,
            )
        except Exception as exc:
            explicit_vault = Path(request.obsidian_vault_path).expanduser().resolve() if request.obsidian_vault_path else None
            _write_failure_artifacts(request, exc, config=config, vault_path=explicit_vault)
            raise

    def run_file(self, request: IngestFileRunRequest) -> IngestPipelineResult:
        config: KnoArborConfig | None = None
        try:
            config = _load_runtime_config(request.config_path)
            markdown_path, processing_result = DocumentProcessingPipeline().prepare_input_file(config, Path(request.input_path))
            file_config = _single_markdown_file_config(config, markdown_path)
            pipeline = _build_ingest_pipeline(file_config, request.provider)
            return pipeline.run(
                file_config,
                connector_names=["markdown"],
                write=request.write,
                max_tokens=request.max_tokens or config.models.default_max_tokens,
                write_report=request.write_report,
                append_ledger=request.append_ledger,
                document_processing_result=processing_result,
            )
        except Exception as exc:
            _write_failure_artifacts(request, exc, config=config)
            raise


def _load_runtime_config(config_path: str | None) -> KnoArborConfig:
    config = load_config(config_path or default_config_path())
    configure_runtime_logging(config.vault.path)
    return config


def _build_ingest_pipeline(config: KnoArborConfig, provider_name: str | None) -> IngestPipeline:
    return IngestPipeline(
        build_ingest_semantic_workflow(config, provider_name),
        semantic_workflow_factory=lambda: build_ingest_semantic_workflow(config, provider_name),
        context_provider=IngestContextProvider(
            candidate_limit=config.ingest.candidate_limit,
            materialized_page_limit=config.ingest.materialized_page_limit,
            max_chars_per_page=config.ingest.max_chars_per_materialized_page,
        ),
    )


def _write_failure_artifacts(
    request: IngestRunRequest | IngestDocumentRunRequest | IngestFileRunRequest,
    exc: BaseException,
    *,
    config: KnoArborConfig | None = None,
    vault_path: Path | None = None,
) -> None:
    if not request.write_report and not request.append_ledger:
        return
    effective_vault = vault_path or (config.vault.path if config else None)
    if effective_vault is None:
        logger.info("ingest_failure_report_skipped reason=no_vault_path error=%s", exc)
        return
    try:
        monitor = current_run_monitor()
        write_run_failure_artifacts(
            effective_vault,
            flow="ingest",
            request=request,
            exc=exc,
            run_id=monitor.run_id if monitor else None,
            stage=monitor.read().stage if monitor else None,
            append_ledger=request.append_ledger,
            write_report=request.write_report,
        )
    except Exception as report_exc:
        logger.exception("ingest_failure_report_write_failed error=%s original_error=%s", report_exc, exc)


def _single_markdown_file_config(config: KnoArborConfig, markdown_path: Path) -> KnoArborConfig:
    document_processing = config.document_processing.model_copy(
        update={"mineru": config.document_processing.mineru.model_copy(update={"enabled": False})}
    )
    connectors = {
        "markdown": ConnectorConfig(
            enabled=True,
            settings={
                "roots": [str(markdown_path.expanduser().resolve())],
                "pattern": markdown_path.name,
                "recursive": False,
            },
        )
    }
    return config.model_copy(update={"connectors": connectors, "document_processing": document_processing})
