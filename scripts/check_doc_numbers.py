#!/usr/bin/env python3
"""Check submission-facing extended-mode numbers against cached reports."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = (ROOT / "README.md", ROOT / "DEVPOST.md", ROOT / "DEMO_SCRIPT.md")
RUNS = {"roti": ("119.9", "229.1", "8"), "lecture": ("30.0", "64.5", "3")}


def main() -> int:
    combined = "\n".join(path.read_text(encoding="utf-8") for path in DOCS)
    for name, expected in RUNS.items():
        report = json.loads((ROOT / "runs" / "ext" / "final" / name / "report.json").read_text())
        actual = (f"{report['duration_s']:.1f}", f"{report['output_duration_s']:.1f}", str(len(report["pauses"])))
        if actual != expected:
            print(f"FAIL {name}: checker constants {expected}, report {actual}")
            return 1
        missing = [value for value in expected if value not in combined]
        if missing:
            print(f"FAIL {name}: documentation missing {missing}")
            return 1
    print("PASS documentation numbers match extended cached reports")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
