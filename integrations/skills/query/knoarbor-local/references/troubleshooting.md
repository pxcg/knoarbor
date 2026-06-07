# KnoArbor Local Skill Troubleshooting

## Check the connection

Run:

```bash
python3 scripts/knoarbor.py check
```

Use `--format json` for machine-readable diagnostics:

```bash
python3 scripts/knoarbor.py --format json check
```

## Service is unavailable

Start KnoArbor:

```bash
uv run knoar serve
```

The helper discovers the service from the active runtime endpoint and local
project config when those files are available.

If `8000` is occupied, `knoar serve` may choose another port and write it to
the user-level `.knoarbor/endpoint.json` and the project-local
`.knoarbor/endpoint.json`. These files include the active `base_url` and
`vault_path`.

## Python is unavailable

The helper needs Python 3.9 or newer, but KnoArbor itself is still accessible
through HTTP. Use `references/http-api.md` for direct `curl` examples. In this
mode:

1. If a base URL is known, call `GET /runtime` to discover `vault_path`.
2. If the port is unknown and local files are readable, read the user-level
   `.knoarbor/endpoint.json` or the project-local endpoint next to
   `config.yaml`.
3. If neither is available, ask the user for the KnoArbor base URL once.

## Vault path is missing

Run:

```bash
python3 scripts/knoarbor.py check
```

The output reports the resolved service URL, config path, vault path, and any
connectivity errors.

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
