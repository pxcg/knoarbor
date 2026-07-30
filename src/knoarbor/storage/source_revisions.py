from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from uuid import uuid4

from knoarbor.core.knowledge_evidence import map_knowledge_evidence
from knoarbor.core.schemas.ingest_execution import FactIdentity, fact_input_revision_key
from knoarbor.core.schemas.knowledge_atoms import KnowledgeAtomBatch
from knoarbor.core.schemas.raw_evidence import SourceProcessingRecord
from knoarbor.runtime.locks import vault_write_lock
from knoarbor.runtime.transactional_ingest import AttemptLease, TransactionalIngestStore
from knoarbor.storage.revision_integrity import (
    revision_file_hash as _hash_file,
    revision_manifest_hash as _hash_payload,
    verify_revision_generation,
    verify_revision_generation_path,
)
from knoarbor.storage.vault_layout import raw_derived_assets_root, runtime_fact_staging_root, runtime_facts_root


@dataclass(frozen=True)
class RevisionDraft:
    """Validated factual payload for one document revision or session window."""

    processing_record: SourceProcessingRecord
    atom_batch: KnowledgeAtomBatch
    diagnostics: dict[str, object] | None = None
    window_id: str | None = None
    window_from_index: int | None = None
    window_to_index: int | None = None
    checkpoint_cursor: dict[str, object] | None = None


def revision_root(vault_path: Path) -> Path:
    return runtime_facts_root(vault_path)


def publish_revision_draft(
    vault_path: Path,
    *,
    store: TransactionalIngestStore,
    lease: AttemptLease,
    draft: RevisionDraft,
) -> tuple[str, Path]:
    """Stage immutable raw facts, then publish them through the source-head CAS."""

    root = revision_root(vault_path)
    processing_record = draft.processing_record
    atom_batch = draft.atom_batch
    window_id = draft.window_id
    window_from_index = draft.window_from_index
    window_to_index = draft.window_to_index
    previous_window_id = store.session_watermark(processing_record.raw_record_id) if window_id else None
    previous_head = store.source_head(processing_record.raw_record_id) if window_id is None else None
    obsolete_image_candidates = (
        source_revision_image_asset_paths(vault_path, processing_record.raw_record_id, store=store)
        if previous_head is not None
        else set()
    )
    revision_id = store.new_revision_id()
    processing_record, atom_batch = _with_revision_identity(
        processing_record,
        atom_batch,
        revision_id=revision_id,
        window_id=window_id,
    )
    stage = runtime_fact_staging_root(vault_path) / uuid4().hex
    stage.mkdir(parents=True, exist_ok=False)
    _write_json(stage / "source.json", processing_record.model_dump(mode="json"))
    _write_json(stage / "knowledge.json", _knowledge_payload(atom_batch))
    _write_json(stage / "diagnostics.json", _diagnostics_payload(draft.diagnostics))
    manifest = {
        "schema_version": "source_revision_manifest.v2",
        "source_id": processing_record.raw_record_id,
        "raw_revision_id": processing_record.raw_revision_id,
        "processing_record_id": processing_record.processing_record_id,
        "revision_id": revision_id,
        "window_id": window_id,
        "previous_window_id": previous_window_id,
        "files": ["source.json", "knowledge.json", "diagnostics.json"],
        "file_hashes": {
            "source.json": _hash_file(stage / "source.json"),
            "knowledge.json": _hash_file(stage / "knowledge.json"),
            "diagnostics.json": _hash_file(stage / "diagnostics.json"),
        },
    }
    manifest_hash = _hash_payload(manifest)
    manifest["manifest_hash"] = manifest_hash
    _write_json(stage / "manifest.json", manifest)
    generation = root / _fact_key(processing_record.raw_record_id) / _fact_key(revision_id)
    generation.parent.mkdir(parents=True, exist_ok=True)
    if generation.exists():
        _remove_tree(stage)
        raise RuntimeError(f"Factual revision target already exists: {revision_id}")
    stage.replace(generation)
    try:
        published_revision_id = store.publish_revision(
            lease,
            source_id=processing_record.raw_record_id,
            expected_source_head=previous_head,
            revision_id=revision_id,
            manifest_path=str(generation.relative_to(vault_path.expanduser().resolve())),
            manifest_hash=manifest_hash,
            window_id=window_id,
            previous_window_id=previous_window_id,
            window_from_index=window_from_index,
            window_to_index=window_to_index,
            entity_contributions={
                entity.atom_id or entity.name: {
                    "entity_id": entity.atom_id or entity.name,
                    "name": entity.name,
                    "aliases": entity.aliases,
                    "raw_record_id": processing_record.raw_record_id,
                    "source_record_id": processing_record.source_record_id,
                }
                for entity in atom_batch.entities
            },
            checkpoint_cursor=draft.checkpoint_cursor,
            input_revision_key=fact_input_revision_key(
                store.command_for_task(lease.task_id),
                FactIdentity(
                    source_id=processing_record.raw_record_id,
                    raw_revision_id=processing_record.raw_revision_id,
                    window_id=window_id,
                ),
            ),
        )
    except Exception:
        # A generation without a source head is unreachable and can be reclaimed.
        _remove_tree(generation)
        raise
    if published_revision_id != revision_id:
        _remove_tree(generation)
        existing = store.revision_manifest(published_revision_id)
        return published_revision_id, vault_path.expanduser().resolve() / str(existing["manifest_path"])
    if previous_head is not None:
        release_unreferenced_image_assets(vault_path, obsolete_image_candidates, store=store)
    return revision_id, generation


