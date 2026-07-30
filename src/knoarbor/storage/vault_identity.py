from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from knoarbor.runtime import vault_write_lock


VAULT_IDENTITY_SCHEMA = "vault_identity.v1"


def vault_identity_path(vault_path: Path) -> Path:
    return vault_path.expanduser().resolve() / ".knoarbor" / "vault_identity.json"


def ensure_vault_identity(vault_path: Path) -> str:
    """Return the immutable local identity used to reject path substitution."""

    path = vault_identity_path(vault_path)
    with vault_write_lock(vault_path):
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid vault identity artifact: {path}") from exc
            value = payload.get("identity")
            if payload.get("schema_version") == VAULT_IDENTITY_SCHEMA and isinstance(value, str) and value:
                return value
            raise ValueError(f"Invalid vault identity artifact: {path}")
        identity = f"vault:{uuid4().hex}"
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps({"schema_version": VAULT_IDENTITY_SCHEMA, "identity": identity}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)
        return identity
