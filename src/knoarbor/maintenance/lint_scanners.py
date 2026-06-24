from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from knoarbor.core.config import PrivacyConfig
from knoarbor.core.markdown import adjacent_duplicate_headings, extract_list_items, extract_section, has_unclosed_fenced_code_blocks
from knoarbor.core.redaction import detect_sensitive_text
from knoarbor.core.schemas.wiki_lint import WikiLintIssue
from knoarbor.core.wiki_schema import (
    FRONTMATTER_TYPES,
    GENERATED_VIEW_DIR,
    INDEX_EXCLUDED_DIRS,
    SYSTEM_PAGE_DIRS,
    UNIFIED_KNOWLEDGE_PAGE_DIR,
    is_index_excluded_file,
)
from knoarbor.maintenance.lint_collection import (
    extract_headings,
    extract_wiki_links,
    graph_health_stats,
    has_section,
    normalize_link_target,
    normalize_title,
    page_lookup_maps,
    resolve_link,
    resolved_paths_from_links,
)
from knoarbor.maintenance.lint_models import LintPage
from knoarbor.maintenance.lint_rules import (
    OVERDENSE_LINK_THRESHOLD,
    OVERDENSE_RELATED_THRESHOLD,
    REQUIRED_FRONTMATTER_KEYS,
    REQUIRED_SECTIONS_BY_DIR,
    WEAK_GRAPH_DIRS,
)
from knoarbor.storage.wiki_paths import content_root
from knoarbor.storage.knowledge_atom_index import KnowledgeAtomRecord, read_knowledge_atom_records
from knoarbor.storage.wiki_index import is_machine_index_stale, machine_index_dir


def lint_collected_pages(
    vault_path: Path,
    pages: list[LintPage],
    *,
    privacy_config: PrivacyConfig | None = None,
) -> tuple[list[WikiLintIssue], dict[str, Any]]:
    issues: list[WikiLintIssue] = []

    issues.extend(_lint_unexpected_markdown(vault_path))
    issues.extend(_lint_page_structure(pages))
    issues.extend(_lint_markdown_integrity(pages))
    issues.extend(_lint_adjacent_duplicate_headings(pages))
    issues.extend(_lint_index_coverage(vault_path, pages))
    issues.extend(_lint_duplicate_identity(pages))
    issues.extend(_lint_links(pages))
    issues.extend(_lint_graph_shape(pages))
    issues.extend(_lint_related_page_lists(pages))
    issues.extend(_lint_repeated_list_sections(pages))
    issues.extend(_lint_specialized_page_contracts(pages))
    issues.extend(_lint_source_pages(vault_path, pages))
    atom_issues, atom_stats = _lint_knowledge_atom_index(vault_path, pages)
    issues.extend(atom_issues)
    issues.extend(_lint_sensitive_content(pages, privacy_config or PrivacyConfig()))

    severity_counts = Counter(issue.severity for issue in issues)
    graph_health = graph_health_stats(pages)
    stats = {
        "page_count": len(pages),
        "issue_count": len(issues),
        "error_count": severity_counts.get("error", 0),
        "warning_count": severity_counts.get("warning", 0),
        "info_count": severity_counts.get("info", 0),
        "directories": dict(Counter(page.directory for page in pages)),
        "page_kinds": dict(Counter(page.page_kind for page in pages)),
        "roles": dict(Counter(page.role for page in pages)),
        "facets": dict(Counter(facet for page in pages for facet in page.facets)),
        "graph_health": graph_health,
        "knowledge_atom_index": atom_stats,
    }
    return issues, stats


def _lint_unexpected_markdown(vault_path: Path) -> list[WikiLintIssue]:
    allowed_dirs = set(FRONTMATTER_TYPES) | set(SYSTEM_PAGE_DIRS) | INDEX_EXCLUDED_DIRS | {GENERATED_VIEW_DIR}
    issues: list[WikiLintIssue] = []
    root = content_root(vault_path)
    for md_path in sorted(root.rglob("*.md")):
        relative = md_path.relative_to(root)
        if is_index_excluded_file(md_path.name):
            continue
        if len(relative.parts) == 1:
            continue
        if relative.parts and relative.parts[0] in allowed_dirs:
            continue
        issues.append(_issue("unexpected_markdown_location", "warning", relative.as_posix(), "Markdown file is outside the schema-defined wiki directories."))
    return issues


