# 1.6 Productized Console Verification

## Automated Checks

Required when console behavior changes:

```bash
cd web && npm run build
cd web && npm run test:e2e
uv run python -m unittest tests.test_ui_api tests.test_api_surface
uv run python scripts/check-doc-links.py
```

## Manual UI Review

Inspect at least:

- Dashboard / overview.
- Sources.
- Runs.
- Ingest.
- Lint.
- Query.
- Wiki pages.
- Graph.
- Reports.
- Settings.
- Project docs.

Review for:

- layout stability;
- no hidden expensive refresh;
- clear empty/error/loading states;
- readable report summaries before raw details;
- vault-aware state.

## Regression Risks

- UI drifting into a second backend implementation.
- Excessive page-load diagnostics.
- Components becoming too granular and hard to trace.
- Raw report payloads becoming the primary user experience.

## Release Evidence

For a 1.6 release note, mention:

- navigation and layout improvements;
- loading and diagnostics changes;
- report/diff readability improvements;
- component consolidation or component-library decision.
