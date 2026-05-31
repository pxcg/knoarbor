from __future__ import annotations

import re
from pathlib import Path

from knoarbor.core.errors import StorageConflict, VaultPathError
from knoarbor.core.markdown import parse_frontmatter
from knoarbor.core.wiki_schema import AI_WRITABLE_DIRS


def slugify_title(title: str, max_length: int = 80) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|#\[\]\n\r\t]", "", normalize_page_title(title)).strip()
    cleaned = re.sub(r"\s+", "-", cleaned)
    return (cleaned[:max_length] or "untitled").rstrip(". ")


def normalize_page_title(title: str) -> str:
    return re.sub(r"\.(?:md|markdown|pdf|docx?|txt|html?)$", "", title.strip(), flags=re.IGNORECASE).strip() or "Untitled"


def normalize_source_digest_title(title: str) -> str:
    cleaned = normalize_page_title(title)
    if re.search(r"(source|source digest|source note|笔记源|来源)$", cleaned, flags=re.IGNORECASE):
        return cleaned
    return f"{cleaned or 'Untitled'} Source"


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
    if not relative.parts or relative.parts[0] not in AI_WRITABLE_DIRS:
        allowed = ", ".join(sorted(AI_WRITABLE_DIRS))
        raise VaultPathError(f"Wiki operation path must be in an AI writable directory ({allowed}): {raw_path}")
    path = (vault_path / relative).resolve()
    if not path.is_relative_to(vault_path.resolve()):
        raise VaultPathError(f"Wiki operation path escapes vault: {raw_path}")
    return path


def resolve_existing_target(vault_path: Path, target_page: str | None) -> Path | None:
    if not target_page:
        return None
    resolved_vault = vault_path.expanduser().resolve()
    try:
        raw_target = Path(target_page.strip()).expanduser()
        target_path = raw_target.resolve() if raw_target.is_absolute() else (resolved_vault / normalize_wiki_page_path(target_page)).resolve()
        target_path.relative_to(resolved_vault)
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
    output_dir = vault_path / page_dir
    if not output_dir.exists():
        return None
    for md_path in sorted(output_dir.glob("*.md")):
        try:
            metadata = parse_frontmatter(md_path.read_text(encoding="utf-8"))
        except UnicodeDecodeError:
            continue
        if metadata.get("content_hash") == digest:
            return md_path
    return None


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