def _lint_page_structure(pages: list[LintPage]) -> list[WikiLintIssue]:
    issues: list[WikiLintIssue] = []
    for page in pages:
        if not page.content:
            issues.append(_issue("unreadable_page", "error", page.relative_path, "Page could not be read as UTF-8."))
            continue
        if not page.metadata:
            issues.append(_issue("missing_frontmatter", "error", page.relative_path, "Page is missing YAML frontmatter."))
        missing_keys = [key for key in REQUIRED_FRONTMATTER_KEYS if key not in page.metadata]
        if page.metadata and missing_keys:
            issues.append(_issue("missing_frontmatter_keys", "warning", page.relative_path, "Page frontmatter is missing expected generated-page keys.", {"missing": missing_keys}))
        if not re.search(r"^#\s+.+$", page.content, flags=re.MULTILINE):
            issues.append(_issue("missing_h1", "warning", page.relative_path, "Page is missing a top-level title."))
        expected_type = FRONTMATTER_TYPES.get(page.directory)
        actual_type = page.metadata.get("type")
        if page.directory != UNIFIED_KNOWLEDGE_PAGE_DIR and expected_type and actual_type and actual_type != expected_type:
            issues.append(_issue("frontmatter_type_mismatch", "error", page.relative_path, "Frontmatter type does not match the containing directory.", {"expected": expected_type, "actual": actual_type}))
        if page.is_source_digest and page.directory != "sources":
            issues.append(_issue("source_digest_wrong_location", "warning", page.relative_path, "Source digest pages should stay under the sources directory.", {"role": page.role, "page_kind": page.page_kind}))
        for section in _required_sections_for_page(page):
            if not has_section(page.content, section):
                issues.append(_issue("missing_required_section", "info", page.relative_path, f"Page is missing required {page.directory} section: {section}.", {"directory": page.directory, "page_type": expected_type, "section": section}))
    return issues


def _required_sections_for_page(page: LintPage) -> tuple[str, ...]:
    if page.is_source_digest:
        return REQUIRED_SECTIONS_BY_DIR.get("sources", ())
    if page.directory != UNIFIED_KNOWLEDGE_PAGE_DIR:
        return REQUIRED_SECTIONS_BY_DIR.get(page.directory, ())
    page_kind_to_legacy_dir = {
        "entity": "entities",
        "concept": "concepts",
        "comparison": "comparisons",
        "query": "queries",
        "timeline": "timelines",
        "workflow": "workflows",
    }
    legacy_dir = page_kind_to_legacy_dir.get(page.page_kind)
    return REQUIRED_SECTIONS_BY_DIR.get(legacy_dir, ())


def _lint_markdown_integrity(pages: list[LintPage]) -> list[WikiLintIssue]:
    issues: list[WikiLintIssue] = []
    for page in pages:
        if has_unclosed_fenced_code_blocks(page.content):
            issues.append(_issue("unclosed_fenced_code_block", "error", page.relative_path, "Page contains an unclosed Markdown fenced code block."))
    return issues


def _lint_adjacent_duplicate_headings(pages: list[LintPage]) -> list[WikiLintIssue]:
    issues: list[WikiLintIssue] = []
    for page in pages:
        for duplicate in adjacent_duplicate_headings(page.content):
            issues.append(_issue("adjacent_duplicate_heading", "info", page.relative_path, "Page has adjacent duplicate Markdown headings with no content between them.", duplicate))
    return issues


def _lint_index_coverage(vault_path: Path, pages: list[LintPage]) -> list[WikiLintIssue]:
    issues: list[WikiLintIssue] = []
    index_dir = machine_index_dir(vault_path)
    if not (index_dir / "manifest.json").exists() or not (index_dir / "graph_index.json").exists():
        return [_issue("missing_machine_index", "error", ".knoarbor/index", "Machine graph index is missing.")]
    if is_machine_index_stale(vault_path):
        issues.append(_issue("stale_machine_index", "warning", ".knoarbor/index", "Machine graph index is stale and should be rebuilt."))
    return issues


