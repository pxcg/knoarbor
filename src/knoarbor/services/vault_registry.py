from __future__ import annotations

from pathlib import Path

from knoarbor.core.config import default_config_path, load_config
from knoarbor.core.schemas.vaults import VaultListResponse, vault_profile_from_path


class VaultRegistryService:
    """Read configured vault profiles as first-class knowledge-base objects."""

    def list_vaults(self, *, config_path: str | None = None) -> VaultListResponse:
        resolved_config_path = Path(config_path).expanduser().resolve() if config_path else default_config_path()
        config = load_config(resolved_config_path)
        default_vault_id = config.active_vault_id()
        sorted_profiles = sorted(
            config.vaults.profiles.items(),
            key=lambda item: (item[0] != default_vault_id, item[0]),
        )
        return VaultListResponse(
            config_path=str(resolved_config_path),
            default_vault_id=default_vault_id,
            vaults=[
                vault_profile_from_path(
                    vault_id=vault_id,
                    name=profile.name,
                    path=profile.path,
                    active=vault_id == default_vault_id,
                )
                for vault_id, profile in sorted_profiles
            ],
        )
