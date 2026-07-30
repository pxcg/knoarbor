from __future__ import annotations

from hashlib import sha256
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from knoarbor.core.schemas.sources import SourceContent, SourceDocument, SourceFingerprint, SourceOrigin
from knoarbor.services.ingest_input_resolver import IngestInputResolver
from knoarbor.storage.ingest_inputs import (
    INPUT_GENERATION_SCHEMA,
    InputGenerationIntegrityError,
    read_input_generation,
    write_input_generation,
)


class IngestInputAttachmentTests(unittest.TestCase):
    def test_folder_source_root_is_shared_across_nested_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            note = root / "notes" / "paper.md"
            image = root / "assets" / "diagram.png"
            note.parent.mkdir()
            image.parent.mkdir()
            note.write_text("![[diagram.png]]", encoding="utf-8")
            image.write_bytes(b"diagram")

            documents = IngestInputResolver()._markdown_documents([note], source_root=root)

        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].content.attachments[0]["path"], str(image.resolve()))

    def test_input_generation_retains_local_attachment_inside_vault(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            vault = root / "vault"
            source_root = root / "source"
            source_root.mkdir()
            image = source_root / "diagram.png"
            data = b"retained-image"
            image.write_bytes(data)
            document = _document(image)

            generation = write_input_generation(vault, documents=[document])
            shutil.rmtree(source_root)
            attachment = generation.documents[0].content.attachments[0]
            retained = vault / str(attachment["relative_path"])
            retained_data = retained.read_bytes()

        digest = sha256(data).hexdigest()
        self.assertNotIn("path", attachment)
        self.assertEqual(attachment["content_hash"], digest)
        self.assertEqual(attachment["relative_path"], f"raw/derived/assets/images/{digest}.png")
        self.assertEqual(retained_data, data)

    def test_input_generation_rejects_noncanonical_generation_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaisesRegex(InputGenerationIntegrityError, "id is invalid"):
                read_input_generation(Path(tmp_dir), "../outside")

    def test_input_generation_rejects_manifest_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            payload = {
                "schema_version": INPUT_GENERATION_SCHEMA,
                "documents": [],
                "files": [{"path": "../outside.json", "sha256": "sha256:" + ("0" * 64)}],
                "failures": [],
                "metadata": {},
            }
            generation_id, generation_path = _write_generation_manifest(vault, payload)

            with self.assertRaisesRegex(InputGenerationIntegrityError, "member path is invalid"):
                read_input_generation(vault, generation_id)

            self.assertTrue(generation_path.is_dir())

    def test_input_generation_requires_documents_in_verified_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            payload = {
                "schema_version": INPUT_GENERATION_SCHEMA,
                "documents": [{"source_id": "missing", "content_hash": "missing", "path": "documents/000000.json"}],
                "files": [],
                "failures": [],
                "metadata": {},
            }
            generation_id, generation_path = _write_generation_manifest(vault, payload)
            document_path = generation_path / "documents" / "000000.json"
            document_path.parent.mkdir(parents=True)
            document_path.write_text("{}", encoding="utf-8")

            with self.assertRaisesRegex(InputGenerationIntegrityError, "absent from verified inventory"):
                read_input_generation(vault, generation_id)

    def test_input_generation_rejects_symlink_member_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            outside = vault / "outside.json"
            outside.write_text("{}", encoding="utf-8")
            payload = {
                "schema_version": INPUT_GENERATION_SCHEMA,
                "documents": [],
                "files": [{"path": "documents/link.json", "sha256": f"sha256:{sha256(b'{}').hexdigest()}"}],
                "failures": [],
                "metadata": {},
            }
            generation_id, generation_path = _write_generation_manifest(vault, payload)
            link = generation_path / "documents" / "link.json"
            link.parent.mkdir(parents=True)
            link.symlink_to(outside)

            with self.assertRaisesRegex(InputGenerationIntegrityError, "escapes its generation"):
                read_input_generation(vault, generation_id)


def _document(image: Path) -> SourceDocument:
    return SourceDocument(
        source_id="markdown:test",
        source_type="markdown",
        origin=SourceOrigin(connector="markdown", uri="file:///source/paper.md", raw_path="/source/paper.md"),
        content=SourceContent(
            format="markdown",
            text="![[diagram.png]]",
            attachments=[
                {
                    "attachment_type": "image",
                    "name": "diagram.png",
                    "path": str(image),
                    "relative_path": "diagram.png",
                    "content_hash": sha256(image.read_bytes()).hexdigest(),
                    "source": "obsidian_image_embed",
                    "metadata": {"obsidian_target": "diagram.png"},
                }
            ],
        ),
        fingerprint=SourceFingerprint(content_hash="source-hash", connector_version="markdown@1"),
    )


def _write_generation_manifest(vault: Path, payload: dict[str, object]) -> tuple[str, Path]:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    generation_id = f"sha256:{sha256(canonical.encode('utf-8')).hexdigest()}"
    generation_path = vault / ".knoarbor" / "ingest_inputs" / "generations" / generation_id.removeprefix("sha256:")
    generation_path.mkdir(parents=True)
    manifest = {**payload, "generation_id": generation_id}
    (generation_path / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return generation_id, generation_path


if __name__ == "__main__":
    unittest.main()
