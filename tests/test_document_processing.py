from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
import sys
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from knoarbor.core.config import KnoArborConfig, MinerUDocumentProcessingConfig
from knoarbor.core.errors import DocumentPreprocessorUnavailable, ExternalServiceError
from knoarbor.document_processing.mineru import (
    MinerUDocumentProcessor,
    MinerUResponse,
    _clean_attachment_content,
    mineru_health_endpoint,
    mineru_max_concurrent_requests,
    probe_mineru_endpoint,
)
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


class FakeZipMinerUProcessor(MinerUDocumentProcessor):
    def _post(self, config: MinerUDocumentProcessingConfig, path: Path, output_dir: Path) -> MinerUResponse:
        body = io.BytesIO()
        with zipfile.ZipFile(body, "w") as archive:
            archive.writestr("paper/auto/paper.md", "# ZIP MinerU\n\n![](images/figure.png)")
            archive.writestr("paper/auto/images/figure.png", b"png")
        return MinerUResponse(status_code=200, headers={"content-type": "application/zip"}, body=body.getvalue())


class FakeUnsafeZipMinerUProcessor(MinerUDocumentProcessor):
    def _post(self, config: MinerUDocumentProcessingConfig, path: Path, output_dir: Path) -> MinerUResponse:
        body = io.BytesIO()
        with zipfile.ZipFile(body, "w") as archive:
            archive.writestr("../outside.md", "# unsafe")
        return MinerUResponse(status_code=200, headers={"content-type": "application/zip"}, body=body.getvalue())


class CountingMinerUProcessor(FakeMinerUProcessor):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[Path] = []

    def _post(self, config: MinerUDocumentProcessingConfig, path: Path, output_dir: Path) -> MinerUResponse:
        self.calls.append(path)
        return super()._post(config, path, output_dir)


