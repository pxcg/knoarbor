from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.core.config import KnoArborConfig, MinerUDocumentProcessingConfig
from knoarbor.core.errors import DocumentPreprocessorUnavailable
from knoarbor.document_processing.mineru import MinerUDocumentProcessor, MinerUResponse
from knoarbor.document_processing.pipeline import DocumentProcessingPipeline


class FakeMinerUProcessor(MinerUDocumentProcessor):
    def _post(self, config: MinerUDocumentProcessingConfig, path: Path, output_dir: Path) -> MinerUResponse:
        return MinerUResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            body=b'{"markdown":"# Parsed\\n\\nBody."}',
        )


class FakeNativeMinerUProcessor(MinerUDocumentProcessor):
    def _post(self, config: MinerUDocumentProcessingConfig, path: Path, output_dir: Path) -> MinerUResponse:
        return MinerUResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            body=b'{"results":{"paper.pdf":{"md_content":"# Native MinerU\\n\\nBody."}}}',
        )


class DocumentProcessingTests(unittest.TestCase):
    def test_pipeline_noops_when_mineru_is_disabled(self) -> None:
        config = KnoArborConfig.model_validate({"vault": {"path": "./vaults/all"}})

        result = DocumentProcessingPipeline().run(config)

        self.assertEqual(result.stats["item_count"], 0)
        self.assertEqual(result.items, [])

    def test_mineru_processor_materializes_markdown_from_service_response(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            input_dir = root / "documents"
            output_dir = root / "markdown"
            input_dir.mkdir()
            (input_dir / "paper.pdf").write_bytes(b"%PDF")
            config = KnoArborConfig.model_validate(
                {
                    "vault": {"path": str(root / "vaults" / "all")},
                    "document_processing": {
                        "mineru": {
                            "enabled": True,
                            "endpoint": "http://localhost:9999/parse",
                            "input_dir": str(input_dir),
                            "output_dir": str(output_dir),
                        }
                    },
                }
            )

            result = DocumentProcessingPipeline(mineru=FakeMinerUProcessor()).run(config)

            self.assertEqual(result.stats["processed_count"], 1)
            self.assertEqual(result.items[0].status, "processed")
            self.assertTrue(result.items[0].output_path.endswith("paper.md"))
            self.assertIn("# Parsed", Path(result.items[0].output_path or "").read_text(encoding="utf-8"))

    def test_mineru_processor_reads_native_results_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            path = root / "paper.pdf"
            output_dir = root / "markdown"
            path.write_bytes(b"%PDF")
            config = KnoArborConfig.model_validate(
                {
                    "vault": {"path": str(root / "vaults" / "all")},
                    "document_processing": {
                        "mineru": {
                            "enabled": True,
                            "endpoint": "http://localhost:9999/file_parse",
                            "output_dir": str(output_dir),
                        }
                    },
                }
            )

            prepared, result = DocumentProcessingPipeline(mineru=FakeNativeMinerUProcessor()).prepare_input_file(config, path)

            self.assertEqual(result.stats["processed_count"], 1)
            self.assertEqual(prepared, (output_dir / "paper.md").resolve())
            self.assertIn("# Native MinerU", prepared.read_text(encoding="utf-8"))

    def test_mineru_defaults_match_native_file_parse_contract(self) -> None:
        config = MinerUDocumentProcessingConfig()

        self.assertEqual(config.file_field, "files")
        self.assertIsNone(config.output_dir_field)
        self.assertEqual(config.mode_field, "parse_method")
        self.assertEqual(config.extra_fields["backend"], "pipeline")
        self.assertTrue(config.extra_fields["return_md"])

    def test_prepare_input_file_passes_markdown_through(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "note.markdown"
            path.write_text("# Note\n\nBody.", encoding="utf-8")
            config = KnoArborConfig.model_validate({"vault": {"path": str(Path(tmp_dir) / "vaults" / "all")}})

            prepared, result = DocumentProcessingPipeline().prepare_input_file(config, path)

        self.assertEqual(prepared, path.resolve())
        self.assertEqual(result.stats["item_count"], 0)

    def test_prepare_input_file_requires_mineru_for_non_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "paper.pdf"
            path.write_bytes(b"%PDF")
            config = KnoArborConfig.model_validate({"vault": {"path": str(Path(tmp_dir) / "vaults" / "all")}})

            with self.assertRaisesRegex(ValueError, "document_processing.mineru.enabled is false"):
                DocumentProcessingPipeline().prepare_input_file(config, path)

    def test_prepare_input_file_processes_non_markdown_with_mineru(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            path = root / "paper.pdf"
            output_dir = root / "markdown"
            path.write_bytes(b"%PDF")
            config = KnoArborConfig.model_validate(
                {
                    "vault": {"path": str(root / "vaults" / "all")},
                    "document_processing": {
                        "mineru": {
                            "enabled": True,
                            "endpoint": "http://localhost:9999/parse",
                            "output_dir": str(output_dir),
                        }
                    },
                }
            )

            prepared, result = DocumentProcessingPipeline(mineru=FakeMinerUProcessor()).prepare_input_file(config, path)

            self.assertEqual(result.stats["processed_count"], 1)
            self.assertEqual(prepared, (output_dir / "paper.md").resolve())
            self.assertIn("# Parsed", prepared.read_text(encoding="utf-8"))

    def test_prepare_input_folder_passes_markdown_files_through(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            folder = root / "notes"
            nested = folder / "nested"
            nested.mkdir(parents=True)
            note = folder / "a.md"
            nested_note = nested / "b.markdown"
            hidden_note = folder / ".hidden.md"
            note.write_text("# A\n", encoding="utf-8")
            nested_note.write_text("# B\n", encoding="utf-8")
            hidden_note.write_text("# Hidden\n", encoding="utf-8")
            config = KnoArborConfig.model_validate({"vault": {"path": str(root / "vaults" / "all")}})

            prepared, result = DocumentProcessingPipeline().prepare_input_folder(config, folder)

        self.assertEqual(prepared, sorted([note.resolve(), nested_note.resolve()]))
        self.assertEqual(result.stats["item_count"], 0)

    def test_prepare_input_folder_requires_mineru_for_non_markdown_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            folder = root / "docs"
            folder.mkdir()
            (folder / "paper.pdf").write_bytes(b"%PDF")
            config = KnoArborConfig.model_validate({"vault": {"path": str(root / "vaults" / "all")}})

            with self.assertRaises(DocumentPreprocessorUnavailable):
                DocumentProcessingPipeline().prepare_input_folder(config, folder)

    def test_prepare_input_folder_processes_rich_files_with_mineru(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            folder = root / "docs"
            output_dir = root / "markdown"
            folder.mkdir()
            markdown = folder / "note.md"
            markdown.write_text("# Note\n", encoding="utf-8")
            (folder / "paper.pdf").write_bytes(b"%PDF")
            config = KnoArborConfig.model_validate(
                {
                    "vault": {"path": str(root / "vaults" / "all")},
                    "document_processing": {
                        "mineru": {
                            "enabled": True,
                            "endpoint": "http://localhost:9999/parse",
                            "output_dir": str(output_dir),
                        }
                    },
                }
            )

            prepared, result = DocumentProcessingPipeline(mineru=FakeMinerUProcessor()).prepare_input_folder(config, folder)

            self.assertEqual(result.stats["processed_count"], 1)
            self.assertEqual(prepared, sorted([markdown.resolve(), (output_dir / "paper.md").resolve()]))

    def test_enabled_mineru_requires_endpoint(self) -> None:
        config = KnoArborConfig.model_validate(
            {
                "vault": {"path": "./vaults/all"},
                "document_processing": {"mineru": {"enabled": True, "input_dir": "./docs"}},
            }
        )

        with self.assertRaisesRegex(ValueError, "endpoint is required"):
            DocumentProcessingPipeline().run(config)


if __name__ == "__main__":
    unittest.main()
