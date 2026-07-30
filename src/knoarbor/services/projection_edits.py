from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from knoarbor.core.errors import PolicyRejection, StorageConflict
from knoarbor.core.markdown import parse_frontmatter
from knoarbor.core.schemas.ingest_execution import IngestExecutionCommand, execution_contract_hash
from knoarbor.core.schemas.knowledge_atoms import (
    KnowledgeAtomBatch,
    KnowledgeAtomObject,
    KnowledgeClaim,
    KnowledgeEvidenceSpan,
    KnowledgeRelation,
)
from knoarbor.core.schemas.projection_edit import (
    ProjectionClaimEdit,
    ProjectionClaimView,
    ProjectionEdit,
    ProjectionEditorState,
    ProjectionEntityEdit,
    ProjectionEvidenceView,
    ProjectionRelationEdit,
    ProjectionRelationObjectEdit,
)
from knoarbor.core.schemas.raw_evidence import SourceProcessingRecord
from knoarbor.runtime import vault_write_lock
from knoarbor.runtime.transactional_ingest import TransactionalIngestStore
from knoarbor.storage.materialization import VaultMaterializer
from knoarbor.storage.source_revisions import (
    RevisionDraft,
    publish_revision_draft,
    read_active_atom_batches,
    read_active_processing_records,
    read_revision_diagnostics,
)
from knoarbor.storage.vault_identity import ensure_vault_identity


def read_projection_edit(vault_path: Path, page_path: Path) -> ProjectionEditorState | None:
    """Return the structured editor state for an editable source projection."""

    vault = vault_path.expanduser().resolve()
    metadata = parse_frontmatter(page_path.read_text(encoding="utf-8"))
    if metadata.get("schema_version") != "wiki_projection.v1" or metadata.get("projection_kind") != "source_index":
        return None
    record, batch = _active_projection(vault, str(metadata.get("raw_record_id") or ""))
    return ProjectionEditorState(
        base_revision_id=record.revision_id or "",
        synthesis=batch.synthesis,
        claims=[
            ProjectionClaimView(
                id=claim.id,
                claim=claim.claim,
                evidence=[
                    ProjectionEvidenceView(
                        excerpt=span.excerpt,
                        source_path=span.source_path,
                        source_unit_id=span.source_unit_id,
                        source_unit_index=span.source_unit_index,
                    )
                    for span in claim.evidence
                ],
            )
            for claim in batch.claims
        ],
        entities=[ProjectionEntityEdit(atom_id=entity.atom_id, name=entity.name, aliases=entity.aliases) for entity in batch.entities],
        relations=[
            ProjectionRelationEdit(
                id=relation.id,
                subject=ProjectionRelationObjectEdit(atom_id=relation.subject.atom_id, name=relation.subject.name),
                predicate=relation.predicate,
                object=ProjectionRelationObjectEdit(atom_id=relation.object.atom_id, name=relation.object.name),
                source_claim_ids=relation.source_claim_ids,
            )
            for relation in batch.relations
        ],
    )


def commit_projection_edit(vault_path: Path, page_path: Path, edit: ProjectionEdit) -> str:
    """Publish an edited source projection as the next canonical revision."""

    vault = vault_path.expanduser().resolve()
    with vault_write_lock(vault):
        revision_id = _commit_projection_edit(vault, page_path, edit)
    VaultMaterializer().reconcile(vault)
    return revision_id


