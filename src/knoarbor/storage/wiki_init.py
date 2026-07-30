from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from knoarbor.runtime import vault_write_lock
from knoarbor.storage.materialization import VaultMaterializer
from knoarbor.storage.wiki_index import ensure_log
from knoarbor.storage.vault_identity import ensure_vault_identity
from knoarbor.storage.vault_layout import (
    ARTIFACTS_ROOT_DIR,
    RAW_ROOT_DIR,
    WIKI_PAGES_DIR,
    WIKI_ROOT_DIR,
    WIKI_SOURCES_DIR,
    wiki_root,
)


class WikiInitResult(BaseModel):
    vault_path: str
    created_paths: list[str] = Field(default_factory=list)
    existing_paths: list[str] = Field(default_factory=list)


def init_wiki_vault(vault_path: Path) -> WikiInitResult:
    vault_path = vault_path.expanduser().resolve()
    with vault_write_lock(vault_path):
        return _init_wiki_vault_locked(vault_path)


def _init_wiki_vault_locked(vault_path: Path) -> WikiInitResult:
    created: list[str] = []
    existing: list[str] = []

    for relative in _initial_directories():
        _ensure_directory(vault_path, relative, created, existing)

    _ensure_directory(vault_path, WIKI_ROOT_DIR, created, existing)
    _ensure_directory(vault_path, f"{WIKI_ROOT_DIR}/{WIKI_PAGES_DIR}", created, existing)
    _ensure_directory(vault_path, f"{WIKI_ROOT_DIR}/{WIKI_SOURCES_DIR}", created, existing)
    ensure_log(vault_path)
    ensure_vault_identity(vault_path)
    VaultMaterializer().reconcile(vault_path, force=True)

    for relative in ("log.md",):
        display = f"{WIKI_ROOT_DIR}/{relative}"
        path = wiki_root(vault_path) / relative
        if display not in created and display not in existing:
            (created if path.exists() else existing).append(display)

    return WikiInitResult(vault_path=str(vault_path), created_paths=created, existing_paths=existing)


def _initial_directories() -> tuple[str, ...]:
    return (
        RAW_ROOT_DIR,
        "raw/inbox",
        "raw/inbox/documents",
        "raw/inbox/notes",
        "raw/inbox/chats",
        "raw/inbox/media",
        "raw/derived",
        "raw/derived/markdown",
        "raw/derived/excerpts",
        "raw/derived/assets",
        "raw/derived/assets/images",
        "raw/derived/assets/tables",
        "raw/derived/assets/pages",
        "raw/derived/assets/media",
        "raw/derived/metadata",
        "raw/derived/metadata/documents",
        "raw/derived/metadata/sources",
        ARTIFACTS_ROOT_DIR,
        "artifacts/chat",
        "maintenance",
        "maintenance/reports",
        "maintenance/reports/ingest",
        "maintenance/reports/lint",
        "maintenance/reports/query",
        "maintenance/reports/run-failure",
        "maintenance/archives",
        ".knoarbor",
        ".knoarbor/index",
        ".knoarbor/ledgers",
        ".knoarbor/runs",
        ".knoarbor/locks",
        ".knoarbor/logs",
        ".knoarbor/tmp",
        ".knoarbor/chat/sessions",
    )


def _ensure_directory(
    vault_path: Path, relative: str, created: list[str], existing: list[str], *, display_prefix: str | None = None
) -> None:
    path = vault_path / relative
    display = f"{display_prefix}/{relative}" if display_prefix else relative
    if path.exists():
        existing.append(display)
        return
    path.mkdir(parents=True, exist_ok=True)
    created.append(display)
