#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_DIR="${HOME}/Downloads"
LABEL="current"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output-dir)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    --label)
      LABEL="$2"
      shift 2
      ;;
    -h|--help)
      cat <<'USAGE'
Usage: scripts/package-source.sh [--output-dir DIR] [--label LABEL]

Create a clean KnoArbor source package. The archive includes project source,
tests, docs, config examples, package manifests, and lockfiles. It excludes
dependency directories, virtual environments, git metadata, generated desktop
service binaries, renderer build output, release packages, and local caches.

Defaults:
  --output-dir ~/Downloads
  --label current
USAGE
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

mkdir -p "$OUTPUT_DIR"

STAMP="$(date +%Y%m%d-%H%M%S)"
ARCHIVE_NAME="KnoArbor-source-${LABEL}-${STAMP}.zip"
ARCHIVE_PATH="${OUTPUT_DIR%/}/${ARCHIVE_NAME}"
STAGE_DIR="$(mktemp -d)"
STAGE_ROOT="${STAGE_DIR}/KnoArbor-source-${LABEL}"

cleanup() {
  rm -rf "$STAGE_DIR"
}
trap cleanup EXIT

rsync -a "$ROOT_DIR/" "$STAGE_ROOT/" \
  --exclude '.git/' \
  --exclude '.venv/' \
  --exclude '.knoarbor/' \
  --exclude 'node_modules/' \
  --exclude 'renderer/dist/' \
  --exclude 'renderer/tsconfig.tsbuildinfo' \
  --exclude 'desktop/out/' \
  --exclude 'desktop/release/' \
  --exclude 'desktop/.pyinstaller/' \
  --exclude 'desktop/resources/service/' \
  --exclude 'src/knoarbor.egg-info/' \
  --exclude '__pycache__/' \
  --exclude '.pytest_cache/' \
  --exclude '.mypy_cache/' \
  --exclude '.ruff_cache/' \
  --exclude '.DS_Store'

(
  cd "$STAGE_DIR"
  zip -qr "$ARCHIVE_PATH" "KnoArbor-source-${LABEL}"
)

ls -lh "$ARCHIVE_PATH"
printf '%s\n' "$ARCHIVE_PATH"
