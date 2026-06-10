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

Recommended recovery order:

1. Run `python3 scripts/knoarbor.py check`.
2. If `service_online` is false, ask the user to start KnoArbor and retry.
3. If the base URL points to the wrong port, use the endpoint file reported by
   `check` or pass `--base-url` once for that call.
4. If the service is online but the vault is missing, use one of the available
   vault IDs from `check`.

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

If multiple knowledge bases are configured, use the reported vault ID:

```bash
python3 scripts/knoarbor.py --vault-id personal query "agent loop"
python3 scripts/knoarbor.py --vault-id personal page read concepts/Agent-Loop.md
```

If a command says `Requested vault ID` and lists `Available vault IDs`, rerun the
operation with one of the listed IDs. For broad search across configured
knowledge bases, use query with `--all-vaults` instead of a single vault ID.

## Page path is missing or wrong

When `page read` or `page links` fails because a page path cannot be found:

1. Run `python3 scripts/knoarbor.py page list --contains "keyword"`.
2. If the page came from a multi-vault query result, repeat the command with
   that result's `vault_id`.
3. Use the exact returned `path` value. Page titles and display names are not
   accepted as path substitutes.

## Query returns no results

- Try a shorter query.
- Use the original terms from the wiki page title when possible.
- Use `--mode deep` for broader evidence.
- Check that the target source has already been ingested.

For multi-vault installations, retry with:

```bash
python3 scripts/knoarbor.py query "topic" --all-vaults
```

If results are still weak, report that the local wiki does not contain enough
evidence and ask whether to compile additional sources.

## Ingest or lint starts but progress is unclear

List recent runs, then inspect the selected run and its events:

```bash
python3 scripts/knoarbor.py runs list
python3 scripts/knoarbor.py runs get RUN_ID
python3 scripts/knoarbor.py runs events RUN_ID
```

If the run has a report path, read it:

```bash
python3 scripts/knoarbor.py report read maintenance/ingest_report_YYYYMMDD_HHMMSS.md
```

For failed ingest runs that report recoverable items, use:

```bash
python3 scripts/knoarbor.py ingest recovery RUN_ID
```

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
