from __future__ import annotations

import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable

from knoarbor.runtime.run_monitor import RunCancelled


class OperationCancellationToken:
    def __init__(self) -> None:
        self._stopped = threading.Event()

    def stop(self) -> None:
        self._stopped.set()

    def raise_if_stopped(self) -> None:
        if self._stopped.is_set():
            raise RunCancelled("Local application operation is shutting down.")


class LocalOperationScheduler:
    """Own finite local operations; it never polls for vault work."""

    def __init__(self, *, max_workers: int = 4) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="knoarbor-operation")
        self._tokens: dict[str, OperationCancellationToken] = {}
        self._futures: dict[str, Future[object]] = {}
        self._lock = threading.Lock()
        self._closed = False

    def submit(self, operation_id: str, operation: Callable[[OperationCancellationToken], object]) -> Future[object]:
        with self._lock:
            if self._closed:
                raise RuntimeError("Local operation scheduler is closed.")
            existing = self._futures.get(operation_id)
            if existing is not None and not existing.done():
                return existing
            token = OperationCancellationToken()
            future = self._executor.submit(operation, token)
            self._tokens[operation_id] = token
            self._futures[operation_id] = future
            future.add_done_callback(lambda _future: self._release(operation_id))
            return future

    def shutdown(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            tokens = list(self._tokens.values())
        for token in tokens:
            token.stop()
        self._executor.shutdown(wait=True, cancel_futures=False)
        with self._lock:
            if any(not future.done() for future in self._futures.values()):
                raise RuntimeError("Local operation scheduler returned with live work.")

    def _release(self, operation_id: str) -> None:
        with self._lock:
            self._tokens.pop(operation_id, None)
            self._futures.pop(operation_id, None)
