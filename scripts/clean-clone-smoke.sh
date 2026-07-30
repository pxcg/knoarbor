#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="${1:-$ROOT_DIR}"
TMP_DIR="$(mktemp -d)"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

echo "== Clean clone smoke test =="
echo "source: $SOURCE"
echo "workdir: $TMP_DIR"

git clone --quiet "$SOURCE" "$TMP_DIR/knoarbor"
cd "$TMP_DIR/knoarbor"
UV=(env -u VIRTUAL_ENV uv)

# Safe: all writes below happen inside this temporary clone, never in the
# maintainer's working tree or real runtime vault.
"${UV[@]}" sync --extra dev
(cd renderer && npm install && npm run build)
"${UV[@]}" run python -m unittest discover -s tests
"${UV[@]}" run knoar --help >/dev/null
SMOKE_ROOT="$TMP_DIR/runtime"
SMOKE_CONFIG="$SMOKE_ROOT/config.yaml"
SMOKE_VAULT="$SMOKE_ROOT/vault"
mkdir -p "$SMOKE_ROOT"
"${UV[@]}" run python - "$SMOKE_CONFIG" "$SMOKE_VAULT" <<'PY'
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
    str(vault / "raw" / "derived" / "markdown"),
]
data["models"]["default_provider"] = "release-smoke"
data["models"]["providers"]["release-smoke"] = {
    "base_url": "https://api.deepseek.com",
    "api_key": "knoarbor-release-smoke-key",
    "model": "deepseek-chat",
}
target.write_text(
    yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
    encoding="utf-8",
)
PY
"${UV[@]}" run knoar --config "$SMOKE_CONFIG" init --vault "$SMOKE_VAULT" >/dev/null
"${UV[@]}" run knoar --config "$SMOKE_CONFIG" doctor >/dev/null
"${UV[@]}" run knoar --config "$SMOKE_CONFIG" status --vault "$SMOKE_VAULT" >/dev/null
"${UV[@]}" build >/dev/null

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Clean clone smoke test left tracked changes:" >&2
  git status --short >&2
  exit 1
fi

echo "Clean clone smoke test passed."
