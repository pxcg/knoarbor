from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from knoarbor.core.config import default_config_path, load_config
from knoarbor.core.errors import UserInputError
from knoarbor.core.vaults import VIRTUAL_ALL_VAULT_ID, concrete_vault_profile_ids, resolve_config_vault_path


@dataclass(frozen=True)
class ResolvedVault:
    path: Path
    vault_id: str | None = None
    vault_name: str | None = None


def resolve_single_vault(vault_path: str | None, vault_id: str | None, config_path: str | None) -> ResolvedVault:
    config = load_config(Path(config_path).expanduser().resolve() if config_path else default_config_path())
    path = resolve_config_vault_path(config, vault_path=vault_path, vault_id=vault_id)
    resolved_id = vault_id
    resolved_name = None
    resolved_path = path.expanduser().resolve()
    for profile_id, profile in config.vaults.profiles.items():
        if resolved_id and profile_id != resolved_id:
            continue
        if profile.path.expanduser().resolve() == resolved_path:
            resolved_id = profile_id
            resolved_name = profile.name
            break
    return ResolvedVault(path=resolved_path, vault_id=resolved_id, vault_name=resolved_name)


def resolve_vault_group(
    *,
    vault_path: str | None,
    vault_id: str | None,
    vault_ids: list[str],
    all_vaults: bool,
    config_path: str | None,
) -> list[ResolvedVault]:
    if vault_id == VIRTUAL_ALL_VAULT_ID:
        all_vaults = True
        vault_id = None
    if not all_vaults and not vault_ids:
        return [resolve_single_vault(vault_path, vault_id, config_path)]

    config = load_config(Path(config_path).expanduser().resolve() if config_path else default_config_path())
    selected_ids = concrete_vault_profile_ids(config) if all_vaults else _unique_nonempty(vault_ids)
    if not selected_ids:
        raise UserInputError("No vault_ids were provided and no configured vault profiles are available.")

    vaults: list[ResolvedVault] = []
    for selected_id in selected_ids:
        profile = config.vaults.profiles.get(selected_id)
        if profile is None:
            known = ", ".join(sorted(config.vaults.profiles)) or "none"
            raise UserInputError(f"Unknown vault_id: {selected_id}. Known vaults: {known}")
        vaults.append(ResolvedVault(path=profile.path.expanduser().resolve(), vault_id=selected_id, vault_name=profile.name))
    return vaults


def _unique_nonempty(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        text = item.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output
