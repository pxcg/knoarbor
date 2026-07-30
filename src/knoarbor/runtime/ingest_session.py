from __future__ import annotations

import threading

from knoarbor.core.schemas.ingest_execution import FactCommit, FactIdentity, PublishedFact, fact_input_revision_key
from knoarbor.runtime.run_monitor import RunMonitor
from knoarbor.runtime.transactional_ingest import AttemptLease, TransactionalIngestStore
from knoarbor.storage.source_revisions import RevisionDraft, publish_revision_draft


class IngestExecutionSession:
    """Own the mutable attempt lease and factual publication port for one execution."""

    def __init__(
        self,
        store: TransactionalIngestStore,
        lease: AttemptLease,
        monitor: RunMonitor,
        *,
        lease_seconds: float,
    ) -> None:
        self.store = store
        self.monitor = monitor
        self.lease_seconds = lease_seconds
        self._lease = lease
        self._lock = threading.Lock()
        self._sync_monitor()

    @property
    def lease(self) -> AttemptLease:
        with self._lock:
            return self._lease

    def before_model_call(self) -> None:
        self.renew()

    def renew(self) -> AttemptLease:
        with self._lock:
            self._lease = self.store.renew(self._lease, lease_seconds=self.lease_seconds)
            self._sync_monitor()
            return self._lease

    def find_published_fact(self, identity: FactIdentity) -> PublishedFact | None:
        command = self.store.command_for_task(self.lease.task_id)
        revision = self.store.revision_for_input(identity.source_id, fact_input_revision_key(command, identity))
        if revision is None:
            return None
        generation_path = self.store.vault_path / str(revision["manifest_path"])
        return PublishedFact(revision_id=str(revision["revision_id"]), generation_path=generation_path)

    def publish_fact(self, commit: FactCommit) -> PublishedFact:
        lease = self.renew()
        revision_id, generation_path = publish_revision_draft(
            self.store.vault_path,
            store=self.store,
            lease=lease,
            draft=RevisionDraft(
                processing_record=commit.processing_record,
                atom_batch=commit.atom_batch,
                diagnostics=commit.diagnostics or {},
                window_id=commit.window_id,
                window_from_index=commit.window_from_index,
                window_to_index=commit.window_to_index,
                checkpoint_cursor=commit.checkpoint_cursor,
            ),
        )
        return PublishedFact(revision_id=revision_id, generation_path=generation_path)

    def _sync_monitor(self) -> None:
        self.monitor.metadata["ingest_lease_epoch"] = self._lease.epoch
        self.monitor.metadata["ingest_lease_expires_at"] = self._lease.expires_at
        self.monitor.metadata["ingest_lease_seconds"] = self.lease_seconds
