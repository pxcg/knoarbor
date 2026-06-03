# KnoArbor Local Skill Troubleshooting

## Check the connection

Run:

```bash
python3 scripts/knoarbor.py check
```

Use `--raw` for machine-readable diagnostics:

```bash
python3 scripts/knoarbor.py --raw check
```

## Service is unavailable

Start KnoArbor:

```bash
uv run knoar serve
```

The helper resolves the service URL in this order:

1. `--base-url`
2. `KNOARBOR_BASE_URL`
3. `.knoarbor/endpoint.json` next to `config.yaml`
4. `server.host` and `server.port` from `config.yaml`
5. `http://127.0.0.1:8000`

If `8000` is occupied, `knoar serve` may choose another port and write it to
`.knoarbor/endpoint.json`.

## Vault path is missing

Set one of:

```bash
export KNOARBOR_VAULT_PATH=/absolute/path/to/wiki
python3 scripts/knoarbor.py --vault /absolute/path/to/wiki query "agent loop"
python3 scripts/knoarbor.py --config /path/to/config.yaml query "agent loop"
```

The helper resolves the vault path in this order:

1. `--vault`
2. `KNOARBOR_VAULT_PATH`
3. `vault.path` from `config.yaml`

## Query returns no results

- Try a shorter query.
- Use the original terms from the wiki page title when possible.
- Use `--mode deep` for broader evidence.
- Check that the target source has already been ingested.

## Need full page content

Use full content only when the user explicitly asks for detailed page reading:

```bash
python3 scripts/knoarbor.py page read concepts/Agent-Loop-and-Control-Patterns.md
```

If the exact page path is not known, first run a query and then read the
returned `results[].path`.

## Response is too large

Use compact mode:

```bash
python3 scripts/knoarbor.py query "agent loop" --context-format compact --max-results 4
```
