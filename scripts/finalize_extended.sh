#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 || ! "$1" =~ ^(roti|lecture)$ ]]; then
  echo "usage: scripts/finalize_extended.sh <roti|lecture>" >&2
  exit 2
fi

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
run_dir="$repo_dir/runs/ext/final/$1"
"$repo_dir/.venv/bin/python" "$repo_dir/scripts/update_extended_manifest.py" "$run_dir"
"$repo_dir/.venv/bin/python" "$repo_dir/scripts/render_magnific_extended.py" "$run_dir"
"$repo_dir/.venv/bin/python" "$repo_dir/scripts/check_extended_timing.py" "$run_dir" | tee "$run_dir/timing_check.txt"
