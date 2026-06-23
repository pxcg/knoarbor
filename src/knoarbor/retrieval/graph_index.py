from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from knoarbor.retrieval.markdown import ScoredPage, SearchPage
from knoarbor.storage import ensure_machine_index, machine_index_dir


def expand_graph_index_pages(
    scored: dict[str, ScoredPage],
    pages: list[SearchPage],
    vault_path: Path,
    mode: str,
) -> dict[str, ScoredPage]:
    """Expand BM25 seed pages through the machine graph index."""

    graph = load_graph_index(vault_path)
    if not graph:
        return scored

    page_by_path = {page.relative_path: page for page in pages}
    node_pages = _node_pages(graph)
    page_nodes = _page_nodes(node_pages)
    edges = _edges(graph)
    source_pages = _source_pages(graph)
    initial = sorted(scored.values(), key=lambda item: item.score, reverse=True)
    seed_count = 3 if mode == "balanced" else 5
    max_added = 5 if mode == "balanced" else 10
    added = 0

    for seed in initial[:seed_count]:
        for candidate_path, reasons in _candidate_paths(seed.page.relative_path, page_nodes, node_pages, edges, source_pages).items():
            if candidate_path == seed.page.relative_path:
                continue
            page = page_by_path.get(candidate_path)
            if not page:
                continue
            boost = _graph_boost(seed.score, reasons)
            if boost <= 0:
                continue
            if candidate_path not in scored and added >= max_added:
                continue
            was_new = candidate_path not in scored
            _apply_graph_boost(scored, page, seed.page.relative_path, boost, reasons)
            if was_new:
                added += 1
    return scored


def load_graph_index(vault_path: Path) -> dict[str, Any]:
    ensure_machine_index(vault_path)
    path = machine_index_dir(vault_path) / "graph_index.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _node_pages(graph: dict[str, Any]) -> dict[str, list[str]]:
    nodes = graph.get("nodes", [])
    if not isinstance(nodes, list):
        return {}
    result: dict[str, list[str]] = {}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id") or "").strip()
        pages = node.get("pages", [])
        if not node_id or not isinstance(pages, list):
            continue
        result[node_id] = [str(path) for path in pages if isinstance(path, str) and path.strip()]
    return result


def _page_nodes(node_pages: dict[str, list[str]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for node_id, pages in node_pages.items():
        for path in pages:
            result.setdefault(path, []).append(node_id)
    return result


def _edges(graph: dict[str, Any]) -> list[dict[str, str]]:
    raw_edges = graph.get("edges", [])
    if not isinstance(raw_edges, list):
        return []
    edges: list[dict[str, str]] = []
    for edge in raw_edges:
        if not isinstance(edge, dict):
            continue
        source = str(edge.get("source") or "").strip()
        predicate = str(edge.get("predicate") or "").strip()
        target = str(edge.get("target") or "").strip()
        page = str(edge.get("page") or "").strip()
        claim = str(edge.get("claim") or "").strip()
        if source and predicate and target and page:
            edges.append({"source": source, "predicate": predicate, "target": target, "page": page, "claim": claim})
    return edges


def _source_pages(graph: dict[str, Any]) -> dict[str, list[str]]:
    raw_sources = graph.get("sources", [])
    if not isinstance(raw_sources, list):
        return {}
    result: dict[str, list[str]] = {}
    for source in raw_sources:
        if not isinstance(source, dict):
            continue
        source_id = str(source.get("source") or "").strip()
        pages = source.get("pages", [])
        if not source_id or not isinstance(pages, list):
            continue
        result[source_id] = [str(path) for path in pages if isinstance(path, str) and path.strip()]
    return result


def _candidate_paths(
    seed_path: str,
    page_nodes: dict[str, list[str]],
    node_pages: dict[str, list[str]],
    edges: list[dict[str, str]],
    source_pages: dict[str, list[str]],
) -> dict[str, list[str]]:
    candidates: dict[str, list[str]] = {}
    seed_nodes = set(page_nodes.get(seed_path, []))

    for node_id in seed_nodes:
        for path in node_pages.get(node_id, []):
            _add_reason(candidates, path, f"shared_entity:{node_id}")

    for edge in edges:
        source = edge["source"]
        target = edge["target"]
        predicate = edge["predicate"]
        edge_page = edge["page"]
        claim = edge.get("claim") or ""
        edge_reason = f"relation:{source}-{predicate}-{target}"
        if claim:
            edge_reason = f"{edge_reason}:{claim}"
        edge_nodes = {source, target}
        edge_pages = {edge_page}
        for node_id in edge_nodes:
            edge_pages.update(node_pages.get(node_id, []))
        if seed_path == edge_page or seed_nodes.intersection(edge_nodes):
            for path in edge_pages:
                _add_reason(candidates, path, edge_reason)

    for source_id, pages in source_pages.items():
        if seed_path in pages:
            for path in pages:
                _add_reason(candidates, path, f"shared_source:{source_id}")

    candidates.pop(seed_path, None)
    return candidates


def _add_reason(candidates: dict[str, list[str]], path: str, reason: str) -> None:
    if not path:
        return
    reasons = candidates.setdefault(path, [])
    if reason not in reasons:
        reasons.append(reason)


def _graph_boost(seed_score: float, reasons: list[str]) -> float:
    boost = 0.0
    for reason in reasons:
        if reason.startswith("relation:"):
            boost += min(seed_score * 0.22, 2.8)
        elif reason.startswith("shared_entity:"):
            boost += min(seed_score * 0.16, 2.0)
        elif reason.startswith("shared_source:"):
            boost += 1.2
    return boost


def _apply_graph_boost(
    scored: dict[str, ScoredPage],
    page: SearchPage,
    seed_path: str,
    boost: float,
    reasons: list[str],
) -> None:
    if page.relative_path in scored:
        item = scored[page.relative_path]
        item.score += boost
        item.graph_boost += boost
        item.matched_fields.add("graph_index")
        item.matched_terms.setdefault("graph_index", []).append(seed_path)
        item.matched_terms.setdefault("graph_reasons", []).extend(reasons)
        item.graph_reasons.extend(reason for reason in reasons if reason not in item.graph_reasons)
        return

    scored[page.relative_path] = ScoredPage(
        page=page,
        score=boost,
        matched_fields={"graph_index"},
        matched_terms={"graph_index": [seed_path], "graph_reasons": reasons},
        graph_boost=boost,
        graph_reasons=list(reasons),
    )
