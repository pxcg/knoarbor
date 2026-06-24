from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from knoarbor.retrieval.graph_index import load_graph_index
from knoarbor.retrieval.index_provider import IndexProvider, IndexRequest
from knoarbor.retrieval.markdown import ScoredPage, SearchPage, query_terms, score_pages
from knoarbor.retrieval.page_graph import build_inbound_paths, graph_relevance_boost


@dataclass(frozen=True)
class GraphRecallSignals:
    """Structured graph signals supplied by query, chat, or ingest callers."""

    text_query: str = ""
    entities: list[str] = field(default_factory=list)
    relation_pairs: list[tuple[str, str]] = field(default_factory=list)
    source_terms: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class GraphLedRetrievalRequest:
    vault_path: Path
    query: str
    signals: GraphRecallSignals = field(default_factory=GraphRecallSignals)
    limit: int = 8
    page_dirs: list[str] = field(default_factory=list)
    page_kinds: list[str] = field(default_factory=list)
    page_roles: list[str] = field(default_factory=list)
    facets: list[str] = field(default_factory=list)
    include_related: bool = True


@dataclass(frozen=True)
class GraphLedRetrievalResult:
    matches: list[ScoredPage]
    warnings: list[str]
    stats: dict[str, object]


class GraphLedRetriever:
    """Two-stage retrieval: graph/index recall first, BM25 rerank second."""

    def __init__(self, index_provider: IndexProvider) -> None:
        self.index_provider = index_provider

    def retrieve(self, request: GraphLedRetrievalRequest) -> GraphLedRetrievalResult:
        vault_path = request.vault_path.expanduser().resolve()
        scoped_pages = self.index_provider.collect(
            IndexRequest(
                vault_path=vault_path,
                page_dirs=request.page_dirs,
                page_kinds=request.page_kinds,
                page_roles=request.page_roles,
                facets=request.facets,
            )
        )
        graph_pages = scoped_pages
        if request.include_related and (request.page_dirs or request.page_kinds or request.page_roles or request.facets):
            graph_pages = self.index_provider.collect(IndexRequest(vault_path=vault_path))

        signals = normalize_recall_signals(request.query, request.signals)
        graph = load_graph_index(vault_path)
        graph_scored = recall_graph_candidates(
            graph=graph,
            scoped_pages=scoped_pages,
            graph_pages=graph_pages,
            signals=signals,
            include_related=request.include_related,
        )
        candidate_pages = [item.page for item in graph_scored.values()]
        terms = query_terms(request.query)
        bm25_scored = score_pages(candidate_pages, terms, request.query)
        merged = merge_graph_and_bm25_scores(graph_scored, bm25_scored)
        ranked = [item for item in sorted(merged.values(), key=lambda item: item.score, reverse=True) if item.score > 0]
        matches = ranked[: request.limit]
        return GraphLedRetrievalResult(
            matches=matches,
            warnings=[],
            stats={
                "retrieval_strategy": "graph_led_bm25",
                "index_provider": self.index_provider.name,
                "scoring_model": "graph_recall_then_field_weighted_bm25",
                "page_count": len(scoped_pages),
                "direct_page_count": len(scoped_pages),
                "graph_page_count": len(graph_pages),
                "page_dirs": request.page_dirs,
                "page_kinds": request.page_kinds,
                "page_roles": request.page_roles,
                "facets": request.facets,
                "initial_scope_dirs": request.page_dirs or sorted({page.directory for page in scoped_pages}),
                "expanded_scope_dirs": sorted({page.directory for page in graph_pages}),
                "initial_scope_page_kinds": request.page_kinds or sorted({page.page_kind for page in scoped_pages if page.page_kind}),
                "expanded_scope_page_kinds": sorted({page.page_kind for page in graph_pages if page.page_kind}),
                "initial_scope_roles": request.page_roles or sorted({page.role for page in scoped_pages if page.role}),
                "expanded_scope_roles": sorted({page.role for page in graph_pages if page.role}),
                "initial_scope_facets": request.facets or sorted({facet for page in scoped_pages for facet in page.facets}),
                "expanded_scope_facets": sorted({facet for page in graph_pages for facet in page.facets}),
                "query_terms": terms,
                "graph_signal_terms": signals.entities,
                "graph_candidate_count": len(graph_scored),
                "bm25_reranked_count": len(bm25_scored),
                "direct_match_count": len([item for item in graph_scored.values() if "graph_related" not in item.matched_fields]),
                "related_expansion_count": len([item for item in graph_scored.values() if "graph_related" in item.matched_fields]),
                "related_seed_pages": sorted(
                    {
                        seed
                        for item in graph_scored.values()
                        for seed in item.matched_terms.get("related_graph", [])
                    }
                ),
                "related_result_paths": sorted(
                    item.page.relative_path
                    for item in graph_scored.values()
                    if "graph_related" in item.matched_fields
                ),
                "graph_index_expansion_count": len(graph_scored),
                "graph_index_seed_pages": sorted(
                    {
                        term
                        for item in graph_scored.values()
                        for term in item.matched_terms.get("graph_recall", [])
                        if term.endswith(".md")
                    }
                ),
                "graph_index_result_paths": sorted(item.page.relative_path for item in graph_scored.values()),
                "candidate_count": len(ranked),
                "returned_count": len(matches),
            },
        )


