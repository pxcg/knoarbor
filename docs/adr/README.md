# Architecture Decision Records

ADR files record durable architecture decisions for KnoArbor. They are used
when a decision changes a long-lived boundary, public contract, storage model,
runtime behavior, model boundary, or extension model.

Use an ADR when the decision is expensive to reverse or likely to affect
multiple future releases.

## Current ADR Index

| ADR | Status | Decision |
| --- | --- | --- |
| [0001 Knowledge Atom Ingest](0001-knowledge-atom-ingest.md) | Partially Superseded | Evidence-backed atoms remain accepted; ADR 0004 replaces its durable publication boundary. |
| [0002 Canonical Wiki Layout And Graph Index](0002-unified-page-namespace.md) | Superseded | ADR 0004 replaces its factual-authority and materialization model. |
| [0003 Semantic-Indexed Raw-Grounded Answering](0003-raw-grounded-answering.md) | Partially Superseded | Local factual support still comes only from active raw evidence; ADR 0006 adds a separate general-model Chat source and ADR 0007 adds a second Raw locator channel. |
| [0004 Ingest Factual Authority And Materialization](0004-ingest-factual-authority.md) | Partially Superseded | SQLite heads and immutable revisions remain factual authority; ADR 0005 replaces only their physical layout. |
| [0005 Factual Revision File Layout](0005-factual-revision-file-layout.md) | Accepted | Immutable revisions use the four-file `.knoarbor/facts/<source>/<revision>/` layout. |
| [0006 Source-Separated Chat Answering](0006-source-separated-chat-answering.md) | Partially Superseded | Raw/general provenance remains accepted; ADR 0019 replaces physically separate answer prompts with one validated final-answer contract. |
| [0007 Unified Active Raw Evidence Retrieval](0007-unified-active-raw-evidence-retrieval.md) | Partially Superseded | Unified channels, active Raw identity, resolution, fusion, and typed outcomes remain accepted; ADR 0009 replaces fixed candidate/page limits. |
| [0008 Immutable Lexical Retrieval Snapshot](0008-immutable-lexical-retrieval-snapshot.md) | Accepted | One verified SQLite FTS5 snapshot serves both lexical locator channels without a runtime fallback or external service. |
| [0009 Complete Retrieval Enumeration With Resource Safety](0009-complete-retrieval-enumeration.md) | Partially Superseded | Complete single-query provider enumeration and resource safety remain accepted; ADR 0015 adds a ranked result window for the Chat batch handoff. |
| [0010 Automatic Chat Source Routing](0010-automatic-chat-source-routing.md) | Superseded | ADR 0019 replaces code-owned answer-source routing with one final semantic answer stage. |
| [0011 Raw-Grounded Graph-Assisted Retrieval](0011-raw-grounded-graph-rag.md) | Superseded | ADR 0018 removes the graph traversal and graph-specific contracts. |
| [0012 Linear Raw-Grounded Chat](0012-linear-raw-grounded-chat.md) | Partially Superseded | Default Chat remains linear; ADR 0013 changes retrieval planning and ADR 0019 unifies the final answer stage. |
| [0013 Corpus-Guided Dual-Path Retrieval](0013-corpus-guided-dual-path-retrieval.md) | Partially Superseded | Preserves the unchanged question and one Query-owned batch; ADR 0014 replaces generated semantic expressions. |
| [0014 Document-Section-Scoped Retrieval](0014-document-section-scoped-retrieval.md) | Partially Superseded | Document/chapter regions remain accepted; ADR 0016 adds model-authored regional expressions alongside the literal question. |
| [0015 BM25-Ranked Chat Retrieval](0015-bm25-ranked-chat-retrieval.md) | Partially Superseded | BM25/RRF and the global window remain accepted; ADR 0016 moves the 12-parent allowance from each expression to each region group. |
| [0016 Direction-First Retrieval Planning](0016-direction-first-retrieval-planning.md) | Partially Superseded | One planner selects visible regions and writes one regional expression; ADR 0017 adds one document synthesis locator to its outline. |
| [0017 Synthesis-Augmented Document Navigation](0017-synthesis-augmented-document-navigation.md) | Accepted | Each document exposes its complete synthesis to first-stage navigation as locator-only context without changing Raw evidence authority. |
| [0018 Two-Channel Raw Retrieval](0018-two-channel-raw-retrieval.md) | Accepted | Query uses only atom/claim and Raw lexical recall; Relation closes through Claims, and synthesis remains navigation-only. |
| [0019 Unified Final Chat Answer](0019-unified-final-chat-answer.md) | Superseded | ADR 0020 separates answer authority selection from response composition while preserving one whole-response authority. |
| [0020 Separate Chat Answer Decision And Composition](0020-separated-chat-answer-decision-and-composition.md) | Partially Superseded | Separate answer judgment and composition remain accepted; ADR 0021 replaces generated-image prompt ownership and provider order. |
| [0021 Compose After Generated-Image Execution](0021-compose-after-generated-image.md) | Accepted | Answer Decision supplies the conditional generated-image prompt, code runs the provider, and Response Composer places successful generated visuals. |

## ADR Rules

Each ADR should describe:

- status;
- context;
- decision;
- consequences;
- alternatives considered;
- verification and follow-up.

ADR language should describe the accepted boundary directly. Historical
migration notes belong in release notes or maintainer records; the ADR should
capture the stable decision.

## Numbering

Use four-digit sequence numbers:

```text
0001-local-python-core.md
0002-public-api-surface.md
0003-source-document-contract.md
```

Keep accepted ADRs immutable except for status updates or links to follow-up
ADRs.
