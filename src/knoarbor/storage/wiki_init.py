from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from knoarbor.core.errors import StorageConflict
from knoarbor.core.wiki_schema import CONTENT_PAGE_DIRS, SYSTEM_PAGE_DIRS
from knoarbor.storage.wiki_index import ensure_log, update_index
from knoarbor.storage.wiki_paths import CONTENT_ROOT_DIR


RAW_DIRS = (
    "raw/articles",
    "raw/chats",
    "raw/datasets",
    "raw/documents/originals",
    "raw/documents/markdown",
    "raw/media",
    "raw/notes",
    "raw/papers",
    "raw/transcripts",
)


class WikiInitResult(BaseModel):
    vault_path: str
    created_paths: list[str] = Field(default_factory=list)
    existing_paths: list[str] = Field(default_factory=list)


class WikiLayoutMigrationResult(BaseModel):
    vault_path: str
    content_root: str
    moved_paths: list[str] = Field(default_factory=list)
    skipped_paths: list[str] = Field(default_factory=list)


def init_wiki_vault(vault_path: Path, *, force: bool = False) -> WikiInitResult:
    vault_path = vault_path.expanduser().resolve()
    created: list[str] = []
    existing: list[str] = []

    for relative in _initial_directories():
        _ensure_directory(vault_path, relative, created, existing)

    pages_root = vault_path / CONTENT_ROOT_DIR
    _ensure_directory(vault_path, CONTENT_ROOT_DIR, created, existing)
    for relative in CONTENT_PAGE_DIRS:
        _ensure_directory(pages_root, relative, created, existing, display_prefix=CONTENT_ROOT_DIR)

    _write_file(
        pages_root,
        "SCHEMA.md",
        _schema_template(),
        created,
        existing,
        display_prefix=CONTENT_ROOT_DIR,
        force=force,
    )
    _write_file(
        vault_path,
        ".knoarborignore",
        _ignore_template(),
        created,
        existing,
        force=force,
    )
    ensure_log(vault_path)
    update_index(vault_path)

    for relative in ("log.md", "index.md"):
        display = f"{CONTENT_ROOT_DIR}/{relative}"
        path = pages_root / relative
        if display not in created and display not in existing:
            (created if path.exists() else existing).append(display)

    return WikiInitResult(vault_path=str(vault_path), created_paths=created, existing_paths=existing)


def migrate_wiki_pages_layout(vault_path: Path) -> WikiLayoutMigrationResult:
    """Move legacy root-level wiki pages into the Obsidian-facing pages/ root."""

    vault_path = vault_path.expanduser().resolve()
    pages_root = vault_path / CONTENT_ROOT_DIR
    moved: list[str] = []
    skipped: list[str] = []
    pages_root.mkdir(parents=True, exist_ok=True)

    for relative in (*CONTENT_PAGE_DIRS, "index.md", "log.md", "SCHEMA.md"):
        source = vault_path / relative
        if not source.exists():
            skipped.append(relative)
            continue
        target = pages_root / relative
        if target.exists():
            raise StorageConflict(f"Cannot migrate `{relative}` because `{CONTENT_ROOT_DIR}/{relative}` already exists.")
        target.parent.mkdir(parents=True, exist_ok=True)
        source.rename(target)
        moved.append(relative)

    update_index(vault_path)
    return WikiLayoutMigrationResult(vault_path=str(vault_path), content_root=str(pages_root), moved_paths=moved, skipped_paths=skipped)


def _initial_directories() -> tuple[str, ...]:
    return tuple(SYSTEM_PAGE_DIRS) + RAW_DIRS


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


def _schema_template() -> str:
    return """# KnoArbor Schema

This file defines the local wiki contract for LLM and automation workflows.

## Layers

- `pages/`: Obsidian-facing wiki pages. Open this directory in Obsidian.
- `raw/`: immutable source material.
- `pages/sources/`: source digest pages.
- `pages/entities/`, `pages/concepts`, `pages/comparisons`, `pages/queries`, `pages/claims`, `pages/timelines`, `pages/workflows`: maintained wiki pages.
- `maintenance/`: human-readable run and maintenance reports.
- `.knoarbor/`: machine state such as runs, locks, indexes, ledgers, and checkpoints.

## Page Rules

- Every maintained page must have YAML frontmatter.
- Raw files are never rewritten by LLM workflows.
- `index.md` is generated and should not be manually curated.
- `log.md` is append-only.
- Page links use Obsidian `[[path/to/page|Title]]` wikilinks.

## Required Frontmatter

```yaml
created: YYYY-MM-DD HH:MM:SS
updated: YYYY-MM-DD HH:MM:SS
type: source | entity | concept | comparison | query | claim | timeline | workflow
status: draft | reviewed | archived
source: raw/path
content_hash: hash
```
"""


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
