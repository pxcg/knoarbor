from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from knoarbor.core.markdown import parse_frontmatter, update_frontmatter_value
from knoarbor.core.schemas.page_identity import normalize_facet
from knoarbor.core.wiki_schema import CONTENT_PAGE_DIRS, GENERATED_VIEW_DIR
from knoarbor.runtime import vault_write_lock
from knoarbor.storage.knowledge_atom_index import knowledge_atom_index_path
from knoarbor.storage.wiki_index import update_index
from knoarbor.storage.wiki_paths import content_root


LEGACY_KNOWLEDGE_DIRS = tuple(directory for directory in CONTENT_PAGE_DIRS if directory != "sources")


class NamespaceMigrationMove(BaseModel):
    source_path: str
    target_path: str
    page_kind: str
    role: str = "knowledge_page"
    legacy_paths: list[str] = Field(default_factory=list)


class NamespaceLinkRewrite(BaseModel):
    file_path: str
    old_target: str
    new_target: str
    replacements: int


class NamespaceMigrationConflict(BaseModel):
    source_path: str
    target_path: str
    reason: str


class NamespaceMigrationResult(BaseModel):
    vault_path: str
    content_root: str
    dry_run: bool
    selected_dirs: list[str]
    planned_moves: list[NamespaceMigrationMove] = Field(default_factory=list)
    moved_paths: list[NamespaceMigrationMove] = Field(default_factory=list)
    link_rewrites: list[NamespaceLinkRewrite] = Field(default_factory=list)
    conflicts: list[NamespaceMigrationConflict] = Field(default_factory=list)
    skipped_paths: list[str] = Field(default_factory=list)
    atom_refs_updated: int = 0
    index_regenerated: bool = False
    report_path: str | None = None
    warnings: list[str] = Field(default_factory=list)

    @property
    def can_apply(self) -> bool:
        return not self.conflicts


def migrate_page_namespace(
    vault_path: Path,
    *,
    dirs: list[str] | None = None,
    apply: bool = False,
) -> NamespaceMigrationResult:
    """Move legacy typed knowledge pages to the flat page namespace.

    The operation is intentionally conservative. Source digest pages remain in
    ``sources/`` and generated views are regenerated instead of migrated.
    """

    vault = vault_path.expanduser().resolve()
    root = content_root(vault)
    selected_dirs = _selected_dirs(dirs)
    planned_moves, skipped_paths, conflicts = _plan_moves(root, selected_dirs)
    link_rewrites = _plan_link_rewrites(root, planned_moves)
    result = NamespaceMigrationResult(
        vault_path=str(vault),
        content_root=str(root),
        dry_run=not apply,
        selected_dirs=list(selected_dirs),
        planned_moves=planned_moves,
        link_rewrites=link_rewrites,
        conflicts=conflicts,
        skipped_paths=skipped_paths,
        warnings=_warnings(root, selected_dirs, conflicts),
    )
    if not apply:
        return result
    if conflicts:
        return result
    return _apply_migration(vault, root, result)


def _selected_dirs(dirs: list[str] | None) -> tuple[str, ...]:
    if not dirs:
        return LEGACY_KNOWLEDGE_DIRS
    selected: list[str] = []
    for item in dirs:
        value = item.strip().lower().replace("\\", "/").strip("/")
        if value == "sources":
            continue
        if value in LEGACY_KNOWLEDGE_DIRS and value not in selected:
            selected.append(value)
    return tuple(selected)


def _plan_moves(root: Path, selected_dirs: tuple[str, ...]) -> tuple[list[NamespaceMigrationMove], list[str], list[NamespaceMigrationConflict]]:
    planned: list[NamespaceMigrationMove] = []
    skipped: list[str] = []
    conflicts: list[NamespaceMigrationConflict] = []
    target_sources: dict[str, list[str]] = {}

    for directory in selected_dirs:
        legacy_dir = root / directory
        if not legacy_dir.exists():
            skipped.append(directory)
            continue
        for md_path in sorted(legacy_dir.glob("*.md")):
            if not md_path.is_file():
                continue
            source_path = md_path.relative_to(root).as_posix()
            target_path = md_path.name
            target_sources.setdefault(target_path, []).append(source_path)
            metadata = _safe_metadata(md_path)
            planned.append(
                NamespaceMigrationMove(
                    source_path=source_path,
                    target_path=target_path,
                    page_kind=_page_kind(directory, metadata),
                    legacy_paths=_merged_legacy_paths(metadata.get("legacy_paths"), source_path, target_path),
                )
            )

    for move in planned:
        target = root / move.target_path
        if target.exists():
            conflicts.append(
                NamespaceMigrationConflict(
                    source_path=move.source_path,
                    target_path=move.target_path,
                    reason="target already exists in flat namespace",
                )
            )
        if len(target_sources.get(move.target_path, [])) > 1:
            conflicts.append(
                NamespaceMigrationConflict(
                    source_path=move.source_path,
                    target_path=move.target_path,
                    reason="multiple legacy pages would map to the same flat filename",
                )
            )
    return planned, skipped, conflicts


