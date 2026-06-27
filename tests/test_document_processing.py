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


class FakeMinerUImageProcessor(MinerUDocumentProcessor):
    def _post(self, config: MinerUDocumentProcessingConfig, path: Path, output_dir: Path) -> MinerUResponse:
        image_dir = output_dir / "paper" / "images"
        image_dir.mkdir(parents=True)
        (image_dir / "figure-1.png").write_bytes(b"png")
        return MinerUResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            body=b'{"markdown":"# Parsed\\n\\n![architecture](paper/images/figure-1.png)"}',
        )


class FakeNativeMinerUResponseImageProcessor(MinerUDocumentProcessor):
    def _post(self, config: MinerUDocumentProcessingConfig, path: Path, output_dir: Path) -> MinerUResponse:
        return MinerUResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            body=(
                b"{"
                b'"results":{'
                b'"paper":{'
                b'"md_content":"# Parsed\\n\\n![](images/figure-1.png)",'
                b'"images":{"figure-1.png":"data:image/png;base64,iVBORw0KGgo="},'
                b'"content_list":"[{'
                b'\\"type\\":\\"image\\",'
                b'\\"img_path\\":\\"images/figure-1.png\\",'
                b'\\"image_caption\\":[\\"Agent loop diagram\\"],'
                b'\\"content\\":\\"diagram content\\",'
                b'\\"page_idx\\":0'
                b'}]"'
                b"}"
                b"}"
                b"}"
            ),
        )


class FakeNativeMinerUContentOnlyImageProcessor(MinerUDocumentProcessor):
    def _post(self, config: MinerUDocumentProcessingConfig, path: Path, output_dir: Path) -> MinerUResponse:
        return MinerUResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            body=(
                b"{"
                b'"results":{'
                b'"paper":{'
                b'"md_content":"# Parsed\\n\\n![](images/figure-1.png)",'
                b'"images":{"figure-1.png":"data:image/png;base64,iVBORw0KGgo="},'
                b'"content_list":"[{'
                b'\\"type\\":\\"image\\",'
                b'\\"img_path\\":\\"images/figure-1.png\\",'
                b'\\"content\\":\\"```mermaid\\\\ngraph LR\\\\n  A --> B\\\\n```\\",'
                b'\\"sub_type\\":\\"flowchart\\",'
                b'\\"page_idx\\":0'
                b'}]"'
                b"}"
                b"}"
                b"}"
            ),
        )


class CountingMinerUProcessor(FakeMinerUProcessor):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[Path] = []

    def _post(self, config: MinerUDocumentProcessingConfig, path: Path, output_dir: Path) -> MinerUResponse:
        self.calls.append(path)
        return super()._post(config, path, output_dir)


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

    def test_mineru_processor_records_image_attachments(self) -> None:
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

            prepared, result = DocumentProcessingPipeline(mineru=FakeMinerUImageProcessor()).prepare_input_file(config, path)

            self.assertEqual(result.stats["processed_count"], 1)
            self.assertEqual(prepared, (output_dir / "paper.md").resolve())
            self.assertEqual(len(result.items[0].attachments), 1)
            relative_path = str(result.items[0].attachments[0]["relative_path"])
            self.assertTrue(relative_path.startswith("images/paper-figure-1-"))
            self.assertTrue(relative_path.endswith(".png"))
            self.assertIn("](../assets/images/paper-figure-1-", prepared.read_text(encoding="utf-8"))
            sidecar = output_dir / "paper.attachments.json"
            self.assertTrue(sidecar.exists())
            self.assertIn("paper-figure-1-", sidecar.read_text(encoding="utf-8"))

    def test_mineru_processor_materializes_native_response_images(self) -> None:
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

            prepared, result = DocumentProcessingPipeline(mineru=FakeNativeMinerUResponseImageProcessor()).prepare_input_file(config, path)

            self.assertEqual(result.stats["processed_count"], 1)
            self.assertEqual(prepared, (output_dir / "paper.md").resolve())
            self.assertEqual(len(result.items[0].attachments), 1)
            relative_path = str(result.items[0].attachments[0]["relative_path"])
            self.assertTrue(relative_path.startswith("images/paper-figure-1-"))
            self.assertTrue(relative_path.endswith(".png"))
            self.assertTrue((output_dir.parent / "assets" / relative_path).exists())
            self.assertIn("Agent loop diagram", str(result.items[0].attachments[0]["description"]))
            self.assertEqual(result.items[0].attachments[0]["metadata"]["page_idx"], 0)

    def test_mineru_image_description_uses_compact_extraction_summary(self) -> None:
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

            _, result = DocumentProcessingPipeline(mineru=FakeNativeMinerUContentOnlyImageProcessor()).prepare_input_file(config, path)

            attachment = result.items[0].attachments[0]
            self.assertIn("graph LR", str(attachment["description"]))
            self.assertIn("mermaid", str(attachment["metadata"]["content"]))

    def test_prepare_input_folder_markdown_only_ignores_obsidian_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            notes = root / "Notes"
            assets = notes / "assets"
            obsidian = notes / ".obsidian"
            assets.mkdir(parents=True)
            obsidian.mkdir()
            (notes / "Agent.md").write_text("# Agent\n\nBody.", encoding="utf-8")
            (assets / "diagram.png").write_bytes(b"png")
            (notes / "paper.pdf").write_bytes(b"%PDF")
            (obsidian / "workspace.json").write_text("{}", encoding="utf-8")
            processor = CountingMinerUProcessor()
            config = KnoArborConfig.model_validate(
                {
                    "vault": {"path": str(root / "vaults" / "all")},
                    "document_processing": {
                        "mineru": {
                            "enabled": True,
                            "endpoint": "http://localhost:9999/file_parse",
                            "output_dir": str(root / "processed"),
                        }
                    },
                }
            )

            markdown_paths, result = DocumentProcessingPipeline(mineru=processor).prepare_input_folder(
                config,
                notes,
                markdown_only=True,
            )

        self.assertEqual(markdown_paths, [(notes / "Agent.md").resolve()])
        self.assertEqual(result.stats["item_count"], 0)
        self.assertEqual(processor.calls, [])

    def test_prepare_input_folder_only_preprocesses_configured_rich_patterns(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            folder = root / "docs"
            folder.mkdir()
            (folder / "note.md").write_text("# Note\n\nBody.", encoding="utf-8")
            (folder / "paper.pdf").write_bytes(b"%PDF")
            (folder / "figure.png").write_bytes(b"png")
            (folder / "archive.zip").write_bytes(b"zip")
            processor = CountingMinerUProcessor()
            config = KnoArborConfig.model_validate(
                {
                    "vault": {"path": str(root / "vaults" / "all")},
                    "document_processing": {
                        "mineru": {
                            "enabled": True,
                            "endpoint": "http://localhost:9999/file_parse",
                            "output_dir": str(root / "processed"),
                            "patterns": ["*.pdf"],
                        }
                    },
                }
            )

            markdown_paths, result = DocumentProcessingPipeline(mineru=processor).prepare_input_folder(config, folder)

        self.assertEqual([path.name for path in processor.calls], ["paper.pdf"])
        self.assertIn((folder / "note.md").resolve(), markdown_paths)
        self.assertIn((root / "processed" / "paper.md").resolve(), markdown_paths)
        self.assertEqual(result.stats["processed_count"], 1)

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
