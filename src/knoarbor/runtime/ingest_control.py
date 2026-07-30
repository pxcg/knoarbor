from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from knoarbor.runtime.transactional_ingest import TransactionalIngestStore


CONTROL_SCHEMA = "ingest_control.v2"


def read_ingest_control(vault_path: Path) -> dict[str, object]:
    return TransactionalIngestStore(vault_path).ingest_control()


def set_ingest_paused(vault_path: Path, paused: bool) -> dict[str, object]:
    return TransactionalIngestStore(vault_path).set_ingest_paused(paused)


def wait_for_ingest_admission(
    vault_path: Path,
    *,
    raise_if_cancelled: Callable[[], None] | None = None,
    on_wait: Callable[[str, float], None] | None = None,
    poll_seconds: float = 0.2,
) -> int:
    """Return the durable admission version observed in an unpaused state."""

    while True:
        if raise_if_cancelled:
            raise_if_cancelled()
        state = read_ingest_control(vault_path)
        if bool(state["paused"]):
            if on_wait:
                on_wait("paused", poll_seconds)
            time.sleep(poll_seconds)
            continue
        return int(state["version"])
