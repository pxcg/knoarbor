# Architecture Decision Records

ADR files record durable architecture decisions for KnoArbor. They are used
when a decision changes a long-lived boundary, public contract, storage model,
runtime behavior, model boundary, or extension model.

Use an ADR when the decision is expensive to reverse or likely to affect
multiple future releases.

## Current ADR Index

| ADR | Status | Decision |
| --- | --- | --- |
| [0001 Knowledge Atom Ingest](0001-knowledge-atom-ingest.md) | Accepted | Ingest produces evidence-backed knowledge atoms; Markdown wiki pages are readable projections of atoms, claims, relations, and evidence. |
| [0002 Canonical Wiki Layout And Graph Index](0002-unified-page-namespace.md) | Accepted | Knowledge pages live under `wiki/pages/`, source digests live under `wiki/sources/`, and graph/index data lives under `.knoarbor/index/`. |
| [0022 Public Upstream And Private Product Downstream](0022-public-upstream-private-downstream.md) | Accepted | Reusable behavior is owned by public KnoArbor and flows one way into private product overlays; private history never becomes public ancestry. |

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
