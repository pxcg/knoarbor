#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
TMP_DIR="$(mktemp -d)"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

TEMP_CONFIG="$TMP_DIR/config.yaml"
TEMP_VAULT="$TMP_DIR/wiki"

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
uv run python - "$TEMP_CONFIG" "$TEMP_VAULT" <<'PY'
from pathlib import Path
import sys
import yaml

target = Path(sys.argv[1])
vault = Path(sys.argv[2])
data = yaml.safe_load(Path("config.example.yaml").read_text(encoding="utf-8"))
data["vault"]["path"] = str(vault)
data["connectors"]["markdown"]["settings"]["roots"] = [
    str(vault / "raw" / "notes"),
    str(vault / "raw" / "documents" / "markdown"),
]
target.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
PY
uv run knoar --config "$TEMP_CONFIG" init --vault "$TEMP_VAULT" >/dev/null
DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:-knoarbor-release-smoke-key}" uv run knoar --config "$TEMP_CONFIG" doctor >/dev/null

echo "6/6 Python package build"
uv build

echo "All local gates passed."
