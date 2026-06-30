from __future__ import annotations

import re
from pathlib import Path

from knoarbor.core.errors import StorageConflict, VaultPathError
from knoarbor.core.markdown import parse_frontmatter
from knoarbor.core.wiki_schema import AI_WRITABLE_DIRS
from knoarbor.storage.vault_layout import WIKI_PAGES_DIR, WIKI_SOURCES_DIR, wiki_pages_root, wiki_sources_root


CONTENT_ROOT_DIR = WIKI_PAGES_DIR
SOURCE_DIGEST_ROOT_DIR = WIKI_SOURCES_DIR


def content_root(vault_path: Path) -> Path:
    """Return the Obsidian-facing wiki page root for a vault.

    The only supported layout is ``wiki/pages/`` for user-facing knowledge
    pages and ``wiki/sources/`` for source audit pages.
    """

    return wiki_pages_root(vault_path)


def source_digest_root(vault_path: Path) -> Path:
    return wiki_sources_root(vault_path)


def is_pages_layout(vault_path: Path) -> bool:
    return content_root(vault_path) == wiki_pages_root(vault_path)


def content_relative_path(vault_path: Path, path: Path) -> str:
    resolved = path.resolve()
    source_root = source_digest_root(vault_path).resolve()
    try:
        return f"{SOURCE_DIGEST_ROOT_DIR}/{resolved.relative_to(source_root).as_posix()}"
    except ValueError:
        return resolved.relative_to(content_root(vault_path).resolve()).as_posix()


def vault_relative_path(vault_path: Path, path: Path) -> str:
    return path.resolve().relative_to(vault_path.expanduser().resolve()).as_posix()


def content_path(vault_path: Path, relative_path: str | Path) -> Path:
    relative = Path(str(relative_path).replace("\\", "/").lstrip("/"))
    if relative.parts and relative.parts[0] == SOURCE_DIGEST_ROOT_DIR:
        return source_digest_root(vault_path).joinpath(*relative.parts[1:])
    return content_root(vault_path) / relative


def slugify_title(title: str, max_length: int = 80) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|#\[\]\n\r\t]", "", normalize_page_title(title)).strip()
    cleaned = re.sub(r"\s+", "-", cleaned)
    return (cleaned[:max_length] or "untitled").rstrip(". ")


def normalize_page_title(title: str) -> str:
    return re.sub(r"\.(?:md|markdown|pdf|docx?|txt|html?)$", "", title.strip(), flags=re.IGNORECASE).strip() or "Untitled"


def normalize_source_digest_title(title: str) -> str:
    cleaned = normalize_page_title(title)
    if re.search(r"(source digest|source note|笔记源|来源)$", cleaned, flags=re.IGNORECASE):
        return cleaned
    if re.search(r"source$", cleaned, flags=re.IGNORECASE):
        return f"{cleaned} Digest"
    return f"{cleaned or 'Untitled'} Source Digest"


def normalize_wiki_page_path(raw_path: str) -> str:
    value = raw_path.strip()
    wiki_link = re.fullmatch(r"\[\[(.+?)(?:\|.*?)?\]\]", value)
    if wiki_link:
        value = wiki_link.group(1)
    value = value.strip().lstrip("/")
    return value if value.endswith(".md") else f"{value}.md"


def resolve_wiki_page(vault_path: Path, raw_path: str) -> Path:
    relative = Path(normalize_wiki_page_path(raw_path))
    if relative.is_absolute() or ".." in relative.parts:
        raise VaultPathError(f"Invalid wiki page path: {raw_path}")
    is_flat_page = len(relative.parts) == 1 and relative.suffix == ".md"
    if not relative.parts or (relative.parts[0] not in AI_WRITABLE_DIRS and not is_flat_page):
        allowed = ", ".join(sorted(AI_WRITABLE_DIRS))
        raise VaultPathError(f"Wiki operation path must be a flat wiki page or in an AI writable directory ({allowed}): {raw_path}")
    if relative.parts and relative.parts[0] == SOURCE_DIGEST_ROOT_DIR:
        root = source_digest_root(vault_path)
        target_relative = Path(*relative.parts[1:])
    else:
        root = content_root(vault_path)
        target_relative = relative
    path = (root / target_relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise VaultPathError(f"Wiki operation path escapes vault: {raw_path}")
    return path


def resolve_existing_target(vault_path: Path, target_page: str | None) -> Path | None:
    if not target_page:
        return None
    root = source_digest_root(vault_path) if target_page.strip().replace("\\", "/").lstrip("/").startswith(f"{SOURCE_DIGEST_ROOT_DIR}/") else content_root(vault_path)
    try:
        raw_target = Path(target_page.strip()).expanduser()
        if raw_target.is_absolute():
            target_path = raw_target.resolve()
        else:
            normalized = Path(normalize_wiki_page_path(target_page))
            if normalized.parts and normalized.parts[0] == SOURCE_DIGEST_ROOT_DIR:
                normalized = Path(*normalized.parts[1:])
            target_path = (root / normalized).resolve()
        target_path.relative_to(root)
    except ValueError:
        return None
    if target_path.exists() and target_path.is_file():
        return target_path
    return None


def resolve_required_target(vault_path: Path, target_page: str | None, write_action: str) -> Path:
    target_path = resolve_existing_target(vault_path, target_page)
    if target_path:
        return target_path
    raise StorageConflict(f"{write_action} requires an existing target_page inside the vault: {target_page}")


def resolve_existing_by_hash(vault_path: Path, page_dir: str, digest: str) -> Path | None:
    for output_dir in _hash_lookup_dirs(vault_path, page_dir):
        if not output_dir.exists():
            continue
        for md_path in sorted(output_dir.glob("*.md")):
            try:
                metadata = parse_frontmatter(md_path.read_text(encoding="utf-8"))
            except UnicodeDecodeError:
                continue
            if metadata.get("content_hash") == digest:
                return md_path
    return None


def _hash_lookup_dirs(vault_path: Path, page_dir: str) -> list[Path]:
    if page_dir == "sources":
        return [source_digest_root(vault_path)]
    return [content_root(vault_path)]


def available_title_path(output_dir: Path, title: str) -> Path:
    base_name = slugify_title(title)
    candidate = output_dir / f"{base_name}.md"
    if not candidate.exists():
        return candidate

    counter = 2
    while True:
        candidate = output_dir / f"{base_name}-{counter}.md"
        if not candidate.exists():
            return candidate
        counter += 1
