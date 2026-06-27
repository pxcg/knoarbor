from __future__ import annotations

from knoarbor.retrieval.markdown import SearchPage


def build_inbound_paths(pages: list[SearchPage]) -> dict[str, list[str]]:
    inbound: dict[str, list[str]] = {}
    for page in pages:
        for linked_path in page.outbound_links:
            inbound.setdefault(linked_path, [])
            if page.relative_path not in inbound[linked_path]:
                inbound[linked_path].append(page.relative_path)
    return inbound


def related_candidate_paths(seed: SearchPage, inbound_paths: dict[str, list[str]]) -> list[str]:
    candidates: list[str] = []
    for path in [*seed.outbound_links, *inbound_paths.get(seed.relative_path, [])]:
        if path == seed.relative_path or path in candidates:
            continue
        candidates.append(path)
    return candidates


def graph_relevance_boost(seed: SearchPage, candidate: SearchPage, seed_score: float) -> tuple[float, list[str]]:
    reasons: list[str] = []
    boost = 0.0

    if candidate.relative_path in seed.outbound_links:
        boost += min(seed_score * 0.18, 2.4)
        reasons.append("outbound_link")

    if seed.relative_path in candidate.outbound_links:
        boost += min(seed_score * 0.14, 1.8)
        reasons.append("backlink")

    return boost, reasons
