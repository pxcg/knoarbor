# Vault Layout v2 Verification

Run:

```bash
uv run python -m unittest \
  tests.test_wiki_paths_storage \
  tests.test_wiki_init \
  tests.test_ledger_storage \
  tests.test_ingest_report \
  tests.test_run_failure_audit \
  tests.test_wiki_index_storage \
  tests.test_source_revisions
```

Expected:

- New vault initialization creates `wiki/pages`, the reserved `wiki/sources`
  namespace, `maintenance/reports`, and `.knoarbor`.
- Current ingest writes its readable projection only under `wiki/pages`.
- Report writes appear under `maintenance/reports/<flow>`.
- Ledger writes appear under `.knoarbor/ledgers`.
- Source checkpoint writes appear under `.knoarbor/checkpoints`.
- Page listing indexes only wiki pages and source records, not maintenance artifacts.
- A published source revision has one deterministic
  `.knoarbor/facts/<source-key>/<revision-key>` path with exactly four files.
- Staging paths are ignored by readers and removable after interruption.
- Fact JSON references attachment assets without copying their bytes.
- Legacy fact generations migrate once, retain integrity, and are not read
  after migration completion.
- Backup and restore preserve source heads, fact directories, raw assets, and
  rebuildable projection behavior.
