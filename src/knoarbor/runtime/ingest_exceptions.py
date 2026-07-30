from __future__ import annotations


class ProviderRateLimited(RuntimeError):
    """The attempt stopped after persisting provider admission cooldown."""

    def __init__(self, provider_key: str, cooldown_until: float, cause: Exception) -> None:
        super().__init__(f"Provider admission paused for {provider_key}.")
        self.provider_key = provider_key
        self.cooldown_until = cooldown_until
        self.__cause__ = cause
