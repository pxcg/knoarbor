from __future__ import annotations

from pathlib import Path

from knoarbor.runtime.transactional_ingest import TransactionalIngestStore
from knoarbor.services.ingest_coordinator import IngestCoordinator
from knoarbor.storage.materialization import VaultMaterializer
from knoarbor.storage.source_revisions import migrate_legacy_fact_layout, prune_unreachable_fact_artifacts


class StartupReconciler:
    """Perform one finite local recovery scan for a configured vault."""

    def __init__(self, coordinator: IngestCoordinator, *, materializer: VaultMaterializer | None = None) -> None:
        self.coordinator = coordinator
        self.materializer = materializer or VaultMaterializer()

    def reconcile(self, vault_path: Path) -> None:
        vault = vault_path.expanduser().resolve()
        store = TransactionalIngestStore(vault)
        migrate_legacy_fact_layout(vault, store=store)
        prune_unreachable_fact_artifacts(vault, store=store)
        store.reap_expired_attempts()
        self.materializer.reconcile(vault)
        self.materializer.prune_unreachable_index_generations(vault)
        self.coordinator.resume_queued(vault)
