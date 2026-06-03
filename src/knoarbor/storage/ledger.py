from __future__ import annotations

import json
from pathlib import Path

from knoarbor.core.errors import VaultPathError
from knoarbor.runtime import vault_write_lock


def append_jsonl_ledger(vault_path: Path, ledger_path: str, record: dict[str, object]) -> Path:
    relative = Path(ledger_path.strip())
    if relative.is_absolute() or ".." in relative.parts:
        raise VaultPathError(f"Invalid ledger path: {ledger_path}")
    path = (vault_path / relative).resolve()
    if not path.is_relative_to(vault_path.resolve()):
        raise VaultPathError(f"Ledger path escapes vault: {ledger_path}")
    with vault_write_lock(vault_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def append_jsonl_records(vault_path: Path, ledger_path: str, records: list[dict[str, object]]) -> Path | None:
    if not records:
        return None
    relative = Path(ledger_path.strip())
    if relative.is_absolute() or ".." in relative.parts:
        raise VaultPathError(f"Invalid ledger path: {ledger_path}")
    path = (vault_path / relative).resolve()
    if not path.is_relative_to(vault_path.resolve()):
        raise VaultPathError(f"Ledger path escapes vault: {ledger_path}")
    with vault_write_lock(vault_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def append_operation_ledger(vault_path: Path, ledger_path: str, record: dict[str, object]) -> Path:
    return append_jsonl_ledger(vault_path, ledger_path, record)


def read_jsonl_ledger(vault_path: Path, ledger_path: str, *, limit: int | None = None) -> list[dict[str, object]]:
    relative = Path(ledger_path.strip())
    if relative.is_absolute() or ".." in relative.parts:
        raise VaultPathError(f"Invalid ledger path: {ledger_path}")
    path = (vault_path / relative).resolve()
    if not path.is_relative_to(vault_path.resolve()):
        raise VaultPathError(f"Ledger path escapes vault: {ledger_path}")
    if not path.exists():
        return []

    records: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            try:
                item = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                records.append(item)
    return records[-limit:] if limit is not None else records
