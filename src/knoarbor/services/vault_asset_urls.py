from __future__ import annotations

from pathlib import Path
from urllib.parse import quote


def vault_asset_path(path: str) -> str:
    cleaned = path.strip().replace("\\", "/").lstrip("/")
    if cleaned.startswith("raw/derived/assets/"):
        return cleaned.removeprefix("raw/derived/assets/")
    if cleaned.startswith("assets/"):
        return cleaned.removeprefix("assets/")
    return cleaned


def vault_asset_src(path: str, vault_path: str | Path) -> str:
    asset_path = vault_asset_path(path)
    vault = Path(vault_path).expanduser().resolve()
    return f"/vault-assets/{quote(asset_path, safe='')}?vault_path={quote(str(vault), safe='')}"
