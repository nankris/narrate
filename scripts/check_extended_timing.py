#!/usr/bin/env python3
"""Audit one or more cached extended-AD runs without network access."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from narrate.extended_audit import audit_cached_run


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('runs', nargs='+', type=Path)
    parser.add_argument('--tolerance', type=float, default=.05)
    args = parser.parse_args()
    failed = False
    for run in args.runs:
        problems = audit_cached_run(run, tolerance=args.tolerance)
        if problems:
            failed = True
            print(f'FAIL {run}: {len(problems)} violation(s)')
            for problem in problems:
                print(f'  cue {problem.get("cue_id")}: {problem["reason"]}'
                      f' ({problem.get("evidence_id", "no evidence")})')
        else:
            print(f'PASS {run}: every cue follows all cited evidence')
    raise SystemExit(1 if failed else 0)


if __name__ == '__main__':
    main()