def _with_revision_identity(
    record: SourceProcessingRecord,
    batch: KnowledgeAtomBatch,
    *,
    revision_id: str,
    window_id: str | None,
) -> tuple[SourceProcessingRecord, KnowledgeAtomBatch]:
    source_units = [unit.model_copy(update={"revision_id": revision_id, "window_id": window_id}) for unit in record.source_units]
    record = record.model_copy(update={"revision_id": revision_id, "window_id": window_id, "source_units": source_units})

    units_by_id = {unit.source_unit_id: unit for unit in source_units}
    units_by_index = {unit.unit_index: unit for unit in source_units}

    def enrich(span):
        unit = units_by_id.get(span.source_unit_id or "")
        if unit is None and span.source_unit_index is not None:
            unit = units_by_index.get(span.source_unit_index)
        if unit is None:
            raise ValueError(f"Evidence for source record {record.source_record_id} does not reference a published source unit.")
        return span.model_copy(
            update={
                "revision_id": revision_id,
                "window_id": window_id,
                "source_unit_id": unit.source_unit_id,
                "source_unit_index": unit.unit_index,
                "source_path": span.source_path or unit.source_path,
                "excerpt_hash": span.excerpt_hash or unit.excerpt_hash,
                "char_start": span.char_start if span.char_start is not None else unit.char_start,
                "char_end": span.char_end if span.char_end is not None else unit.char_end,
            }
        )

    enriched_batch = map_knowledge_evidence(batch, enrich)
    return record, enriched_batch.model_copy(update={"revision_id": revision_id, "window_id": window_id})


def read_active_processing_records(vault_path: Path) -> list[SourceProcessingRecord] | None:
    """Read the source-head materialization; ``None`` means no transactional facts exist yet."""

    store_path = vault_path.expanduser().resolve() / ".knoarbor" / "ingest.sqlite"
    if not store_path.exists():
        return None
    records: list[SourceProcessingRecord] = []
    for revision in TransactionalIngestStore(vault_path).active_revision_manifests():
        generation_path = verify_revision_generation(vault_path, revision)
        record_path = generation_path / "source.json"
        if not record_path.exists():
            raise RuntimeError(f"Published source revision is missing its processing record: {revision['revision_id']}")
        records.append(SourceProcessingRecord.model_validate_json(record_path.read_text(encoding="utf-8")))
    return records


def read_revision_processing_record(
    vault_path: Path,
    revision_id: str,
    *,
    store: TransactionalIngestStore | None = None,
) -> SourceProcessingRecord:
    runtime_store = store or TransactionalIngestStore(vault_path)
    generation = verify_revision_generation(vault_path, runtime_store.revision_manifest(revision_id))
    return SourceProcessingRecord.model_validate_json((generation / "source.json").read_text(encoding="utf-8"))


