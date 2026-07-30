from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re
from typing import Any, Iterable

from knoarbor.core.schemas.raw_evidence import (
    SourceProcessingRecord,
    SourceUnitRecord,
)
from knoarbor.core.vault_selection import ResolvedVault
from knoarbor.storage.source_revisions import (
    read_active_atom_batches,
    read_active_processing_records,
)


_NUMBERED_HEADING = re.compile(
    r"^(?P<prefix>\d+(?:\.\d+)*|[A-Z](?:\.\d+)*)(?:\.(?=\s)|\s+)"
)
_CHINESE_MAJOR_HEADING = re.compile(
    r"^(?:第?[一二三四五六七八九十百]+[章节部分、.])"
)
_TRAILING_PAGE = re.compile(r"^(?P<label>.+?)\s+(?P<page>\d+)$")


@dataclass(frozen=True)
class NavigationRegionScope:
    """A locator-only document region resolved by Query."""

    region_id: str
    source_record_ids: frozenset[str]
    source_unit_ids: frozenset[str]


@dataclass(frozen=True)
class _Region:
    region_id: str
    title: str
    source_unit_ids: tuple[str, ...]


@dataclass(frozen=True)
class _CatalogIndex:
    payload: dict[str, object]
    scopes: dict[str, NavigationRegionScope]


def build_active_corpus_catalog(
    vaults: Iterable[ResolvedVault],
) -> dict[str, object]:
    """Build the compact document/section outline shown to Chat navigation."""

    indexes = [_build_vault_index(vault) for vault in vaults]
    return {
        "schema_version": "active_corpus_outline.v1",
        "authority": "query_locator_only",
        "vaults": [index.payload for index in indexes],
        "document_count": sum(
            len(index.payload["documents"])  # type: ignore[arg-type]
            for index in indexes
        ),
        "region_count": sum(len(index.scopes) for index in indexes),
    }


def resolve_navigation_region_scope(
    vault: ResolvedVault,
    region_id: str,
) -> NavigationRegionScope | None:
    return _build_vault_index(vault, include_synthesis=False).scopes.get(region_id)


def resolve_navigation_region_scopes(
    vault: ResolvedVault,
    region_ids: Iterable[str],
) -> dict[str, NavigationRegionScope]:
    scopes = _build_vault_index(vault, include_synthesis=False).scopes
    return {
        region_id: scopes[region_id]
        for region_id in dict.fromkeys(region_ids)
        if region_id in scopes
    }


def _build_vault_index(
    vault: ResolvedVault,
    *,
    include_synthesis: bool = True,
) -> _CatalogIndex:
    records = read_active_processing_records(vault.path) or []
    syntheses = {
        batch.source_record_id: batch.synthesis
        for batch in (
            read_active_atom_batches(vault.path) or []
            if include_synthesis
            else []
        )
    }
    documents: list[dict[str, object]] = []
    scopes: dict[str, NavigationRegionScope] = {}
    for record in records:
        document_region = _document_region(record, vault_id=vault.vault_id)
        sections = _section_regions(record, vault_id=vault.vault_id)
        language_hint = _record_language_hint(record)
        documents.append(
            {
                "region_id": document_region.region_id,
                "title": _source_title(record),
                "source_name": _source_name(record),
                "source_type": record.source.source_type,
                "language_hint": language_hint,
                "synthesis": syntheses.get(record.source_record_id, ""),
                "sections": [
                    {
                        "region_id": section.region_id,
                        "title": section.title,
                        "language_hint": language_hint,
                    }
                    for section in sections
                ],
            }
        )
        for region in (document_region, *sections):
            scopes[region.region_id] = NavigationRegionScope(
                region_id=region.region_id,
                source_record_ids=frozenset((record.source_record_id,)),
                source_unit_ids=frozenset(region.source_unit_ids),
            )
    documents.sort(
        key=lambda item: (
            str(item["title"]).casefold(),
            str(item["source_name"]).casefold(),
        )
    )
    return _CatalogIndex(
        payload={
            "vault_id": vault.vault_id,
            "vault_name": vault.vault_name,
            "documents": documents,
        },
        scopes=scopes,
    )


def _document_region(
    record: SourceProcessingRecord,
    *,
    vault_id: str,
) -> _Region:
    return _Region(
        region_id=_region_id(
            vault_id,
            record.source_record_id,
            "document",
        ),
        title=_source_title(record),
        source_unit_ids=tuple(
            unit.source_unit_id
            for unit in record.source_units
            if unit.source_unit_id
        ),
    )


