# Query Report

- run_id: golden-query-run
- created_at: <normalized>
- query: agent loop workflow
- mode: balanced
- retrieval_mode: machine_graph_led_bm25_balanced
- returned_count: 3
- context_pack_chars: 3401
- context_pack_truncated: False

## Results

### 1. Agent Loop

- path: Agent-Loop.md
- match_kind: related
- relevance: high
- score: 61.432
- matched_fields: body, claims, entities, graph_index, graph_recall, graph_related, headings, path, related_graph, summary, title
- reason: Matched body, claims, entities, graph_index, graph_recall, graph_related, headings, path, related_graph, summary, title; graph relevance boost 36.8 via node:Agent Loop, node:Workflow, page_identity:title, related:backlink, related:outbound_link, relation:Agent Loop-differs from-Workflow.

Summary:

Agent loop is a control pattern where a model observes context, reasons, acts with tools, and uses feedback.

Excerpts:
- Claims: - C1: Agent loops are dynamic and tool-aware. - C2: Workflows provide deterministic structure around uncertain agent decisions.

### 2. OpenClaw

- path: OpenClaw.md
- match_kind: related
- relevance: high
- score: 35.151
- matched_fields: body, entities, graph_index, graph_recall, graph_related, related_graph, summary
- reason: Matched body, entities, graph_index, graph_recall, graph_related, related_graph, summary; graph relevance boost 26.3 via node:Agent Loop, page_identity:entity, related:backlink, related:outbound_link, relation:Agent Loop-differs from-Workflow.

Summary:

OpenClaw is an engineering agent system that combines structured workflows with agent loops.

Excerpts:
- Summary: OpenClaw is an engineering agent system that combines structured workflows with agent loops.

### 3. Agent Loop Source

- path: sources/Agent-Loop-Source.md
- match_kind: direct
- relevance: high
- score: 10.695
- matched_fields: body, graph_index, graph_recall, headings, path, title
- reason: Matched body, graph_index, graph_recall, headings, path, title; graph relevance boost 4.0 via page_identity:title.

Excerpts:
- Audit Summary: Source digest for agent loop and workflow comparison notes.

## Response Guidance

- Use primary_pages as the maintained wiki answer unit when they answer the question directly.
- Use supporting_pages and source_pages for context, provenance, and follow-up suggestions.
- Use the returned wiki pages as local evidence, not as the only possible source of truth.
- Cite page paths when making claims, especially for specific facts or recommendations.
- Primary page candidate: Agent-Loop.md.

## Gap Signals

- No gap signals.

## Trace

- answer_scope: {'kind': 'narrow', 'vault_ids': [], 'initial_page_dirs': ['pages', 'sources'], 'expanded_page_dirs': ['pages', 'sources'], 'include_related': True, 'reason': 'Top result appears sufficient as the main answer unit.'}
- answer_set: {'kind': 'single_page', 'primary_paths': ['Agent-Loop.md'], 'supporting_paths': [], 'source_paths': ['sources/Agent-Loop-Source.md'], 'further_reading_paths': ['OpenClaw.md'], 'rejected_candidates': [{'path': 'OpenClaw.md', 'title': 'OpenClaw', 'reason': 'redundant_dimension', 'score': 35.151, 'role_hint': 'further_reading'}], 'reason': 'The query is narrow enough to anchor on Agent-Loop.md. Source digest pages are kept for provenance.', 'stop_reason': 'answer_set_selected'}
- atom_trace_count: 0
- atom_trace_counts: {}
- candidate_count: 3
- context_pack_chars: 3401
- context_pack_truncated: False
- direct_match_count: 1
- direct_page_count: 3
- expanded_scope_dirs: ['pages', 'sources']
- gap_count: 0
- gap_suggestion_count: 0
- graph_page_count: 3
- initial_scope_dirs: ['pages', 'sources']
- origin_counts: {'direct': 1, 'related': 2}
- page_count: 3
- query_terms: ['agent', 'loop', 'workflow']
- rejected_candidates: [{'path': 'OpenClaw.md', 'title': 'OpenClaw', 'reason': 'redundant_dimension', 'score': 35.151, 'role_hint': 'further_reading'}]
- related_expansion_count: 2
- related_result_paths: ['Agent-Loop.md', 'OpenClaw.md']
- related_seed_pages: ['Agent-Loop.md', 'OpenClaw.md']
- returned_count: 3
- returned_paths: ['Agent-Loop.md', 'OpenClaw.md', 'sources/Agent-Loop-Source.md']
- role_counts: {'primary': 1, 'supporting': 1, 'source': 1}
- schema_version: query_trace.v1
- scoring_model: graph_recall_then_field_weighted_bm25
- top_matches: [{'path': 'Agent-Loop.md', 'score': 61.432, 'relevance': 'high', 'matched_fields': ['body', 'claims', 'entities', 'graph_index', 'graph_recall', 'graph_related', 'headings', 'path', 'related_graph', 'summary', 'title'], 'atom_trace_count': 0, 'reason': 'Matched body, claims, entities, graph_index, graph_recall, graph_related, headings, path, related_graph, summary, title; graph relevance boost 36.8 via node:Agent Loop, node:Workflow, page_identity:title, related:backlink, related:outbound_link, relation:Agent Loop-differs from-Workflow.'}, {'path': 'OpenClaw.md', 'score': 35.151, 'relevance': 'high', 'matched_fields': ['body', 'entities', 'graph_index', 'graph_recall', 'graph_related', 'related_graph', 'summary'], 'atom_trace_count': 0, 'reason': 'Matched body, entities, graph_index, graph_recall, graph_related, related_graph, summary; graph relevance boost 26.3 via node:Agent Loop, page_identity:entity, related:backlink, related:outbound_link, relation:Agent Loop-differs from-Workflow.'}, {'path': 'sources/Agent-Loop-Source.md', 'score': 10.695, 'relevance': 'high', 'matched_fields': ['body', 'graph_index', 'graph_recall', 'headings', 'path', 'title'], 'atom_trace_count': 0, 'reason': 'Matched body, graph_index, graph_recall, headings, path, title; graph relevance boost 4.0 via page_identity:title.'}]

