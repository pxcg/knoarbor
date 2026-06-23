from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from knoarbor.core.schemas.knowledge_atoms import KnowledgeAtomBatch, KnowledgeAtomObject
from knoarbor.core.schemas.knowledge_extract import KnowledgeExtract
from knoarbor.retrieval.graph_index import load_graph_index
from knoarbor.retrieval.index_provider import IndexProvider, IndexRequest
from knoarbor.retrieval.markdown import ScoredPage


def graph_first_ingest_candidates(
    *,
    vault_path: Path,
    extract: KnowledgeExtract,
    atom_batch: KnowledgeAtomBatch | None,
    index_provider: IndexProvider,
    limit: int,
) -> list[ScoredPage]:
    if atom_batch is None:
        return []
    pages = index_provider.collect(IndexRequest(vault_path=vault_path))
    graph = load_graph_index(vault_path)
    if not pages or not graph:
        return []
    page_by_path = {page.relative_path: page for page in pages}
    scores = _score_graph_first_candidates(graph, extract, atom_batch)
    matches: list[ScoredPage] = []
    for path, payload in scores.items():
        page = page_by_path.get(path)
        if page is None:
            continue
        reasons = payload["reasons"]
        matched_terms = payload["terms"]
        matches.append(
            ScoredPage(
                page=page,
                score=float(payload["score"]),
                matched_fields={"graph_first"},
                matched_terms={"graph_first": matched_terms, "graph_reasons": reasons},
                graph_boost=float(payload["score"]),
                graph_reasons=reasons,
            )
        )
    return sorted(matches, key=lambda item: item.score, reverse=True)[:limit]


def merge_candidate_matches(text_matches: list[ScoredPage], graph_matches: list[ScoredPage]) -> list[ScoredPage]:
    merged: dict[str, ScoredPage] = {item.page.relative_path: deepcopy(item) for item in graph_matches}
    for item in text_matches:
        path = item.page.relative_path
        if path not in merged:
            merged[path] = deepcopy(item)
            continue
        target = merged[path]
        target.score += item.score
        target.matched_fields.update(item.matched_fields)
        for field, terms in item.matched_terms.items():
            target.matched_terms.setdefault(field, [])
            for term in terms:
                if term not in target.matched_terms[field]:
                    target.matched_terms[field].append(term)
        target.graph_boost += item.graph_boost
        for reason in item.graph_reasons:
            if reason not in target.graph_reasons:
                target.graph_reasons.append(reason)
    return sorted(merged.values(), key=lambda item: item.score, reverse=True)


def _score_graph_first_candidates(
    graph: dict[str, object],
    extract: KnowledgeExtract,
    atom_batch: KnowledgeAtomBatch,
) -> dict[str, dict[str, object]]:
    node_pages = _graph_node_pages(graph)
    node_key_to_ids = {_graph_key(node_id): node_id for node_id in node_pages}
    edge_rows = _graph_edges(graph)
    source_rows = _graph_source_rows(graph)
    atom_entities = _atom_entity_terms(atom_batch)
    atom_relations = _atom_relation_terms(atom_batch)
    source_terms = _source_lineage_terms(extract, atom_batch)
    scores: dict[str, dict[str, object]] = {}

    for entity in atom_entities:
        node_id = node_key_to_ids.get(_graph_key(entity))
        if not node_id:
            continue
        for path in node_pages.get(node_id, []):
            _add_graph_score(scores, path, 4.0, f"entity:{node_id}", entity)

    for subject, obj in atom_relations:
        subject_key = _graph_key(subject)
        object_key = _graph_key(obj)
        for edge in edge_rows:
            edge_source_key = _graph_key(edge["source"])
            edge_target_key = _graph_key(edge["target"])
            if {subject_key, object_key} != {edge_source_key, edge_target_key}:
                continue
            reason = f"relation:{edge['source']}-{edge['predicate']}-{edge['target']}"
            _add_graph_score(scores, edge["page"], 6.0, reason, f"{subject}->{obj}")
            for node_id in (edge["source"], edge["target"]):
                for path in node_pages.get(node_id, []):
                    _add_graph_score(scores, path, 2.0, reason, f"{subject}->{obj}")

    for source in source_terms:
        source_key = _graph_key(source)
        for row in source_rows:
            if source_key not in {_graph_key(row["source"]), _graph_key(row["raw"])}:
                continue
            for path in row["pages"]:
                _add_graph_score(scores, path, 5.0, f"source_lineage:{row['source']}", source)
            if row["source"]:
                _add_graph_score(scores, row["source"], 4.0, f"source_digest:{row['source']}", source)

    return scores


