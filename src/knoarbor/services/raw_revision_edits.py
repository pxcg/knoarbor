from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from knoarbor.core.errors import PolicyRejection, StorageConflict
from knoarbor.core.markdown import extract_heading, parse_frontmatter
from knoarbor.core.schemas.ingest_run import UnifiedIngestRequest
from knoarbor.core.schemas.raw_revision_edit import RawRevisionEdit, RawRevisionEditorState
from knoarbor.core.schemas.sources import SourceDocument
from knoarbor.core.schemas.raw_evidence import SourceProcessingRecord
from knoarbor.storage.ingest_inputs import read_input_generation
from knoarbor.storage.source_revisions import read_active_atom_batches, read_active_processing_records
from knoarbor.runtime.transactional_ingest import TransactionalIngestStore


def read_raw_revision_editor(vault_path: Path, page_path: Path) -> RawRevisionEditorState | None:
    vault = vault_path.expanduser().resolve()
    metadata = parse_frontmatter(page_path.read_text(encoding="utf-8"))
    if metadata.get("schema_version") != "wiki_projection.v1" or metadata.get("projection_kind") != "source_index":
        return None
    record = _active_source(vault, str(metadata.get("raw_record_id") or ""))
    document = _source_document(vault, record)
    if not document.content.text.strip():
        return None
    return RawRevisionEditorState(
        base_revision_id=record.revision_id or "",
        content=document.content.text,
        source_unit_count=len(record.source_units),
        evidence_span_count=_evidence_span_count(vault, record),
    )


def build_raw_revision_ingest_request(
    vault_path: Path,
    page_path: Path,
    edit: RawRevisionEdit,
    *,
    config_path: str | None,
    vault_id: str | None,
) -> UnifiedIngestRequest:
    """Build a normal ingest request for a user-authored Raw revision."""

    vault = vault_path.expanduser().resolve()
    metadata = parse_frontmatter(page_path.read_text(encoding="utf-8"))
    if metadata.get("schema_version") != "wiki_projection.v1" or metadata.get("projection_kind") != "source_index":
        raise PolicyRejection("Only source_index raw material can be revised.")
    record = _active_source(vault, str(metadata.get("raw_record_id") or ""))
    if not record.revision_id:
        raise PolicyRejection("The raw material has no active canonical revision.")
    if edit.base_revision_id != record.revision_id:
        raise StorageConflict("The raw material changed after the editor was opened. Refresh it before saving.")
    document = _source_document(vault, record)
    if edit.content == document.content.text:
        raise PolicyRejection("The revised raw material is unchanged.")
    revised = _edited_document(document, edit.content, record.revision_id)
    return UnifiedIngestRequest(
        kind="document",
        execution="queued",
        config_path=config_path,
        vault_path=None if vault_id else str(vault),
        vault_id=vault_id,
        source_document=revised,
        write=True,
        write_report=True,
        append_ledger=True,
        force_reprocess=True,
        auto_scoped_lint=True,
    )


def _active_source(vault: Path, raw_record_id: str) -> SourceProcessingRecord:
    records = [
        record
        for record in read_active_processing_records(vault) or []
        if record.raw_record_id == raw_record_id and record.window_id is None
    ]
    if len(records) != 1:
        raise PolicyRejection("The raw material does not resolve to exactly one editable canonical source.")
    return records[0]


def _source_document(vault: Path, record: SourceProcessingRecord) -> SourceDocument:
    if not record.revision_id:
        raise PolicyRejection("The raw material has no active source revision.")
    store = TransactionalIngestStore(vault)
    generation = read_input_generation(vault, store.input_generation_id_for_revision(record.revision_id))
    documents = [document for document in generation.documents if document.source_id == record.source.source_id]
    if len(documents) != 1:
        raise PolicyRejection("The canonical raw material could not be resolved from its input generation.")
    return documents[0]


def _edited_document(document: SourceDocument, content: str, parent_revision_id: str) -> SourceDocument:
    metadata = {key: value for key, value in document.metadata.items() if key != "source_unitization"}
    if document.source_type == "excerpt":
        selected_content = _excerpt_revision_fragment(content)
        metadata.update(
            {
                "title": extract_heading(content, str(metadata.get("title") or "").strip()),
                "selected_fragments": [selected_content],
                "excerpt_chars": len(selected_content),
                "excerpt_lines": len(selected_content.splitlines()),
            }
        )
    metadata.update({"revision_origin": "raw_revision_ingest", "raw_revision_parent_id": parent_revision_id})
    return document.model_copy(
        update={
            "content": document.content.model_copy(update={"text": content, "sections": []}),
            "metadata": metadata,
            "fingerprint": document.fingerprint.model_copy(
                update={"content_hash": f"sha256:{sha256(content.encode('utf-8')).hexdigest()}"}
            ),
        }
    )


def _excerpt_revision_fragment(content: str) -> str:
    lines = content.strip().splitlines()
    first = next((index for index, line in enumerate(lines) if line.strip()), None)
    if first is None or not lines[first].startswith("# "):
        return content.strip()
    second = next((index for index in range(first + 1, len(lines)) if lines[index].strip()), None)
    if second is None or lines[second].strip() != "## Selected Excerpt":
        return content.strip()
    fragment = "\n".join(lines[second + 1 :]).strip()
    return fragment or content.strip()


def _evidence_span_count(vault: Path, record: SourceProcessingRecord) -> int:
    batches = [
        batch
        for batch in read_active_atom_batches(vault) or []
        if batch.source_record_id == record.source_record_id and batch.window_id is None
    ]
    if len(batches) != 1:
        return 0
    batch = batches[0]
    return sum(len(entity.evidence) for entity in batch.entities) + sum(len(claim.evidence) for claim in batch.claims) + sum(
        len(relation.evidence) for relation in batch.relations
    )
