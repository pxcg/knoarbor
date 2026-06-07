from __future__ import annotations

from pathlib import Path

from knoarbor.core.config import KnoArborConfig
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
