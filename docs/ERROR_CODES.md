# Error Codes

KnoArbor returns structured errors from the CLI and public HTTP API. Error codes are stable lookup keys for users, logs, UI messages, and support notes.

## Error Shape

HTTP errors use this shape:

```json
{
  "error": {
    "code": "KA-INPUT-001",
    "category": "user_input_error",
    "message": "Request validation failed.",
    "retryable": false,
    "hint": "Check the command arguments or request payload and retry."
  },
  "detail": "Request validation failed."
}
```

CLI errors use the same catalog:

```text
knoarbor: error: [KA-CFG-001] user_input_error: Config file does not exist: /path/config.yaml
hint: Create config.yaml from config.example.yaml or pass --config with a valid path.
```

## Catalog

| Code | Category | HTTP | Retryable | Meaning | Typical action |
| --- | --- | ---: | --- | --- | --- |
| `KA-INPUT-001` | `user_input_error` | 400/422 | No | Invalid request, invalid command argument, unsupported value, or failed schema validation. | Check the command/API payload, required fields, paths, and option values. |
| `KA-INPUT-002` | `user_input_error` | 400 | No | A required local file or path does not exist. | Create the file, fix the configured path, or run `knoar init` for a missing vault. |
| `KA-CFG-001` | `user_input_error` | 400 | No | A required KnoArbor config file does not exist. | Create the config file, pass `--config`, or run `knoar init`. |
| `KA-CFG-002` | `user_input_error` | 400 | No | Config content is malformed, unsupported, or internally inconsistent. | Fix the YAML/JSON structure, unsupported extension, or invalid option combination. |
| `KA-VAULT-001` | `user_input_error` | 400 | No | Vault path, wiki page path, checkpoint path, or ledger path is invalid or escapes the vault. | Use a path under the configured vault and avoid absolute/parent traversal paths for wiki writes. |
| `KA-SRC-001` | `user_input_error` | 400 | No | Source connector configuration or source reference is invalid. | Check connector settings, source refs, file URI metadata, and enabled connector names. |
| `KA-SRC-002` | `user_input_error` | 400 | No | A configured source root, source file, or chat session file does not exist. | Fix the source path or connector configuration before ingest. |
| `KA-DOC-001` | `user_input_error` | 400 | No | A non-Markdown document needs preprocessing but the configured processor is unavailable or incomplete. | Enable and configure the document processor, or provide preprocessed Markdown. |
| `KA-EXT-001` | `external_service_error` | 502 | Yes | A configured external service failed, such as an OpenAI-compatible model endpoint or document processor. | Check service availability, credentials, endpoint URL, timeout, and retry later. |
| `KA-MODEL-001` | `model_output_error` | 502 | Yes | The model response was not valid JSON or did not match the expected structured contract. | Retry with the same input, lower input size, or use a more reliable model/provider. |
| `KA-SEM-001` | `model_output_error` | 502 | Yes | A semantic contract, prompt contract, or model response shape was invalid. | Retry, inspect the contract name/schema, or use a more reliable model/provider. |
| `KA-POLICY-001` | `policy_rejection` | 422 | No | A generated operation or draft was rejected by KnoArbor policy. | Inspect the report and adjust the source, prompt contract, or policy if the rejection is expected. |
| `KA-STORAGE-001` | `storage_conflict` | 409 | Yes | A vault write conflict, stale hash, or lock conflict prevented a safe write. | Re-run after the other process finishes, or refresh the page/index state. |
| `KA-RUN-001` | `user_input_error` | 400 | No | Requested run monitor record does not exist. | Refresh the run list or use a valid run id. |
| `KA-RUNTIME-001` | `internal_error` | 500 | No | Required local runtime capability is unavailable, such as file locking on an unsupported platform. | Run on a supported platform or open an issue with environment details. |
| `KA-INTERNAL-001` | `internal_error` | 500 | No | Unexpected internal failure. | Preserve the run report/log and open an issue with the stack trace and reproduction steps. |

## Design Rules

- New public errors must use this catalog rather than ad-hoc strings.
- `code` is the stable lookup key. `message` may become clearer over time.
- `category` is for coarse programmatic handling and can group multiple codes.
- `retryable=true` only means automatic retry is reasonable; it does not guarantee success.
- API clients should display `message` and `hint`, log `code/category/retryable`, and keep any `details` object for debugging.
- Run monitor records, run events, semantic retry events, and ingest reports should carry the same `code/category/retryable/hint` fields whenever an operation fails.
