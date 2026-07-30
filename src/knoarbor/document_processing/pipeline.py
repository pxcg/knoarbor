from __future__ import annotations

from pathlib import Path
from fnmatch import fnmatch
from concurrent.futures import ThreadPoolExecutor, as_completed

from knoarbor.core.config import KnoArborConfig
from knoarbor.core.errors import DocumentPreprocessorUnavailable, SourceNotFound
from knoarbor.document_processing.mineru import MinerUDocumentProcessor, mineru_max_concurrent_requests
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

    def prepare_input_folder(
        self,
        config: KnoArborConfig,
        input_path: Path,
        *,
        recursive: bool = True,
        markdown_only: bool = False,
    ) -> tuple[list[Path], DocumentProcessingResult]:
        root = input_path.expanduser().resolve()
        if not root.exists() or not root.is_dir():
            raise SourceNotFound(f"Ingest input folder does not exist: {root}")

        files = _discover_folder_files(root, recursive=recursive)
        markdown_paths = [path for path in files if is_markdown_file(path)]
        if markdown_only:
            return sorted(set(markdown_paths)), _empty_processing_result()

        rich_files = [
            path
            for path in files
            if not is_markdown_file(path) and _matches_any_pattern(path, config.document_processing.mineru.patterns)
        ]
        if not rich_files:
            return markdown_paths, _empty_processing_result()

        if not config.document_processing.mineru.enabled:
            raise DocumentPreprocessorUnavailable(
                f"Folder contains {len(rich_files)} non-Markdown file(s), but MinerU preprocessing is not enabled."
            )

        mineru_config = config.document_processing.mineru
        capacity = min(
            len(rich_files),
            mineru_max_concurrent_requests(str(mineru_config.endpoint), headers=mineru_config.headers),
        )
        items_by_path: dict[Path, DocumentProcessingItem] = {}
        with ThreadPoolExecutor(max_workers=capacity) as executor:
            futures = {
                executor.submit(self.mineru.process_file, mineru_config, path, input_root=root): path
                for path in rich_files
            }
            for future in as_completed(futures):
                path = futures[future]
                try:
                    items_by_path[path] = future.result()
                except Exception as exc:
                    items_by_path[path] = DocumentProcessingItem(
                        adapter=self.mineru.name,
                        input_path=str(path),
                        status="failed",
                        reason="Document preprocessing failed.",
                        error_type=type(exc).__name__,
                        error_message=str(exc),
                    )
        items = [items_by_path[path] for path in rich_files]
        for item in items:
            if item.status == "processed" and item.output_path:
                markdown_paths.append(Path(item.output_path).expanduser().resolve())

        failed_count = sum(1 for item in items if item.status == "failed")
        if failed_count:
            raise DocumentPreprocessorUnavailable(f"Document preprocessing failed for {failed_count} file(s) in folder: {root}")
        return sorted(set(markdown_paths)), DocumentProcessingResult(
            items=items,
            stats={
                "item_count": len(items),
                "processed_count": sum(1 for item in items if item.status == "processed"),
                "skipped_count": sum(1 for item in items if item.status == "skipped"),
                "failed_count": failed_count,
            },
        )


def is_markdown_file(path: Path) -> bool:
    return path.suffix.lower() in {".md", ".markdown"}


def _empty_processing_result() -> DocumentProcessingResult:
    return DocumentProcessingResult(stats={"item_count": 0, "processed_count": 0, "skipped_count": 0, "failed_count": 0})


def _discover_folder_files(root: Path, *, recursive: bool) -> list[Path]:
    iterator = root.rglob("*") if recursive else root.glob("*")
    return sorted(path for path in iterator if path.is_file() and not _is_hidden_path(root, path))


def _is_hidden_path(root: Path, path: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    return any(part.startswith(".") for part in relative.parts)


def _matches_any_pattern(path: Path, patterns: list[str]) -> bool:
    if not patterns:
        return False
    name = path.name
    return any(fnmatch(name, pattern) for pattern in patterns)
