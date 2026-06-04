# Direct HTTP Usage Without Python

Use this reference when the host AI environment cannot run `python3`. The
Python helper is preferred because it formats output and discovers config, but
all operations ultimately call the local KnoArbor HTTP API.

Set these values first:

```bash
export KNOARBOR_BASE_URL="http://127.0.0.1:8000"
export KNOARBOR_VAULT_PATH="/absolute/path/to/wiki"
```

## Check Service

```bash
curl -sS "$KNOARBOR_BASE_URL/health"
```

## Query Wiki Context

```bash
curl -sS -X POST "$KNOARBOR_BASE_URL/query" \
  -H 'Content-Type: application/json' \
  -d "{\"query\":\"agent loop\",\"vault_path\":\"$KNOARBOR_VAULT_PATH\",\"mode\":\"balanced\",\"context_format\":\"compact\",\"max_results\":6,\"include_related\":true,\"include_content\":false,\"caller\":\"generic-skill\"}"
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

## Start Folder Ingest

```bash
curl -sS -X POST "$KNOARBOR_BASE_URL/ingest" \
  -H 'Content-Type: application/json' \
  -d "{\"execution\":\"queued\",\"kind\":\"folder\",\"input_path\":\"/absolute/path/to/folder\",\"recursive\":true,\"write\":true,\"write_report\":true,\"append_ledger\":true}"
```

## Run Lint Maintenance

```bash
curl -sS -X POST "$KNOARBOR_BASE_URL/lint" \
  -H 'Content-Type: application/json' \
  -d "{\"execution\":\"queued\",\"vault_path\":\"$KNOARBOR_VAULT_PATH\",\"mode\":\"semantic_structural\",\"profile\":\"standard\",\"apply_safe_fixes\":true,\"auto_apply_reviewed_changes\":true,\"write_report\":true}"
```

## Reports

```bash
curl -sS --get "$KNOARBOR_BASE_URL/reports" \
  --data-urlencode "vault_path=$KNOARBOR_VAULT_PATH"
```

Prefer the Python helper when available; it avoids shell quoting mistakes,
formats text for the host AI, and discovers the active port from
`.knoarbor/endpoint.json`.
