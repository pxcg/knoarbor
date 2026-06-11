# Troubleshooting

This guide focuses on common first-run and local-runtime problems. For stable
error codes, see [Error Codes](ERROR_CODES.md).

## First Checks

Run:

```bash
uv run knoar doctor
uv run knoar status --vault vaults/all
```

`doctor` is read-only. It checks configuration, vault structure, model
environment variables, connector availability, document preprocessing settings,
and recent run state.

## Config File Does Not Exist

Symptom:

```text
[KA-CFG-001] Config file does not exist
```

Fix:

```bash
cp config.example.yaml config.yaml
cp .env.example .env
```

Then edit `config.yaml` and load secrets:

```bash
set -a && source .env && set +a
uv run knoar doctor
```

## API Key Or Model Provider Is Missing

Symptoms:

- `doctor` reports the model environment variable is missing.
- Ingest or lint fails while waiting for a model.
- Query works but semantic workflows fail.

Fix:

1. Confirm `models.default_provider` in `config.yaml`.
2. For hosted providers, confirm the provider has `api_key_env`.
3. Confirm that environment variable is exported in the shell running KnoArbor.
4. For local or private endpoints such as Ollama/vLLM, set `api_key_env: null` and confirm the endpoint is running.

Example:

```bash
export DEEPSEEK_API_KEY=...
uv run knoar doctor
```

## UI Opens But Shows No Pages

Common causes:

- The vault has no generated pages yet.
- Machine indexes are stale.
- The UI is pointed at a different vault path.

Fix:

```bash
uv run knoar --config config.yaml status --vault vaults/all
uv run python - <<'PY'
from pathlib import Path
from knoarbor.storage import update_index
update_index(Path("vaults/all"))
PY
```

Then refresh the console.

## Ingest Skips Sources

Skipping is usually expected when the source checkpoint hash has not changed.

Check:

- Ingest report under `vaults/all/maintenance/`.
- Connector roots in `config.yaml`.
- `uv run knoar sources --connector markdown --json`.

To process a changed file, edit the source content or remove only the relevant
checkpoint after making a backup. Do not delete the whole vault to force ingest.

## PDF Or Office File Fails To Ingest

Markdown files run directly. Rich documents such as PDF, DOCX, PPTX, and XLSX
require a configured document preprocessor.

If MinerU is not configured, non-Markdown ingest should fail with:

```text
KA-DOC-001
```

Fix:

- Start a compatible MinerU service.
- Configure `document_processing.mineru.endpoint`.
- Run `uv run knoar doctor` to verify the preprocessor.

## Run Appears Stuck

Long semantic workflows may wait on model calls. Check the run monitor:

```bash
uv run knoar runs --vault vaults/all
uv run knoar runs events <run_id> --vault vaults/all
```

If cancellation is needed:

```bash
uv run knoar runs cancel <run_id> --vault vaults/all
```

Cancellation is cooperative. An active model call may finish before the pipeline
stops at the next checkpoint.

## Restored Pages Are Not Searchable

If files were restored manually, rebuild indexes:

```bash
uv run python - <<'PY'
from pathlib import Path
from knoarbor.storage import update_index
update_index(Path("vaults/all"))
PY
```

See [Backup And Recovery](BACKUP_AND_RECOVERY.md) for more recovery guidance.

## Frontend Build Or UI Asset Problems

When changing UI source:

```bash
cd web
npm install
npm run build
```

The built assets are copied to `src/knoarbor/ui/dist/` and served by
`uv run knoar serve`.

## Still Blocked

When opening an issue, include:

- KnoArbor version or commit.
- Command or endpoint used.
- Redacted config section.
- Redacted error output.
- Whether the problem happens in a temporary vault.

Do not include API keys, private notes, raw documents, or full local chat logs.
