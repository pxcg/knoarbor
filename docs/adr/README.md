# Architecture Decision Records

ADR files record durable architecture decisions for KnoArbor. They are used
when a decision changes a long-lived boundary, public contract, storage model,
runtime behavior, model boundary, or extension model.

Use an ADR when the decision is expensive to reverse or likely to affect
multiple future releases.

## Current ADR Index

No ADR has been accepted yet. Use [0000-template.md](0000-template.md) when
recording the first decision.

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
