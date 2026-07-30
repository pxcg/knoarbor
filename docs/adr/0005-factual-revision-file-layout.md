# ADR 0005: Factual Revision File Layout

## Status

Accepted

## Context

ADR 0004 established immutable source revisions selected by SQLite source heads
as ingest factual authority. Its original path and payload names used
implementation-oriented terminology and did not clearly separate source,
accepted knowledge, and diagnostics for backup and inspection.

## Decision

Published factual revisions use this physical shape:

```text
.knoarbor/facts/<source-key>/<revision-key>/
  source.json
  knowledge.json
  diagnostics.json
  manifest.json
```

`source.json` stores source identity, units, ranges, and attachment metadata.
`knowledge.json` stores accepted synthesis, entities, claims, relations, and
evidence. `diagnostics.json` stores non-factual extraction audit data.
`manifest.json` binds identity and file hashes.

SQLite source and session heads remain the only active-revision selectors.
Directory ordering and modification times have no authority. Random paths are
limited to unreachable `.knoarbor/facts/.staging/` writes.

Legacy factual generations migrate without model calls. Current readers do not
retain a legacy fallback after migration.

## Consequences

- Backup and recovery have one inspectable factual tree.
- File names describe domain content instead of internal pipeline classes.
- Projection and machine indexes remain rebuildable.
- Migration verifies payload schemas and hashes before changing SQLite
  manifest pointers.

## Supersession

This ADR supersedes only the physical source-revision path and payload naming in
ADR 0004. ADR 0004 continues to own factual authority, transactional source
heads, and rebuildable materialization.

## Verification

Specifications 1.17, 1.26, and 1.37 require exact artifact-tree, integrity,
migration, crash-recovery, and model-free rebuild tests.
