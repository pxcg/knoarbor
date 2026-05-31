#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "== KnoArbor release gates =="
echo "1/3 Local development gate"
scripts/dev-check.sh

echo "2/3 Release readiness"
scripts/release-readiness.py

echo "3/3 Clean clone smoke"
scripts/clean-clone-smoke.sh

echo "All release gates passed."
