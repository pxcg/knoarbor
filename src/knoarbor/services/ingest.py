from __future__ import annotations

from knoarbor.core.config import KnoArborConfig
from knoarbor.core.schemas.ingest_execution import IngestExecutionCommand, IngestExecutionPort
from knoarbor.core.schemas.ingest_pipeline import IngestPipelineResult
from knoarbor.pipelines.ingest_auto import AutoIngestPipeline, IndexMetadataExtractor
from knoarbor.runtime import configure_runtime_logging
from knoarbor.semantic import build_semantic_runner
from knoarbor.services.ingest_execution import load_execution_config
from knoarbor.storage.ingest_inputs import read_input_generation


class IngestService:
    """Pure executor for an already-admitted immutable ingest command."""

    def run_generation_command(
        self,
        command: IngestExecutionCommand,
        *,
        execution: IngestExecutionPort,
    ) -> IngestPipelineResult:
        config = _load_runtime_config(command)
        generation = read_input_generation(config.vault.path, command.generation_id)
        concurrency = _execution_concurrency(command)
        pipeline = _build_auto_ingest_pipeline(
            config,
            command.provider,
            max_provider_requests=concurrency["max_concurrent_provider_requests"],
        )
        return pipeline.run_generation(
            generation.documents,
            resolver_failures=generation.failures,
            vault_path=config.vault.path,
            write=command.write,
            privacy_config=config.privacy,
            segmentation_config=config.ingest.segmentation,
            max_concurrent_segments=concurrency["max_concurrent_segments"],
            initial_concurrent_segments=concurrency["initial_concurrent_requests"],
            write_report=command.write_report,
            append_ledger=command.append_ledger,
            max_tokens=command.max_tokens,
            execution=execution,
        )

    def validate_generation_command(self, command: IngestExecutionCommand) -> None:
        """Validate the runtime contract before a durable attempt is claimed."""

        _load_runtime_config(command)


def _load_runtime_config(command: IngestExecutionCommand) -> KnoArborConfig:
    config = load_execution_config(command)
    configure_runtime_logging(config.vault.path)
    return config


def _build_auto_ingest_pipeline(
    config: KnoArborConfig,
    provider_name: str | None,
    *,
    max_provider_requests: int,
) -> AutoIngestPipeline:
    return AutoIngestPipeline(
        extractor=IndexMetadataExtractor(
            build_semantic_runner(config, provider_name),
            max_provider_requests=max_provider_requests,
            vault_path=config.vault.path,
        )
    )


def _execution_concurrency(command: IngestExecutionCommand) -> dict[str, int]:
    ingest = command.execution_contract.get("ingest")
    ingest_payload = ingest if isinstance(ingest, dict) else {}
    concurrency = ingest_payload.get("concurrency")
    payload = concurrency if isinstance(concurrency, dict) else {}
    ceiling = max(1, int(payload.get("max_concurrent_segments") or 1))
    provider_ceiling = max(1, int(payload.get("max_concurrent_provider_requests") or ceiling))
    initial = max(1, min(int(payload.get("initial_concurrent_requests") or 1), ceiling, provider_ceiling))
    return {
        "initial_concurrent_requests": initial,
        "max_concurrent_segments": min(ceiling, provider_ceiling),
        "max_concurrent_provider_requests": provider_ceiling,
    }