def _lint_duplicate_identity(pages: list[LintPage]) -> list[WikiLintIssue]:
    issues: list[WikiLintIssue] = []
    title_groups: dict[str, list[LintPage]] = defaultdict(list)
    hash_groups: dict[str, list[LintPage]] = defaultdict(list)
    stem_groups: dict[str, list[LintPage]] = defaultdict(list)
    for page in pages:
        normalized_title = re.sub(r"\s+", " ", page.title).strip().lower()
        if normalized_title:
            title_groups[normalized_title].append(page)
        content_hash = page.metadata.get("content_hash")
        if content_hash:
            hash_groups[content_hash].append(page)
        normalized_stem = normalize_title(page.stem)
        if normalized_stem:
            stem_groups[normalized_stem].append(page)

    for group in title_groups.values():
        if len(group) > 1:
            paths = [page.relative_path for page in group]
            for page in group:
                issues.append(_issue("duplicate_title", "info", page.relative_path, "Multiple pages share the same title.", {"pages": paths}))
    for group in hash_groups.values():
        if len(group) > 1:
            paths = [page.relative_path for page in group]
            for page in group:
                issues.append(_issue("duplicate_content_hash", "warning", page.relative_path, "Multiple pages share the same content hash.", {"pages": paths}))
    for group in stem_groups.values():
        directories = {page.directory for page in group}
        if len(group) > 1 and len(directories) > 1:
            paths = [page.relative_path for page in group]
            for page in group:
                issues.append(_issue("path_alias_conflict", "info", page.relative_path, "Multiple pages share the same filename stem across directories, which can make short wikilinks ambiguous.", {"pages": paths}))
    return issues


def _lint_links(pages: list[LintPage]) -> list[WikiLintIssue]:
    pages_by_relative, pages_by_stem, pages_by_title = page_lookup_maps(pages)
    incoming_links: dict[str, set[str]] = defaultdict(set)
    issues: list[WikiLintIssue] = []

    for page in pages:
        for raw_link in page.links:
            target = normalize_link_target(raw_link)
            if not target:
                continue
            resolved = resolve_link(target, pages_by_relative, pages_by_stem, pages_by_title)
            if len(resolved) == 0:
                issues.append(_issue("broken_wikilink", "error", page.relative_path, "Wiki link target does not exist.", {"target": raw_link}))
            elif len(resolved) > 1:
                issues.append(_issue("ambiguous_wikilink", "warning", page.relative_path, "Wiki link matches multiple pages by title/stem.", {"target": raw_link, "matches": [item.relative_path for item in resolved]}))
            else:
                incoming_links[resolved[0].relative_path].add(page.relative_path)

    for page in pages:
        if page.directory == "maintenance":
            continue
        if page.relative_path not in incoming_links:
            issues.append(_issue("orphan_page", "info", page.relative_path, "No other wiki page links to this page."))

    return issues


def _lint_graph_shape(pages: list[LintPage]) -> list[WikiLintIssue]:
    pages_by_relative, pages_by_stem, pages_by_title = page_lookup_maps(pages)
    incoming: dict[str, set[str]] = defaultdict(set)
    outgoing: dict[str, set[str]] = defaultdict(set)
    issues: list[WikiLintIssue] = []

    for page in pages:
        for raw_link in page.links:
            target = normalize_link_target(raw_link)
            resolved = resolve_link(target, pages_by_relative, pages_by_stem, pages_by_title)
            if len(resolved) != 1:
                continue
            target_path = resolved[0].relative_path
            if target_path == page.relative_path:
                continue
            outgoing[page.relative_path].add(target_path)
            incoming[target_path].add(page.relative_path)

    for page in pages:
        if (page.is_knowledge_page or page.directory in WEAK_GRAPH_DIRS) and not incoming.get(page.relative_path) and not outgoing.get(page.relative_path):
            issues.append(_issue("weak_link_graph", "info", page.relative_path, "Generated knowledge page has no resolved incoming or outgoing wiki links.", {"incoming_count": 0, "outgoing_count": 0}))

        related_count = len(extract_wiki_links(extract_section(page.content, "Related Pages")))
        outgoing_count = len(outgoing.get(page.relative_path, set()))
        if related_count > OVERDENSE_RELATED_THRESHOLD or outgoing_count > OVERDENSE_LINK_THRESHOLD:
            issues.append(_issue("overdense_link_graph", "info", page.relative_path, "Page has a dense link graph that may need relationship pruning or section organization.", {"related_count": related_count, "resolved_outgoing_count": outgoing_count, "related_threshold": OVERDENSE_RELATED_THRESHOLD, "outgoing_threshold": OVERDENSE_LINK_THRESHOLD}))
    return issues


