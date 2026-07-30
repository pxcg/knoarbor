# Model Capability Check Verification

## Unit Tests

Run:

```bash
uv run --offline python -m unittest tests.test_model_probe tests.test_semantic_runner tests.test_api_surface
uv run --offline python -m unittest discover tests
uv run --offline ruff check src tests
```

Expected coverage:

- provider list hides secrets and marks credential readiness;
- discovery parses OpenAI-compatible `/models` metadata;
- Ollama context metadata can be detected from `/api/show`;
- apply endpoint updates only allowed provider fields.
- root and exact full endpoint inputs resolve to one canonical base URL;
- partial completion paths, URL credentials, queries, and fragments fail before
  discovery or generation;
- discovery and completion append their paths exactly once.

## Manual Checks

With a local provider configured:

```bash
uv run knoar serve
curl http://127.0.0.1:8000/models/providers
curl -X POST http://127.0.0.1:8000/models/discover \
  -H 'Content-Type: application/json' \
  -d '{"provider":"vllm"}'
```

For hosted providers, configure `api_key` directly in the isolated test
`config.yaml`.

## Release Gate

This feature is release-ready when the public API docs, config docs, specs, and
tests agree on the same endpoint names and field names.

## Current Verification

- `uv run --offline python -m unittest discover tests`: 385 tests passed.
- `uv run --offline ruff check src tests`: passed.