def _graph_node_pages(graph: dict[str, object]) -> dict[str, list[str]]:
    raw_nodes = graph.get("nodes", [])
    if not isinstance(raw_nodes, list):
        return {}
    nodes: dict[str, list[str]] = {}
    for node in raw_nodes:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("id") or "").strip()
        pages = node.get("pages", [])
        if not node_id or not isinstance(pages, list):
            continue
        nodes[node_id] = [str(path).strip() for path in pages if str(path).strip()]
    return nodes


def _graph_edges(graph: dict[str, object]) -> list[dict[str, str]]:
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
        if source and predicate and target and page:
            edges.append({"source": source, "predicate": predicate, "target": target, "page": page})
    return edges


def _graph_source_rows(graph: dict[str, object]) -> list[dict[str, object]]:
    raw_sources = graph.get("sources", [])
    if not isinstance(raw_sources, list):
        return []
    rows: list[dict[str, object]] = []
    for source in raw_sources:
        if not isinstance(source, dict):
            continue
        source_id = str(source.get("source") or "").strip()
        raw = str(source.get("raw") or "").strip()
        pages = source.get("pages", [])
        if not source_id or not isinstance(pages, list):
            continue
        rows.append({"source": source_id, "raw": raw, "pages": [str(path).strip() for path in pages if str(path).strip()]})
    return rows


def _atom_entity_terms(batch: KnowledgeAtomBatch) -> list[str]:
    entities: list[str] = []
    for fact in batch.facts:
        _append_object_terms(entities, fact.subject)
        _append_object_terms(entities, fact.object)
    for relation in batch.relations:
        _append_object_terms(entities, relation.subject)
        _append_object_terms(entities, relation.object)
    return _dedupe_terms(entities)


def _atom_relation_terms(batch: KnowledgeAtomBatch) -> list[tuple[str, str]]:
    relations: list[tuple[str, str]] = []
    for relation in batch.relations:
        relations.append((relation.subject.name, relation.object.name))
    for fact in batch.facts:
        if fact.subject and fact.object:
            relations.append((fact.subject.name, fact.object.name))
    seen: set[tuple[str, str]] = set()
    result: list[tuple[str, str]] = []
    for subject, obj in relations:
        key = (_graph_key(subject), _graph_key(obj))
        if not key[0] or not key[1] or key in seen:
            continue
        seen.add(key)
        result.append((subject, obj))
    return result


def _source_lineage_terms(extract: KnowledgeExtract, batch: KnowledgeAtomBatch) -> list[str]:
    values = [
        extract.source.source_path or "",
        extract.source.source_id or "",
        extract.source.title,
    ]
    for fact in batch.facts:
        values.extend(span.source_path or "" for span in fact.evidence)
    for claim in batch.claims:
        values.extend(span.source_path or "" for span in claim.evidence)
    for relation in batch.relations:
        values.extend(span.source_path or "" for span in relation.evidence)
    return _dedupe_terms(values)


def _append_object_terms(terms: list[str], obj: KnowledgeAtomObject | None) -> None:
    if obj is None:
        return
    terms.append(obj.name)
    terms.extend(obj.aliases)
    if obj.page_path:
        terms.append(Path(obj.page_path).stem)


def _add_graph_score(scores: dict[str, dict[str, object]], path: str, score: float, reason: str, term: str) -> None:
    if not path:
        return
    payload = scores.setdefault(path, {"score": 0.0, "reasons": [], "terms": []})
    payload["score"] = float(payload["score"]) + score
    reasons = payload["reasons"]
    terms = payload["terms"]
    if isinstance(reasons, list) and reason not in reasons:
        reasons.append(reason)
    if isinstance(terms, list) and term not in terms:
        terms.append(term)


def _dedupe_terms(values: list[str]) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = value.strip()
        key = _graph_key(text)
        if not key or key in seen:
            continue
        seen.add(key)
        terms.append(text)
    return terms


def _graph_key(value: str) -> str:
    text = value.strip()
    wiki_link = text.removeprefix("[[").removesuffix("]]")
    if "|" in wiki_link:
        wiki_link = wiki_link.split("|", 1)[-1]
    return " ".join(wiki_link.lower().replace("_", " ").replace("-", " ").split())
