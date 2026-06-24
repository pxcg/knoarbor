#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -z "${DEEPSEEK_API_KEY:-}" ]]; then
  echo "DEEPSEEK_API_KEY is required for the live release-candidate smoke test." >&2
  exit 2
fi

TMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

cd "$TMP_DIR"
mkdir -p wiki/raw/notes codex-sessions

# This live smoke intentionally calls a real model provider, but all config,
# sources, reports, and vault writes stay inside TMP_DIR.

cat > config.yaml <<'YAML'
project:
  name: release-candidate-smoke
  host_project_root: .
config_version: 1
vault:
  path: ./wiki
models:
  default_provider: deepseek
  default_max_tokens: 30000
  request_timeout_seconds: 600
  providers:
    deepseek:
      model: deepseek-v4-flash
      base_url: https://api.deepseek.com
      api_key_env: DEEPSEEK_API_KEY
      json_mode: true
connectors:
  markdown:
    enabled: true
    settings:
      roots:
        - ./wiki/raw/notes
      recursive: true
      raw_output_dir: ./wiki/raw/notes
      preserve_relative_paths: true
  codex:
    enabled: true
    settings:
      sessions_dir: ./codex-sessions
      pattern: "rollout-*.jsonl"
      recursive: true
      raw_output_dir: ./wiki/raw/chats
ingest:
  recovery:
    enabled: true
  concurrency:
    max_concurrent_sources: 2
  segmentation:
    enabled: true
    max_chars_per_segment: 18000
    soft_chars_per_segment: 12000
    max_segments_per_source: 8
    min_segment_chars: 800
YAML

cat > wiki/raw/notes/agent-loop.md <<'MD'
# Agent Loop Smoke Test

Agent Loop is a control pattern where a model repeatedly observes context,
reasons about the next step, calls tools when useful, and integrates tool
results before answering.

## Control Patterns

- ReAct combines reasoning and acting.
- Routing sends requests to specialized handlers.
- Evaluator-optimizer uses a reviewer to improve drafts.
MD

cat > codex-sessions/rollout-smoke.jsonl <<'JSONL'
{"type":"session_meta","timestamp":"2026-05-30T10:00:00Z","payload":{"id":"smoke","timestamp":"2026-05-30T10:00:00Z"}}
{"type":"response_item","timestamp":"2026-05-30T10:00:01Z","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"Agent Loop 的控制模式是什么？"}]}}
{"type":"response_item","timestamp":"2026-05-30T10:00:02Z","payload":{"type":"message","role":"assistant","content":[{"type":"output_text","text":"Agent Loop 通常包含观察、推理、行动和反馈，也可以组合 routing、parallelisation 和 evaluator-optimizer 等控制模式。"}]}}
JSONL

printf "%s" "%PDF-1.4" > missing-preprocessor.pdf

echo "== Live release candidate smoke =="
uv run --project "$ROOT_DIR" knoar --config config.yaml init --force >/dev/null
uv run --project "$ROOT_DIR" knoar --config config.yaml doctor >/dev/null
uv run --project "$ROOT_DIR" knoar --config config.yaml ingest --connector markdown --write --write-report --append-ledger --no-follow --json > ingest-markdown.json
uv run --project "$ROOT_DIR" knoar --config config.yaml ingest --connector codex --write --write-report --append-ledger --no-follow --json > ingest-codex.json
uv run --project "$ROOT_DIR" knoar --config config.yaml lint --mode structural --write-report --append-ledger --no-follow --json > lint.json
uv run --project "$ROOT_DIR" knoar --config config.yaml query "Agent Loop 控制模式" --json > query.json

set +e
uv run --project "$ROOT_DIR" knoar --config config.yaml ingest --input missing-preprocessor.pdf --no-write --json > nonmarkdown.json 2>nonmarkdown.err
nonmarkdown_status=$?
set -e
if [[ "$nonmarkdown_status" -eq 0 ]]; then
  echo "Expected non-Markdown ingest without MinerU to fail." >&2
  exit 1
fi
if ! grep -q "KA-DOC-001" nonmarkdown.err; then
  echo "Expected KA-DOC-001 for missing document preprocessor." >&2
  cat nonmarkdown.err >&2
  exit 1
fi

uv run --project "$ROOT_DIR" python - <<'PY'
import json
from pathlib import Path

base = Path(".")
markdown = json.loads((base / "ingest-markdown.json").read_text())
codex = json.loads((base / "ingest-codex.json").read_text())
lint = json.loads((base / "lint.json").read_text())
query = json.loads((base / "query.json").read_text())

summary = {
    "markdown_processed": markdown.get("stats", {}).get("processed_count"),
    "markdown_written": markdown.get("stats", {}).get("written_count"),
    "codex_processed": codex.get("stats", {}).get("processed_count"),
    "codex_written": codex.get("stats", {}).get("written_count"),
    "lint_report": lint.get("report_path"),
    "query_results": len(query.get("results", [])),
    "wiki_pages": len(list((base / "wiki").glob("*/*.md"))),
}
if not summary["markdown_processed"]:
    raise SystemExit("Markdown ingest processed no sources.")
if not summary["codex_processed"]:
    raise SystemExit("Codex ingest processed no sources.")
if not summary["query_results"]:
    raise SystemExit("Query returned no results.")
print(json.dumps(summary, ensure_ascii=False, indent=2))
PY

echo "Live release candidate smoke passed."
