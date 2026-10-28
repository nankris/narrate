#!/usr/bin/env python3
"""Render or update documentation numbers from shipped cached reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "samples" / "cached_runs"
START = "<!-- numbers:start -->"
END = "<!-- numbers:end -->"

RUNS = (
    ("cooking_roti_0028-0148", "Cooking (roti)"),
    ("nasa_chile_harvest_0000-0150", "NASA harvest"),
    ("tears_of_steel_0015-0155", "Tears of Steel"),
    ("sample_kitchen", "Kitchen (synthetic)"),
    ("failure_continuous_speech", "Continuous speech"),
)


def load_reports(reports_dir: Path = REPORTS_DIR) -> dict[str, dict[str, Any]]:
    """Load every report used by the documentation, failing on missing inputs."""
    reports: dict[str, dict[str, Any]] = {}
    for run, _ in RUNS:
        path = reports_dir / run / "report.json"
        try:
            reports[run] = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise RuntimeError(f"missing cached report: {path}") from exc
    return reports


def _narratable_gaps(report: dict[str, Any]) -> int:
    return sum(bool(gap.get("narratable", True)) for gap in report["gaps"])


def _row(run: str, label: str, report: dict[str, Any]) -> str:
    duration = round(report["duration_s"])
    cues = report["cues_committed"]
    gaps = _narratable_gaps(report)
    refused = ", refused by design" if not gaps else ""
    coverage = report["gap_coverage_percent"]
    verified = report["agent_stats"]["verifications"]
    return (
        f"| {label}, {duration} s | {report['agent_stats']['orchestrator_turns']} | "
        f"{cues} / {gaps}{refused} | {coverage['en']:.0f}% / {coverage['hi']:.0f}% | "
        f"{report['overlaps_with_speech']} | {verified['verified']} / "
        f"{verified['contradicted']} / {verified['unverified']} | "
        f"${report['estimated_cost_usd']:.3f} | ${report['cost_per_minute_usd']:.2f} | "
        f"{report['latency_s']:.0f} s |"
    )


def readme_block(reports: dict[str, dict[str, Any]]) -> str:
    header = (
        "| Clip | Turns | Cues / narratable gaps | Gap coverage EN / HI | Detected overlaps | "
        "Verified / contradicted / unverified | Cost | Cost per min | Model latency |\n"
        "|---|---|---|---|---|---|---|---|---|"
    )
    rows = [_row(run, label, reports[run]) for run, label in RUNS]
    return "\n".join((START, header, *rows, END))


def demo_block(reports: dict[str, dict[str, Any]]) -> str:
    report = reports["tears_of_steel_0015-0155"]
    gaps = _narratable_gaps(report)
    coverage = report["gap_coverage_percent"]
    return "\n".join(
        (
            START,
            f"- ${report['estimated_cost_usd']:.3f} per run, about "
            f"${report['cost_per_minute_usd']:.2f} per minute at Token Factory list prices;",
            f"- {report['agent_stats']['orchestrator_turns']} Ultra turns;",
            f"- {report['cues_committed']} of {gaps} narratable gaps described, "
            f"{coverage['en']:.0f}% EN coverage;",
            f"- {report['overlaps_with_speech']} overlaps with detected speech.",
            END,
        )
    )


def expected_blocks(reports_dir: Path = REPORTS_DIR) -> dict[Path, str]:
    reports = load_reports(reports_dir)
    return {ROOT / "README.md": readme_block(reports), ROOT / "DEMO_SCRIPT.md": demo_block(reports)}


def replace_block(text: str, block: str, path: Path) -> str:
    if text.count(START) != 1 or text.count(END) != 1:
        raise RuntimeError(f"{path} must contain exactly one {START!r} and one {END!r}")
    before, rest = text.split(START, 1)
    _, after = rest.split(END, 1)
    return before + block + after


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="update marked blocks in place")
    mode.add_argument("--check", action="store_true", help="fail if marked blocks are stale")
    args = parser.parse_args()

    stale: list[Path] = []
    for path, block in expected_blocks().items():
        current = path.read_text(encoding="utf-8")
        updated = replace_block(current, block, path)
        if current != updated:
            stale.append(path)
            if args.write:
                path.write_text(updated, encoding="utf-8")
        if not args.write and not args.check:
            print(f"## {path.relative_to(ROOT)}\n{block}")

    if args.check and stale:
        print("stale documentation numbers: " + ", ".join(str(p.relative_to(ROOT)) for p in stale))
        print("run: python scripts/sync_numbers.py --write")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
