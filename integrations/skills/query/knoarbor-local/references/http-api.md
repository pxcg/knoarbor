# Direct HTTP API Usage

Use this reference when the host AI environment cannot run `python3`, or when
the host tool has a native HTTP client. Direct HTTP calls do not perform helper
formatting.

## Discover Runtime Context

If the service URL is already known, read the runtime context first:

```bash
export KNOARBOR_BASE_URL="http://127.0.0.1:8000"

curl -sS "$KNOARBOR_BASE_URL/runtime"
```

The response includes `base_url`, `config_path`, `vault_path`, and
`endpoint_path`. Use `vault_path` as `KNOARBOR_VAULT_PATH` for later calls.

If the service auto-selected a different port and the host can read local files,
read the user-level `.knoarbor/endpoint.json` written by `knoar serve`, or the
project-local `.knoarbor/endpoint.json` next to `config.yaml`; it contains the
active `base_url` and `vault_path`.

If neither the service URL nor the endpoint file is available to the host, ask
the user for the KnoArbor base URL once.

The examples below use shell variables populated from runtime discovery:

```bash
export KNOARBOR_BASE_URL="http://127.0.0.1:8000"
export KNOARBOR_VAULT_PATH="/absolute/path/to/wiki"
export KNOARBOR_CONFIG_PATH="/absolute/path/to/config.yaml"
```

## Check Service

```bash
curl -sS "$KNOARBOR_BASE_URL/health"
```

## Diagnostics

```bash
curl -sS --get "$KNOARBOR_BASE_URL/doctor"
```

## Source Catalog

```bash
curl -sS --get "$KNOARBOR_BASE_URL/sources" \
  --data-urlencode "config_path=$KNOARBOR_CONFIG_PATH"

curl -sS --get "$KNOARBOR_BASE_URL/sources" \
  --data-urlencode "config_path=$KNOARBOR_CONFIG_PATH" \
  --data-urlencode "connector=codex"
```

This reads connector capabilities and settings schemas only. It does not scan
local files and does not start ingest.

## Query Wiki Context

```bash
curl -sS -X POST "$KNOARBOR_BASE_URL/query" \
  -H 'Content-Type: application/json' \
  -d "{\"query\":\"agent loop\",\"vault_path\":\"$KNOARBOR_VAULT_PATH\",\"mode\":\"balanced\",\"context_format\":\"compact\",\"max_results\":6,\"include_related\":true,\"include_content\":false,\"caller\":\"generic-skill\"}"
```

Query all configured vaults:

```bash
curl -sS -X POST "$KNOARBOR_BASE_URL/query" \
  -H 'Content-Type: application/json' \
  -d "{\"query\":\"agent loop\",\"config_path\":\"$KNOARBOR_CONFIG_PATH\",\"all_vaults\":true,\"mode\":\"balanced\",\"context_format\":\"compact\",\"max_results\":6,\"include_related\":true,\"include_content\":false,\"caller\":\"generic-skill\"}"
```

Query selected configured vaults:

```bash
curl -sS -X POST "$KNOARBOR_BASE_URL/query" \
  -H 'Content-Type: application/json' \
  -d "{\"query\":\"agent loop\",\"config_path\":\"$KNOARBOR_CONFIG_PATH\",\"vault_ids\":[\"personal\",\"team\"],\"mode\":\"balanced\",\"context_format\":\"compact\",\"max_results\":6,\"include_related\":true,\"include_content\":false,\"caller\":\"generic-skill\"}"
```

## List Pages

```bash
curl -sS --get "$KNOARBOR_BASE_URL/wiki/pages" \
  --data-urlencode "vault_path=$KNOARBOR_VAULT_PATH"
```

## Read One Page

```bash
curl -sS --get "$KNOARBOR_BASE_URL/wiki/pages/content" \
  --data-urlencode "vault_path=$KNOARBOR_VAULT_PATH" \
  --data-urlencode "path=concepts/Agent-Loop-and-Control-Patterns.md"
```

Read a page selected from a multi-vault query result:

```bash
curl -sS --get "$KNOARBOR_BASE_URL/wiki/pages/content" \
  --data-urlencode "config_path=$KNOARBOR_CONFIG_PATH" \
  --data-urlencode "vault_id=personal" \
  --data-urlencode "path=concepts/Agent-Loop-and-Control-Patterns.md"
```

## Page Links

```bash
curl -sS --get "$KNOARBOR_BASE_URL/wiki/pages/links" \
  --data-urlencode "vault_path=$KNOARBOR_VAULT_PATH" \
  --data-urlencode "path=concepts/Agent-Loop-and-Control-Patterns.md"
```

Inspect links for a page selected from a multi-vault query result:

```bash
curl -sS --get "$KNOARBOR_BASE_URL/wiki/pages/links" \
  --data-urlencode "config_path=$KNOARBOR_CONFIG_PATH" \
  --data-urlencode "vault_id=personal" \
  --data-urlencode "path=concepts/Agent-Loop-and-Control-Patterns.md"
```

