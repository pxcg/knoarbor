from __future__ import annotations

from pathlib import Path

from knoarbor.core.config import KnoArborConfig, VaultConfig
from knoarbor.core.errors import UserInputError


def resolve_config_vault_path(config: KnoArborConfig, *, vault_path: str | None = None, vault_id: str | None = None) -> Path:
    """Resolve a caller vault selector against configured vault profiles.

    Explicit paths stay supported for automation. Profile IDs are preferred for
    multi-vault UX because they are stable across machines when config paths move.
    """

    if vault_path:
        return Path(vault_path).expanduser().resolve()
    if vault_id:
        profile = config.vaults.profiles.get(vault_id)
        if profile is None:
            known = ", ".join(sorted(config.vaults.profiles))
            raise UserInputError(f"Unknown vault_id: {vault_id}. Known vaults: {known or 'none'}")
        return profile.path.expanduser().resolve()
    return config.vault.path.expanduser().resolve()


def select_config_vault(config: KnoArborConfig, *, vault_path: str | None = None, vault_id: str | None = None) -> KnoArborConfig:
    """Return a config view whose active vault matches the caller selection."""

    resolved_path = resolve_config_vault_path(config, vault_path=vault_path, vault_id=vault_id)
    updates: dict[str, object] = {"vault": VaultConfig(path=resolved_path)}
    if vault_id:
        updates["vaults"] = config.vaults.model_copy(update={"default": vault_id})
    return config.model_copy(update=updates)
