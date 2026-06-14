# Query Report

- run_id: golden-query-run
- created_at: <normalized>
- query: agent loop workflow
- mode: balanced
- retrieval_mode: machine_hybrid_balanced
- returned_count: 3
- context_pack_chars: 2101
- context_pack_truncated: False

## Results

### 1. Agent Loop

- path: concepts/Agent-Loop.md
- type: concept
- match_kind: direct
- relevance: high
- score: 20.853
- matched_fields: body, headings, key_points, path, related_graph, summary, tags, title
- reason: Matched body, headings, key_points, path, related_graph, summary, tags, title; graph relevance boost 3.954 via backlink, shared_source.

Summary:

Agent loop is a control pattern where a model observes context, reasons, acts with tools, and uses feedback.

Excerpts:
- Key Points: - Agent loops are dynamic and tool-aware. - Workflows provide deterministic structure around uncertain agent decisions.

### 2. Agent Loop Source

- path: sources/Agent-Loop-Source.md
- type: source
- match_kind: direct
- relevance: high
- score: 13.453
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
- relevance: medium
- score: 6.813
- matched_fields: body, related_graph, summary, tags
- reason: Matched body, related_graph, summary, tags; graph relevance boost 2.4 via outbound_link.

Summary:

OpenClaw is an engineering agent system that combines structured workflows with agent loops.

Excerpts:
- Summary: OpenClaw is an engineering agent system that combines structured workflows with agent loops.

## Answer Guidance

- Use primary_pages as the maintained wiki answer unit when they answer the question directly.
- Use supporting_pages and source_pages for context, provenance, and follow-up suggestions.
- Use the returned wiki pages as local evidence, not as the only possible source of truth.
- Cite page paths when making claims, especially for specific facts or recommendations.
- Primary page candidate: concepts/Agent-Loop.md.

## Gap Signals

- No gap signals.

## Trace

- answer_scope: {'kind': 'narrow', 'vault_ids': [], 'initial_page_dirs': ['concepts', 'entities', 'sources'], 'expanded_page_dirs': ['concepts', 'entities', 'sources'], 'include_related': True, 'reason': 'Top result appears sufficient as the main answer unit.'}
- answer_set: {'kind': 'single_page', 'primary_paths': ['concepts/Agent-Loop.md'], 'supporting_paths': [], 'source_paths': ['sources/Agent-Loop-Source.md'], 'further_reading_paths': ['entities/OpenClaw.md'], 'reason': 'The query is narrow enough to anchor on the strongest maintained wiki page.', 'stop_reason': 'top_answer_selected'}
- candidate_count: 3
- context_pack_chars: 2101
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
- role_counts: {'primary': 1, 'supporting': 1, 'source': 1}
- schema_version: query_trace.v1
- scoring_model: field_weighted_bm25
- top_matches: [{'path': 'concepts/Agent-Loop.md', 'score': 20.853, 'relevance': 'high', 'matched_fields': ['body', 'headings', 'key_points', 'path', 'related_graph', 'summary', 'tags', 'title'], 'reason': 'Matched body, headings, key_points, path, related_graph, summary, tags, title; graph relevance boost 3.954 via backlink, shared_source.'}, {'path': 'sources/Agent-Loop-Source.md', 'score': 13.453, 'relevance': 'high', 'matched_fields': ['body', 'headings', 'path', 'related_graph', 'summary', 'title'], 'reason': 'Matched body, headings, path, related_graph, summary, title; graph relevance boost 3.6 via outbound_link, shared_source.'}, {'path': 'entities/OpenClaw.md', 'score': 6.813, 'relevance': 'medium', 'matched_fields': ['body', 'related_graph', 'summary', 'tags'], 'reason': 'Matched body, related_graph, summary, tags; graph relevance boost 2.4 via outbound_link.'}]

## Context Pack

```text
Relevant KnoArbor context for the host AI.
Query: agent loop workflow

Answer guidance:
- Use primary_pages as the maintained wiki answer unit when they answer the question directly.
- Use supporting_pages and source_pages for context, provenance, and follow-up suggestions.
- Use the returned wiki pages as local evidence, not as the only possible source of truth.
- Cite page paths when making claims, especially for specific facts or recommendations.
- Primary page candidate: concepts/Agent-Loop.md.

1. Agent Loop (concepts/Agent-Loop.md, relevance: high, score: 20.853)
Match origin: direct
Summary: Agent loop is a control pattern where a model observes context, reasons, acts with tools, and uses feedback.
Key points:
- Agent loops are dynamic and tool-aware.
- Workflows provide deterministic structure around uncertain agent decisions.
Relevant excerpts:
- concepts/Agent-Loop.md#Key Points: - Agent loops are dynamic and tool-aware. - Workflows provide deterministic structure around uncertain agent decisions.
Source: raw/notes/agent-loop.md
Why matched: Matched body, headings, key_points, path, related_graph, summary, tags, title; graph relevance boost 3.954 via backlink, shared_source.

2. Agent Loop Source (sources/Agent-Loop-Source.md, relevance: high, score: 13.453)
Match origin: direct
Summary: Source digest for agent loop and workflow comparison notes.
Relevant excerpts:
- sources/Agent-Loop-Source.md#Summary: Source digest for agent loop and workflow comparison notes.
Source: raw/notes/agent-loop.md
Why matched: Matched body, headings, path, related_graph, summary, title; graph relevance boost 3.6 via outbound_link, shared_source.

3. OpenClaw (entities/OpenClaw.md, relevance: medium, score: 6.813)
Match origin: direct
Summary: OpenClaw is an engineering agent system that combines structured workflows with agent loops.
Relevant excerpts:
- entities/OpenClaw.md#Summary: OpenClaw is an engineering agent system that combines structured workflows with agent loops.
Why matched: Matched body, related_graph, summary, tags; graph relevance boost 2.4 via outbound_link.
```
