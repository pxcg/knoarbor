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
echo "1/14 Renderer build"
(cd renderer && npm run build)

echo "2/14 Renderer dependency audit"
(cd renderer && npm audit --audit-level=moderate)

echo "3/14 Renderer e2e smoke"
(cd renderer && npm run test:e2e)

echo "4/14 Desktop contracts"
(cd desktop && npm run typecheck && npm test && npm run verify:icons && npm run build)

echo "5/14 Desktop production dependency audit"
(cd desktop && npm audit --omit=dev --audit-level=high)

echo "6/14 Python lint"
uv run --extra dev ruff check src tests scripts

echo "7/14 Documentation governance"
uv run python scripts/check-doc-governance.py

echo "8/14 Documentation links"
uv run python scripts/check-doc-links.py

echo "9/14 Architecture governance"
uv run python scripts/check-architecture.py

echo "10/14 Product identity generation"
uv run python scripts/generate-product-identity.py --check

echo "11/14 Public product boundary"
uv run python scripts/check-public-product-boundary.py

echo "12/14 Python tests"
uv run python -m unittest discover -s tests

echo "13/14 CLI diagnostics"
# Keep release checks isolated from the maintainer's real config.yaml and wiki/.
uv run python - "$TEMP_CONFIG" "$TEMP_VAULT" <<'PY'
from pathlib import Path
import sys
import yaml

target = Path(sys.argv[1])
vault = Path(sys.argv[2])
data = yaml.safe_load(Path("config.example.yaml").read_text(encoding="utf-8"))
data["vault"]["path"] = str(vault)
data["vaults"]["profiles"]["default"]["path"] = str(vault)
data["connectors"]["markdown"]["settings"]["roots"] = [
    str(vault / "raw" / "inbox" / "notes"),
    str(vault / "raw" / "normalized" / "markdown"),
]
data["models"]["default_provider"] = "release-smoke"
data["models"]["providers"]["release-smoke"] = {
    "base_url": "https://api.deepseek.com",
    "api_key": "knoarbor-release-smoke-key",
    "model": "deepseek-chat",
}
target.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
PY
uv run knoar --config "$TEMP_CONFIG" init --vault "$TEMP_VAULT" >/dev/null
uv run knoar --config "$TEMP_CONFIG" doctor >/dev/null

echo "14/14 Python package build"
uv build

echo "All local gates passed."