## Start Connector Ingest

```bash
curl -sS -X POST "$KNOARBOR_BASE_URL/ingest" \
  -H 'Content-Type: application/json' \
  -d "{\"execution\":\"queued\",\"kind\":\"connectors\",\"config_path\":\"$KNOARBOR_CONFIG_PATH\",\"vault_id\":\"personal\",\"connector_names\":[\"codex\"],\"write\":true,\"write_report\":true,\"append_ledger\":true}"
```

## Start File Ingest

```bash
curl -sS -X POST "$KNOARBOR_BASE_URL/ingest" \
  -H 'Content-Type: application/json' \
  -d "{\"execution\":\"queued\",\"kind\":\"file\",\"config_path\":\"$KNOARBOR_CONFIG_PATH\",\"vault_id\":\"personal\",\"input_path\":\"/absolute/path/to/file.md\",\"write\":true,\"write_report\":true,\"append_ledger\":true}"
```

## Start Folder Ingest

```bash
curl -sS -X POST "$KNOARBOR_BASE_URL/ingest" \
  -H 'Content-Type: application/json' \
  -d "{\"execution\":\"queued\",\"kind\":\"folder\",\"config_path\":\"$KNOARBOR_CONFIG_PATH\",\"vault_id\":\"personal\",\"input_path\":\"/absolute/path/to/folder\",\"recursive\":true,\"write\":true,\"write_report\":true,\"append_ledger\":true}"
```

## Retry Failed Ingest

```bash
curl -sS -X POST "$KNOARBOR_BASE_URL/ingest" \
  -H 'Content-Type: application/json' \
  -d "{\"execution\":\"queued\",\"kind\":\"recovery\",\"config_path\":\"$KNOARBOR_CONFIG_PATH\",\"vault_id\":\"personal\",\"recovery_of_run_id\":\"RUN_ID\",\"write\":true,\"write_report\":true,\"append_ledger\":true}"
```

Ingest is a write workflow and targets one vault per request. Use
`vault_path`, or use `config_path` plus `vault_id` for a configured vault.

## Run Lint Maintenance

```bash
curl -sS -X POST "$KNOARBOR_BASE_URL/lint" \
  -H 'Content-Type: application/json' \
  -d "{\"execution\":\"queued\",\"config_path\":\"$KNOARBOR_CONFIG_PATH\",\"vault_id\":\"personal\",\"mode\":\"semantic_structural\",\"profile\":\"standard\",\"apply_safe_fixes\":true,\"auto_apply_reviewed_changes\":true,\"write_report\":true,\"scope\":{\"schema_version\":\"maintenance_scope.v1\",\"scope_id\":\"skill:http\",\"trigger\":\"manual\",\"source\":{\"kind\":\"skill\"},\"changed_pages\":[],\"recommended_lint_modes\":[\"semantic_structural\"],\"reason\":\"Manual maintenance run from KnoArbor skill.\"}}"
```

Lint is also write-capable and targets one vault per request.

## Reports

```bash
curl -sS --get "$KNOARBOR_BASE_URL/reports" \
  --data-urlencode "vault_path=$KNOARBOR_VAULT_PATH"

curl -sS --get "$KNOARBOR_BASE_URL/reports" \
  --data-urlencode "config_path=$KNOARBOR_CONFIG_PATH" \
  --data-urlencode "all_vaults=true"
```

## Read One Report

```bash
curl -sS --get "$KNOARBOR_BASE_URL/reports/content" \
  --data-urlencode "vault_path=$KNOARBOR_VAULT_PATH" \
  --data-urlencode "path=maintenance/ingest_report_YYYYMMDD_HHMMSS.md"
```

## Runs

```bash
curl -sS --get "$KNOARBOR_BASE_URL/runs" \
  --data-urlencode "vault_path=$KNOARBOR_VAULT_PATH" \
  --data-urlencode "active_only=false" \
  --data-urlencode "limit=10"

curl -sS --get "$KNOARBOR_BASE_URL/runs" \
  --data-urlencode "config_path=$KNOARBOR_CONFIG_PATH" \
  --data-urlencode "all_vaults=true" \
  --data-urlencode "active_only=false" \
  --data-urlencode "limit=10"

curl -sS --get "$KNOARBOR_BASE_URL/runs/RUN_ID" \
  --data-urlencode "vault_path=$KNOARBOR_VAULT_PATH"

curl -sS --get "$KNOARBOR_BASE_URL/runs/RUN_ID/events" \
  --data-urlencode "vault_path=$KNOARBOR_VAULT_PATH" \
  --data-urlencode "after=0" \
  --data-urlencode "limit=50"

curl -sS -X POST -G "$KNOARBOR_BASE_URL/runs/RUN_ID/cancel" \
  --data-urlencode "vault_path=$KNOARBOR_VAULT_PATH"
```

For host AI use, summarize returned JSON instead of pasting it verbatim unless
the user asks for raw structured output.

When a value contains spaces or shell-sensitive characters, prefer the host
tool's HTTP client with structured query parameters.
