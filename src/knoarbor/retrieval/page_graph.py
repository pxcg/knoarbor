from __future__ import annotations

from knoarbor.retrieval.markdown import SearchPage


def build_inbound_paths(pages: list[SearchPage]) -> dict[str, list[str]]:
    inbound: dict[str, list[str]] = {}
    for page in pages:
        for related_path in page.related_pages:
            inbound.setdefault(related_path, [])
            if page.relative_path not in inbound[related_path]:
                inbound[related_path].append(page.relative_path)
    return inbound


def related_candidate_paths(seed: SearchPage, inbound_paths: dict[str, list[str]]) -> list[str]:
    candidates: list[str] = []
    for path in [*seed.related_pages, *inbound_paths.get(seed.relative_path, [])]:
        if path == seed.relative_path or path in candidates:
            continue
        candidates.append(path)
    return candidates


def graph_relevance_boost(seed: SearchPage, candidate: SearchPage, seed_score: float) -> tuple[float, list[str]]:
    reasons: list[str] = []
    boost = 0.0

    if candidate.relative_path in seed.related_pages:
        boost += min(seed_score * 0.18, 2.4)
        reasons.append("outbound_link")

    if seed.relative_path in candidate.related_pages:
        boost += min(seed_score * 0.14, 1.8)
        reasons.append("backlink")

    if seed.source and candidate.source and seed.source == candidate.source:
        boost += 1.2
        reasons.append("shared_source")

    if seed.directory == candidate.directory or seed.page_type == candidate.page_type:
        boost += 0.6
        reasons.append("type_affinity")

    return boost, reasons
