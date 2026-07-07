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
"${UV[@]}" run knoar init --vault wiki >/dev/null
DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:-knoarbor-release-smoke-key}" "${UV[@]}" run knoar --config config.example.yaml doctor >/dev/null
"${UV[@]}" run knoar status --vault wiki >/dev/null
"${UV[@]}" build >/dev/null

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Clean clone smoke test left tracked changes:" >&2
  git status --short >&2
  exit 1
fi

echo "Clean clone smoke test passed."
