# Vault Layout v2 Verification

Run:

```bash
uv run python -m unittest \
  tests.test_wiki_paths_storage \
  tests.test_wiki_init \
  tests.test_ledger_storage \
  tests.test_ingest_report \
  tests.test_run_failure_audit \
  tests.test_wiki_index_storage
```

Expected:

- New vault initialization creates `wiki/pages`, `wiki/sources`, `maintenance/reports`, and `.knoarbor`.
- Report writes appear under `maintenance/reports/<flow>`.
- Ledger writes appear under `.knoarbor/ledgers`.
- Source checkpoint writes appear under `.knoarbor/checkpoints`.
- Page listing indexes only wiki pages and source digests, not maintenance artifacts.
