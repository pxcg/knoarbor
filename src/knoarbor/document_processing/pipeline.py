from __future__ import annotations

from pathlib import Path

from knoarbor.core.config import KnoArborConfig
from knoarbor.core.errors import DocumentPreprocessorUnavailable, SourceNotFound
from knoarbor.document_processing.mineru import MinerUDocumentProcessor
from knoarbor.document_processing.schemas import DocumentProcessingItem, DocumentProcessingResult


class DocumentProcessingPipeline:
    """Runs deterministic document processors before source connectors."""

    def __init__(self, *, mineru: MinerUDocumentProcessor | None = None) -> None:
        self.mineru = mineru or MinerUDocumentProcessor()

    def run(self, config: KnoArborConfig) -> DocumentProcessingResult:
        items: list[DocumentProcessingItem] = []
        if config.document_processing.mineru.enabled:
            items.extend(self.mineru.run(config.document_processing.mineru))
        return DocumentProcessingResult(
            items=items,
            stats={
                "item_count": len(items),
                "processed_count": sum(1 for item in items if item.status == "processed"),
                "skipped_count": sum(1 for item in items if item.status == "skipped"),
                "failed_count": sum(1 for item in items if item.status == "failed"),
            },
        )

    def prepare_input_file(self, config: KnoArborConfig, input_path: Path) -> tuple[Path, DocumentProcessingResult]:
        path = input_path.expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise SourceNotFound(f"Ingest input file does not exist: {path}")
        if is_markdown_file(path):
            return path, DocumentProcessingResult(stats={"item_count": 0, "processed_count": 0, "skipped_count": 0, "failed_count": 0})

        item = self.mineru.process_file(config.document_processing.mineru, path)
        if item.status != "processed" or not item.output_path:
            raise DocumentPreprocessorUnavailable(f"Document preprocessing failed for {path}: {item.reason}")
        return Path(item.output_path).expanduser().resolve(), DocumentProcessingResult(
            items=[item],
            stats={"item_count": 1, "processed_count": 1, "skipped_count": 0, "failed_count": 0},
        )


def is_markdown_file(path: Path) -> bool:
    return path.suffix.lower() in {".md", ".markdown"}
