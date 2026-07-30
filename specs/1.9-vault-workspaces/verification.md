# Vault Workspaces Verification

## Automated

```bash
uv run --offline python -m unittest \
  tests.test_api_surface \
  tests.test_cli \
  tests.test_skill_query_helper

uv run --offline ruff check src tests integrations/skills/knoarbor-local/scripts/knoarbor.py
uv run --offline python scripts/check-doc-links.py
cd renderer && npm run build
```

## Manual

1. Start the service with a config containing at least two vault profiles.
2. Open `/docs` and confirm `GET /vaults` is present.
3. Run `knoar vaults`.
4. Run the skill helper with `vaults list`.
5. Use one listed `vault_id` with query/page/report commands.
6. Select different vaults from Wiki, graph, ingest, lint, reports, and tokens;
   confirm each page reloads the matching vault-scoped data.
7. Select Chat's all-vault scope, then open Knowledge; confirm Knowledge still
   uses the concrete workspace vault.

Verified 2026-07-18: the renderer production build and all 7 Playwright cases
passed with two mocked vaults; Wiki, graph, flows, reports, and tokens shared a
concrete page-local selection while Chat retained its independent all-vault
scope. Reports exposed no nested vault filter, hidden Tokens issued no requests
after a workspace-vault change, and run/report citation navigation required its
originating vault identity.