def normalize_recall_signals(query: str, signals: GraphRecallSignals | None = None) -> GraphRecallSignals:
    base = signals or GraphRecallSignals()
    entities = _dedupe_terms([*base.entities, *query_terms(query), query])
    source_terms = _dedupe_terms(base.source_terms)
    relation_pairs = _dedupe_relation_pairs(base.relation_pairs)
    return GraphRecallSignals(text_query=base.text_query or query, entities=entities, relation_pairs=relation_pairs, source_terms=source_terms)


def recall_graph_candidates(
    *,
    graph: dict[str, Any],
    scoped_pages: list[SearchPage],
    graph_pages: list[SearchPage],
    signals: GraphRecallSignals,
    include_related: bool,
) -> dict[str, ScoredPage]:
    page_by_path = {page.relative_path: page for page in graph_pages}
    scores: dict[str, dict[str, object]] = {}
    scoped_paths = {page.relative_path for page in scoped_pages}
    _recall_from_graph_nodes(scores, graph, signals, scoped_paths)
    _recall_from_graph_relations(scores, graph, signals, scoped_paths)
    _recall_from_graph_sources(scores, graph, signals, scoped_paths)
    _recall_from_page_identity(scores, scoped_pages, signals)

    if include_related:
        _expand_related_graph_candidates(scores, graph_pages)
    else:
        scores = {path: payload for path, payload in scores.items() if path in scoped_paths}

    output: dict[str, ScoredPage] = {}
    for path, payload in scores.items():
        page = page_by_path.get(path)
        if page is None:
            continue
        reasons = _payload_list(payload, "reasons")
        terms = _payload_list(payload, "terms")
        fields = {"graph_recall", "graph_index"}
        matched_terms = {"graph_recall": terms, "graph_reasons": reasons}
        if any(reason.startswith("related:") for reason in reasons):
            fields.update({"graph_related", "related_graph"})
            matched_terms["related_graph"] = [term for term in terms if term.endswith(".md")]
        output[path] = ScoredPage(
            page=page,
            score=float(payload.get("score", 0.0)),
            matched_fields=fields,
            matched_terms=matched_terms,
            graph_boost=float(payload.get("score", 0.0)),
            graph_reasons=reasons,
        )
    return output


def merge_graph_and_bm25_scores(
    graph_scored: dict[str, ScoredPage],
    bm25_scored: dict[str, ScoredPage],
) -> dict[str, ScoredPage]:
    merged = {path: _copy_scored_page(item) for path, item in graph_scored.items()}
    for path, bm25 in bm25_scored.items():
        target = merged.get(path)
        if target is None:
            continue
        target.score += bm25.score
        target.matched_fields.update(bm25.matched_fields)
        for field_name, terms in bm25.matched_terms.items():
            target.matched_terms.setdefault(field_name, [])
            for term in terms:
                if term not in target.matched_terms[field_name]:
                    target.matched_terms[field_name].append(term)
    return merged


def _recall_from_graph_nodes(
    scores: dict[str, dict[str, object]],
    graph: dict[str, Any],
    signals: GraphRecallSignals,
    allowed_paths: set[str],
) -> None:
    node_pages = _node_pages(graph)
    if not node_pages:
        return
    signal_keys = [_graph_key(term) for term in signals.entities if _graph_key(term)]
    for node_id, pages in node_pages.items():
        node_key = _graph_key(node_id)
        if not _key_matches_any(node_key, signal_keys):
            continue
        for path in pages:
            if path not in allowed_paths:
                continue
            _add_graph_score(scores, path, 5.0, f"node:{node_id}", node_id)


def _recall_from_graph_relations(
    scores: dict[str, dict[str, object]],
    graph: dict[str, Any],
    signals: GraphRecallSignals,
    allowed_paths: set[str],
) -> None:
    relation_pairs = [(_graph_key(subject), _graph_key(obj)) for subject, obj in signals.relation_pairs]
    signal_keys = {_graph_key(term) for term in signals.entities if _graph_key(term)}
    node_pages = _node_pages(graph)
    for edge in _edges(graph):
        source_key = _graph_key(edge["source"])
        target_key = _graph_key(edge["target"])
        exact_pair = any({source_key, target_key} == {left, right} for left, right in relation_pairs if left and right)
        endpoint_hit = bool(signal_keys.intersection({source_key, target_key}))
        if not exact_pair and not endpoint_hit:
            continue
        score = 7.0 if exact_pair else 3.0
        reason = f"relation:{edge['source']}-{edge['predicate']}-{edge['target']}"
        if edge["page"] in allowed_paths:
            _add_graph_score(scores, edge["page"], score, reason, f"{edge['source']}->{edge['target']}")
        for node_id in (edge["source"], edge["target"]):
            for path in node_pages.get(node_id, []):
                if path not in allowed_paths:
                    continue
                _add_graph_score(scores, path, 2.0 if exact_pair else 1.5, reason, f"{edge['source']}->{edge['target']}")