def _plan_link_rewrites(root: Path, moves: list[NamespaceMigrationMove]) -> list[NamespaceLinkRewrite]:
    rewrites: list[NamespaceLinkRewrite] = []
    for md_path in _rewrite_candidate_paths(root):
        try:
            content = md_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        relative = md_path.relative_to(root).as_posix()
        for move in moves:
            _, count = replace_wikilink_targets(content, move.source_path, Path(move.target_path).stem)
            if count:
                rewrites.append(
                    NamespaceLinkRewrite(
                        file_path=relative,
                        old_target=move.source_path,
                        new_target=Path(move.target_path).stem,
                        replacements=count,
                    )
                )
    return rewrites


def _apply_migration(vault: Path, root: Path, result: NamespaceMigrationResult) -> NamespaceMigrationResult:
    moved: list[NamespaceMigrationMove] = []
    with vault_write_lock(vault):
        for move in result.planned_moves:
            source = root / move.source_path
            target = root / move.target_path
            if not source.exists() or target.exists():
                continue
            content = source.read_text(encoding="utf-8")
            content = update_frontmatter_value(content, "canonical_path", move.target_path)
            content = update_frontmatter_value(content, "legacy_paths", _frontmatter_list(move.legacy_paths))
            content = update_frontmatter_value(content, "page_kind", move.page_kind)
            content = update_frontmatter_value(content, "role", move.role)
            target.write_text(content, encoding="utf-8")
            source.unlink()
            moved.append(move)

        actual_rewrites = _rewrite_links(root, result.planned_moves)
        atom_updates = _rewrite_atom_refs(vault, result.planned_moves)

    update_index(vault)
    report_path = _write_migration_report(vault, result, moved=moved, rewrites=actual_rewrites, atom_updates=atom_updates)
    return result.model_copy(
        update={
            "dry_run": False,
            "moved_paths": moved,
            "link_rewrites": actual_rewrites,
            "atom_refs_updated": atom_updates,
            "index_regenerated": True,
            "report_path": report_path,
        }
    )


def _rewrite_links(root: Path, moves: list[NamespaceMigrationMove]) -> list[NamespaceLinkRewrite]:
    rewrites: list[NamespaceLinkRewrite] = []
    for md_path in _rewrite_candidate_paths(root):
        try:
            original = md_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        updated = original
        file_rewrites: list[NamespaceLinkRewrite] = []
        for move in moves:
            updated, count = replace_wikilink_targets(updated, move.source_path, Path(move.target_path).stem)
            if count:
                file_rewrites.append(
                    NamespaceLinkRewrite(
                        file_path=md_path.relative_to(root).as_posix(),
                        old_target=move.source_path,
                        new_target=Path(move.target_path).stem,
                        replacements=count,
                    )
                )
        if updated != original:
            md_path.write_text(updated, encoding="utf-8")
            rewrites.extend(file_rewrites)
    return rewrites


def _rewrite_atom_refs(vault: Path, moves: list[NamespaceMigrationMove]) -> int:
    path = knowledge_atom_index_path(vault)
    if not path.exists():
        return 0
    mapping = {move.source_path: move.target_path for move in moves}
    updates = 0
    output: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            output.append(line)
            continue
        page_paths = record.get("page_paths")
        if isinstance(page_paths, list):
            rewritten = [mapping.get(str(item), str(item)) for item in page_paths]
            if rewritten != page_paths:
                updates += 1
                record["page_paths"] = rewritten
        output.append(json.dumps(record, ensure_ascii=False, sort_keys=True))
    path.write_text("\n".join(output).rstrip() + ("\n" if output else ""), encoding="utf-8")
    return updates


