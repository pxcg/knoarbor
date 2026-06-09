# 1.4 Machine Index Layer Verification

## Automated Checks

Required when index code changes:

```bash
uv run python -m unittest tests.test_query_pipeline tests.test_retrieval_markdown tests.test_wiki_index_storage
uv run python scripts/check-doc-links.py
```

Once a durable provider exists, add dedicated provider tests for:

- record extraction;
- fresh/stale detection;
- rebuild idempotence;
- query ranking stability;
- corrupted or missing index files.

## Manual Smoke

Before exposing public rebuild commands:

1. Create a temporary vault.
2. Generate several pages.
3. Build the machine index.
4. Query a known concept.
5. Modify one page.
6. Confirm freshness reports stale state.
7. Rebuild and confirm query still works.

## Regression Risks

- Treating an index as the source of truth for page content.
- Returning stale results without trace metadata.
- Making query slower by rebuilding synchronously.
- Adding a vector dependency to the default path.

## Release Evidence

For a 1.4 release note, mention:

- provider contract;
- durable local index provider if implemented;
- rebuild/freshness surfaces;
- query trace improvements.