def _commit_projection_edit(vault: Path, page_path: Path, edit: ProjectionEdit) -> str:
    metadata = parse_frontmatter(page_path.read_text(encoding="utf-8"))
    if metadata.get("schema_version") != "wiki_projection.v1" or metadata.get("projection_kind") != "source_index":
        raise PolicyRejection("Only source_index projection pages can be edited.")
    record, batch = _active_projection(vault, str(metadata.get("raw_record_id") or ""))
    if not record.revision_id:
        raise PolicyRejection("The edited projection has no active canonical revision.")
    if edit.base_revision_id != record.revision_id:
        raise StorageConflict("The projection changed after the editor was opened. Refresh it before saving.")
    edited_batch = _edited_batch(batch, edit)
    changed_fields = _edited_fields(batch, edited_batch)
    if not changed_fields:
        return record.revision_id
    inherited_fields = [
        field
        for field in record.metadata.get("edited_fields", [])
        if field in {"synthesis", "claims", "entities", "relations"}
    ]
    edited_fields = list(dict.fromkeys([*inherited_fields, *changed_fields]))
    edited_record = record.model_copy(
        update={
            "revision_id": None,
            "atom_ids": _atom_ids(edited_batch),
            "metadata": {
                **record.metadata,
                "revision_origin": "user_edit",
                "parent_revision_id": record.revision_id,
                "edited_fields": edited_fields,
            },
        }
    )
    store = TransactionalIngestStore(vault)
    parent_revision = store.revision_manifest(record.revision_id)
    parent_command = store.command_for_task(str(parent_revision["task_id"]))
    contract = {
        "operation": "projection_edit",
        "raw_record_id": record.raw_record_id,
        "parent_revision_id": record.revision_id,
    }
    command = IngestExecutionCommand(
        generation_id=parent_command.generation_id,
        request_kind="projection_edit",
        config_path=parent_command.config_path,
        vault_id=parent_command.vault_id,
        vault_path=str(vault),
        vault_identity=ensure_vault_identity(vault),
        write=True,
        write_report=False,
        append_ledger=True,
        force_reprocess=True,
        force_invocation_id=f"projection-edit:{uuid4().hex}",
        execution_contract=contract,
        execution_contract_hash=execution_contract_hash(contract),
        factual_contract_hash=parent_command.factual_contract_hash,
    )
    task, attempt = store.submit_command(command)
    lease = store.claim(str(task["task_id"]), str(attempt["attempt_id"]), owner_id="projection-edit", lease_seconds=60)
    try:
        diagnostics = {
            **read_revision_diagnostics(vault, record.revision_id),
            "user_edit": {
                "revision_origin": "user_edit",
                "parent_revision_id": record.revision_id,
                "edited_fields": edited_record.metadata["edited_fields"],
            },
        }
        revision_id, _ = publish_revision_draft(
            vault,
            store=store,
            lease=lease,
            draft=RevisionDraft(processing_record=edited_record, atom_batch=edited_batch, diagnostics=diagnostics),
        )
        store.finish(lease, state="completed", result={"revision_id": revision_id})
    except Exception as exc:
        store.finish(lease, state="failed", error=f"{type(exc).__name__}: {exc}")
        raise
    return revision_id


def _active_projection(vault: Path, raw_record_id: str) -> tuple[SourceProcessingRecord, KnowledgeAtomBatch]:
    records = [record for record in read_active_processing_records(vault) or [] if record.raw_record_id == raw_record_id]
    if len(records) != 1 or records[0].window_id is not None:
        raise PolicyRejection("The projection does not resolve to exactly one editable canonical source.")
    record = records[0]
    batches = [batch for batch in read_active_atom_batches(vault) or [] if batch.source_record_id == record.source_record_id]
    if len(batches) != 1:
        raise PolicyRejection("The projection does not resolve to exactly one active knowledge batch.")
    return record, batches[0]


def _edited_batch(current: KnowledgeAtomBatch, edit: ProjectionEdit) -> KnowledgeAtomBatch:
    claims = _edited_claims(current, edit.claims)
    entities = _edited_entities(current, edit.entities)
    relations = _edited_relations(current, claims, entities, edit.relations)
    return current.model_copy(
        update={
            "revision_id": None,
            "synthesis": edit.synthesis,
            "claims": claims,
            "entities": entities,
            "relations": relations,
        }
    )


def _edited_claims(current: KnowledgeAtomBatch, edits: list[ProjectionClaimEdit]) -> list[KnowledgeClaim]:
    current_by_id = {claim.id: claim for claim in current.claims}
    edit_by_id = {edit.id: edit for edit in edits}
    if len(edit_by_id) != len(edits):
        raise PolicyRejection("Claim identities must be unique.")
    if set(edit_by_id) != set(current_by_id):
        raise PolicyRejection("Projection editing must retain every existing claim identity and evidence mapping.")
    return [claim.model_copy(update={"claim": edit_by_id[claim.id].claim}) for claim in current.claims]


def _edited_entities(current: KnowledgeAtomBatch, edits: list[ProjectionEntityEdit]) -> list[KnowledgeAtomObject]:
    entities: list[KnowledgeAtomObject] = []
    current_by_id = {entity.atom_id: entity for entity in current.entities if entity.atom_id}
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    for edit in edits:
        atom_id = edit.atom_id or _user_atom_id("entity", edit.name)
        if atom_id in seen_ids or edit.name.casefold() in seen_names:
            raise PolicyRejection("Entity identities and names must be unique.")
        seen_ids.add(atom_id)
        seen_names.add(edit.name.casefold())
        matched = current_by_id.get(atom_id)
        if matched is not None:
            entities.append(matched.model_copy(update={"name": edit.name, "aliases": edit.aliases}))
        else:
            entities.append(KnowledgeAtomObject(name=edit.name, atom_id=atom_id, aliases=edit.aliases))
    return entities