def _lint_source_pages(vault_path: Path, pages: list[LintPage]) -> list[WikiLintIssue]:
    issues: list[WikiLintIssue] = []
    pages_by_relative, pages_by_stem, pages_by_title = page_lookup_maps(pages)
    source_digest_by_source: dict[str, LintPage] = {}
    knowledge_page_paths = {page.relative_path for page in pages if page.is_knowledge_page}
    for page in pages:
        if not page.is_source_digest:
            continue
        for source in _page_sources(page):
            source_digest_by_source[source] = page
    knowledge_pages_by_source: dict[str, list[LintPage]] = defaultdict(list)
    for page in pages:
        for source in _page_sources(page):
            if page.is_knowledge_page and source.startswith("raw/"):
                knowledge_pages_by_source[source].append(page)

    for page in pages:
        sources = _page_sources(page)
        raw_sources = [source for source in sources if source.startswith("raw/")]
        if page.metadata.get("source") and has_section(page.content, "Source"):
            section_sources = extract_list_items(extract_section(page.content, "Source"))
            for source in _metadata_sources(page.metadata.get("source")):
                if source.startswith("raw/") and source not in section_sources:
                    issues.append(_issue("source_section_mismatch", "info", page.relative_path, "Frontmatter source is missing from the Source section.", {"source": source, "section_sources": section_sources}))

        if page.is_source_digest:
            for source in raw_sources:
                if not (vault_path / source).exists():
                    issues.append(_issue("missing_raw_source", "warning", page.relative_path, "Source digest points to a missing raw file.", {"source": source}))
            expected_knowledge_pages = [item for source in raw_sources for item in knowledge_pages_by_source.get(source, [])]
            if not expected_knowledge_pages:
                related_paths = resolved_paths_from_links(page.links, pages_by_relative, pages_by_stem, pages_by_title)
                if not related_paths.intersection(knowledge_page_paths):
                    issues.append(_issue("source_without_knowledge_links", "info", page.relative_path, "Source digest does not link to any generated knowledge page."))
            continue

        for source in raw_sources:
            if not page.is_knowledge_page:
                continue
            source_digest = source_digest_by_source.get(source)
            if not source_digest:
                issues.append(_issue("knowledge_without_source_digest", "info", page.relative_path, "Generated knowledge page points to a raw source without a matching source digest page.", {"source": source}))
                continue
    return issues


def _metadata_sources(value: object) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _page_sources(page: LintPage) -> list[str]:
    sources: list[str] = []
    for source in [
        *_metadata_sources(page.metadata.get("source")),
        *_evidence_sources(page.content),
        *extract_list_items(extract_section(page.content, "Source")),
        *extract_list_items(extract_section(page.content, "Raw Source")),
    ]:
        text = source.strip().strip("`")
        if text.lower().startswith("raw source:"):
            text = text.split(":", 1)[1].strip().strip("`")
        if text and text not in sources:
            sources.append(text)
    return sources


def _evidence_sources(content: str) -> list[str]:
    sources: list[str] = []
    for line in extract_section(content, "Evidence").splitlines():
        text = line.strip()
        if not text.startswith("|") or text.startswith("|---") or "Source" in text and "Claim" in text:
            continue
        cells = [cell.strip() for cell in text.strip("|").split("|")]
        if len(cells) < 2:
            continue
        source = cells[1]
        if source and source not in sources:
            sources.append(source)
    return sources


def _lint_sensitive_content(pages: list[LintPage], config: PrivacyConfig) -> list[WikiLintIssue]:
    issues: list[WikiLintIssue] = []
    for page in pages:
        if page.directory == "maintenance":
            continue
        counts = detect_sensitive_text(page.content, config)
        if not counts:
            continue
        secret_categories = {"api_keys", "bearer_tokens", "env_secrets", "private_keys"}
        severity = "error" if secret_categories.intersection(counts) else "warning"
        issues.append(
            _issue(
                "privacy_sensitive_content",
                severity,
                page.relative_path,
                "Page contains text that matches configured privacy redaction patterns.",
                {
                    "redaction_counts": counts,
                    "pattern_types": sorted(counts),
                },
            )
        )
    return issues