def read_active_atom_batches(vault_path: Path) -> list[KnowledgeAtomBatch] | None:
    store_path = vault_path.expanduser().resolve() / ".knoarbor" / "ingest.sqlite"
    if not store_path.exists():
        return None
    batches: list[KnowledgeAtomBatch] = []
    for revision in TransactionalIngestStore(vault_path).active_revision_manifests():
        generation_path = verify_revision_generation(vault_path, revision)
        batch_path = generation_path / "knowledge.json"
        if not batch_path.exists():
            raise RuntimeError(f"Published source revision is missing its atom batch: {revision['revision_id']}")
        batches.append(_read_knowledge_payload(generation_path, batch_path))
    return batches


def read_revision_atom_batch(vault_path: Path, revision_id: str) -> KnowledgeAtomBatch:
    generation = verify_revision_generation(vault_path, TransactionalIngestStore(vault_path).revision_manifest(revision_id))
    return _read_knowledge_payload(generation, generation / "knowledge.json")


def read_revision_diagnostics(vault_path: Path, revision_id: str) -> dict[str, object]:
    generation = verify_revision_generation(vault_path, TransactionalIngestStore(vault_path).revision_manifest(revision_id))
    payload = json.loads((generation / "diagnostics.json").read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Published source revision diagnostics are invalid: {revision_id}")
    return payload


def source_revision_image_asset_paths(
    vault_path: Path,
    source_id: str,
    *,
    store: TransactionalIngestStore | None = None,
) -> set[Path]:
    """Return contained image assets explicitly referenced by one source's revisions."""

    runtime_store = store or TransactionalIngestStore(vault_path)
    revisions = [revision for revision in runtime_store.revision_manifests() if str(revision["source_id"]) == source_id]
    return _revision_image_asset_paths(vault_path, revisions, strict=False)


def release_unreferenced_image_assets(
    vault_path: Path,
    candidates: set[Path],
    *,
    store: TransactionalIngestStore | None = None,
) -> list[Path]:
    """Delete candidate images that no SQLite-selected active revision retains."""

    if not candidates:
        return []
    runtime_store = store or TransactionalIngestStore(vault_path)
    protected = _revision_image_asset_paths(vault_path, runtime_store.active_revision_manifests(), strict=True)
    removed: list[Path] = []
    for candidate in sorted(candidates - protected):
        if candidate.is_file():
            candidate.unlink()
            removed.append(candidate)
    return removed


def _revision_image_asset_paths(
    vault_path: Path,
    revisions: list[dict[str, object]],
    *,
    strict: bool,
) -> set[Path]:
    vault = vault_path.expanduser().resolve()
    images_root = (raw_derived_assets_root(vault) / "images").resolve()
    paths: set[Path] = set()
    for revision in revisions:
        try:
            generation = verify_revision_generation(vault, revision)
            record = SourceProcessingRecord.model_validate_json((generation / "source.json").read_text(encoding="utf-8"))
        except (OSError, RuntimeError, ValueError):
            if strict:
                raise
            continue
        for attachment in record.attachments:
            if attachment.attachment_type != "image" or not attachment.relative_path:
                continue
            relative = PurePosixPath(attachment.relative_path)
            if (
                relative.is_absolute()
                or "\\" in attachment.relative_path
                or relative.as_posix() != attachment.relative_path
                or any(part in {"", ".", ".."} for part in relative.parts)
            ):
                continue
            path = (vault / Path(*relative.parts)).resolve()
            if path != images_root and path.is_relative_to(images_root):
                paths.add(path)
    return paths


def migrate_legacy_fact_layout(vault_path: Path, *, store: TransactionalIngestStore | None = None) -> int:
    """Convert legacy revision generations before current readers are admitted."""

    vault = vault_path.expanduser().resolve()
    store = store or TransactionalIngestStore(vault)
    with vault_write_lock(vault):
        return _migrate_legacy_fact_layout(vault, store)


def _migrate_legacy_fact_layout(vault: Path, store: TransactionalIngestStore) -> int:
    migrated = 0
    for revision in store.revision_manifests():
        legacy = vault / str(revision["manifest_path"])
        if "source_revisions" not in legacy.parts:
            continue
        verify_revision_generation_path(legacy, revision)
        legacy_manifest = json.loads((legacy / "manifest.json").read_text(encoding="utf-8"))
        source_payload = json.loads((legacy / "source_processing_record.json").read_text(encoding="utf-8"))
        knowledge_payload = json.loads((legacy / "knowledge_atom_batch.json").read_text(encoding="utf-8"))
        source_payload["schema_version"] = "source_processing_record.v2"
        source_payload.setdefault("attachments", [])
        knowledge_payload["schema_version"] = "knowledge_atoms.v3"
        processing_record = SourceProcessingRecord.model_validate(source_payload)
        atom_batch = KnowledgeAtomBatch.model_validate(knowledge_payload)
        diagnostics_path = legacy / "diagnostics.json"
        diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8")) if diagnostics_path.exists() else {}
        target = revision_root(vault) / _fact_key(processing_record.raw_record_id) / _fact_key(str(revision["revision_id"]))
        if target.exists():
            target_manifest = _validated_unselected_target(target, str(revision["revision_id"]))
            store.replace_revision_manifest(
                str(revision["revision_id"]),
                manifest_path=str(target.relative_to(vault)),
                manifest_hash=str(target_manifest["manifest_hash"]),
            )
            _remove_tree(legacy)
            migrated += 1
            continue
        stage = runtime_fact_staging_root(vault) / uuid4().hex
        stage.mkdir(parents=True, exist_ok=False)
        _write_json(stage / "source.json", processing_record.model_dump(mode="json"))
        _write_json(stage / "knowledge.json", _knowledge_payload(atom_batch))
        _write_json(stage / "diagnostics.json", _diagnostics_payload(diagnostics if isinstance(diagnostics, dict) else {}))
        manifest = {
            "schema_version": "source_revision_manifest.v2",
            "source_id": processing_record.raw_record_id,
            "raw_revision_id": processing_record.raw_revision_id,
            "processing_record_id": processing_record.processing_record_id,
            "revision_id": str(revision["revision_id"]),
            "window_id": processing_record.window_id,
            "previous_window_id": legacy_manifest.get("previous_window_id"),
            "files": ["source.json", "knowledge.json", "diagnostics.json"],
            "file_hashes": {
                "source.json": _hash_file(stage / "source.json"),
                "knowledge.json": _hash_file(stage / "knowledge.json"),
                "diagnostics.json": _hash_file(stage / "diagnostics.json"),
            },
        }
        manifest_hash = _hash_payload(manifest)
        manifest["manifest_hash"] = manifest_hash
        _write_json(stage / "manifest.json", manifest)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            _remove_tree(stage)
            raise RuntimeError(f"Fact migration target already exists: {revision['revision_id']}")
        stage.replace(target)
        try:
            store.replace_revision_manifest(
                str(revision["revision_id"]),
                manifest_path=str(target.relative_to(vault)),
                manifest_hash=manifest_hash,
            )
        except Exception:
            _remove_tree(target)
            raise
        _remove_tree(legacy)
        migrated += 1
    legacy_root = vault / ".knoarbor" / "source_revisions"
    if legacy_root.exists() and not any(path.is_file() for path in legacy_root.rglob("*")):
        _remove_tree(legacy_root)
    return migrated


def _validated_unselected_target(target: Path, revision_id: str) -> dict[str, object]:
    manifest_path = target / "manifest.json"
    if not manifest_path.is_file():
        raise RuntimeError(f"Fact migration target has no manifest: {revision_id}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("revision_id") != revision_id:
        raise RuntimeError(f"Fact migration target identity conflicts: {revision_id}")
    expected = str(manifest.get("manifest_hash") or "")
    actual = _hash_payload({key: value for key, value in manifest.items() if key != "manifest_hash"})
    if not expected or expected != actual:
        raise RuntimeError(f"Fact migration target manifest failed integrity verification: {revision_id}")
    file_hashes = manifest.get("file_hashes")
    if not isinstance(file_hashes, dict):
        raise RuntimeError(f"Fact migration target has no file hashes: {revision_id}")
    for name, file_hash in file_hashes.items():
        path = target / str(name)
        if not path.is_file() or _hash_file(path) != file_hash:
            raise RuntimeError(f"Fact migration target file failed integrity verification: {revision_id} ({name})")
    return manifest


def prune_unreachable_fact_artifacts(vault_path: Path, *, store: TransactionalIngestStore | None = None) -> list[str]:
    """Remove interrupted staging and fact directories absent from SQLite revisions."""

    vault = vault_path.expanduser().resolve()
    store = store or TransactionalIngestStore(vault)
    root = revision_root(vault)
    protected = {(vault / str(revision["manifest_path"])).resolve() for revision in store.revision_manifests()}
    removed: list[str] = []
    with vault_write_lock(vault):
        staging = runtime_fact_staging_root(vault)
        if staging.exists():
            for path in staging.iterdir():
                removed.append(str(path.relative_to(vault)))
                _remove_tree(path)
        if root.exists():
            for source_dir in root.iterdir():
                if not source_dir.is_dir() or source_dir.name == ".staging":
                    continue
                for fact_dir in source_dir.iterdir():
                    if fact_dir.is_dir() and fact_dir.resolve() not in protected:
                        removed.append(str(fact_dir.relative_to(vault)))
                        _remove_tree(fact_dir)
                if not any(source_dir.iterdir()):
                    source_dir.rmdir()
    return removed


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _diagnostics_payload(payload: dict[str, object] | None) -> dict[str, object]:
    values = dict(payload or {})
    values["schema_version"] = "ingest_diagnostics.v1"
    return values


def _knowledge_payload(batch: KnowledgeAtomBatch) -> dict[str, object]:
    payload = batch.model_dump(mode="json")
    for collection in ("entities", "claims", "relations"):
        items = payload.get(collection)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            evidence = item.get("evidence")
            if not isinstance(evidence, list):
                continue
            for span in evidence:
                if isinstance(span, dict) and span.get("source_unit_id"):
                    span.pop("excerpt", None)
    return payload


def _read_knowledge_payload(generation: Path, path: Path) -> KnowledgeAtomBatch:
    batch = KnowledgeAtomBatch.model_validate_json(path.read_text(encoding="utf-8"))
    record = SourceProcessingRecord.model_validate_json((generation / "source.json").read_text(encoding="utf-8"))
    units_by_id = {unit.source_unit_id: unit for unit in record.source_units}

    def hydrate(span):
        if span.excerpt:
            return span
        unit = units_by_id.get(span.source_unit_id or "")
        if unit is None:
            raise ValueError(f"Persisted evidence references an unknown source unit: {span.source_unit_id or '<missing>'}")
        excerpt = _excerpt_for_span(unit.excerpt or unit.content, unit.char_start, unit.char_end, span.char_start, span.char_end)
        return span.model_copy(
            update={
                "excerpt": excerpt,
                "source_path": span.source_path or unit.source_path,
                "excerpt_hash": span.excerpt_hash or unit.excerpt_hash,
                "char_start": span.char_start if span.char_start is not None else unit.char_start,
                "char_end": span.char_end if span.char_end is not None else unit.char_end,
            }
        )

    return map_knowledge_evidence(batch, hydrate)


def _excerpt_for_span(
    unit_text: str,
    unit_start: int | None,
    unit_end: int | None,
    span_start: int | None,
    span_end: int | None,
) -> str:
    if span_start is None and span_end is None:
        return unit_text
    if span_start is None or span_end is None:
        raise ValueError("Persisted evidence range must define both start and end offsets.")
    base_start = unit_start or 0
    limit = unit_end if unit_end is not None else base_start + len(unit_text)
    relative_start = span_start - base_start
    relative_end = span_end - base_start
    if 0 <= relative_start <= relative_end <= len(unit_text) and span_end <= limit:
        return unit_text[relative_start:relative_end]
    raise ValueError(
        f"Persisted evidence range {span_start}:{span_end} is outside source unit range "
        f"{base_start}:{limit}."
    )


def _fact_key(identity: str) -> str:
    return sha256(identity.encode("utf-8")).hexdigest()[:24]


def _remove_tree(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)
