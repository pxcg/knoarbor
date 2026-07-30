from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from knoarbor.core.schemas.knowledge_atoms import KnowledgeAtomBatch
from knoarbor.core.schemas.raw_evidence import SourceProcessingRecord
from knoarbor.runtime.locks import vault_write_lock
from knoarbor.runtime.transactional_ingest import MaterializationToken, TransactionalIngestStore
from knoarbor.storage.index_snapshot import open_index_generation, open_index_snapshot
from knoarbor.storage.source_revisions import read_active_atom_batches, read_active_processing_records
from knoarbor.storage.wiki_projection import write_session_projection_page, write_source_projection_page
from knoarbor.storage.wiki_index import (
    _discard_machine_index,
    _prune_index_generations,
    prepare_machine_index,
    _publish_machine_index,
    wiki_tree_fingerprint,
)


class VaultMaterializer:
    """Reconcile at most one requested content epoch for a local vault."""

    def reconcile(self, vault_path: Path, *, force: bool = False) -> dict[str, object]:
        vault = vault_path.expanduser().resolve()
        store = TransactionalIngestStore(vault)
        with vault_write_lock(vault):
            if force:
                store.request_materialization()
            elif self._published_snapshot_needs_rebuild(store, vault):
                store.request_materialization()
            elif self._external_wiki_change(store, vault):
                store.request_materialization()

            resumed = self._resume_prepared(store, vault)
            if resumed is not None:
                return self._clean_state(store) if resumed else store.materialization_state()

            token = store.begin_materialization()
            if token is None:
                return self._clean_state(store)
            prepared = False
            try:
                self._write_projections(vault)
                before = wiki_tree_fingerprint(vault)
                snapshot = prepare_machine_index(vault, target_generation=token.fact_generation)
                after = wiki_tree_fingerprint(vault)
                if before != after:
                    _discard_machine_index(vault, snapshot)
                    store.request_materialization()
                    return store.materialization_state()
                store.prepare_materialization(
                    token,
                    index_generation=snapshot.generation_id,
                    wiki_fingerprint=after,
                )
                prepared = True
                _publish_machine_index(vault, snapshot)
                if store.finish_materialization(
                    token,
                    index_generation=snapshot.generation_id,
                    wiki_fingerprint=after,
                ):
                    return self._clean_state(store)
                return store.materialization_state()
            except Exception as exc:
                if not prepared:
                    store.fail_materialization(token, error=f"{type(exc).__name__}: {exc}")
                raise

    def prune_unreachable_index_generations(self, vault_path: Path) -> list[str]:
        """Remove unreachable snapshots during startup, before readers are admitted."""

        vault = vault_path.expanduser().resolve()
        store = TransactionalIngestStore(vault)
        with vault_write_lock(vault):
            state = store.materialization_state()
            current = open_index_snapshot(vault)
            protected = {
                generation
                for generation in (
                    current.generation_id if current else None,
                    state.get("published_index_generation"),
                    state.get("prepared_index_generation"),
                )
                if isinstance(generation, str) and generation
            }
            return _prune_index_generations(vault, protected=protected)

    @staticmethod
    def _published_snapshot_needs_rebuild(store: TransactionalIngestStore, vault: Path) -> bool:
        state = store.materialization_state()
        published = str(state.get("published_index_generation") or "")
        if not published:
            return False
        try:
            current = open_index_snapshot(vault)
        except RuntimeError:
            return True
        return current is None or current.generation_id != published

    @staticmethod
    def _external_wiki_change(store: TransactionalIngestStore, vault: Path) -> bool:
        state = store.materialization_state()
        published = str(state.get("published_wiki_fingerprint") or "")
        return bool(published) and published != wiki_tree_fingerprint(vault)

    @staticmethod
    def _clean_state(store: TransactionalIngestStore) -> dict[str, object]:
        state = store.materialization_state()
        if state["phase"] == "clean":
            store.complete_v5_migration()
        return state

    @staticmethod
    def _resume_prepared(store: TransactionalIngestStore, vault: Path) -> bool | None:
        state = store.materialization_state()
        if state["phase"] != "prepared":
            return None
        generation = str(state.get("prepared_index_generation") or "")
        fingerprint = str(state.get("prepared_wiki_fingerprint") or "")
        if not generation or not fingerprint:
            raise RuntimeError("Prepared materialization state is incomplete.")
        if wiki_tree_fingerprint(vault) != fingerprint:
            _discard_machine_index(vault, open_index_generation(vault, generation))
            store.request_materialization()
            return False
        token = MaterializationToken(
            requested_epoch=int(state["requested_epoch"]),
            fact_generation=str(state["requested_fact_generation"]),
        )
        _publish_machine_index(vault, open_index_generation(vault, generation))
        return store.finish_materialization(
            token,
            index_generation=generation,
            wiki_fingerprint=fingerprint,
        )

    @staticmethod
    def _write_projections(vault: Path) -> None:
        records = read_active_processing_records(vault) or []
        batches = {batch.source_record_id: batch for batch in read_active_atom_batches(vault) or []}
        sessions: dict[str, list[tuple[SourceProcessingRecord, KnowledgeAtomBatch]]] = defaultdict(list)
        for record in records:
            batch = batches.get(record.source_record_id)
            if batch is None:
                raise RuntimeError(f"Active source revision has no atom batch: {record.revision_id}")
            if record.window_id is None:
                write_source_projection_page(vault, processing_record=record, atom_batch=batch)
            else:
                sessions[record.raw_record_id].append((record, batch))
        for windows in sessions.values():
            write_session_projection_page(vault, windows=windows)
