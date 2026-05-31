from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from knoarbor.core.wiki_schema import CONTENT_PAGE_DIRS, SYSTEM_PAGE_DIRS
from knoarbor.storage.wiki_index import ensure_log, update_index


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


def init_wiki_vault(vault_path: Path, *, force: bool = False) -> WikiInitResult:
    vault_path = vault_path.expanduser().resolve()
    created: list[str] = []
    existing: list[str] = []

    for relative in _initial_directories():
        _ensure_directory(vault_path, relative, created, existing)

    _write_file(
        vault_path,
        "SCHEMA.md",
        _schema_template(),
        created,
        existing,
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
        path = vault_path / relative
        if relative not in created and relative not in existing:
            (created if path.exists() else existing).append(relative)

    return WikiInitResult(vault_path=str(vault_path), created_paths=created, existing_paths=existing)


def _initial_directories() -> tuple[str, ...]:
    return tuple(CONTENT_PAGE_DIRS) + tuple(SYSTEM_PAGE_DIRS) + RAW_DIRS


def _ensure_directory(vault_path: Path, relative: str, created: list[str], existing: list[str]) -> None:
    path = vault_path / relative
    if path.exists():
        existing.append(relative)
        return
    path.mkdir(parents=True, exist_ok=True)
    created.append(relative)


def _write_file(
    vault_path: Path,
    relative: str,
    content: str,
    created: list[str],
    existing: list[str],
    *,
    force: bool,
) -> None:
    path = vault_path / relative
    if path.exists() and not force:
        existing.append(relative)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    created.append(relative)


def _schema_template() -> str:
    return """# KnoArbor Schema

This file defines the local wiki contract for LLM and automation workflows.

## Layers

- `raw/`: immutable source material.
- `sources/`: source digest pages.
- `entities/`, `concepts`, `comparisons`, `queries`, `claims`, `timelines`, `workflows`: maintained wiki pages.
- `maintenance/`: reports, checkpoints, ledgers, and archived maintenance artifacts.

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
