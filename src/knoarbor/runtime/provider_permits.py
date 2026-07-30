from __future__ import annotations

import contextvars
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

from knoarbor.runtime.ingest_control import wait_for_ingest_admission
from knoarbor.runtime.ingest_exceptions import ProviderRateLimited
from knoarbor.runtime.provider_control import impose_provider_cooldown, provider_cooldown_until, wait_for_provider_admission


@dataclass
class _ProviderState:
    limit: int
    active_requests: int = 0
    attempt_reserved: bool = False


@dataclass(frozen=True)
class _AttemptReservation:
    key: str
    request_slots: threading.BoundedSemaphore
    vault_path: Path


@dataclass(frozen=True)
class AdmissionEpoch:
    provider_key: str
    control_version: int
    request_limit: int


_ATTEMPT_RESERVATION: contextvars.ContextVar[_AttemptReservation | None] = contextvars.ContextVar(
    "ingest_provider_attempt_reservation", default=None
)


class ProviderPermitPool:
    """Process-wide provider admission plus per-request concurrency control.

    An admitted attempt owns the provider epoch, so it cannot block on capacity
    after claiming its durable lease.  Every model request inside that epoch is
    still counted by the reservation's request semaphore, including requests
    launched through a copied thread context.
    """

    def __init__(self) -> None:
        self._states: dict[str, _ProviderState] = {}
        self._rate_limit_failures: dict[str, int] = {}
        self._condition = threading.Condition()

    @contextmanager
    def acquire(
        self,
        key: str,
        *,
        limit: int,
        vault_path: Path,
        raise_if_cancelled: Callable[[], None] | None = None,
        on_wait: Callable[[str, float], None] | None = None,
        defer_on_cooldown: bool = False,
    ) -> Iterator[AdmissionEpoch]:
        reservation = _ATTEMPT_RESERVATION.get()
        if reservation is not None and reservation.key == key:
            wait_for_ingest_admission(
                reservation.vault_path,
                raise_if_cancelled=raise_if_cancelled,
                on_wait=on_wait,
            )
            _acquire_semaphore(reservation.request_slots, raise_if_cancelled, on_wait)
            try:
                wait_for_ingest_admission(
                    reservation.vault_path,
                    raise_if_cancelled=raise_if_cancelled,
                    on_wait=on_wait,
                )
                _provider_admission(
                    key,
                    defer=defer_on_cooldown,
                    raise_if_cancelled=raise_if_cancelled,
                    on_wait=on_wait,
                )
                yield
            finally:
                reservation.request_slots.release()
            return

        self._wait_runtime_admission(vault_path, key, defer_on_cooldown, raise_if_cancelled, on_wait)
        state = self._state(key, limit)
        with self._condition:
            while state.attempt_reserved or state.active_requests >= state.limit:
                if raise_if_cancelled:
                    raise_if_cancelled()
                if on_wait:
                    on_wait("provider_busy", 0.2)
                self._condition.wait(0.2)
            state.active_requests += 1
        try:
            self._wait_runtime_admission(vault_path, key, defer_on_cooldown, raise_if_cancelled, on_wait)
            yield
        finally:
            with self._condition:
                state.active_requests -= 1
                self._condition.notify_all()

    @contextmanager
    def reserve_attempt(
        self,
        key: str,
        *,
        limit: int,
        vault_path: Path,
        raise_if_cancelled: Callable[[], None] | None = None,
        on_wait: Callable[[str, float], None] | None = None,
    ) -> Iterator[AdmissionEpoch]:
        self._wait_runtime_admission(vault_path, key, False, raise_if_cancelled, on_wait)
        state = self._state(key, limit)
        with self._condition:
            while state.attempt_reserved or state.active_requests:
                if raise_if_cancelled:
                    raise_if_cancelled()
                if on_wait:
                    on_wait("provider_busy", 0.2)
                self._condition.wait(0.2)
            state.attempt_reserved = True
            effective_limit = state.limit
        token = None
        try:
            control_version = self._wait_runtime_admission(
                vault_path, key, False, raise_if_cancelled, on_wait
            )
            token = _ATTEMPT_RESERVATION.set(
                _AttemptReservation(
                    key=key,
                    request_slots=threading.BoundedSemaphore(effective_limit),
                    vault_path=vault_path.expanduser().resolve(),
                )
            )
            yield AdmissionEpoch(
                provider_key=key,
                control_version=control_version,
                request_limit=effective_limit,
            )
        finally:
            if token is not None:
                _ATTEMPT_RESERVATION.reset(token)
            with self._condition:
                state.attempt_reserved = False
                self._condition.notify_all()

    def impose_cooldown(self, key: str, *, seconds: float | None = None) -> float:
        with self._condition:
            failures = self._rate_limit_failures.get(key, 0) + 1
            self._rate_limit_failures[key] = failures
        delay = seconds if seconds is not None else min(300.0, 15.0 * (2 ** min(failures - 1, 4)))
        return impose_provider_cooldown(key, seconds=delay)

    def record_success(self, key: str) -> None:
        with self._condition:
            self._rate_limit_failures.pop(key, None)

    def _state(self, key: str, limit: int) -> _ProviderState:
        if limit < 1:
            raise ValueError("Provider concurrency limit must be positive.")
        with self._condition:
            state = self._states.get(key)
            if state is None:
                state = _ProviderState(limit=limit)
                self._states[key] = state
            elif not state.attempt_reserved and state.active_requests == 0:
                # A new immutable attempt may select a different code-derived
                # policy. Capacity can move in either direction while the
                # provider is idle without invalidating any live permit.
                state.limit = limit
            elif limit < state.limit:
                # While work is active, only a stricter policy can take effect.
                state.limit = limit
            return state

    @staticmethod
    def _wait_runtime_admission(
        vault_path: Path,
        key: str,
        defer: bool,
        raise_if_cancelled: Callable[[], None] | None,
        on_wait: Callable[[str, float], None] | None,
    ) -> int:
        version = wait_for_ingest_admission(vault_path, raise_if_cancelled=raise_if_cancelled, on_wait=on_wait)
        _provider_admission(key, defer=defer, raise_if_cancelled=raise_if_cancelled, on_wait=on_wait)
        return version


def _acquire_semaphore(
    semaphore: threading.BoundedSemaphore,
    raise_if_cancelled: Callable[[], None] | None,
    on_wait: Callable[[str, float], None] | None,
) -> None:
    while not semaphore.acquire(timeout=0.2):
        if raise_if_cancelled:
            raise_if_cancelled()
        if on_wait:
            on_wait("provider_busy", 0.2)


provider_permit_pool = ProviderPermitPool()


def _provider_admission(
    key: str,
    *,
    defer: bool,
    raise_if_cancelled: Callable[[], None] | None,
    on_wait: Callable[[str, float], None] | None,
) -> None:
    deadline = provider_cooldown_until(key)
    if defer and deadline > time.time():
        raise ProviderRateLimited(key, deadline, RuntimeError("Provider cooldown is active."))
    wait_for_provider_admission(key, raise_if_cancelled=raise_if_cancelled, on_wait=on_wait)


def rate_limit_delay_seconds(exc: Exception) -> float | None:
    """Return a provider retry hint; the pool owns fallback backoff policy."""

    headers = getattr(getattr(exc, "response", None), "headers", None) or getattr(exc, "headers", None)
    retry_after = headers.get("retry-after") if hasattr(headers, "get") else None
    try:
        return min(300.0, max(1.0, float(retry_after)))
    except (TypeError, ValueError):
        return None