def _recall_from_graph_sources(
    scores: dict[str, dict[str, object]],
    graph: dict[str, Any],
    signals: GraphRecallSignals,
    allowed_paths: set[str],
) -> None:
    source_keys = {_graph_key(term) for term in signals.source_terms if _graph_key(term)}
    if not source_keys:
        return
    for row in _source_rows(graph):
        source_key = _graph_key(row["source"])
        raw_key = _graph_key(row["raw"])
        if source_key not in source_keys and raw_key not in source_keys:
            continue
        for path in row["pages"]:
            if path not in allowed_paths:
                continue
            _add_graph_score(scores, path, 5.0, f"source_lineage:{row['source']}", row["source"])
        if row["source"] and row["source"] in allowed_paths:
            _add_graph_score(scores, row["source"], 4.0, f"source_digest:{row['source']}", row["source"])


def _recall_from_page_identity(scores: dict[str, dict[str, object]], pages: list[SearchPage], signals: GraphRecallSignals) -> None:
    signal_keys = [_graph_key(term) for term in signals.entities if _graph_key(term)]
    if not signal_keys:
        return
    for page in pages:
        fields = [
            ("title", page.title, 4.0),
            ("path", page.relative_path, 2.0),
            ("entity", " ".join(page.tags), 3.0),
            ("facet", " ".join(page.facets), 2.0),
            ("kind", page.page_kind, 1.5),
        ]
        for field_name, value, score in fields:
            key = _graph_key(value)
            if not key or not _key_matches_any(key, signal_keys):
                continue
            _add_graph_score(scores, page.relative_path, score, f"page_identity:{field_name}", value)
            break


def _expand_related_graph_candidates(scores: dict[str, dict[str, object]], pages: list[SearchPage]) -> None:
    if not scores:
        return
    page_by_path = {page.relative_path: page for page in pages}
    inbound_paths = build_inbound_paths(pages)
    seed_paths = list(scores)
    for seed_path in seed_paths:
        seed = page_by_path.get(seed_path)
        if not seed:
            continue
        seed_score = float(scores[seed_path].get("score", 0.0))
        candidate_paths = [*seed.related_pages, *inbound_paths.get(seed.relative_path, [])]
        for related_path in candidate_paths:
            if related_path == seed.relative_path:
                continue
            candidate = page_by_path.get(related_path)
            if not candidate:
                continue
            boost, reasons = graph_relevance_boost(seed, candidate, seed_score)
            if boost <= 0:
                continue
            for reason in reasons:
                _add_graph_score(scores, related_path, boost, f"related:{reason}", seed.relative_path)


def _node_pages(graph: dict[str, Any]) -> dict[str, list[str]]:
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
        if source and predicate and target and page:
            edges.append({"source": source, "predicate": predicate, "target": target, "page": page})
    return edges


def _source_rows(graph: dict[str, Any]) -> list[dict[str, object]]:
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


def _key_matches_any(candidate_key: str, signal_keys: list[str]) -> bool:
    if not candidate_key:
        return False
    for signal_key in signal_keys:
        if candidate_key == signal_key:
            return True
        if len(signal_key) >= 3 and signal_key in candidate_key:
            return True
        if len(candidate_key) >= 3 and candidate_key in signal_key:
            return True
    return False


def _add_graph_score(scores: dict[str, dict[str, object]], path: str, score: float, reason: str, term: str) -> None:
    if not path:
        return
    payload = scores.setdefault(path, {"score": 0.0, "reasons": [], "terms": []})
    payload["score"] = float(payload["score"]) + score
    reasons = _payload_list(payload, "reasons")
    terms = _payload_list(payload, "terms")
    if reason not in reasons:
        reasons.append(reason)
    if term and term not in terms:
        terms.append(term)


def _payload_list(payload: dict[str, object], key: str) -> list[str]:
    value = payload.setdefault(key, [])
    if not isinstance(value, list):
        payload[key] = []
        return []
    return value


def _copy_scored_page(item: ScoredPage) -> ScoredPage:
    return ScoredPage(
        page=item.page,
        score=item.score,
        matched_fields=set(item.matched_fields),
        matched_terms={field: list(terms) for field, terms in item.matched_terms.items()},
        graph_boost=item.graph_boost,
        graph_reasons=list(item.graph_reasons),
    )


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


def _dedupe_relation_pairs(values: list[tuple[str, str]]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for subject, obj in values:
        key = (_graph_key(subject), _graph_key(obj))
        if not key[0] or not key[1] or key in seen:
            continue
        seen.add(key)
        pairs.append((subject, obj))
    return pairs


def _graph_key(value: str) -> str:
    text = value.strip()
    wiki_link = text.removeprefix("[[").removesuffix("]]")
    if "|" in wiki_link:
        wiki_link = wiki_link.split("|", 1)[-1]
    return " ".join(wiki_link.lower().replace("_", " ").replace("-", " ").split())
