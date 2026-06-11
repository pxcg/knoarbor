# Query Report

- run_id: golden-query-run
- created_at: <normalized>
- query: agent loop workflow
- mode: balanced
- retrieval_mode: machine_hybrid_balanced
- returned_count: 3
- context_pack_chars: 1960
- context_pack_truncated: False

## Results

### 1. Agent Loop

- path: concepts/Agent-Loop.md
- type: concept
- match_kind: direct
- relevance: high
- score: 42.7
- matched_fields: body, headings, key_points, path, related_graph, summary, tags, title
- reason: Matched body, headings, key_points, path, related_graph, summary, tags, title; graph relevance boost 4.8 via backlink, shared_source.

Summary:

Agent loop is a control pattern where a model observes context, reasons, acts with tools, and uses feedback.

Excerpts:
- Key Points: - Agent loops are dynamic and tool-aware. - Workflows provide deterministic structure around uncertain agent decisions.

### 2. Agent Loop Source

- path: sources/Agent-Loop-Source.md
- type: source
- match_kind: direct
- relevance: high
- score: 31.0
- matched_fields: body, headings, path, related_graph, summary, title
- reason: Matched body, headings, path, related_graph, summary, title; graph relevance boost 3.6 via outbound_link, shared_source.

Summary:

Source digest for agent loop and workflow comparison notes.

Excerpts:
- Summary: Source digest for agent loop and workflow comparison notes.

### 3. OpenClaw

- path: entities/OpenClaw.md
- type: entity
- match_kind: direct
- relevance: high
- score: 16.8
- matched_fields: body, related_graph, summary, tags
- reason: Matched body, related_graph, summary, tags; graph relevance boost 2.4 via outbound_link.

Summary:

OpenClaw is an engineering agent system that combines structured workflows with agent loops.

Excerpts:
- Summary: OpenClaw is an engineering agent system that combines structured workflows with agent loops.

## Answer Guidance

- Use the returned wiki pages as local evidence, not as the only possible source of truth.
- Cite page paths when making claims, especially for specific facts or recommendations.
- Prefer high-relevance results and quoted excerpts; use low-relevance pages only as supporting context.

## Gap Signals

- No gap signals.

## Trace

- candidate_count: 3
- context_pack_chars: 1960
- context_pack_truncated: False
- direct_match_count: 3
- direct_page_count: 3
- expanded_scope_dirs: ['concepts', 'entities', 'sources']
- gap_count: 0
- gap_suggestion_count: 0
- graph_page_count: 3
- initial_scope_dirs: ['concepts', 'entities', 'sources']
- origin_counts: {'direct': 3, 'related': 0}
- page_count: 3
- query_terms: ['agent', 'loop', 'workflow']
- related_expansion_count: 3
- related_result_paths: ['concepts/Agent-Loop.md', 'entities/OpenClaw.md', 'sources/Agent-Loop-Source.md']
- related_seed_pages: ['concepts/Agent-Loop.md', 'entities/OpenClaw.md', 'sources/Agent-Loop-Source.md']
- returned_count: 3
- returned_paths: ['concepts/Agent-Loop.md', 'sources/Agent-Loop-Source.md', 'entities/OpenClaw.md']
- schema_version: query_trace.v1
- top_matches: [{'path': 'concepts/Agent-Loop.md', 'score': 42.7, 'relevance': 'high', 'matched_fields': ['body', 'headings', 'key_points', 'path', 'related_graph', 'summary', 'tags', 'title'], 'reason': 'Matched body, headings, key_points, path, related_graph, summary, tags, title; graph relevance boost 4.8 via backlink, shared_source.'}, {'path': 'sources/Agent-Loop-Source.md', 'score': 31.0, 'relevance': 'high', 'matched_fields': ['body', 'headings', 'path', 'related_graph', 'summary', 'title'], 'reason': 'Matched body, headings, path, related_graph, summary, title; graph relevance boost 3.6 via outbound_link, shared_source.'}, {'path': 'entities/OpenClaw.md', 'score': 16.8, 'relevance': 'high', 'matched_fields': ['body', 'related_graph', 'summary', 'tags'], 'reason': 'Matched body, related_graph, summary, tags; graph relevance boost 2.4 via outbound_link.'}]

## Context Pack

```text
Relevant KnoArbor context for the host AI.
Query: agent loop workflow

Answer guidance:
- Use the returned wiki pages as local evidence, not as the only possible source of truth.
- Cite page paths when making claims, especially for specific facts or recommendations.
- Prefer high-relevance results and quoted excerpts; use low-relevance pages only as supporting context.

1. Agent Loop (concepts/Agent-Loop.md, relevance: high, score: 42.7)
Match origin: direct
Summary: Agent loop is a control pattern where a model observes context, reasons, acts with tools, and uses feedback.
Key points:
- Agent loops are dynamic and tool-aware.
- Workflows provide deterministic structure around uncertain agent decisions.
Relevant excerpts:
- concepts/Agent-Loop.md#Key Points: - Agent loops are dynamic and tool-aware. - Workflows provide deterministic structure around uncertain agent decisions.
Source: raw/notes/agent-loop.md
Why matched: Matched body, headings, key_points, path, related_graph, summary, tags, title; graph relevance boost 4.8 via backlink, shared_source.

2. Agent Loop Source (sources/Agent-Loop-Source.md, relevance: high, score: 31.0)
Match origin: direct
Summary: Source digest for agent loop and workflow comparison notes.
Relevant excerpts:
- sources/Agent-Loop-Source.md#Summary: Source digest for agent loop and workflow comparison notes.
Source: raw/notes/agent-loop.md
Why matched: Matched body, headings, path, related_graph, summary, title; graph relevance boost 3.6 via outbound_link, shared_source.

3. OpenClaw (entities/OpenClaw.md, relevance: high, score: 16.8)
Match origin: direct
Summary: OpenClaw is an engineering agent system that combines structured workflows with agent loops.
Relevant excerpts:
- entities/OpenClaw.md#Summary: OpenClaw is an engineering agent system that combines structured workflows with agent loops.
Why matched: Matched body, related_graph, summary, tags; graph relevance boost 2.4 via outbound_link.
```
