# ADR 0004: Ingest Factual Authority And Materialization

## Status

Partially superseded by ADR 0005 for physical fact paths and payload names.
The factual-authority and materialization decisions remain accepted.

## Context

Earlier decisions described knowledge atoms, source-record Markdown, wiki page
bodies, and machine indexes at different times as durable knowledge or
provenance boundaries. The local ingest runtime now publishes immutable source
revisions through a transactional active-head authority and deterministically
materializes user-readable and machine-readable views.

The project needs one durable statement of which artifacts are facts and which
are rebuildable views.

## Decision

The factual authority for transactional ingest is the combination of:

1. immutable source revision generations under `.knoarbor/source_revisions/`;
2. the active source and session heads, cursors, entity contributions, and
   materialization state in `.knoarbor/ingest.sqlite`.

Each reachable revision contains the normalized source processing record and
its evidence-backed knowledge atom batch. The SQLite source-head transaction is
the sole factual publication point.

`wiki/pages/*.md` source projections and `.knoarbor/index/` generations are
derived views. They can be deleted and rebuilt from active revisions without a
model call. Wiki pages remain user-readable locators and machine indexes remain
retrieval accelerators; neither becomes an alternate factual authority.

Materialization is separately observable from factual commit. A committed
revision remains valid when projection fails, and recovery rebuilds projection
without repeating semantic extraction.

## Consequences

- Source-record Markdown is a legacy or optional projection, not required
  authority.
- Raw evidence and source units remain answer-bearing factual material.
- Page and index readers must identify the fact generation they represent.
- Backup policy protects SQLite authority and reachable revision generations;
  projections and machine indexes are rebuildable.
- Stable docs and contracts must distinguish authored wiki pages from
  deterministic source projections.

## Alternatives Considered

- Wiki page body as authority: rejected because projection can fail or be
  rebuilt independently of factual publication.
- Machine index as authority: rejected because indexes are replaceable derived
  generations.
- Source-record Markdown as a second provenance authority: rejected because it
  duplicates structured source processing records.

## Verification And Follow-Up

- Transactional tests verify revision staging, source-head fencing, recovery,
  and idempotency.
- Materialization tests verify model-free rebuild and atomic index publication.
- Specification 1.37 owns local execution and materialization mechanics.
- Specifications 1.26 and 1.27 own the current semantic and entity contracts.
