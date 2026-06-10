from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class VaultProfile(BaseModel):
    id: str
    name: str
    path: str
    active: bool = False
    exists: bool = False


class VaultListResponse(BaseModel):
    schema_version: str = "vaults.v1"
    config_path: str | None = None
    default_vault_id: str | None = None
    vaults: list[VaultProfile] = Field(default_factory=list)


def vault_profile_from_path(*, vault_id: str, name: str, path: Path, active: bool) -> VaultProfile:
    resolved = path.expanduser().resolve()
    return VaultProfile(
        id=vault_id,
        name=name,
        path=str(resolved),
        active=active,
        exists=resolved.exists() and resolved.is_dir(),
    )
