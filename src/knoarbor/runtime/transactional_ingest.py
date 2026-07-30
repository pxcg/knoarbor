from __future__ import annotations

import json
import sqlite3
import time
from hashlib import sha256
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from knoarbor.core.errors import StorageConflict, UserInputError
from knoarbor.core.schemas.ingest_execution import IngestExecutionCommand
from knoarbor.runtime.locks import FileLock


FORMAT_VERSION = "transactional_ingest.v5"
RECOVERABLE_TASK_STATES = frozenset({"paused_rate_limited", "recovery_needed", "failed", "partially_failed"})


@dataclass(frozen=True)
class AttemptLease:
    task_id: str
    attempt_id: str
    epoch: int
    expires_at: float


@dataclass(frozen=True)
class MaterializationToken:
    requested_epoch: int
    fact_generation: str


class TransactionalIngestStore:
    """Vault-scoped authority for ingest task, attempt, lease, and source head state."""

    def __init__(self, vault_path: Path) -> None:
        self.vault_path = vault_path.expanduser().resolve()
        self.path = self.vault_path / ".knoarbor" / "ingest.sqlite"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def submit_command(self, command: IngestExecutionCommand) -> tuple[dict[str, object], dict[str, object]]:
        payload = command.model_dump(mode="json")
        command_hash = command.command_hash()
        with self._transaction() as connection:
            existing = connection.execute(
                "select task_id, current_attempt_id from tasks where command_hash=? order by created_at limit 1",
                (command_hash,),
            ).fetchone()
            if existing:
                return self._task(connection, existing["task_id"]), self._attempt(connection, existing["current_attempt_id"])
            task_id = _id("task")
            attempt_id = _id("attempt")
            now = time.time()
            canonical = _canonical_json(payload)
            connection.execute(
                """
                insert into tasks(task_id, command, command_hash, input_generation_id,
                  state, current_attempt_id, version, created_at, updated_at)
                values(?,?,?,?,?,?,?,?,?)
                """,
                (
                    task_id,
                    canonical,
                    command_hash,
                    command.generation_id,
                    "queued",
                    attempt_id,
                    1,
                    now,
                    now,
                ),
            )
            connection.execute(
                "insert into attempts(attempt_id, task_id, ordinal, state, created_at, updated_at) values(?,?,?,?,?,?)",
                (attempt_id, task_id, 1, "queued", now, now),
            )
            return self._task(connection, task_id), self._attempt(connection, attempt_id)

    def claim(
        self,
        task_id: str,
        attempt_id: str,
        *,
        owner_id: str,
        lease_seconds: float,
        expected_admission_version: int | None = None,
    ) -> AttemptLease:
        with self._transaction() as connection:
            task = self._task(connection, task_id)
            control = connection.execute("select paused, version from ingest_control where singleton=1").fetchone()
            if control is None or bool(control["paused"]):
                raise StorageConflict("Ingest admission is paused.")
            if expected_admission_version is not None and int(control["version"]) != expected_admission_version:
                raise StorageConflict("Ingest admission changed before claim.")
            if task["current_attempt_id"] != attempt_id or task["state"] != "queued" or task["cancel_requested"]:
                raise StorageConflict("Ingest task is no longer claimable.")
            now = time.time()
            epoch = int(task["lease_epoch"] or 0) + 1
            expires = now + lease_seconds
            updated = connection.execute(
                "update tasks set state='running', version=version+1, lease_owner=?, lease_epoch=?, lease_expires_at=?, updated_at=? where task_id=? and version=?",
                (owner_id, epoch, expires, now, task_id, task["version"]),
            )
            if updated.rowcount != 1:
                raise StorageConflict("Ingest task changed while being claimed.")
            connection.execute("update attempts set state='running', updated_at=? where attempt_id=?", (now, attempt_id))
            return AttemptLease(task_id, attempt_id, epoch, expires)

    def ingest_control(self) -> dict[str, object]:
        with self._read_connection() as connection:
            row = connection.execute("select paused, version from ingest_control where singleton=1").fetchone()
            return {"schema_version": "ingest_control.v2", "paused": bool(row["paused"]), "version": int(row["version"])}

    def set_ingest_paused(self, paused: bool) -> dict[str, object]:
        with self._transaction() as connection:
            connection.execute(
                "update ingest_control set paused=?, version=version+1, updated_at=? where singleton=1",
                (int(paused), time.time()),
            )
            row = connection.execute("select paused, version from ingest_control where singleton=1").fetchone()
            return {"schema_version": "ingest_control.v2", "paused": bool(row["paused"]), "version": int(row["version"])}

    def renew(self, lease: AttemptLease, *, lease_seconds: float) -> AttemptLease:
        """Extend the current worker lease without changing its epoch."""

        with self._transaction() as connection:
            task = self._task(connection, lease.task_id)
            now = time.time()
            if (
                task["current_attempt_id"] != lease.attempt_id
                or task["state"] != "running"
                or int(task["lease_epoch"] or 0) != lease.epoch
                or task["lease_expires_at"] is None
                or float(task["lease_expires_at"]) < now
                or task["cancel_requested"]
            ):
                raise StorageConflict("Stale ingest worker cannot renew this lease.")
            expires = now + lease_seconds
            connection.execute("update tasks set lease_expires_at=?, updated_at=? where task_id=?", (expires, now, lease.task_id))
            return AttemptLease(lease.task_id, lease.attempt_id, lease.epoch, expires)

    def request_cancel(self, task_id: str, *, expected_attempt_id: str | None = None) -> dict[str, object]:
        with self._transaction() as connection:
            task = self._task(connection, task_id)
            if expected_attempt_id and task["current_attempt_id"] != expected_attempt_id:
                raise StorageConflict("Historical attempts cannot cancel the current task.")
            if task["state"] in {"completed", "cancelled"}:
                return task
            now = time.time()
            state = (
                "cancelled"
                if task["state"] in {"queued", "failed", "partially_failed", "paused_rate_limited", "recovery_needed"}
                else task["state"]
            )
            connection.execute(
                "update tasks set state=?, cancel_requested=1, version=version+1, updated_at=? where task_id=?", (state, now, task_id)
            )
            if state == "cancelled":
                connection.execute(
                    "update attempts set state='cancelled', updated_at=?, finished_at=? where attempt_id=?",
                    (now, now, task["current_attempt_id"]),
                )
            return self._task(connection, task_id)

    def fail_queued_task(
        self,
        task_id: str,
        attempt_id: str,
        *,
        error: str,
        result: dict[str, object] | None = None,
    ) -> dict[str, object]:
        with self._transaction() as connection:
            task = self._task(connection, task_id)
            if task["current_attempt_id"] != attempt_id or task["state"] != "queued":
                raise StorageConflict("Queued ingest task is no longer current.")
            now = time.time()
            connection.execute(
                "update tasks set state='failed', version=version+1, updated_at=? where task_id=?",
                (now, task_id),
            )
            connection.execute(
                "update attempts set state='failed', result=?, error=?, updated_at=?, finished_at=? where attempt_id=?",
                (_canonical_json(result or {}), error, now, now, attempt_id),
            )
            return self._task(connection, task_id)

    def admit_recovery(self, task_id: str, *, expected_attempt_id: str) -> tuple[dict[str, object], dict[str, object]]:
        with self._transaction() as connection:
            task = self._task(connection, task_id)
            expired_running = (
                task["state"] == "running" and task["lease_expires_at"] is not None and float(task["lease_expires_at"]) < time.time()
            )
            assessment = _recovery_assessment(task, self._attempt(connection, expected_attempt_id), expired_running=expired_running)
            if task["current_attempt_id"] != expected_attempt_id or not assessment["available"]:
                raise UserInputError(str(assessment["reason"]))
            attempt_id = _id("attempt")
            now = time.time()
            if expired_running:
                connection.execute(
                    "update attempts set state='recovery_needed', error=?, updated_at=?, finished_at=? where attempt_id=?",
                    ("Worker lease expired before completion.", now, now, expected_attempt_id),
                )
            ordinal = int(connection.execute("select count(*) from attempts where task_id=?", (task_id,)).fetchone()[0]) + 1
            connection.execute(
                "insert into attempts(attempt_id, task_id, ordinal, state, created_at, updated_at) values(?,?,?,?,?,?)",
                (attempt_id, task_id, ordinal, "queued", now, now),
            )
            connection.execute(
                "update tasks set state='queued', current_attempt_id=?, cancel_requested=0, version=version+1, lease_owner=null, lease_expires_at=null, updated_at=? where task_id=?",
                (attempt_id, now, task_id),
            )
            return self._task(connection, task_id), self._attempt(connection, attempt_id)

    def recovery_assessment(self, task_id: str, *, expected_attempt_id: str) -> dict[str, object]:
        with self._read_connection() as connection:
            task = self._task(connection, task_id)
            attempt = self._attempt(connection, expected_attempt_id)
            expired_running = (
                task["state"] == "running" and task["lease_expires_at"] is not None and float(task["lease_expires_at"]) < time.time()
            )
            if task["current_attempt_id"] != expected_attempt_id:
                return {
                    "available": False,
                    "reason_code": "historical_attempt",
                    "reason": "Historical ingest attempts cannot recover the current task.",
                }
            return _recovery_assessment(task, attempt, expired_running=expired_running)

    def finish(
        self,
        lease: AttemptLease,
        *,
        state: str,
        result: dict[str, object] | None = None,
        error: str | None = None,
    ) -> dict[str, object]:
        if state not in {"completed", "partially_failed", "failed", "paused_rate_limited", "cancelled", "recovery_needed"}:
            raise ValueError(f"Unsupported ingest terminal state: {state}")
        with self._transaction() as connection:
            task = self._task(connection, lease.task_id)
            if (
                task["current_attempt_id"] != lease.attempt_id
                or task["state"] != "running"
                or int(task["lease_epoch"] or 0) != lease.epoch
                or task["lease_expires_at"] is None
                or float(task["lease_expires_at"]) < time.time()
            ):
                raise StorageConflict("Stale ingest worker cannot finalize this task.")
            now = time.time()
            terminal_state = "cancelled" if task["cancel_requested"] else state
            connection.execute(
                "update attempts set state=?, result=?, error=?, updated_at=?, finished_at=? where attempt_id=?",
                (terminal_state, _canonical_json(result or {}), error, now, now, lease.attempt_id),
            )
            connection.execute(
                "update tasks set state=?, version=version+1, lease_owner=null, lease_expires_at=null, updated_at=? where task_id=?",
                (terminal_state, now, lease.task_id),
            )
            return self._task(connection, lease.task_id)

    def publish_revision(
        self,
        lease: AttemptLease,
        *,
        source_id: str,
        expected_source_head: str | None,
        revision_id: str,
        manifest_path: str,
        manifest_hash: str,
        window_id: str | None = None,
        previous_window_id: str | None = None,
        window_from_index: int | None = None,
        window_to_index: int | None = None,
        entity_contributions: dict[str, dict[str, object]] | None = None,
        checkpoint_cursor: dict[str, object] | None = None,
        input_revision_key: str | None = None,
    ) -> str:
        """Publish one staged factual revision through the task and source fences."""

        with self._transaction() as connection:
            task = self._task(connection, lease.task_id)
            if (
                task["current_attempt_id"] != lease.attempt_id
                or int(task["lease_epoch"] or 0) != lease.epoch
                or task["lease_expires_at"] is None
                or float(task["lease_expires_at"]) < time.time()
            ):
                raise StorageConflict("Stale ingest worker cannot publish a revision.")
            if task["cancel_requested"]:
                raise StorageConflict("Cancelled ingest task cannot publish a revision.")
            if input_revision_key:
                existing_revision = connection.execute(
                    "select revision_id from source_revisions where source_id=? and input_revision_key=?",
                    (source_id, input_revision_key),
                ).fetchone()
                if existing_revision is not None:
                    return str(existing_revision["revision_id"])
            head = None
            current_head = None
            if window_id is None:
                head = connection.execute("select revision_id, version from source_heads where source_id=?", (source_id,)).fetchone()
                current_head = head["revision_id"] if head else None
                if current_head != expected_source_head:
                    raise StorageConflict("Source head changed before ingest publication.")
            else:
                if window_from_index is None or window_to_index is None:
                    raise ValueError("Session window publication requires inclusive source indexes.")
                if window_to_index < window_from_index:
                    raise ValueError("Session window indexes must be ordered.")
                stream = connection.execute(
                    "select watermark_window_id, watermark_to_index, version from session_streams where source_id=?", (source_id,)
                ).fetchone()
                current_window = stream["watermark_window_id"] if stream else None
                expected_start = int(stream["watermark_to_index"]) + 1 if stream else window_from_index
                if current_window != previous_window_id or window_from_index != expected_start:
                    raise StorageConflict("Session window is not the next contiguous committed window.")
                if stream is None and previous_window_id is not None:
                    raise StorageConflict("A session baseline cannot reference a previous window.")
            now = time.time()
            connection.execute(
                "insert into source_revisions(revision_id, source_id, task_id, attempt_id, lease_epoch, manifest_path, manifest_hash, input_revision_key, window_id, previous_window_id, state, created_at) values(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    revision_id,
                    source_id,
                    lease.task_id,
                    lease.attempt_id,
                    lease.epoch,
                    manifest_path,
                    manifest_hash,
                    input_revision_key,
                    window_id,
                    previous_window_id,
                    "published",
                    now,
                ),
            )
            if head:
                updated = connection.execute(
                    "update source_heads set revision_id=?, version=version+1, updated_at=? where source_id=? and version=?",
                    (revision_id, now, source_id, head["version"]),
                )
                if updated.rowcount != 1:
                    raise StorageConflict("Source head changed during ingest publication.")
                connection.execute(
                    "update entity_contributions set active=0 where source_id=? and revision_id=?", (source_id, current_head)
                )
            else:
                if window_id is None:
                    connection.execute(
                        "insert into source_heads(source_id, revision_id, version, updated_at) values(?,?,?,?)",
                        (source_id, revision_id, 1, now),
                    )
            if window_id is not None:
                connection.execute(
                    "insert into session_window_heads(source_id, window_id, revision_id, updated_at) values(?,?,?,?)",
                    (source_id, window_id, revision_id, now),
                )
                if stream:
                    updated = connection.execute(
                        "update session_streams set watermark_window_id=?, watermark_to_index=?, version=version+1, updated_at=? where source_id=? and version=?",
                        (window_id, window_to_index, now, source_id, stream["version"]),
                    )
                    if updated.rowcount != 1:
                        raise StorageConflict("Session watermark changed during publication.")
                else:
                    connection.execute(
                        "insert into session_streams(source_id, watermark_window_id, watermark_to_index, version, updated_at) values(?,?,?,?,?)",
                        (source_id, window_id, window_to_index, 1, now),
                    )
            for entity_id, payload in (entity_contributions or {}).items():
                connection.execute(
                    "insert into entity_contributions(source_id, revision_id, window_id, entity_id, payload) values(?,?,?,?,?)",
                    (source_id, revision_id, window_id, entity_id, _canonical_json(payload)),
                )
            if checkpoint_cursor:
                cursor_key = str(checkpoint_cursor["cursor_key"])
                cursor_payload = dict(checkpoint_cursor["payload"])
                cursor_payload["factual_revision_id"] = revision_id
                connection.execute(
                    """
                    insert into source_cursors(cursor_key, cursor_type, source_id, revision_id, payload, updated_at)
                    values(?,?,?,?,?,?)
                    on conflict(cursor_key) do update set cursor_type=excluded.cursor_type, source_id=excluded.source_id,
                      revision_id=excluded.revision_id, payload=excluded.payload, updated_at=excluded.updated_at
                    """,
                    (
                        cursor_key,
                        str(checkpoint_cursor["cursor_type"]),
                        source_id,
                        revision_id,
                        _canonical_json(cursor_payload),
                        now,
                    ),
                )
            _request_materialization(connection)
            return revision_id

    def new_revision_id(self) -> str:
        return _id("revision")

    def active_entity_contributions(self) -> list[dict[str, object]]:
        with self._read_connection() as connection:
            rows = connection.execute(
                "select payload from entity_contributions where active=1 order by entity_id, source_id, revision_id"
            ).fetchall()
            return [json.loads(str(row["payload"])) for row in rows]

    def purge_source(self, source_id: str) -> list[str]:
        """Remove one source and every registered factual revision it owns."""

        with self._transaction() as connection:
            head = connection.execute("select 1 from source_heads where source_id=?", (source_id,)).fetchone()
            windows = connection.execute("select 1 from session_window_heads where source_id=? limit 1", (source_id,)).fetchone()
            if head is None and windows is None:
                raise UserInputError(f"Active source was not found: {source_id}")
            rows = connection.execute(
                """
                select source_revisions.manifest_path, source_revisions.task_id, tasks.input_generation_id
                from source_revisions
                join tasks on tasks.task_id = source_revisions.task_id
                where source_revisions.source_id=?
                """,
                (source_id,),
            ).fetchall()
            task_ids = {str(row["task_id"]) for row in rows}
            input_generation_ids = {
                str(row["input_generation_id"])
                for row in rows
                if row["input_generation_id"]
            }
            connection.execute("delete from source_heads where source_id=?", (source_id,))
            connection.execute("delete from session_window_heads where source_id=?", (source_id,))
            connection.execute("delete from session_streams where source_id=?", (source_id,))
            connection.execute("delete from source_cursors where source_id=?", (source_id,))
            connection.execute("delete from entity_contributions where source_id=?", (source_id,))
            connection.execute("delete from source_revisions where source_id=?", (source_id,))
            for task_id in task_ids:
                connection.execute("update tasks set command_hash=null where task_id=?", (task_id,))
            for generation_id in input_generation_ids:
                connection.execute("update tasks set command_hash=null where input_generation_id=?", (generation_id,))
            _request_materialization(connection)
            return [str(row["manifest_path"]) for row in rows]

    def revision_manifest(self, revision_id: str) -> dict[str, object]:
        with self._read_connection() as connection:
            row = connection.execute("select * from source_revisions where revision_id=?", (revision_id,)).fetchone()
            if row is None:
                raise UserInputError(f"Source revision was not found: {revision_id}")
            return dict(row)

    def input_generation_id_for_revision(self, revision_id: str) -> str:
        with self._read_connection() as connection:
            row = connection.execute(
                """
                select tasks.input_generation_id
                from source_revisions
                join tasks on tasks.task_id = source_revisions.task_id
                where source_revisions.revision_id = ?
                """,
                (revision_id,),
            ).fetchone()
            if row is None or not row["input_generation_id"]:
                raise UserInputError(f"Source revision input generation was not found: {revision_id}")
            return str(row["input_generation_id"])

    def revision_for_input(self, source_id: str, input_revision_key: str) -> dict[str, object] | None:
        with self._read_connection() as connection:
            row = connection.execute(
                "select * from source_revisions where source_id=? and input_revision_key=?",
                (source_id, input_revision_key),
            ).fetchone()
            return dict(row) if row is not None else None

    def materialization_state(self) -> dict[str, object]:
        with self._read_connection() as connection:
            row = connection.execute("select * from materialization_state where singleton=1").fetchone()
            if row is None:
                raise StorageConflict("Vault materialization state is missing.")
            return dict(row)

    def request_materialization(self) -> MaterializationToken:
        with self._transaction() as connection:
            return _request_materialization(connection)

    def begin_materialization(self) -> MaterializationToken | None:
        with self._transaction() as connection:
            row = connection.execute("select * from materialization_state where singleton=1").fetchone()
            if row is None:
                raise StorageConflict("Vault materialization state is missing.")
            if row["phase"] == "clean" and int(row["published_epoch"]) == int(row["requested_epoch"]):
                return None
            token = MaterializationToken(
                requested_epoch=int(row["requested_epoch"]),
                fact_generation=str(row["requested_fact_generation"]),
            )
            connection.execute(
                """
                update materialization_state set phase='building', error=null,
                  prepared_index_generation=null, prepared_wiki_fingerprint=null, updated_at=?
                where singleton=1
                """,
                (time.time(),),
            )
            return token

    def prepare_materialization(
        self,
        token: MaterializationToken,
        *,
        index_generation: str,
        wiki_fingerprint: str,
    ) -> None:
        with self._transaction() as connection:
            updated = connection.execute(
                """
                update materialization_state set phase='prepared', prepared_index_generation=?,
                  prepared_wiki_fingerprint=?, error=null, updated_at=?
                where singleton=1 and requested_epoch=? and requested_fact_generation=?
                """,
                (index_generation, wiki_fingerprint, time.time(), token.requested_epoch, token.fact_generation),
            )
            if updated.rowcount != 1:
                raise StorageConflict("Materialization token changed before preparation.")

    def finish_materialization(
        self,
        token: MaterializationToken,
        *,
        index_generation: str,
        wiki_fingerprint: str,
    ) -> bool:
        with self._transaction() as connection:
            row = connection.execute("select * from materialization_state where singleton=1").fetchone()
            if row is None:
                raise StorageConflict("Vault materialization state is missing.")
            prepared_matches = (
                row["phase"] == "prepared"
                and str(row["prepared_index_generation"] or "") == index_generation
                and str(row["prepared_wiki_fingerprint"] or "") == wiki_fingerprint
            )
            if not prepared_matches:
                raise StorageConflict("Prepared materialization generation changed before publication.")
            current = (
                int(row["requested_epoch"]) == token.requested_epoch and str(row["requested_fact_generation"]) == token.fact_generation
            )
            connection.execute(
                """
                update materialization_state set published_epoch=?, published_fact_generation=?,
                  published_index_generation=?, published_wiki_fingerprint=?, phase=?,
                  prepared_index_generation=null, prepared_wiki_fingerprint=null,
                  error=null, updated_at=? where singleton=1
                """,
                (
                    token.requested_epoch,
                    token.fact_generation,
                    index_generation,
                    wiki_fingerprint,
                    "clean" if current else "dirty",
                    time.time(),
                ),
            )
            return current

    def fail_materialization(self, token: MaterializationToken, *, error: str) -> None:
        with self._transaction() as connection:
            connection.execute(
                """
                update materialization_state set phase='failed', error=?, updated_at=?
                where singleton=1 and requested_epoch=? and requested_fact_generation=?
                """,
                (error, time.time(), token.requested_epoch, token.fact_generation),
            )

    def task(self, task_id: str) -> dict[str, object]:
        with self._read_connection() as connection:
            return _decode_row(self._task(connection, task_id), "command")

    def attempt(self, attempt_id: str) -> dict[str, object]:
        with self._read_connection() as connection:
            return _decode_row(self._attempt(connection, attempt_id), "result")

    def tasks(self) -> list[dict[str, object]]:
        with self._read_connection() as connection:
            rows = connection.execute("select * from tasks order by created_at desc").fetchall()
            return [_decode_row(dict(row), "command") for row in rows]

    def reap_expired_attempts(self) -> int:
        """Normalize expired execution leases into an explicit recoverable state."""

        with self._transaction() as connection:
            return _reap_expired_attempts(connection)

    def dispatchable_tasks(self) -> list[dict[str, object]]:
        self.reap_expired_attempts()
        with self._read_connection() as connection:
            rows = connection.execute("select * from tasks where state='queued' and cancel_requested=0 order by created_at").fetchall()
            return [_decode_row(dict(row), "command") for row in rows]

    def command_for_task(self, task_id: str) -> IngestExecutionCommand:
        task = self.task(task_id)
        command = task.get("command")
        if not isinstance(command, dict) or not command:
            raise StorageConflict(f"Ingest task has no v4 execution command: {task_id}")
        return IngestExecutionCommand.model_validate(command)

    def attempts_for_task(self, task_id: str) -> list[dict[str, object]]:
        with self._read_connection() as connection:
            rows = connection.execute("select * from attempts where task_id=? order by ordinal", (task_id,)).fetchall()
            return [_decode_row(dict(row), "result") for row in rows]

    def attempt_projections(self, *, limit: int) -> list[tuple[dict[str, object], dict[str, object]]]:
        with self._read_connection() as connection:
            rows = connection.execute(
                """
                select attempts.*, tasks.task_id as joined_task_id, tasks.command,
                  tasks.input_generation_id, tasks.current_attempt_id, tasks.cancel_requested
                from attempts join tasks on tasks.task_id=attempts.task_id
                order by attempts.updated_at desc limit ?
                """,
                (limit,),
            ).fetchall()
        return [_decode_attempt_projection(dict(row)) for row in rows]

    def attempt_projection(self, attempt_id: str) -> tuple[dict[str, object], dict[str, object]]:
        with self._read_connection() as connection:
            row = connection.execute(
                """
                select attempts.*, tasks.task_id as joined_task_id, tasks.command,
                  tasks.input_generation_id, tasks.current_attempt_id, tasks.cancel_requested
                from attempts join tasks on tasks.task_id=attempts.task_id
                where attempts.attempt_id=?
                """,
                (attempt_id,),
            ).fetchone()
        if row is None:
            raise UserInputError(f"Ingest attempt was not found: {attempt_id}")
        return _decode_attempt_projection(dict(row))

    def source_head(self, source_id: str) -> str | None:
        with self._read_connection() as connection:
            row = connection.execute("select revision_id from source_heads where source_id=?", (source_id,)).fetchone()
            return str(row["revision_id"]) if row else None

    def source_cursor(self, cursor_key: str) -> dict[str, object] | None:
        with self._read_connection() as connection:
            row = connection.execute("select * from source_cursors where cursor_key=?", (cursor_key,)).fetchone()
            return _decode_row(dict(row), "payload") if row else None

    def session_watermark(self, source_id: str) -> str | None:
        with self._read_connection() as connection:
            row = connection.execute("select watermark_window_id from session_streams where source_id=?", (source_id,)).fetchone()
            return str(row["watermark_window_id"]) if row else None

    def active_revision_manifests(self) -> list[dict[str, object]]:
        with self._read_connection() as connection:
            rows = connection.execute(
                """
                select revisions.* from source_heads heads join source_revisions revisions on revisions.revision_id=heads.revision_id where revisions.window_id is null
                union all
                select revisions.* from session_window_heads windows join source_revisions revisions on revisions.revision_id=windows.revision_id
                order by source_id, created_at
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def revision_manifests(self) -> list[dict[str, object]]:
        with self._read_connection() as connection:
            return [dict(row) for row in connection.execute("select * from source_revisions order by created_at, revision_id").fetchall()]

    def replace_revision_manifest(self, revision_id: str, *, manifest_path: str, manifest_hash: str) -> None:
        with self._transaction() as connection:
            updated = connection.execute(
                "update source_revisions set manifest_path=?, manifest_hash=? where revision_id=?",
                (manifest_path, manifest_hash, revision_id),
            )
            if updated.rowcount != 1:
                raise UserInputError(f"Source revision was not found: {revision_id}")

    def _initialize(self) -> None:
        migration_lock = self.path.with_suffix(".migration.lock")
        with FileLock(migration_lock):
            self._initialize_locked()

    def _initialize_locked(self) -> None:
        legacy_queue = self.vault_path / ".knoarbor" / "ingest_queue"
        if legacy_queue.exists():
            if not legacy_queue.is_dir() or any(legacy_queue.iterdir()):
                raise StorageConflict(
                    "Vault uses the removed JSON ingest queue format with retained data. "
                    "Migrate or archive that queue before using transactional ingest."
                )
            legacy_queue.rmdir()
        # Migration eligibility is a read-only phase.  In particular, never run
        # schema DDL (SQLite may auto-commit it) before an old-format store has
        # proved that every task and factual revision can be migrated.
        migrating_from: str | None = None
        with self._read_connection() as connection:
            existing_version = _existing_format_version(connection)
            if existing_version not in {None, "transactional_ingest.v4", FORMAT_VERSION}:
                raise StorageConflict(f"Unsupported transactional ingest store format: {existing_version}")
            if existing_version == "transactional_ingest.v4":
                migrating_from = existing_version
                _preflight_v4_tasks(connection, self.vault_path)

        with self._transaction() as connection:
            _execute_schema(
                connection,
                """
                create table if not exists ingest_format(version text primary key);
                create table if not exists ingest_migrations(
                  name text primary key, phase text not null, payload text not null, updated_at real not null);
                create table if not exists ingest_control(
                  singleton integer primary key check(singleton=1), paused integer not null,
                  version integer not null, updated_at real not null);
                create table if not exists tasks(
                  task_id text primary key, command text, command_hash text, input_generation_id text, state text not null,
                  current_attempt_id text not null, version integer not null, cancel_requested integer not null default 0,
                  lease_owner text, lease_epoch integer not null default 0, lease_expires_at real, created_at real not null, updated_at real not null);
                create table if not exists attempts(
                  attempt_id text primary key, task_id text not null, ordinal integer not null, state text not null,
                  created_at real not null, updated_at real not null, finished_at real, result text, error text);
                create table if not exists source_heads(
                  source_id text primary key, revision_id text not null, version integer not null, updated_at real not null);
                create table if not exists source_revisions(
                  revision_id text primary key, source_id text not null, task_id text not null, attempt_id text not null,
                  lease_epoch integer not null, manifest_path text not null, manifest_hash text not null,
                  input_revision_key text, window_id text, previous_window_id text, state text not null, created_at real not null);
                create table if not exists source_cursors(
                  cursor_key text primary key, cursor_type text not null, source_id text not null,
                  revision_id text not null, payload text not null, updated_at real not null);
                create table if not exists session_window_heads(
                  source_id text not null, window_id text not null, revision_id text not null, updated_at real not null,
                  primary key(source_id, window_id));
                create table if not exists session_streams(
                  source_id text primary key, watermark_window_id text not null, watermark_to_index integer not null,
                  version integer not null, updated_at real not null);
                create table if not exists entity_contributions(
                  source_id text not null, revision_id text not null, window_id text, entity_id text not null,
                  payload text not null, active integer not null default 1,
                  primary key(source_id, revision_id, window_id, entity_id));
                create table if not exists materialization_state(
                  singleton integer primary key check(singleton=1),
                  requested_epoch integer not null, published_epoch integer not null,
                  requested_fact_generation text not null, published_fact_generation text,
                  prepared_index_generation text, prepared_wiki_fingerprint text,
                  published_index_generation text, published_wiki_fingerprint text,
                  phase text not null, error text, updated_at real not null);
                create unique index if not exists task_attempt_ordinal on attempts(task_id, ordinal);
                """,
            )
            _ensure_column(connection, "source_revisions", "input_revision_key", "text")
            connection.execute(
                "insert or ignore into ingest_control(singleton, paused, version, updated_at) values(1,?,?,?)",
                (0, 1, time.time()),
            )
            connection.execute(
                """
                insert or ignore into materialization_state(
                  singleton, requested_epoch, published_epoch, requested_fact_generation,
                  phase, updated_at) values(1,?,?,?, ?,?)
                """,
                (
                    1 if existing_version is None else 0,
                    0,
                    _active_fact_generation(connection),
                    "dirty" if existing_version is None else "clean",
                    time.time(),
                ),
            )
            _ensure_column(connection, "tasks", "command", "text")
            _ensure_column(connection, "tasks", "command_hash", "text")
            _ensure_column(connection, "tasks", "input_generation_id", "text")
            connection.execute("create unique index if not exists task_command_hash on tasks(command_hash) where command_hash is not null")
            connection.execute(
                "create unique index if not exists source_input_revision on source_revisions(source_id, input_revision_key) where input_revision_key is not null"
            )
            row = connection.execute("select version from ingest_format").fetchone()
            if row is None:
                connection.execute("insert into ingest_format(version) values(?)", (FORMAT_VERSION,))
            elif row[0] == "transactional_ingest.v4":
                connection.execute("update ingest_format set version=?", (FORMAT_VERSION,))
            elif row[0] != FORMAT_VERSION:
                raise StorageConflict(f"Unsupported transactional ingest store format: {row[0]}")
            if migrating_from is not None:
                connection.execute(
                    """
                    insert into ingest_migrations(name, phase, payload, updated_at)
                    values('transactional_ingest.v5','db_migrated',?,?)
                    on conflict(name) do update set phase=excluded.phase, payload=excluded.payload, updated_at=excluded.updated_at
                    """,
                    (
                        _canonical_json(
                            {
                                "from_version": migrating_from,
                            }
                        ),
                        time.time(),
                    ),
                )
            if migrating_from is not None:
                connection.execute(
                    "update tasks set state='queued', updated_at=? where state='waiting_admission'",
                    (time.time(),),
                )
                connection.execute(
                    "update attempts set state='queued', updated_at=? where state='waiting_admission'",
                    (time.time(),),
                )
                _request_materialization(connection)
                _reap_expired_attempts(connection)
            connection.execute("drop table if exists derived_jobs")
            connection.execute("drop table if exists segment_results")
            connection.execute("drop table if exists task_commands")
            connection.execute("drop table if exists revision_materializations")
        self._resume_v5_migration()

    def _resume_v5_migration(self) -> None:
        with self._read_connection() as connection:
            row = connection.execute("select phase, payload from ingest_migrations where name='transactional_ingest.v5'").fetchone()
        if row is None or row["phase"] in {"index_ready", "complete"}:
            return
        if row["phase"] != "db_migrated":
            raise StorageConflict(f"Unsupported v5 migration phase: {row['phase']}")
        with self._transaction() as connection:
            updated = connection.execute(
                """
                update ingest_migrations set phase='index_ready', updated_at=?
                where name='transactional_ingest.v5' and phase='db_migrated'
                """,
                (time.time(),),
            )
            if updated.rowcount != 1:
                raise StorageConflict("The v5 migration phase changed while it was being completed.")

    def complete_v5_migration(self) -> None:
        with self._transaction() as connection:
            state = connection.execute("select phase from materialization_state where singleton=1").fetchone()
            if state is None or state["phase"] != "clean":
                raise StorageConflict("The v5 migration cannot complete before vault materialization is clean.")
            connection.execute(
                """
                update ingest_migrations set phase='complete', updated_at=?
                where name='transactional_ingest.v5' and phase='index_ready'
                """,
                (time.time(),),
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("pragma journal_mode=WAL")
        connection.execute("pragma foreign_keys=on")
        return connection

    @contextmanager
    def _read_connection(self):
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    def _transaction(self):
        connection = self._connect()

        class Transaction:
            def __enter__(_self):
                connection.execute("begin immediate")
                return connection

            def __exit__(_self, exc_type, _exc, _tb):
                connection.execute("rollback" if exc_type else "commit")
                connection.close()

        return Transaction()

    def _task(self, connection: sqlite3.Connection, task_id: str) -> dict[str, object]:
        row = connection.execute("select * from tasks where task_id=?", (task_id,)).fetchone()
        if row is None:
            raise UserInputError(f"Ingest task was not found: {task_id}")
        return dict(row)

    def _attempt(self, connection: sqlite3.Connection, attempt_id: str) -> dict[str, object]:
        row = connection.execute("select * from attempts where attempt_id=?", (attempt_id,)).fetchone()
        if row is None:
            raise UserInputError(f"Ingest attempt was not found: {attempt_id}")
        return dict(row)


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _preflight_v4_tasks(connection: sqlite3.Connection, vault_path: Path) -> None:
    del connection, vault_path
    raise StorageConflict(
        "transactional_ingest.v4 requires the explicit KnoArbor 2.3.1 migration path, "
        "which is not enabled until its historical fixtures pass."
    )


def _reap_expired_attempts(connection: sqlite3.Connection) -> int:
    now = time.time()
    rows = connection.execute(
        """
        select task_id, current_attempt_id, version from tasks
        where state='running' and lease_expires_at is not null and lease_expires_at < ?
        """,
        (now,),
    ).fetchall()
    for row in rows:
        connection.execute(
            """
            update attempts set state='recovery_needed', error=?, updated_at=?, finished_at=?
            where attempt_id=? and state='running'
            """,
            ("Worker lease expired before completion.", now, now, row["current_attempt_id"]),
        )
        connection.execute(
            """
            update tasks set state='recovery_needed', version=version+1,
              lease_owner=null, lease_expires_at=null, updated_at=?
            where task_id=? and state='running' and version=?
            """,
            (now, row["task_id"], row["version"]),
        )
    return len(rows)


def _active_fact_generation(connection: sqlite3.Connection) -> str:
    rows = connection.execute(
        """
        select source_id, revision_id from source_heads
        union all
        select source_id || ':' || window_id, revision_id from session_window_heads
        order by source_id
        """
    ).fetchall()
    return f"sha256:{sha256(_canonical_json([dict(row) for row in rows]).encode('utf-8')).hexdigest()}"


def _request_materialization(connection: sqlite3.Connection) -> MaterializationToken:
    fact_generation = _active_fact_generation(connection)
    row = connection.execute("select requested_epoch from materialization_state where singleton=1").fetchone()
    if row is None:
        raise StorageConflict("Vault materialization state is missing.")
    epoch = int(row["requested_epoch"]) + 1
    connection.execute(
        """
        update materialization_state set requested_epoch=?, requested_fact_generation=?,
          phase='dirty', prepared_index_generation=null, prepared_wiki_fingerprint=null,
          error=null, updated_at=? where singleton=1
        """,
        (epoch, fact_generation, time.time()),
    )
    return MaterializationToken(epoch, fact_generation)


def _recovery_assessment(
    task: dict[str, object],
    attempt: dict[str, object],
    *,
    expired_running: bool,
) -> dict[str, object]:
    state = str(task.get("state") or "")
    if expired_running or state == "recovery_needed":
        return {
            "available": True,
            "reason_code": "interrupted_attempt",
            "reason": "The ingest attempt was interrupted before completion.",
        }
    if state == "paused_rate_limited":
        return {
            "available": True,
            "reason_code": "provider_rate_limited",
            "reason": "The provider rate limit interrupted the ingest attempt.",
        }
    if state not in RECOVERABLE_TASK_STATES:
        return {
            "available": False,
            "reason_code": "task_not_recoverable",
            "reason": "The ingest task is not recoverable in its current state.",
        }

    result = attempt.get("result")
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError:
            result = {}
    result = result if isinstance(result, dict) else {}
    failure = result.get("failure")
    if isinstance(failure, dict) and failure.get("retryable") is True:
        return {
            "available": True,
            "reason_code": "retryable_run_error",
            "reason": "The ingest attempt failed with a retryable runtime error.",
        }
    failures = result.get("failures")
    if isinstance(failures, list) and any(isinstance(item, dict) and item.get("error_retryable") is True for item in failures):
        return {
            "available": True,
            "reason_code": "retryable_source_failures",
            "reason": "The ingest attempt contains retryable failed source items.",
        }
    return {
        "available": False,
        "reason_code": "no_recoverable_items",
        "reason": "The failed ingest items are not marked retryable.",
    }


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _decode_row(row: dict[str, object], *json_columns: str) -> dict[str, object]:
    for column in json_columns:
        value = row.get(column)
        if isinstance(value, str):
            try:
                row[column] = json.loads(value)
            except json.JSONDecodeError:
                row[column] = {}
    return row


def _decode_attempt_projection(payload: dict[str, object]) -> tuple[dict[str, object], dict[str, object]]:
    task_columns = {"joined_task_id", "command", "input_generation_id", "current_attempt_id", "cancel_requested"}
    attempt = _decode_row({key: value for key, value in payload.items() if key not in task_columns}, "result")
    task = _decode_row(
        {
            "task_id": payload["joined_task_id"],
            "command": payload["command"],
            "input_generation_id": payload["input_generation_id"],
            "current_attempt_id": payload["current_attempt_id"],
            "cancel_requested": payload["cancel_requested"],
        },
        "command",
    )
    return attempt, task


def _ensure_column(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {str(row["name"]) for row in connection.execute(f"pragma table_info({table})")}
    if column not in columns:
        connection.execute(f"alter table {table} add column {column} {definition}")


def _execute_schema(connection: sqlite3.Connection, schema: str) -> None:
    """Execute simple schema statements without sqlite3.executescript's implicit commit."""

    for statement in schema.split(";"):
        if statement.strip():
            connection.execute(statement)


def _existing_format_version(connection: sqlite3.Connection) -> str | None:
    table = connection.execute("select 1 from sqlite_master where type='table' and name='ingest_format'").fetchone()
    if table is None:
        return None
    row = connection.execute("select version from ingest_format").fetchone()
    return str(row[0]) if row is not None else None
