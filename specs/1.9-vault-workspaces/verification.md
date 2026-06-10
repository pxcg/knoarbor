# Vault Workspaces Verification

## Automated

```bash
uv run --offline python -m unittest \
  tests.test_api_surface \
  tests.test_cli \
  tests.test_skill_query_helper

uv run --offline ruff check src tests integrations/skills/knoarbor-local/scripts/knoarbor.py
uv run --offline python scripts/check-doc-links.py
```

## Manual

1. Start the service with a config containing at least two vault profiles.
2. Open `/docs` and confirm `GET /vaults` is present.
3. Run `knoar vaults`.
4. Run the skill helper with `vaults list`.
5. Use one listed `vault_id` with query/page/report commands.
