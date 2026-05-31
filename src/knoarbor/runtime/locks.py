from __future__ import annotations

import contextvars
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from knoarbor.core.errors import RuntimeCapabilityError


_HELD_LOCKS: contextvars.ContextVar[frozenset[str]] = contextvars.ContextVar("knoarbor_held_locks", default=frozenset())


class FileLock:
    """Small cross-process file lock for local vault mutations."""

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().resolve()
        self._handle = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("a+")
        _lock_file(self._handle)

    def release(self) -> None:
        if self._handle is None:
            return
        try:
            _unlock_file(self._handle)
        finally:
            self._handle.close()
            self._handle = None

    def __enter__(self) -> FileLock:
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


@contextmanager
def vault_write_lock(vault_path: Path) -> Iterator[None]:
    path = (lock_dir(vault_path) / "vault.write.lock").resolve()
    held = _HELD_LOCKS.get()
    key = str(path)
    if key in held:
        yield
        return
    token = _HELD_LOCKS.set(frozenset((*held, key)))
    try:
        with FileLock(path):
            yield
    finally:
        _HELD_LOCKS.reset(token)


def lock_dir(vault_path: Path) -> Path:
    return vault_path.expanduser().resolve() / ".knoarbor" / "locks"


def _lock_file(handle) -> None:
    try:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        return
    except ImportError:
        pass

    try:
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
    except ImportError as exc:
        raise RuntimeCapabilityError("File locking is not supported on this platform") from exc


def _unlock_file(handle) -> None:
    try:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return
    except ImportError:
        pass

    try:
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    except ImportError as exc:
        raise RuntimeCapabilityError("File locking is not supported on this platform") from exc
