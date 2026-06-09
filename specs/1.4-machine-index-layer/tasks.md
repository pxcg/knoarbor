# 1.4 Machine Index Layer Tasks

Status values:

- `[next]`: next reasonable implementation work.
- `[later]`: still in 1.4 scope, but not the next change.
- `[deferred]`: intentionally outside 1.4.

## Provider Contract

- [next] Define `PageIndexRecord` and `IndexProvider` contracts.
- [next] Add provider tests with the current Markdown provider.
- [later] Move current retrieval callers onto the provider boundary.

## Durable Local Index

- [later] Design local index artifact path under the vault runtime boundary.
- [later] Implement SQLite FTS/BM25-style provider.
- [later] Track provider schema version and rebuild metadata.

## Rebuild And Freshness

- [later] Add rebuild service.
- [later] Add freshness diagnostics.
- [later] Decide whether rebuild is CLI-only first or public API at the same time.

## Query Integration

- [later] Use machine index when fresh and available.
- [later] Keep Markdown provider as explicit fallback until durable provider is stable.
- [later] Record index provider and freshness in query trace.

## Deferred

- [deferred] Mandatory vector database.
- [deferred] Cross-device index sync.
- [deferred] Hosted search service.