def _section_regions(
    record: SourceProcessingRecord,
    *,
    vault_id: str,
) -> tuple[_Region, ...]:
    ordered_units = sorted(
        record.source_units,
        key=lambda unit: (unit.unit_index, unit.source_unit_id),
    )
    grouped: dict[str, list[str]] = {}
    labels: dict[str, str] = {}
    label_ranks: dict[str, tuple[int, int]] = {}
    toc_locators, body_anchor_groups = _toc_locator_index(ordered_units)
    current: str | None = None
    for index, unit in enumerate(ordered_units):
        title = unit.title.strip()
        group = _chapter_group(title)
        if index in toc_locators:
            current = None
            if group is not None:
                label, rank = _chapter_label(title)
                if group not in label_ranks or rank < label_ranks[group]:
                    labels[group] = label
                    label_ranks[group] = rank
            continue
        if group is not None:
            current = group
            label, rank = _chapter_label(title)
            if group not in label_ranks or rank < label_ranks[group]:
                labels[group] = label
                label_ranks[group] = rank
        else:
            matched_groups = body_anchor_groups.get(_heading_label_key(title), ())
            current = matched_groups[0] if len(matched_groups) == 1 else current
        if current is not None and unit.source_unit_id:
            grouped.setdefault(current, []).append(unit.source_unit_id)
    return tuple(
        _Region(
            region_id=_region_id(
                vault_id,
                record.source_record_id,
                key,
            ),
            title=labels.get(key, key),
            source_unit_ids=tuple(dict.fromkeys(grouped[key])),
        )
        for key in sorted(grouped, key=_chapter_sort_key)
        if grouped[key]
    )


def _toc_locator_index(
    ordered_units: list[SourceUnitRecord],
) -> tuple[frozenset[int], dict[str, tuple[str, ...]]]:
    """Identify TOC rows only when a later body heading confirms their label."""

    later_labels: dict[str, list[int]] = {}
    for index, unit in enumerate(ordered_units):
        key = _heading_label_key(unit.title)
        if key:
            later_labels.setdefault(key, []).append(index)

    locator_indexes: set[int] = set()
    anchor_groups: dict[str, set[str]] = {}
    for index, unit in enumerate(ordered_units):
        title = unit.title.strip()
        group = _chapter_group(title)
        trailing_page = _TRAILING_PAGE.match(title)
        if group is None or trailing_page is None:
            continue
        label, _ = _chapter_label(title)
        key = _heading_label_key(label)
        if not key or not any(other > index for other in later_labels.get(key, ())):
            continue
        locator_indexes.add(index)
        anchor_groups.setdefault(key, set()).add(group)
    return (
        frozenset(locator_indexes),
        {
            key: tuple(sorted(groups, key=_chapter_sort_key))
            for key, groups in anchor_groups.items()
        },
    )


def _heading_label_key(value: str) -> str:
    text = value.strip()
    numbered = _NUMBERED_HEADING.match(text)
    if numbered is not None:
        text = text[numbered.end() :]
    return _normalized(text)


def _chapter_group(value: str) -> str | None:
    text = value.strip()
    numbered = _NUMBERED_HEADING.match(text)
    if numbered is not None:
        root = numbered.group("prefix").split(".", 1)[0]
        if root.isdigit() and int(root) >= 100:
            return None
        return root
    if _CHINESE_MAJOR_HEADING.match(text):
        return _normalized(text)
    return None


def _chapter_label(value: str) -> tuple[str, tuple[int, int]]:
    text = value.strip()
    numbered = _NUMBERED_HEADING.match(text)
    depth = 0
    if numbered is not None:
        parts = numbered.group("prefix").split(".")
        depth = 0 if len(parts) == 1 or parts[1:] == ["0"] else len(parts)
    trailing_page = _TRAILING_PAGE.match(text)
    label = trailing_page.group("label") if trailing_page is not None else text
    return label, (depth, 1 if trailing_page is not None else 0)


def _chapter_sort_key(value: str) -> tuple[int, int | str]:
    if value.isdigit():
        return (0, int(value))
    return (1, value)


def _source_title(record: SourceProcessingRecord) -> str:
    return record.source.title.strip() or _source_name(record)


def _source_name(record: SourceProcessingRecord) -> str:
    raw_path = record.source.raw_path.strip()
    if raw_path:
        name = Path(raw_path).name
        if name:
            return name
    source_id = record.source.source_id.strip()
    if source_id:
        return source_id.rsplit("/", 1)[-1]
    return "Untitled source"


def _record_language_hint(record: SourceProcessingRecord) -> str:
    """Derive a compact locator hint without exposing source content."""

    remaining = 16_000
    samples: list[str] = [_source_title(record), _source_name(record)]
    for unit in sorted(
        record.source_units,
        key=lambda item: (item.unit_index, item.source_unit_id),
    ):
        if remaining <= 0:
            break
        value = f"{unit.title}\n{unit.content}"[:remaining]
        samples.append(value)
        remaining -= len(value)
    text = "\n".join(samples)
    cjk = sum(1 for char in text if "\u3400" <= char <= "\u9fff")
    latin = sum(1 for char in text if char.isascii() and char.isalpha())
    if not cjk and not latin:
        return "unknown"
    if cjk >= max(8, latin * 0.25):
        return "zh"
    if latin >= max(8, cjk * 4):
        return "en"
    return "mixed"


def _region_id(vault_id: str, source_record_id: str, key: str) -> str:
    digest = sha256(
        f"{vault_id}\x1f{source_record_id}\x1f{key}".encode("utf-8")
    ).hexdigest()[:20]
    return f"region_{digest}"


def _normalized(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())
