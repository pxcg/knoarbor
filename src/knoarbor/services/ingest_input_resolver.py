from __future__ import annotations

from pathlib import Path

from knoarbor.connectors.base import ConnectorConfig
from knoarbor.connectors.markdown import MarkdownConnector
from knoarbor.connectors.selection import selected_connector_configs
from knoarbor.core.config import KnoArborConfig
from knoarbor.core.errors import UserInputError
from knoarbor.core.schemas.ingest_run import UnifiedIngestRequest
from knoarbor.core.schemas.sources import SourceDocument
from knoarbor.document_processing import DocumentProcessingPipeline
from knoarbor.pipelines.source import SourcePipeline
from knoarbor.storage.ingest_inputs import InputGeneration, write_input_generation


class IngestInputResolver:
    """Resolve every source into immutable normalized documents before admission."""

    def __init__(
        self,
        *,
        source_pipeline: SourcePipeline | None = None,
        document_processing: DocumentProcessingPipeline | None = None,
    ) -> None:
        self.source_pipeline = source_pipeline or SourcePipeline()
        self.document_processing = document_processing or DocumentProcessingPipeline()

    def resolve(self, request: UnifiedIngestRequest, config: KnoArborConfig) -> InputGeneration:
        documents = []
        failures: list[dict[str, object]] = []
        processing: dict[str, object] = {}
        if request.kind == "document":
            documents = [request.to_document_request().source_document]
        elif request.kind == "excerpt":
            documents = [request.to_excerpt_request().source_document]
        elif request.kind == "file":
            input_path = Path(str(request.input_path)).expanduser().resolve()
            markdown_path, result = self.document_processing.prepare_input_file(config, input_path)
            documents = self._markdown_documents([markdown_path], source_root=input_path.parent)
            processing = result.model_dump(mode="json")
        elif request.kind == "folder":
            input_path = Path(str(request.input_path)).expanduser().resolve()
            markdown_paths, result = self.document_processing.prepare_input_folder(
                config,
                input_path,
                recursive=request.recursive,
                markdown_only=set(request.connector_names or []) == {"markdown"},
            )
            documents = self._markdown_documents(markdown_paths, source_root=input_path)
            processing = result.model_dump(mode="json")
        elif request.kind == "connectors":
            for name, connector_config in selected_connector_configs(config, request.connector_names).items():
                result = self.source_pipeline.run(name, connector_config)
                documents.extend(item.document for item in result.items)
                failures.extend(failure.model_dump(mode="json") for failure in result.failures)
        else:
            raise UserInputError(f"Input resolution does not support request kind: {request.kind}")
        if not documents and not failures:
            raise UserInputError("Ingest input resolution produced no source documents.")
        return write_input_generation(
            config.vault.path,
            documents=documents,
            failures=failures,
            metadata={"request_kind": request.kind, "document_processing": processing},
        )

    def _markdown_documents(self, paths: list[Path], *, source_root: Path) -> list[SourceDocument]:
        if not paths:
            raise UserInputError("Ingest input resolution produced no Markdown documents.")
        connector = MarkdownConnector()
        config = ConnectorConfig(
            enabled=True,
            settings={
                "roots": [str(path.expanduser().resolve()) for path in paths],
                "source_root": str(source_root.expanduser().resolve()),
                "pattern": "*",
                "recursive": False,
            },
        )
        documents = []
        for ref in connector.discover(config):
            documents.append(connector.to_document(connector.fetch(ref, config), config))
        return documents
