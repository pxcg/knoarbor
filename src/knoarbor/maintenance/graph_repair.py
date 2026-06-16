from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from knoarbor.maintenance.related_pages_repair import reconcile_related_pages
from knoarbor.retrieval.markdown import SearchPage, collect_search_pages, query_terms, score_pages
from knoarbor.storage.wiki_index import update_index
from knoarbor.storage.wiki_paths import resolve_existing_target


MAX_GRAPH_REPAIR_LINKS = 5
GRAPH_REPAIR_ISSUES = {"weak_link_graph", "source_without_knowledge_links"}


@dataclass
class GraphRepairResult:
    applied_operations: list[dict[str, object]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class GraphRepairExecutor:
    """Executes safe graph integration repairs from approved lint queue items."""

    def apply(self, *, vault_path: Path, queued_actions: list[dict[str, object]]) -> GraphRepairResult:
        pages = collect_search_pages(vault_path)
        page_by_path = {page.relative_path: page for page in pages}
        result = GraphRepairResult()
        changed = False

        for action in queued_actions:
            if not _is_graph_repair_action(action):
                continue
            target_page = _optional_str(action.get("target_page"))
            if not target_page:
                result.warnings.append("graph repair skipped because target_page is missing.")
                continue
            target_path = resolve_existing_target(vault_path, target_page)
            target = page_by_path.get(target_page)
            if target_path is None or target is None:
                result.warnings.append(f"graph repair skipped because target page does not exist: {target_page}")
                continue

            related_pages = _explicit_related_pages(action, page_by_path) or _select_related_pages(target, pages)
            if not related_pages:
                result.warnings.append(f"graph repair skipped because no related pages were found for {target_page}.")
                continue

            operation = reconcile_related_pages(vault_path, target_path, related_pages, str(action.get("issue_type") or "graph_repair"))
            if not operation:
                continue
            operation.update(
                {
                    "operation_id": f"graph:{action.get('operation_index', 'unknown')}:{target_page}",
                    "action": "attach_related_pages",
                    "target_page": target_page,
                    "reason": "Attached related pages from approved graph maintenance queue item.",
                }
            )
            result.applied_operations.append(operation)
            changed = True

        if changed:
            update_index(vault_path)
        return result


def _is_graph_repair_action(action: dict[str, object]) -> bool:
    if action.get("queue_type") != "graph_repair":
        return False
    if action.get("issue_type") not in GRAPH_REPAIR_ISSUES:
        return False
    if action.get("risk_level") not in {"safe", "low"}:
        return False
    if action.get("action") not in {"queue_graph_review", "report_only"}:
        return False
    return True


def _explicit_related_pages(action: dict[str, object], page_by_path: dict[str, SearchPage]) -> list[str]:
    related = action.get("related_pages")
    if not isinstance(related, list):
        return []
    output: list[str] = []
    for item in related:
        path = str(item).strip()
        if path in page_by_path and path not in output:
            output.append(path)
    return output[:MAX_GRAPH_REPAIR_LINKS]


def _select_related_pages(target: SearchPage, pages: list[SearchPage]) -> list[str]:
    query = _graph_query(target)
    terms = query_terms(query)
    if not terms:
        return []
    candidates = score_pages(_candidate_pages(target, pages), terms, query)
    ordered = sorted(candidates.values(), key=lambda item: item.score, reverse=True)
    return [item.page.relative_path for item in ordered[:MAX_GRAPH_REPAIR_LINKS]]


def _candidate_pages(target: SearchPage, pages: list[SearchPage]) -> list[SearchPage]:
    candidates: list[SearchPage] = []
    for page in pages:
        if page.relative_path == target.relative_path:
            continue
        if target.directory == "sources" and page.directory == "sources":
            continue
        if target.directory != "sources" and page.directory == "queries":
            continue
        candidates.append(page)
    return candidates


def _graph_query(page: SearchPage) -> str:
    parts = [
        page.title,
        page.summary,
        " ".join(page.key_points),
        " ".join(page.tags),
        " ".join(page.headings[:6]),
    ]
    return " ".join(part for part in parts if part).strip()


def _optional_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None
