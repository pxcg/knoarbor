# 1.7 CLI, API, And Skill Closure Verification

## Automated Checks

Required when public entry points change:

```bash
uv run python -m unittest tests.test_api_surface tests.test_cli tests.test_skill_query_helper tests.test_run_monitor tests.test_query_pipeline
uv run python scripts/check-doc-links.py
```

Before release:

```bash
scripts/dev-check.sh
scripts/clean-clone-smoke.sh
```

## Manual Smoke

Use a temporary vault:

1. `knoar doctor`.
2. `knoar sources --catalog`.
3. `knoar ingest --input <example.md> --write`.
4. `knoar lint --mode deterministic`.
5. `knoar query "Agent Loop 是什么？"`.
6. Read reports and wiki pages through API.
7. Use the skill helper for query, page content, report, and source catalog.

## Regression Risks

- CLI and API naming drift.
- Skill depending on local absolute project paths.
- Public docs accidentally describing `/ui/api/*`.
- Query becoming answer generation rather than evidence retrieval.

## Release Evidence

For a 1.7 release note, mention:

- public API closure changes;
- CLI parity improvements;
- skill operation maturity;
- compatibility decisions before 2.0.
