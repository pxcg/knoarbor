#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "== KnoArbor local gates =="
echo "1/6 Frontend build"
(cd web && npm run build)

echo "2/6 Frontend dependency audit"
(cd web && npm audit --audit-level=moderate)

echo "3/6 Frontend e2e smoke"
(cd web && npm run test:e2e)

echo "4/6 Python tests"
uv run python -m unittest discover -s tests

echo "5/6 CLI diagnostics"
uv run knoar init --vault wiki >/dev/null
DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:-knoarbor-release-smoke-key}" uv run knoar --config config.example.yaml doctor >/dev/null

echo "6/6 Python package build"
uv build

echo "All local gates passed."