def _edited_relations(
    current: KnowledgeAtomBatch,
    claims: list[KnowledgeClaim],
    entities: list[KnowledgeAtomObject],
    edits: list[ProjectionRelationEdit],
) -> list[KnowledgeRelation]:
    claim_ids = {claim.id for claim in claims}
    entities_by_id = {entity.atom_id: entity for entity in entities if entity.atom_id}
    entities_by_name = {entity.name.casefold(): entity for entity in entities}
    current_by_id = {relation.id: relation for relation in current.relations}
    relations: list[KnowledgeRelation] = []
    seen_ids: set[str] = set()
    for edit in edits:
        if not edit.source_claim_ids or any(claim_id not in claim_ids for claim_id in edit.source_claim_ids):
            raise PolicyRejection("Relations must reference existing supporting claims.")
        existing = current_by_id.get(edit.id or "")
        subject = _relation_object(edit.subject, entities_by_id, entities_by_name, existing.subject if existing else None)
        object_ = _relation_object(edit.object, entities_by_id, entities_by_name, existing.object if existing else None)
        signature = f"{subject.atom_id or subject.name}|{edit.predicate}|{object_.atom_id or object_.name}"
        relation_id = edit.id or _user_atom_id("relation", signature)
        if relation_id in seen_ids:
            raise PolicyRejection("Relation identities must be unique.")
        seen_ids.add(relation_id)
        relations.append(
            KnowledgeRelation(
                id=relation_id,
                subject=subject,
                predicate=edit.predicate,
                object=object_,
                source_claim_ids=edit.source_claim_ids,
                evidence=_relation_evidence(edit.source_claim_ids, claims),
            )
        )
    return relations


def _relation_object(
    edit: ProjectionRelationObjectEdit,
    entities_by_id: dict[str, KnowledgeAtomObject],
    entities_by_name: dict[str, KnowledgeAtomObject],
    existing: KnowledgeAtomObject | None,
) -> KnowledgeAtomObject:
    if existing is not None and (existing.atom_id == edit.atom_id or existing.name.casefold() == edit.name.casefold()):
        entity = entities_by_id.get(edit.atom_id or "") or entities_by_name.get(edit.name.casefold())
        return existing.model_copy(update={"atom_id": entity.atom_id if entity else edit.atom_id, "name": entity.name if entity else edit.name})
    if edit.atom_id and edit.atom_id in entities_by_id:
        return entities_by_id[edit.atom_id].model_copy(update={"evidence": []})
    matched = entities_by_name.get(edit.name.casefold())
    if matched is not None:
        return matched.model_copy(update={"evidence": []})
    return KnowledgeAtomObject(name=edit.name, atom_id=edit.atom_id or _user_atom_id("object", edit.name))


def _relation_evidence(source_claim_ids: list[str], claims: list[KnowledgeClaim]) -> list[KnowledgeEvidenceSpan]:
    claims_by_id = {claim.id: claim for claim in claims}
    evidence = []
    seen: set[tuple[str, str | None, int | None, int | None]] = set()
    for claim_id in source_claim_ids:
        for span in claims_by_id[claim_id].evidence:
            key = (span.source_record_id, span.source_unit_id, span.char_start, span.char_end)
            if key not in seen:
                seen.add(key)
                evidence.append(span)
    return evidence


def _atom_ids(batch: KnowledgeAtomBatch) -> list[str]:
    return [
        *[entity.atom_id for entity in batch.entities if entity.atom_id],
        *[claim.id for claim in batch.claims],
        *[relation.id for relation in batch.relations],
    ]


def _edited_fields(before: KnowledgeAtomBatch, after: KnowledgeAtomBatch) -> list[str]:
    fields = []
    for field in ("synthesis", "claims", "entities", "relations"):
        if getattr(before, field) != getattr(after, field):
            fields.append(field)
    return fields


def _user_atom_id(kind: str, value: str) -> str:
    return f"{kind}:user:{sha256(value.encode('utf-8')).hexdigest()[:20]}"
