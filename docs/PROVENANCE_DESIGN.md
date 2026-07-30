# Provenance Design

This document defines the stable provenance meaning shared by ingest,
retrieval, Chat, projection, and maintenance. Field-level contracts live in
[Contracts](CONTRACTS.md); factual authority is recorded by
[ADR 0004](adr/0004-ingest-factual-authority.md).

## Provenance Chain

```text
raw source
  -> normalized source units
  -> immutable source revision
  -> evidence-backed knowledge metadata
  -> readable and machine projections
  -> raw-grounded retrieval
```

## Authority

| Layer | Role | Authority |
| --- | --- | --- |
| Raw source | User material or deterministic normalized derivative | Factual input |
| Source unit | Stable evidence coordinate within a source revision | Answer-bearing evidence |
| Source revision | Processing record, source units, knowledge atoms, manifest | Published factual record |
| SQLite source head | Selects the active revision and session window | Publication authority |
| Wiki source projection | Readable synthesis, claims, entities, and relations | Rebuildable locator |
| Machine index | Search, graph, page, source, and link records | Rebuildable retrieval view |
| Run/report artifacts | Execution, failure, token, and recovery diagnostics | Operational audit only |

The active source heads in `.knoarbor/ingest.sqlite` and their reachable
immutable revisions under `.knoarbor/facts/` jointly define the
published factual state. Wiki Markdown and machine indexes do not redefine it.

## Evidence

Every accepted entity, claim, or relation points to source evidence constructed
from stable source units. Evidence records carry source, revision, unit,
excerpt, and integrity information. Model-local array positions are transient
request references and are not durable provenance.

Query and Chat may use wiki pages and atom metadata to locate relevant facts.
Factual answers use raw evidence or source units, in line with
[ADR 0003](adr/0003-raw-grounded-answering.md). A wiki page is useful navigation
and synthesis, but its prose is not promoted to raw evidence merely because it
was generated during ingest.

## Projection

Transactional ingest materializes one readable source projection under
`wiki/pages/` for each active replaceable source, or one combined projection
for an incremental session. These pages are marked as projection material and
can be rebuilt without semantic extraction.

`wiki/sources/` belongs to an earlier source-record Markdown design. Existing
files remain readable historical material, but current ingest does not require
or generate them as provenance authority.

## Maintenance Boundary

Maintenance may validate:

- revision and source-unit references;
- evidence integrity and missing raw material;
- projection freshness against the active fact generation;
- broken user-facing source navigation;
- machine-index generation consistency.

Maintenance does not infer provenance from ordinary wiki links, rewrite raw
sources, or treat run diagnostics as knowledge facts.

## Recovery And Backup

Backup protects raw material, `.knoarbor/ingest.sqlite`, and reachable source
revision generations. Wiki projections and machine indexes are rebuildable.
A factual commit that precedes a projection failure is recovered by
materialization and does not repeat the model call.
