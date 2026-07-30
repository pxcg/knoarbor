from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from knoarbor.storage.wiki_index import ensure_machine_index, machine_index_dir


class WikiGraphNode(BaseModel):
    id: str
    title: str
    type: str = "page"
    role: str | None = None
    summary: str
    entities: list[str] = Field(default_factory=list)
    pages: list[str] = Field(default_factory=list)
    source: str | None = None


class WikiGraphEdge(BaseModel):
    source: str
    target: str
    kind: str = "wikilink"
    label: str | None = None
    page: str | None = None
    claim: str | None = None


class WikiGraphStats(BaseModel):
    page_count: int
    edge_count: int
    orphan_count: int
    unresolved_link_count: int
    directory_counts: dict[str, int] = Field(default_factory=dict)
    role_counts: dict[str, int] = Field(default_factory=dict)
    entity_counts: dict[str, int] = Field(default_factory=dict)


class WikiGraph(BaseModel):
    vault_path: str
    graph_kind: str = "page"
    nodes: list[WikiGraphNode] = Field(default_factory=list)
    edges: list[WikiGraphEdge] = Field(default_factory=list)
    stats: WikiGraphStats


def build_wiki_graph(vault_path: Path) -> WikiGraph:
    return build_page_graph(vault_path)


def build_page_graph(vault_path: Path) -> WikiGraph:
    """Build a deterministic page-link graph from the machine index."""

    vault_path = vault_path.expanduser().resolve()
    ensure_machine_index(vault_path)
    index_dir = machine_index_dir(vault_path)
    pages_path = index_dir / "pages.json"
    links_path = index_dir / "links.json"

    pages_payload = _read_json(pages_path)
    links_payload = _read_json(links_path)
    page_records = [item for item in pages_payload.get("pages", []) if isinstance(item, dict) and _is_visible_wiki_page(item)]
    link_records = [item for item in links_payload.get("links", []) if isinstance(item, dict)]
    nodes: list[WikiGraphNode] = []
    edges: list[WikiGraphEdge] = []
    directory_counts: dict[str, int] = {}
    role_counts: dict[str, int] = {}
    entity_counts: dict[str, int] = {}
    unresolved = sum(1 for link in link_records if not link.get("resolved"))

    page_ids = {str(page.get("path")) for page in page_records if page.get("path")}
    for page in page_records:
        page_id = str(page.get("path") or "")
        if not page_id:
            continue
        role = str(page.get("role") or "")
        directory = str(page.get("directory") or Path(page_id).parent.name)
        entities = [str(entity) for entity in page.get("entities", []) if isinstance(entity, str)]
        directory_counts[directory] = directory_counts.get(directory, 0) + 1
        if role:
            role_counts[role] = role_counts.get(role, 0) + 1
        for entity in entities:
            entity_counts[entity] = entity_counts.get(entity, 0) + 1
        nodes.append(
            WikiGraphNode(
                id=page_id,
                title=str(page.get("title") or Path(page_id).stem),
                type="page",
                role=role,
                summary=str(page.get("summary") or ""),
                entities=entities,
            )
        )

    seen_edges: set[tuple[str, str, str]] = set()
    for link in link_records:
        source = str(link.get("source") or "")
        target = str(link.get("target_path") or "")
        if not source or not target or source == target:
            continue
        if source not in page_ids or target not in page_ids:
            continue
        edge_key = _edge_key(source, target)
        if (*edge_key, "wikilink") in seen_edges:
            continue
        seen_edges.add((*edge_key, "wikilink"))
        edges.append(WikiGraphEdge(source=source, target=target))

    semantic_edges = _semantic_page_edges(vault_path, page_ids)
    for source, target, label in semantic_edges:
        edge_key = _edge_key(source, target)
        if any(item[0] == edge_key[0] and item[1] == edge_key[1] for item in seen_edges):
            continue
        seen_edges.add((*edge_key, "semantic"))
        edges.append(WikiGraphEdge(source=source, target=target, kind="semantic", label=label))

    connected = {edge.source for edge in edges} | {edge.target for edge in edges}
    stats = WikiGraphStats(
        page_count=len(nodes),
        edge_count=len(edges),
        orphan_count=sum(1 for node in nodes if node.id not in connected),
        unresolved_link_count=unresolved,
        directory_counts=dict(sorted(directory_counts.items())),
        role_counts=dict(sorted(role_counts.items())),
        entity_counts=dict(sorted(entity_counts.items(), key=lambda item: (-item[1], item[0]))[:20]),
    )
    return WikiGraph(vault_path=str(vault_path), graph_kind="page", nodes=nodes, edges=edges, stats=stats)


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _edge_key(source: str, target: str) -> tuple[str, str]:
    return (source, target) if source <= target else (target, source)


def _is_visible_wiki_page(page: dict[str, object]) -> bool:
    page_id = str(page.get("path") or "")
    role = str(page.get("role") or "")
    return bool(page_id) and not page_id.startswith("sources/") and role != "source_record"


def _semantic_page_edges(vault_path: Path, page_ids: set[str]) -> list[tuple[str, str, str]]:
    graph = _read_json(machine_index_dir(vault_path) / "graph_index.json")
    edges: list[tuple[str, str, str]] = []
    for node in graph.get("nodes", []):
        if not isinstance(node, dict):
            continue
        label = str(node.get("label") or node.get("id") or "semantic").strip() or "semantic"
        paths = sorted({str(path) for path in node.get("pages", []) if str(path) in page_ids}) if isinstance(node.get("pages"), list) else []
        for index, source in enumerate(paths):
            for target in paths[index + 1 :]:
                edges.append((source, target, label))
    return edges
