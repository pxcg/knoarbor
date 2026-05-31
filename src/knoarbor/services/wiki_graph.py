from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from knoarbor.storage import ensure_machine_index, machine_index_dir


class WikiGraphNode(BaseModel):
    id: str
    title: str
    type: str
    summary: str
    tags: list[str] = Field(default_factory=list)
    source: str | None = None


class WikiGraphEdge(BaseModel):
    source: str
    target: str
    kind: str = "wikilink"


class WikiGraphStats(BaseModel):
    page_count: int
    edge_count: int
    orphan_count: int
    unresolved_link_count: int
    directory_counts: dict[str, int] = Field(default_factory=dict)
    tag_counts: dict[str, int] = Field(default_factory=dict)


class WikiGraph(BaseModel):
    vault_path: str
    nodes: list[WikiGraphNode] = Field(default_factory=list)
    edges: list[WikiGraphEdge] = Field(default_factory=list)
    stats: WikiGraphStats


def build_wiki_graph(vault_path: Path) -> WikiGraph:
    """Build a deterministic page-link graph from the machine index."""

    vault_path = vault_path.expanduser().resolve()
    index_dir = machine_index_dir(vault_path)
    pages_path = index_dir / "pages.json"
    links_path = index_dir / "links.json"
    ensure_machine_index(vault_path)

    pages_payload = _read_json(pages_path)
    links_payload = _read_json(links_path)
    page_records = [item for item in pages_payload.get("pages", []) if isinstance(item, dict)]
    link_records = [item for item in links_payload.get("links", []) if isinstance(item, dict)]
    nodes: list[WikiGraphNode] = []
    edges: list[WikiGraphEdge] = []
    directory_counts: dict[str, int] = {}
    tag_counts: dict[str, int] = {}
    unresolved = sum(1 for link in link_records if not link.get("resolved"))

    page_ids = {str(page.get("path")) for page in page_records if page.get("path")}
    for page in page_records:
        page_id = str(page.get("path") or "")
        if not page_id:
            continue
        page_type = str(page.get("type") or "page")
        directory = str(page.get("directory") or Path(page_id).parent.name)
        tags = [str(tag) for tag in page.get("tags", []) if isinstance(tag, str)]
        directory_counts[directory] = directory_counts.get(directory, 0) + 1
        for tag in tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
        nodes.append(
            WikiGraphNode(
                id=page_id,
                title=str(page.get("title") or Path(page_id).stem),
                type=page_type,
                summary=str(page.get("summary") or ""),
                tags=tags,
                source=_metadata_text(page.get("source")),
            )
        )

    seen_edges: set[tuple[str, str]] = set()
    for link in link_records:
        source = str(link.get("source") or "")
        target = str(link.get("target_path") or "")
        if not source or not target or source == target:
            continue
        if source not in page_ids or target not in page_ids:
            continue
        edge_key = (source, target)
        if edge_key in seen_edges:
            continue
        seen_edges.add(edge_key)
        edges.append(WikiGraphEdge(source=source, target=target))

    connected = {edge.source for edge in edges} | {edge.target for edge in edges}
    stats = WikiGraphStats(
        page_count=len(nodes),
        edge_count=len(edges),
        orphan_count=sum(1 for node in nodes if node.id not in connected),
        unresolved_link_count=unresolved,
        directory_counts=dict(sorted(directory_counts.items())),
        tag_counts=dict(sorted(tag_counts.items(), key=lambda item: (-item[1], item[0]))[:20]),
    )
    return WikiGraph(vault_path=str(vault_path), nodes=nodes, edges=edges, stats=stats)


def _read_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _metadata_text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None