def _lint_knowledge_atom_index(vault_path: Path, pages: list[LintPage]) -> tuple[list[WikiLintIssue], dict[str, Any]]:
    records = read_knowledge_atom_records(vault_path)
    if not records:
        return [], {"record_count": 0, "issue_count": 0}

    page_paths = {page.relative_path for page in pages}
    atom_ids = {record.atom_id for record in records}
    issues: list[WikiLintIssue] = []
    for record in records:
        existing_page_paths = [path for path in record.page_paths if path in page_paths]
        if not record.page_paths:
            issues.append(
                _atom_issue(
                    "atom_without_page_trace",
                    "warning",
                    record,
                    "Knowledge atom is not associated with any generated wiki page.",
                )
            )
        elif not existing_page_paths:
            issues.append(
                _atom_issue(
                    "atom_missing_page",
                    "warning",
                    record,
                    "Knowledge atom points only to missing wiki pages.",
                    {"page_paths": record.page_paths},
                )
            )
        if record.atom_type == "relation":
            missing_sources = [
                atom_id
                for atom_id in _string_list(record.payload.get("source_claim_ids"))
                if atom_id not in atom_ids
            ]
            if missing_sources:
                issues.append(
                    _atom_issue(
                        "atom_relation_missing_support",
                        "warning",
                        record,
                        "Knowledge relation references source atoms that are missing from the atom index.",
                        {"missing_atom_ids": missing_sources},
                    )
                )

    issues.extend(_lint_conflicting_atom_relations(records))
    return issues, {"record_count": len(records), "issue_count": len(issues)}


def _lint_conflicting_atom_relations(records: list[KnowledgeAtomRecord]) -> list[WikiLintIssue]:
    relation_states: dict[tuple[str, str], dict[str, list[KnowledgeAtomRecord]]] = defaultdict(lambda: {"supports": [], "contradicts": []})
    for record in records:
        if record.atom_type != "relation":
            continue
        predicate = str(record.payload.get("predicate") or "").strip()
        if predicate not in {"supports", "contradicts"}:
            continue
        subject = _object_name(record.payload.get("subject"))
        object_name = _object_name(record.payload.get("object"))
        if not subject or not object_name:
            continue
        relation_states[(subject, object_name)][predicate].append(record)

    issues: list[WikiLintIssue] = []
    for (subject, object_name), states in relation_states.items():
        if states["supports"] and states["contradicts"]:
            involved = [record.atom_id for record in [*states["supports"], *states["contradicts"]]]
            issues.append(
                _issue(
                    "atom_conflicting_relation",
                    "warning",
                    _atom_issue_path(states["supports"][0]),
                    "Knowledge atom index contains both supports and contradicts relations for the same subject/object pair.",
                    {"subject": subject, "object": object_name, "atom_ids": involved},
                )
            )
    return issues


def _atom_issue(
    code: str,
    severity: str,
    record: KnowledgeAtomRecord,
    message: str,
    details: dict[str, Any] | None = None,
) -> WikiLintIssue:
    return _issue(
        code,
        severity,
        _atom_issue_path(record),
        message,
        {
            "atom_id": record.atom_id,
            "atom_type": record.atom_type,
            "source_digest_id": record.source_digest_id,
            **(details or {}),
        },
    )


