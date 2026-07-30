from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from knoarbor.storage.revision_integrity import (
    revision_file_hash,
    revision_manifest_hash,
    verify_revision_generation,
)
from knoarbor.storage.vault_layout import runtime_fact_staging_root, runtime_facts_root


class RevisionIntegrityTests(unittest.TestCase):
    def test_verified_generation_is_selected_inside_facts_root(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            generation, revision = self._write_generation(vault)

            self.assertEqual(verify_revision_generation(vault, revision), generation.resolve())
            self.assertEqual(runtime_facts_root(vault), vault.resolve() / ".knoarbor" / "facts")
            self.assertEqual(
                runtime_fact_staging_root(vault),
                vault.resolve() / ".knoarbor" / "facts" / ".staging",
            )

    def test_changed_payload_fails_closed(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            generation, revision = self._write_generation(vault)
            (generation / "source.json").write_text('{"changed":true}\n', encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "file failed integrity"):
                verify_revision_generation(vault, revision)

    def test_changed_manifest_fails_closed(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            generation, revision = self._write_generation(vault)
            manifest_path = generation / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["source_id"] = "other-source"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "manifest failed integrity"):
                verify_revision_generation(vault, revision)

    def test_revision_and_member_paths_cannot_escape_authority_roots(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            vault = Path(tmp_dir)
            _, revision = self._write_generation(vault)
            escaped_revision = {**revision, "manifest_path": "../outside"}
            with self.assertRaisesRegex(RuntimeError, "invalid manifest_path"):
                verify_revision_generation(vault, escaped_revision)

            generation = vault / str(revision["manifest_path"])
            manifest_path = generation / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["file_hashes"] = {"../outside.json": "sha256:invalid"}
            manifest["manifest_hash"] = revision_manifest_hash(
                {key: value for key, value in manifest.items() if key != "manifest_hash"}
            )
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            escaped_member_revision = {**revision, "manifest_hash": manifest["manifest_hash"]}
            with self.assertRaisesRegex(RuntimeError, "invalid file_hashes"):
                verify_revision_generation(vault, escaped_member_revision)

    @staticmethod
    def _write_generation(vault: Path) -> tuple[Path, dict[str, object]]:
        generation = vault / ".knoarbor" / "facts" / "source-1" / "revision-1"
        generation.mkdir(parents=True)
        source_path = generation / "source.json"
        source_path.write_text('{"schema_version":"source_processing_record.v2"}\n', encoding="utf-8")
        manifest: dict[str, object] = {
            "schema_version": "source_revision_manifest.v2",
            "source_id": "source-1",
            "revision_id": "revision-1",
            "files": ["source.json"],
            "file_hashes": {"source.json": revision_file_hash(source_path)},
        }
        manifest_hash = revision_manifest_hash(manifest)
        manifest["manifest_hash"] = manifest_hash
        (generation / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        return generation, {
            "revision_id": "revision-1",
            "manifest_path": ".knoarbor/facts/source-1/revision-1",
            "manifest_hash": manifest_hash,
        }
