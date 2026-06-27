from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from knoarbor.core.markdown import extract_list_items, extract_section
from knoarbor.core.schemas.wiki_write import WikiDraftBatchWriteItem, WikiDraftBatchWriteRequest, WikiDraftBatchWriteResponse, WikiDraftInput
from knoarbor.pipelines.write import WikiWritePipeline
from knoarbor.storage.wiki_index import relative_wiki_path, update_index
from knoarbor.storage.wiki_paths import normalize_source_digest_title, resolve_existing_target, source_digest_root


@dataclass
class ProvenanceRefreshResult:
    applied_operations: list[dict[str, object]] = field(default_factory=list)
    written_pages: list[str] = field(default_factory=list)
    written_page_details: list[dict[str, object]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class ProvenanceRefreshExecutor:
    """Executes approved refresh requests that repair source provenance.

    The executor owns the refresh-request architecture boundary: semantic lint
    can request a provenance refresh, but concrete source digest creation and
    source-digest association recording stay deterministic.
    """

    def __init__(self, write_pipeline: WikiWritePipeline | None = None) -> None:
        self.write_pipeline = write_pipeline or WikiWritePipeline()

    def apply(self, *, vault_path: Path, queued_actions: list[dict[str, object]]) -> ProvenanceRefreshResult:
        digest_by_source = _source_digest_by_source(vault_path)
        source_targets, warnings = self._collect_source_targets(vault_path, queued_actions, digest_by_source)
        result = ProvenanceRefreshResult(warnings=warnings)
        if not source_targets:
            return result

        index_changed = False
        for source, targets in source_targets.items():
            existing_digest = digest_by_source.get(source)
            if existing_digest is None:
                created = self._create_source_digest(vault_path, source, sorted(targets))
                result.written_pages.extend(created["written_pages"])
                result.written_page_details.extend(created["written_page_details"])
                result.applied_operations.extend(created["applied_operations"])
                created_path = created.get("digest_page")
                if isinstance(created_path, str):
                    existing_digest = created_path
                    digest_by_source[source] = existing_digest

            if existing_digest is None:
                continue

            linked = self._attach_digest_links(vault_path, source, existing_digest, sorted(targets))
            result.applied_operations.extend(linked["applied_operations"])
            index_changed = index_changed or bool(linked["applied_operations"])

        if index_changed:
            update_index(vault_path)
        return result

    def _collect_source_targets(
        self,
        vault_path: Path,
        queued_actions: list[dict[str, object]],
        digest_by_source: dict[str, str],
    ) -> tuple[dict[str, set[str]], list[str]]:
        source_targets: dict[str, set[str]] = {}
        warnings: list[str] = []
        for action in queued_actions:
            if action.get("queue_type") != "refresh_request":
                continue
            target_page = _optional_str(action.get("target_page"))
            if not target_page:
                warnings.append("refresh_request skipped because target_page is missing.")
                continue
            target_path = resolve_existing_target(vault_path, target_page)
            if target_path is None:
                warnings.append(f"refresh_request skipped because target page does not exist: {target_page}")
                continue

            sources = _raw_sources_for_action(vault_path, target_path, action)
            if not sources:
                warnings.append(f"refresh_request skipped because no local raw source was found for {target_page}.")
                continue
            for source in sources:
                raw_path = (vault_path / source).resolve()
                if (not raw_path.exists() or not raw_path.is_file()) and source not in digest_by_source:
                    warnings.append(f"refresh_request skipped missing raw source for {target_page}: {source}")
                    continue
                source_targets.setdefault(source, set()).add(relative_wiki_path(vault_path, target_path))
        return source_targets, warnings

    def _create_source_digest(self, vault_path: Path, source: str, target_pages: list[str]) -> dict[str, object]:
        title = normalize_source_digest_title(Path(source).stem)
        draft = WikiDraftInput(
            title=title,
            page_dir="sources",
            question=f"Source digest for {source}",
            summary=f"Source digest for `{source}` created during lint provenance refresh.",
            synthesis=(
                "This page records provenance for a raw source used by generated wiki pages. "
                "It is intentionally source-focused and does not add claims beyond the raw source path "
                "and the pages linked from this refresh operation."
            ),
            confidence=0.8,
            model_provider="knoarbor",
            model_name="deterministic-provenance-refresh",
        )
        write_response = self.write_pipeline.run(
            WikiDraftBatchWriteRequest(
                vault_path=str(vault_path),
                drafts=[
                    WikiDraftBatchWriteItem(
                        wiki_draft=draft,
                        write_action="create",
                        source_file=source,
                    )
                ],
            )
        )
        written_pages = _written_page_paths(vault_path, write_response)
        written_page_details = _written_page_details(vault_path, write_response, "create_source_digest")
        digest_page = written_pages[0] if written_pages else None
        return {
            "digest_page": digest_page,
            "written_pages": written_pages,
            "written_page_details": written_page_details,
            "applied_operations": [
                {
                    "operation_id": f"refresh:{source}:create_source_digest",
                    "action": "create_source_digest",
                    "target_page": digest_page,
                    "source_file": source,
                    "target_pages": target_pages,
                    "status": "applied",
                    "reason": "Created missing source digest from approved refresh_request.",
                    "write_details": detail.get("write_details", {}),
                }
                for detail in written_page_details[:1]
            ],
        }

    def _attach_digest_links(self, vault_path: Path, source: str, digest_page: str, target_pages: list[str]) -> dict[str, object]:
        applied: list[dict[str, object]] = []
        for target_page in target_pages:
            target_path = resolve_existing_target(vault_path, target_page)
            if target_path is None or not target_path.exists():
                continue
            applied.append(
                {
                    "operation_id": f"refresh:{source}:knowledge_source_digest_association:{target_page}",
                    "action": "record_source_digest",
                    "source_file": source,
                    "target_page": target_page,
                    "source_digest_page": digest_page,
                    "status": "applied",
                    "reason": "Recorded source digest association without mutating wiki page body.",
                    "write_details": {
                        "patched_sections": [],
                        "diff": "",
                        "diff_truncated": False,
                    },
                }
            )
        return {"applied_operations": applied}


def _source_digest_by_source(vault_path: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    sources_dir = source_digest_root(vault_path)
    if not sources_dir.exists():
        return mapping
    for page_path in sorted(sources_dir.glob("*.md")):
        content = page_path.read_text(encoding="utf-8")
        candidates = [*_source_values_from_section(content), *_source_values_from_raw_source(content), *_source_values_from_evidence(content), *_source_values_from_identity(content)]
        for source in candidates:
            digest_page = relative_wiki_path(vault_path, page_path)
            for alias in _source_aliases(source):
                mapping.setdefault(alias, digest_page)
    return mapping


def _raw_sources_for_action(vault_path: Path, target_path: Path, action: dict[str, object]) -> list[str]:
    content = target_path.read_text(encoding="utf-8")
    params = action.get("params") if isinstance(action.get("params"), dict) else {}
    candidates = [
        _optional_str(params.get("source_file")) if isinstance(params, dict) else None,
        _optional_str(params.get("source")) if isinstance(params, dict) else None,
        *_source_values_from_section(content),
        *_source_values_from_raw_source(content),
        *_source_values_from_evidence(content),
        *_source_values_from_identity(content),
    ]
    seen: set[str] = set()
    sources: list[str] = []
    for source in candidates:
        if not source or not source.startswith("raw/") or source in seen:
            continue
        seen.add(source)
        sources.append(source)
    return sources


def _source_aliases(source: str) -> list[str]:
    text = source.strip()
    if not text:
        return []

    aliases = [text]
    path = Path(text)
    suffix = path.suffix
    stem = path.stem
    name = path.name
    if name:
        aliases.append(name)
    if stem:
        aliases.append(stem)
        aliases.append(f"raw/inbox/notes/{stem}.md")
        aliases.append(f"raw/normalized/markdown/{stem}.md")
        aliases.append(f"raw/normalized/chats/{stem}.json")
        aliases.append(f"raw/normalized/chats/{stem}.jsonl")
    if suffix and stem:
        aliases.append(f"raw/inbox/notes/{stem}{suffix}")
        aliases.append(f"raw/normalized/chats/{stem}{suffix}")

    normalized: list[str] = []
    seen: set[str] = set()
    for alias in aliases:
        item = alias.strip()
        if item and item not in seen:
            seen.add(item)
            normalized.append(item)
    return normalized


def _source_values_from_section(content: str) -> list[str]:
    return [item.strip("`").strip() for item in extract_list_items(extract_section(content, "Source")) if item.strip()]


def _source_values_from_raw_source(content: str) -> list[str]:
    values: list[str] = []
    for item in extract_list_items(extract_section(content, "Raw Source")):
        text = item.strip().strip("`")
        lowered = text.lower().replace("_", " ")
        if lowered.startswith("raw source:"):
            text = text.split(":", 1)[1].strip().strip("`")
        if text:
            values.append(text)
    return values


def _source_values_from_identity(content: str) -> list[str]:
    values: list[str] = []
    for item in extract_list_items(extract_section(content, "Source Identity")):
        text = item.strip().strip("`")
        lowered = text.lower().replace("_", " ")
        if lowered.startswith("raw source:"):
            values.append(text.split(":", 1)[1].strip().strip("`"))
    return values


def _source_values_from_evidence(content: str) -> list[str]:
    sources: list[str] = []
    for line in extract_section(content, "Evidence").splitlines():
        text = line.strip()
        if not text.startswith("|") or text.startswith("|---") or ("Claim" in text and "Source" in text):
            continue
        cells = [cell.strip() for cell in text.strip("|").split("|")]
        if len(cells) < 2:
            continue
        source = cells[1]
        if source and source not in sources:
            sources.append(source)
    return sources


def _written_page_paths(vault_path: Path, response: WikiDraftBatchWriteResponse) -> list[str]:
    return [relative_wiki_path(vault_path, Path(result.wiki_file_path)) for result in response.results]


def _written_page_details(vault_path: Path, response: WikiDraftBatchWriteResponse, action: str) -> list[dict[str, object]]:
    details: list[dict[str, object]] = []
    for result in response.results:
        stats = dict(result.stats)
        details.append(
            {
                "path": relative_wiki_path(vault_path, Path(result.wiki_file_path)),
                "created": bool(stats.get("created")),
                "write_action": action,
                "target_page": stats.get("target_page"),
                "operation_index": stats.get("operation_index"),
                "write_details": stats.get("write_details") if isinstance(stats.get("write_details"), dict) else {},
            }
        )
    return details


def _optional_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None
