from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from knoarbor.core.errors import StorageConflict
from knoarbor.core.schemas.ingest_execution import FactCommit, IngestExecutionPort, PublishedFact
from knoarbor.core.schemas.ingest_pipeline import IngestSourceResult
from knoarbor.core.schemas.knowledge_atoms import KnowledgeAtomBatch
from knoarbor.core.schemas.raw_evidence import SourceProcessingRecord
from knoarbor.core.schemas.source_record import SourceRecord
from knoarbor.core.schemas.sources import SourceDocument
from knoarbor.storage.source_records import build_source_processing_record, enrich_atom_batch_evidence
from knoarbor.storage.source_revisions import read_active_processing_records
from knoarbor.storage.wiki_projection import source_projection_path


@dataclass(frozen=True)
class IngestPublication:
    processing_record: SourceProcessingRecord
    published_fact: PublishedFact


def publish_ingest_source(
    vault_path: Path,
    *,
    result: IngestSourceResult,
    document: SourceDocument,
    source_record: SourceRecord,
    source_file: str,
    atom_batch: KnowledgeAtomBatch,
    execution: IngestExecutionPort,
    ingest_profile: str,
    run_id: str = "",
) -> IngestPublication:
    processing_record = build_source_processing_record(
        document,
        source_record,
        source_path=source_file,
        ingest_profile=ingest_profile,
        atom_batch=atom_batch,
        page_paths=[],
        run_id=run_id,
    )
    _validate_raw_revision_parent(vault_path, document, processing_record)
    processing_record = processing_record.model_copy(update={"page_paths": [source_projection_path(vault_path, processing_record)]})
    published = execution.publish_fact(
        FactCommit(
            processing_record=processing_record,
            atom_batch=enrich_atom_batch_evidence(atom_batch, processing_record),
            diagnostics={
                "schema_version": "ingest_diagnostics.v1",
                "compilation": result.context.get("index_metadata", {}).get("compilation", {}),
                "ambiguities": result.context.get("index_metadata", {}).get("ambiguities", []),
            },
            checkpoint_cursor=checkpoint_cursor(result),
            **session_window(document),
        )
    )
    return IngestPublication(processing_record=processing_record, published_fact=published)


def _validate_raw_revision_parent(
    vault_path: Path,
    document: SourceDocument,
    processing_record: SourceProcessingRecord,
) -> None:
    expected = str(document.metadata.get("raw_revision_parent_id") or "").strip()
    if not expected:
        return
    active = [
        record
        for record in read_active_processing_records(vault_path) or []
        if record.raw_record_id == processing_record.raw_record_id and record.window_id is None
    ]
    if len(active) != 1 or active[0].revision_id != expected:
        raise StorageConflict("The raw material changed after this revision was submitted. Open it again before saving.")


def checkpoint_cursor(result: IngestSourceResult) -> dict[str, object] | None:
    checkpoint = result.checkpoint if isinstance(result.checkpoint, dict) else {}
    checkpoint_type = checkpoint.get("checkpoint_type")
    source_file = str(checkpoint.get("source_file") or result.source_file)
    if checkpoint_type == "session":
        session_id = str(checkpoint.get("session_id") or checkpoint.get("source_id") or result.source_id)
        to_index = checkpoint.get("to_raw_index")
        if not isinstance(to_index, int):
            return None
        return _cursor(
            key=f"session:{session_id}",
            cursor_type="session",
            source_file=source_file,
            checkpoint=checkpoint,
            last_processed_raw_index=to_index,
        )
    if checkpoint_type == "source":
        source_id = str(checkpoint.get("source_id") or result.source_id)
        return _cursor(
            key=f"source:{source_id}",
            cursor_type="source",
            source_file=source_file,
            checkpoint=checkpoint,
        )
    return None


def _cursor(
    *,
    key: str,
    cursor_type: str,
    source_file: str,
    checkpoint: dict[str, object],
    last_processed_raw_index: int | None = None,
) -> dict[str, object]:
    payload = {
        "source_file": source_file,
        "last_processed_content_hash": checkpoint.get("content_hash"),
        "connector_version": checkpoint.get("connector_version"),
        "parser_version": checkpoint.get("parser_version"),
        "generated_pages": [],
        "generated_outputs": [],
    }
    if last_processed_raw_index is not None:
        payload["last_processed_raw_index"] = last_processed_raw_index
    return {"cursor_key": key, "cursor_type": cursor_type, "payload": payload}


def session_window(document: SourceDocument) -> dict[str, object]:
    if document.checkpoint.mode != "incremental" or document.source_type not in {
        "hermes_chat",
        "codex_chat",
        "openclaw_chat",
        "claude_code_chat",
        "knoarbor_chat",
        "generic_chat",
    }:
        return {}
    start = document.checkpoint.from_index
    end = document.checkpoint.to_index
    if start is None or end is None:
        return {}
    return {
        "window_id": f"{document.source_id}:{start}-{end}:{document.fingerprint.content_hash}",
        "window_from_index": start,
        "window_to_index": end,
    }
