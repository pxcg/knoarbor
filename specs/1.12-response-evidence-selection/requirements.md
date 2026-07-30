# 1.12 Response Evidence Selection Requirements

## Lifecycle

Superseded by `1.38-semantic-indexed-raw-query`. This document records the
historical page-level selector and owns no current implementation boundary.

## Problem

KnoArbor retrieves maintained wiki pages, not raw chunks. A search result can
still contain topic-adjacent pages that are not useful for the user's current
answer. Ranking alone cannot express which pages should anchor the answer,
which pages should support it, which pages only provide provenance, and which
pages should stay out of the answer.

## Goals

- Add a deterministic page-level answer set selection layer after candidate
  retrieval and before evidence packaging.
- Select a small, high-confidence set of answer-bearing pages.
- Preserve source record pages as provenance unless the query asks about
  sources.
- Record why pages were selected or rejected.
- Keep `/query`, `/chat`, skill, and UI consumers on the same page-role
  contract.

## Non-Goals

- Do not add a model-based reranker in this feature.
- Do not change BM25 candidate retrieval.
- Do not turn wiki pages back into chunk-level RAG evidence.
- Do not expose selector knobs in the Chat UI.

## User Scenarios

### Focused Question

For "Agent Loop 是什么？", KnoArbor should choose the strongest maintained
concept page as `primary_pages`, keep implementation pages as optional
`supporting_pages`, and keep source records as `source_pages`.

### Broad Question

For "Agent Loop 的架构、模式和实现有哪些？", KnoArbor should choose one or more
primary pages when they represent distinct answer anchors, then add supporting
pages that cover complementary evidence dimensions.

### Source Question

For "Agent Loop 的来源是什么？", source record pages can become the primary
answer pages because the user asks about provenance.

### Noisy Candidate Set

When several pages are similar but redundant, KnoArbor should reject or demote
pages that do not add a new evidence dimension. Rejected candidates should remain
visible in trace metadata, not in the default answer package.

## Acceptance Criteria

- `WikiAnswerSet` includes selected primary, supporting, source, further
  reading, and rejected candidate paths with reasons.
- Query trace exposes selection decisions.
- Primary page bodies remain available for answer synthesis.
- Supporting pages remain structured evidence by default.
- Existing query/chat tests pass with the new selector.
