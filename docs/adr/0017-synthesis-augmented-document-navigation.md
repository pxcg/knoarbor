# ADR 0017: Synthesis-Augmented Document Navigation

## Status

Accepted

## Context

Document titles and top-level chapter labels are compact, but they do not
always express the terminology used in a user's question. Ingest already
produces one short source-level synthesis per document. Excluding that locator
can make the planner miss a relevant document even though later claim and Raw
retrieval could answer the question.

## Decision

`active_corpus_outline.v1` includes the complete active synthesis once on each
document node. Query joins active processing and atom records by
`source_record_id`; it does not truncate, rewrite, or copy the synthesis into
chapter nodes.

The synthesis is locator-only planning context. It may justify selecting the
document region when titles or chapter labels do not match the user's wording,
but it is excluded from retrieval FTS, candidates, evidence, and context packs.
It cannot seed, admit, authorize, or cite Raw. Claims and answers still require
the ordinary Query path and active Raw evidence.

Empty synthesis remains an empty document field. Ingest, persisted fact
schemas, region identity, result windows, and answer contracts do not change.

## Consequences

- Planner input grows by one existing short synthesis per document rather than
  by the number of claims, entities, relations, or source units.
- Documents with weak or absent chapter metadata remain discoverable through
  their main supported themes.
- The model must treat synthesis as a direction locator, not factual answer
  material.

## Supersession

This ADR supersedes ADR 0016 only where it excluded every semantic atom from
the outline. ADR 0018 further fixes synthesis to the navigation plane and
excludes it from retrieval materialization. ADR 0016's region selection,
regional-expression, Query ownership, result-window, and Raw-authority
decisions remain accepted.

## Verification

- each active document projects its full synthesis exactly once;
- multiline synthesis is preserved without truncation;
- chapter nodes do not repeat synthesis;
- retrieval snapshots contain no synthesis row;
- no Raw, individual Claim/Entity/Relation row, attachment, storage path, or
  revision/evidence identity enters the outline;
- selected regions still retrieve and cite only active Raw evidence.