def _atom_issue_path(record: KnowledgeAtomRecord) -> str:
    return record.page_paths[0] if record.page_paths else ".knoarbor/index/knowledge_atoms.jsonl"


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _object_name(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    return str(value.get("name") or "").strip()


def _lint_related_page_lists(pages: list[LintPage]) -> list[WikiLintIssue]:
    pages_by_relative, pages_by_stem, pages_by_title = page_lookup_maps(pages)
    issues: list[WikiLintIssue] = []
    for page in pages:
        related_links = extract_wiki_links(extract_section(page.content, "Related Pages"))
        if not related_links:
            continue
        by_target: dict[str, list[str]] = defaultdict(list)
        for raw_link in related_links:
            target = normalize_link_target(raw_link)
            resolved = resolve_link(target, pages_by_relative, pages_by_stem, pages_by_title)
            key = resolved[0].relative_path if len(resolved) == 1 else target
            by_target[key].append(raw_link)
        duplicates = {target: links for target, links in by_target.items() if len(links) > 1}
        for target, links in duplicates.items():
            issues.append(_issue("duplicate_related_target", "info", page.relative_path, "Related Pages contains multiple list items pointing to the same wiki target.", {"section": "Related Pages", "target": target, "links": links}))
    return issues


def _lint_repeated_list_sections(pages: list[LintPage]) -> list[WikiLintIssue]:
    issues: list[WikiLintIssue] = []
    for page in pages:
        for section in ("Key Points", "Tags", "Source"):
            items = [item for item in extract_list_items(extract_section(page.content, section)) if _is_meaningful_list_item(item)]
            duplicates = _duplicate_items(items)
            if duplicates:
                issues.append(_issue("duplicate_section_item", "info", page.relative_path, f"{section} contains duplicate list items.", {"section": section, "duplicates": duplicates}))
    return issues


def _lint_specialized_page_contracts(pages: list[LintPage]) -> list[WikiLintIssue]:
    issues: list[WikiLintIssue] = []
    for page in pages:
        headings = {heading.strip().lower() for heading in extract_headings(page.content)}
        if page.directory == "timelines":
            if len(_date_tokens(_markdown_body(page.content))) < 2:
                issues.append(_issue("timeline_missing_chronology", "info", page.relative_path, "Timeline page does not expose at least two date-like chronology markers."))
        elif page.directory == "workflows":
            workflow_step_state = _workflow_step_state(page.content, headings)
            if not workflow_step_state["has_canonical_steps"]:
                issues.append(
                    _issue(
                        "workflow_missing_steps",
                        "info",
                        page.relative_path,
                        "Workflow page lacks a canonical Steps section with actionable steps.",
                        workflow_step_state,
                    )
                )
    return issues


def _is_meaningful_list_item(item: str) -> bool:
    text = item.strip()
    if not text:
        return False
    return text not in {"暂无内容", "暂无关联知识", "暂无标签", "暂无来源"}


def _duplicate_items(items: list[str]) -> list[str]:
    seen: dict[str, str] = {}
    duplicates: list[str] = []
    duplicate_keys: set[str] = set()
    for item in items:
        key = _normalize_list_item(item)
        if not key:
            continue
        if key in seen and key not in duplicate_keys:
            duplicates.append(seen[key])
            duplicate_keys.add(key)
            continue
        seen[key] = item
    return duplicates


def _normalize_list_item(item: str) -> str:
    return re.sub(r"\s+", " ", item.strip()).strip("- ").lower()


def _date_tokens(content: str) -> list[str]:
    return re.findall(r"\b(?:19|20)\d{2}(?:[-/年.]\d{1,2}(?:[-/月.]\d{1,2}日?)?)?\b", content)


def _markdown_body(content: str) -> str:
    return re.sub(r"^---\s*\n.*?^---\s*$\n?", "", content, count=1, flags=re.MULTILINE | re.DOTALL).strip()


def _has_workflow_steps(content: str, headings: set[str]) -> bool:
    return bool(_workflow_step_state(content, headings)["has_canonical_steps"])


def _workflow_step_state(content: str, headings: set[str]) -> dict[str, bool]:
    step_heading_found = False
    for section in ("Steps", "Procedure", "流程", "步骤", "操作步骤"):
        if section.lower() not in headings:
            continue
        step_heading_found = True
        if _section_has_workflow_steps(extract_section(content, section)):
            return {
                "has_canonical_steps": True,
                "canonical_section_present": True,
                "steps_detected_elsewhere": True,
            }
    return {
        "has_canonical_steps": False,
        "canonical_section_present": step_heading_found,
        "steps_detected_elsewhere": _section_has_workflow_steps(content),
    }


def _section_has_workflow_steps(content: str) -> bool:
    ordered_items = re.findall(r"^\s*\d+[\.)、]\s+\S+", content, flags=re.MULTILINE)
    task_items = re.findall(r"^\s*-\s+\[[ xX]\]\s+\S+", content, flags=re.MULTILINE)
    meaningful_bullets = [
        item
        for item in re.findall(r"^\s*[-*]\s+(.+)$", content, flags=re.MULTILINE)
        if _is_meaningful_list_item(item)
    ]
    return len(ordered_items) >= 2 or len(task_items) >= 2 or len(meaningful_bullets) >= 2


def _issue(code: str, severity: str, path: str, message: str, details: dict[str, Any] | None = None) -> WikiLintIssue:
    return WikiLintIssue(code=code, severity=severity, path=path, message=message, details=details or {})
