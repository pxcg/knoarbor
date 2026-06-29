from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from knoarbor.storage.wiki_index import ensure_log, update_machine_index
from knoarbor.storage.vault_layout import (
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


def init_wiki_vault(vault_path: Path, *, force: bool = False) -> WikiInitResult:
    vault_path = vault_path.expanduser().resolve()
    created: list[str] = []
    existing: list[str] = []

    for relative in _initial_directories():
        _ensure_directory(vault_path, relative, created, existing)

    _ensure_directory(vault_path, WIKI_ROOT_DIR, created, existing)
    _ensure_directory(vault_path, f"{WIKI_ROOT_DIR}/{WIKI_PAGES_DIR}", created, existing)
    _ensure_directory(vault_path, f"{WIKI_ROOT_DIR}/{WIKI_SOURCES_DIR}", created, existing)
    _write_file(
        vault_path,
        ".knoarborignore",
        _ignore_template(),
        created,
        existing,
        force=force,
    )
    ensure_log(vault_path)
    update_machine_index(vault_path)

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
        "raw/inbox/media",
        "raw/normalized",
        "raw/normalized/markdown",
        "raw/normalized/chats",
        "raw/normalized/excerpts",
        "raw/assets",
        "raw/assets/images",
        "raw/assets/tables",
        "raw/assets/pages",
        "raw/assets/media",
        "raw/sidecars",
        "raw/sidecars/documents",
        "raw/sidecars/sources",
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
        ".knoarbor/checkpoints",
        ".knoarbor/runs",
        ".knoarbor/queue",
        ".knoarbor/locks",
        ".knoarbor/logs",
        ".knoarbor/chat/sessions",
    )


def _ensure_directory(vault_path: Path, relative: str, created: list[str], existing: list[str], *, display_prefix: str | None = None) -> None:
    path = vault_path / relative
    display = f"{display_prefix}/{relative}" if display_prefix else relative
    if path.exists():
        existing.append(display)
        return
    path.mkdir(parents=True, exist_ok=True)
    created.append(display)


def _write_file(
    vault_path: Path,
    relative: str,
    content: str,
    created: list[str],
    existing: list[str],
    *,
    force: bool,
    display_prefix: str | None = None,
) -> None:
    path = vault_path / relative
    display = f"{display_prefix}/{relative}" if display_prefix else relative
    if path.exists() and not force:
        existing.append(display)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    created.append(display)


def _ignore_template() -> str:
    return """# Gitignore-style patterns for KnoArbor source discovery.
# Patterns are evaluated against source paths before ingest.

.DS_Store
*.tmp
*.key
*.pem
*.secret
.env
.env.*
node_modules/
__pycache__/

# Add private folders below.
# confidential/
"""
