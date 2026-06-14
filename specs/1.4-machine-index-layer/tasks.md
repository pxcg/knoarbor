# 1.4 Machine Index Layer Tasks

Status values:

- `[next]`: next reasonable implementation work.
- `[later]`: still in 1.4 scope, but not the next change.
- `[deferred]`: intentionally outside 1.4.

## Provider Contract

- [done] Define `PageIndexRecord` and `IndexProvider` contracts.
- [done] Add provider tests with the current Markdown provider.
- [done] Move current retrieval callers onto the provider boundary.
- [done] Add field-weighted BM25 page scoring to the Markdown provider.

## Durable Local Index

- [later] Design local index artifact path under the vault runtime boundary.
- [later] Implement SQLite FTS provider.
- [later] Track provider schema version and rebuild metadata.

## Rebuild And Freshness

- [later] Add rebuild service.
- [later] Add freshness diagnostics.
- [later] Decide whether rebuild is CLI-only first or public API at the same time.

## Query Integration

- [done] Record scoring model in query trace.
- [done] Expose page roles in query output: primary, supporting, and source.
- [done] Expose `answer_scope`, `answer_set`, and `evidence_coverage` so page-first callers can handle broad questions without treating pages as raw chunks.
- [later] Use durable machine index when fresh and available.
- [later] Keep Markdown provider as explicit fallback until durable provider is stable.
- [later] Record durable index provider and freshness in query trace.

## Deferred

- [deferred] Mandatory vector database.
- [deferred] Cross-device index sync.
- [deferred] Hosted search service.