def _write_migration_report(
    vault: Path,
    result: NamespaceMigrationResult,
    *,
    moved: list[NamespaceMigrationMove],
    rewrites: list[NamespaceLinkRewrite],
    atom_updates: int,
) -> str:
    created = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_dir = vault / "maintenance"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"page_namespace_migration_{report_id}.md"
    lines = [
        "# Page Namespace Migration Report",
        "",
        f"- created_at: {created}",
        f"- content_root: {result.content_root}",
        f"- selected_dirs: {', '.join(result.selected_dirs) or '-'}",
        f"- moved_pages: {len(moved)}",
        f"- link_rewrites: {sum(item.replacements for item in rewrites)}",
        f"- atom_refs_updated: {atom_updates}",
        "- index_regenerated: True",
        "",
        "## Moved Pages",
        "",
    ]
    lines.extend([f"- `{move.source_path}` -> `{move.target_path}` ({move.page_kind})" for move in moved] or ["- No pages moved."])
    lines.extend(["", "## Link Rewrites", ""])
    lines.extend(
        [f"- `{rewrite.file_path}`: `{rewrite.old_target}` -> `{rewrite.new_target}` ({rewrite.replacements})" for rewrite in rewrites]
        or ["- No links rewritten."]
    )
    lines.extend(["", "## Rollback Notes", ""])
    lines.extend(_rollback_notes(moved))
    report_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return report_path.relative_to(vault).as_posix()


def _rollback_notes(moved: list[NamespaceMigrationMove]) -> list[str]:
    lines = [
        "- Review this report before any rollback.",
        "- Stop KnoArbor workflows before moving files back.",
        "- Restore moved pages from the mapping below, then run `uv run knoar vaults migrate-namespace --json` to verify no unexpected plan remains.",
        "- Regenerate the index with any normal write workflow or run a lint scan after rollback.",
        "",
    ]
    lines.extend([f"- `{move.target_path}` -> `{move.source_path}`" for move in moved] or ["- No moved pages to roll back."])
    return lines


def _rewrite_candidate_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    for md_path in sorted(root.rglob("*.md")):
        if not md_path.is_file():
            continue
        relative_parts = md_path.relative_to(root).parts
        if not relative_parts:
            continue
        if relative_parts[0] == GENERATED_VIEW_DIR:
            continue
        if md_path.name in {"index.md", "log.md", "SCHEMA.md"}:
            continue
        paths.append(md_path)
    return paths


def _safe_metadata(path: Path) -> dict[str, str]:
    try:
        return parse_frontmatter(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        return {}


def _page_kind(directory: str, metadata: dict[str, str]) -> str:
    raw = metadata.get("page_kind") or metadata.get("kind") or metadata.get("type") or directory
    normalized = normalize_facet(raw)
    aliases = {
        "concepts": "concept",
        "entities": "entity",
        "workflows": "workflow",
        "comparisons": "comparison",
        "queries": "query",
        "timelines": "timeline",
        "page": "unknown",
    }
    return aliases.get(normalized, normalized or "unknown")


def _merged_legacy_paths(raw_legacy_paths: object, source_path: str, target_path: str) -> list[str]:
    paths = _metadata_list(raw_legacy_paths)
    if source_path not in paths:
        paths.append(source_path)
    return [path for path in paths if path != target_path]


def _metadata_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("[") and text.endswith("]"):
            text = text[1:-1]
        return [item.strip().strip("'\"") for item in text.split(",") if item.strip().strip("'\"")]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def _frontmatter_list(items: list[str]) -> str:
    escaped = [item.replace('"', '\\"') for item in items]
    return "[" + ", ".join(f'"{item}"' for item in escaped) + "]"


def _warnings(root: Path, selected_dirs: tuple[str, ...], conflicts: list[NamespaceMigrationConflict]) -> list[str]:
    warnings: list[str] = []
    if not root.exists():
        warnings.append("content root does not exist")
    if not selected_dirs:
        warnings.append("no legacy knowledge directories selected")
    if conflicts:
        warnings.append("conflicts must be resolved before applying migration")
    return warnings


def replace_wikilink_targets(content: str, old_target: str, new_target: str, link_text: str | None = None) -> tuple[str, int]:
    old_key = _wiki_target_key(old_target)
    replacements = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal replacements
        target = match.group("target").strip()
        alias = match.group("alias")
        if _wiki_target_key(target) != old_key:
            return match.group(0)
        replacements += 1
        suffix = "#" + target.split("#", 1)[1].strip() if "#" in target else ""
        rendered_target = new_target.strip() + suffix
        rendered_alias = link_text or alias
        return f"[[{rendered_target}|{rendered_alias}]]" if rendered_alias else f"[[{rendered_target}]]"

    updated = re.sub(r"\[\[(?P<target>[^\]|]+)(?:\|(?P<alias>[^\]]+))?\]\]", replace, content)
    return updated, replacements


def _wiki_target_key(value: str) -> str:
    target = value.strip()
    if "|" in target:
        target = target.split("|", 1)[0].strip()
    target = target.split("#", 1)[0].strip()
    if target.endswith(".md"):
        target = target[:-3]
    return target.casefold()
