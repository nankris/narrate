#!/usr/bin/env bash
set -uo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
fail=0

check() {
  local label=$1
  shift
  if "$@"; then
    printf 'PASS  %s\n' "$label"
  else
    printf 'FAIL  %s\n' "$label"
    fail=1
  fi
}

cd "$ROOT"
export NO_PROXY='*'
export no_proxy='*'
export GRADIO_ANALYTICS_ENABLED=False

check "required files" test -f README.md -a -f LICENSE -a -f DEVPOST.md -a -f DEMO_SCRIPT.md -a -f issues-found/INDEX.md
check "documentation numbers" .venv/bin/python scripts/check_doc_numbers.py
check "offline test suite" .venv/bin/python -m pytest -q
check "secret scan" /workspace/tig-tools/secret_scan.sh "$ROOT"

if (( fail )); then
  printf '\nPRE-SUBMIT: FAIL\n'
  exit 1
fi
printf '\nPRE-SUBMIT: PASS\n'