class DocumentProcessingTests(unittest.TestCase):
    def test_attachment_content_normalizes_single_line_fenced_markdown(self) -> None:
        self.assertEqual(
            _clean_attachment_content("```mermaid graph LR A --> B ```"),
            "```mermaid\ngraph LR A --> B\n```",
        )

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

    def test_real_mineru_transport_posts_native_multipart_contract(self) -> None:
        class Response:
            status = 200
            headers = {"Content-Type": "application/json"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self) -> bytes:
                return b'{"results":{"paper":{"md_content":"# Real transport"}}}'

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            path = root / "paper.pdf"
            path.write_bytes(b"%PDF")
            config = KnoArborConfig.model_validate({
                "vault": {"path": str(root / "vault")},
                "document_processing": {"mineru": {
                    "enabled": True,
                    "endpoint": "https://mineru.example/file_parse",
                    "output_dir": str(root / "markdown"),
                    "extra_fields": {
                        "backend": "pipeline",
                        "lang_list": ["ch"],
                        "return_md": True,
                        "return_images": False,
                    },
                }},
            })

            with patch("knoarbor.document_processing.mineru.request.urlopen", return_value=Response()) as urlopen:
                prepared, _ = DocumentProcessingPipeline().prepare_input_file(config, path)
                prepared_content = prepared.read_text(encoding="utf-8")

        request_value = urlopen.call_args.args[0]
        body = request_value.data
        self.assertEqual(request_value.full_url, "https://mineru.example/file_parse")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 600.0)
        self.assertIn(b'name="files"; filename="paper.pdf"', body)
        self.assertIn(b"Content-Type: application/pdf", body)
        self.assertIn(b'name="return_md"\r\n\r\ntrue', body)
        self.assertIn(b'name="lang_list"\r\n\r\nch', body)
        self.assertIn("# Real transport", prepared_content)

    def test_real_mineru_transport_sends_official_backend_name(self) -> None:
        class Response:
            status = 200
            headers = {"Content-Type": "application/json"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self) -> bytes:
                return b'{"results":{"paper":{"md_content":"# VLM"}}}'

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            path = root / "paper.pdf"
            path.write_bytes(b"%PDF")
            config = KnoArborConfig.model_validate(
                {
                    "vault": {"path": str(root / "vault")},
                    "document_processing": {
                        "mineru": {
                            "enabled": True,
                            "endpoint": "https://mineru.example/file_parse",
                            "output_dir": str(root / "markdown"),
                            "extra_fields": {"backend": "vlm-auto-engine", "return_md": True},
                        }
                    },
                }
            )

            with patch("knoarbor.document_processing.mineru.request.urlopen", return_value=Response()) as urlopen:
                DocumentProcessingPipeline().prepare_input_file(config, path)

        body = urlopen.call_args.args[0].data
        self.assertIn(b'name="backend"\r\n\r\nvlm-auto-engine', body)

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

    def test_mineru_processor_materializes_zip_response_and_images(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            path = root / "paper.pdf"
            path.write_bytes(b"%PDF")
            config = KnoArborConfig.model_validate({
                "vault": {"path": str(root / "vault")},
                "document_processing": {"mineru": {
                    "enabled": True,
                    "endpoint": "http://localhost:9999/file_parse",
                    "output_dir": str(root / "markdown"),
                    "extra_fields": {"return_md": True, "response_format_zip": True},
                }},
            })

            prepared, result = DocumentProcessingPipeline(mineru=FakeZipMinerUProcessor()).prepare_input_file(config, path)

            self.assertEqual(prepared, (root / "markdown" / "paper" / "auto" / "paper.md").resolve())
            self.assertIn("# ZIP MinerU", prepared.read_text(encoding="utf-8"))
            self.assertEqual(len(result.items[0].attachments), 1)

    def test_mineru_processor_rejects_zip_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            path = root / "paper.pdf"
            path.write_bytes(b"%PDF")
            config = KnoArborConfig.model_validate({
                "vault": {"path": str(root / "vault")},
                "document_processing": {"mineru": {
                    "enabled": True,
                    "endpoint": "http://localhost:9999/file_parse",
                    "output_dir": str(root / "markdown"),
                }},
            })

            with self.assertRaisesRegex(ExternalServiceError, "unsafe path"):
                DocumentProcessingPipeline(mineru=FakeUnsafeZipMinerUProcessor()).prepare_input_file(config, path)
            self.assertFalse((root / "outside.md").exists())

    def test_mineru_image_description_preserves_extraction_content(self) -> None:
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
            expected = "```mermaid\ngraph LR\n  A --> B\n```"
            self.assertEqual(attachment["description"], expected)
            self.assertEqual(attachment["metadata"]["content"], expected)

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

    def test_prepare_input_folder_preserves_relative_parent_for_same_stem_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            folder = root / "docs"
            (folder / "a").mkdir(parents=True)
            (folder / "b").mkdir()
            (folder / "a" / "report.pdf").write_bytes(b"first")
            (folder / "b" / "report.pdf").write_bytes(b"second")
            output = root / "processed"
            config = KnoArborConfig.model_validate({
                "vault": {"path": str(root / "vault")},
                "document_processing": {"mineru": {
                    "enabled": True,
                    "endpoint": "http://localhost:9999/file_parse",
                    "output_dir": str(output),
                    "patterns": ["*.pdf"],
                }},
            })

            markdown_paths, result = DocumentProcessingPipeline(mineru=FakeMinerUProcessor()).prepare_input_folder(config, folder)

            self.assertEqual(result.stats["processed_count"], 2)
            self.assertEqual(markdown_paths, [(output / "a" / "report.md").resolve(), (output / "b" / "report.md").resolve()])
            self.assertTrue(all(path.exists() for path in markdown_paths))

    def test_mineru_defaults_match_native_file_parse_contract(self) -> None:
        config = MinerUDocumentProcessingConfig()

        self.assertEqual(config.file_field, "files")
        self.assertIsNone(config.output_dir_field)
        self.assertEqual(config.mode_field, "parse_method")
        self.assertEqual(config.extra_fields["backend"], "pipeline")
        self.assertTrue(config.extra_fields["return_md"])
        self.assertEqual(mineru_health_endpoint("http://127.0.0.1:18000/file_parse"), "http://127.0.0.1:18000/health")

    def test_mineru_health_probe_requires_json_health_response(self) -> None:
        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self) -> bytes:
                return b'{"protocol_version":"3"}'

        with patch("knoarbor.document_processing.mineru.request.urlopen", return_value=Response()) as urlopen:
            ok, detail = probe_mineru_endpoint("https://mineru.example/file_parse")

        self.assertTrue(ok)
        self.assertIn("(3)", detail)
        self.assertEqual(urlopen.call_args.args[0].full_url, "https://mineru.example/health")

    def test_mineru_capacity_uses_health_capability(self) -> None:
        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self) -> bytes:
                return b'{"max_concurrent_requests":3}'

        with patch("knoarbor.document_processing.mineru.request.urlopen", return_value=Response()):
            capacity = mineru_max_concurrent_requests("https://mineru.example/file_parse")

        self.assertEqual(capacity, 3)

    def test_mineru_loopback_health_bypasses_environment_proxy(self) -> None:
        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self) -> bytes:
                return b'{"protocol_version":"3"}'

        class Opener:
            def open(self, req, *, timeout):
                self.request = req
                self.timeout = timeout
                return Response()

        opener = Opener()
        with patch("knoarbor.document_processing.mineru.request.build_opener", return_value=opener) as build_opener:
            with patch("knoarbor.document_processing.mineru.request.urlopen") as urlopen:
                ok, _ = probe_mineru_endpoint("http://127.0.0.1:18000/file_parse")

        self.assertTrue(ok)
        build_opener.assert_called_once()
        urlopen.assert_not_called()
        self.assertEqual(opener.request.full_url, "http://127.0.0.1:18000/health")

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
