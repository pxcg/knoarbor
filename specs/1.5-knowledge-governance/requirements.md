# 1.5 Knowledge Governance Requirements

## Problem

Ingest now owns raw-derived canonical facts, knowledge atoms, evidence identity,
indexes, and page projection. The former lint workflow still treated generated
wiki pages as independently editable knowledge: it could ask a model to rewrite
sections, merge content, and create provenance pages. Those writes can diverge
from canonical facts and create a second knowledge authority.

Lint must govern integrity without becoming another ingest or editor.

## Goals

- Verify raw, source records, canonical facts, knowledge atoms, evidence,
  indexes, and projections as one dependency chain.
- Automatically route deterministic derived-state defects to their owning
  rebuild workflow and execute the repair.
- Represent canonical semantic defects as reingest requests.
- Represent index and projection drift as rebuild requests.
- Keep semantic diagnosis read-only and evidence-bound.
- Preserve reports, ledgers, risk, confidence, evidence, and requested action.

## Non-Goals

- Model-authored page rewrites, summaries, claims, entities, or relations.
- Direct lint mutation of canonical facts or raw material.
- Source-record reconstruction from page text or path aliases.
- Page merge, split, or deletion based on semantic similarity.
- External fact checking or automatic freshness claims.
- Multiple user-facing lint modes with different correctness semantics.

## Acceptance Criteria

- A lint run always performs the same deterministic integrity scan.
- Optional semantic diagnosis classifies evidence-backed quality findings but
  writes no knowledge or projection content.
- Every repair-plan action is one of `reingest_request`, `index_rebuild_request`,
  `projection_rebuild_request`, or `report_only`.
- Direct page draft compilation and provenance refresh execution are absent
  from the active maintenance path.
- Generated pages remain projections of ingest-owned canonical state.
- Editing a source projection publishes a canonical revision through the
  transactional fact store and rematerializes the page and indexes.
- Projection editing cannot alter source identity, raw evidence, attachments,
  or claim evidence mappings.
- Later raw ingest carries forward only fields explicitly marked by the active
  user-edit revision.
- Reports clearly separate detected issues, repair plans, execution results,
  post-repair findings, and unresolved failures.

## User Scenarios

### Check Knowledge Health

The user runs lint and receives integrity findings spanning raw-to-projection
references, rather than only Markdown style findings.

### Repair Derived Drift

When an index or projection can be reconstructed from canonical state, lint
automatically invokes the established materialization path and verifies the
result with a rescan.

### Handle Semantic Extraction Problems

When claims, entities, relations, synthesis, or evidence mapping appear weak or
inconsistent, lint resolves the committed source revision and automatically
forces reingest. The ingest workflow remains the only producer of replacement
knowledge.
