from __future__ import annotations

from pathlib import Path

from knoarbor.core.schemas.ingest_execution import IngestExecutionCommand, execution_contract_hash
from knoarbor.core.schemas.knowledge_atoms import KnowledgeAtomBatch
from knoarbor.core.schemas.raw_evidence import OriginalSourceRecord, SourceProcessingRecord, SourceUnitRecord
from knoarbor.core.schemas.sources import SourceCheckpointWindow, SourceContent, SourceDocument, SourceFingerprint, SourceOrigin
from knoarbor.runtime.transactional_ingest import TransactionalIngestStore
from knoarbor.storage.source_revisions import RevisionDraft, publish_revision_draft
from knoarbor.storage.ingest_inputs import write_input_generation
from knoarbor.storage.vault_identity import ensure_vault_identity


def admit_test_task(vault: Path, label: str = "test", *, documents: list[SourceDocument] | None = None):
    store = TransactionalIngestStore(vault)
    generation = write_input_generation(vault, documents=documents or [], metadata={"label": label})
    contract = {"test": label}
    command = IngestExecutionCommand(
        generation_id=generation.generation_id,
        request_kind="test",
        vault_id="test",
        vault_path=str(vault),
        vault_identity=ensure_vault_identity(vault),
        write=True,
        write_report=False,
        append_ledger=False,
        execution_contract=contract,
        execution_contract_hash=execution_contract_hash(contract),
    )
    task, attempt = store.submit_command(command)
    return store, task, attempt


def publish_batch(
    vault: Path,
    batch: KnowledgeAtomBatch,
    *,
    raw_record_id: str = "raw:test",
    raw_revision_id: str = "rawrev:test",
    source_path: str = "raw/test.md",
    page_paths: list[str] | None = None,
) -> SourceProcessingRecord:
    """Create a real committed revision for storage-facing tests."""

    batch = _bind_single_test_unit(batch, source_unit_id=f"unit:{raw_revision_id}")

    record = SourceProcessingRecord(
        processing_record_id=f"spr:{raw_revision_id}",
        raw_record_id=raw_record_id,
        raw_revision_id=raw_revision_id,
        source_record_id=batch.source_record_id,
        source=OriginalSourceRecord(
            raw_record_id=raw_record_id,
            raw_revision_id=raw_revision_id,
            source_id=batch.source_record_id,
            source_type="markdown",
            connector="test",
            raw_path=source_path,
            content_hash=raw_revision_id,
            normalized_content_hash=raw_revision_id,
        ),
        source_units=[
            SourceUnitRecord(
                source_unit_id=f"unit:{raw_revision_id}",
                raw_record_id=raw_record_id,
                raw_revision_id=raw_revision_id,
                unit_index=0,
                content="Test source evidence.",
                excerpt="Test source evidence.",
                source_path=source_path,
            )
        ],
        page_paths=page_paths or [],
    )
    publish_record(vault, record, batch)
    return record


def _bind_single_test_unit(batch: KnowledgeAtomBatch, *, source_unit_id: str) -> KnowledgeAtomBatch:
    def bind(spans):
        return [span.model_copy(update={"source_unit_id": source_unit_id, "source_unit_index": 0}) for span in spans]

    entities = [entity.model_copy(update={"evidence": bind(entity.evidence)}) for entity in batch.entities]
    claims = [claim.model_copy(update={"evidence": bind(claim.evidence)}) for claim in batch.claims]
    relations = [relation.model_copy(update={"evidence": bind(relation.evidence)}) for relation in batch.relations]
    return batch.model_copy(update={"entities": entities, "claims": claims, "relations": relations})


def publish_record(vault: Path, record: SourceProcessingRecord, batch: KnowledgeAtomBatch | None = None) -> None:
    batch = batch or KnowledgeAtomBatch(source_record_id=record.source_record_id)
    normalized_content = "\n\n".join(unit.content for unit in sorted(record.source_units, key=lambda item: item.unit_index))
    document = SourceDocument(
        source_id=record.source.source_id,
        source_type="markdown",
        origin=SourceOrigin(
            connector=record.source.connector or "test",
            uri=f"file://{record.source.raw_path}",
            raw_path=record.source.raw_path or "raw/test.md",
        ),
        content=SourceContent(format="markdown", text=normalized_content),
        metadata={"title": record.source.title},
        fingerprint=SourceFingerprint(
            content_hash=record.source.content_hash or record.raw_revision_id,
            connector_version="test.v1",
        ),
        checkpoint=SourceCheckpointWindow(mode="full"),
    )
    store, task, attempt = admit_test_task(vault, record.raw_revision_id, documents=[document])
    lease = store.claim(str(task["task_id"]), str(attempt["attempt_id"]), owner_id="test", lease_seconds=30)
    publish_revision_draft(vault, store=store, lease=lease, draft=RevisionDraft(processing_record=record, atom_batch=batch))
    store.finish(lease, state="completed")