## Context Pack

```text
Relevant KnoArbor context for the host AI.
Query: agent loop workflow

Response guidance:
- Use primary_pages as the maintained wiki answer unit when they answer the question directly.
- Use supporting_pages and source_pages for context, provenance, and follow-up suggestions.
- Use the returned wiki pages as local evidence, not as the only possible source of truth.
- Cite page paths when making claims, especially for specific facts or recommendations.
- Primary page candidate: Agent-Loop.md.

1. Agent Loop (Agent-Loop.md, relevance: high, score: 61.432)
Answer role: primary
Match origin: related
Summary: Agent loop is a control pattern where a model observes context, reasons, acts with tools, and uses feedback.
Claims:
- C1: Agent loops are dynamic and tool-aware.
- C2: Workflows provide deterministic structure around uncertain agent decisions.
Relevant excerpts:
- Agent-Loop.md#Claims: - C1: Agent loops are dynamic and tool-aware. - C2: Workflows provide deterministic structure around uncertain agent decisions.
Full page body:
# Agent Loop

## Summary

Agent loop is a control pattern where a model observes context, reasons, acts with tools, and uses feedback.

## Claims

- C1: Agent loops are dynamic and tool-aware.
- C2: Workflows provide deterministic structure around uncertain agent decisions.

## Entities

- [[Agent Loop]]
- [[Workflow]]
- [[OpenClaw]]

## Relations

| Subject | Predicate | Object | Based on |
|---|---|---|---|
| [[Agent Loop]] | differs from | [[Workflow]] | C1 |
| [[OpenClaw]] | implements | [[Agent Loop]] | C2 |

## Synthesis

Agent loop systems repeat observation, reasoning, action, and feedback. A workflow follows a predefined path, while an agent loop lets the model choose the next step.

## Evidence

| Claim | Source | Range | Basis | Confidence |
|---|---|---|---|---|
| C1 | sources/Agent-Loop-Source.md | unit:0 | Source supports agent loop behavior. | high |
Why matched: Matched body, claims, entities, graph_index, graph_recall, graph_related, headings, path, related_graph, summary, title; graph relevance boost 36.8 via node:Agent Loop, node:Workflow, page_identity:title, related:backlink, related:outbound_link, relation:Agent Loop-differs from-Workflow.

2. OpenClaw (OpenClaw.md, relevance: high, score: 35.151)
Answer role: supporting
Match origin: related
Summary: OpenClaw is an engineering agent system that combines structured workflows with agent loops.
Relevant excerpts:
- OpenClaw.md#Summary: OpenClaw is an engineering agent system that combines structured workflows with agent loops.
Full page body:
# OpenClaw

## Summary

OpenClaw is an engineering agent system that combines structured workflows with agent loops.

## Entities

- [[OpenClaw]]
- [[Agent Loop]]
Why matched: Matched body, entities, graph_index, graph_recall, graph_related, related_graph, summary; graph relevance boost 26.3 via node:Agent Loop, page_identity:entity, related:backlink, related:outbound_link, relation:Agent Loop-differs from-Workflow.

3. Agent Loop Source (sources/Agent-Loop-Source.md, relevance: high, score: 10.695)
Answer role: source
Match origin: direct
Summary: No summary.
Relevant excerpts:
- sources/Agent-Loop-Source.md#Audit Summary: Source digest for agent loop and workflow comparison notes.
Why matched: Matched body, graph_index, graph_recall, headings, path, title; graph relevance boost 4.0 via page_identity:title.
```
