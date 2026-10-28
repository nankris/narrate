#!/usr/bin/env python3
"""Compute deterministic, offline quality metrics for cached Narrate reports."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


REPEAT_THRESHOLD = 0.5
WORD_RE = re.compile(r"[^\W_]+(?:['’][^\W_]+)?", re.UNICODE)
STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "in", "into", "is", "it", "of", "on", "or", "that", "the", "their",
    "this", "to", "with",
}
BANNED_PATTERNS = (
    ("we see", re.compile(r"\bwe\s+see\b", re.IGNORECASE)),
    ("camera", re.compile(r"\bcamera\b", re.IGNORECASE)),
    ("literal TITLE", re.compile(r"\btitle\b", re.IGNORECASE)),
    ("leading Screen", re.compile(r"^\s*Screen\b", re.IGNORECASE)),
    ("video shows", re.compile(r"\bvideo\s+shows\b", re.IGNORECASE)),
)


def words(text: str) -> list[str]:
    """Return stable Unicode word tokens."""
    return WORD_RE.findall(text)


def content_words(text: str) -> set[str]:
    return {word.casefold() for word in words(text) if word.casefold() not in STOP_WORDS}


def word_count(text: str) -> int:
    """Match the pipeline's whitespace-separated budget convention."""
    return len(text.split())


def jaccard(left: str, right: str) -> float:
    a, b = content_words(left), content_words(right)
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def evaluate_report(report: dict[str, Any], clip: str) -> dict[str, Any]:
    cues = report.get("cues", [])
    repeats: list[dict[str, Any]] = []
    for previous, current in zip(cues, cues[1:]):
        score = jaccard(str(previous.get("en", "")), str(current.get("en", "")))
        if score >= REPEAT_THRESHOLD:
            repeats.append({
                "previous_cue_id": previous.get("id"),
                "cue_id": current.get("id"),
                "jaccard": round(score, 3),
            })

    banned: list[dict[str, Any]] = []
    budgets: list[dict[str, Any]] = []
    for cue in cues:
        for lang in ("en", "hi"):
            text = str(cue.get(lang, ""))
            for phrase, pattern in BANNED_PATTERNS:
                if pattern.search(text):
                    banned.append({"cue_id": cue.get("id"), "language": lang, "phrase": phrase})
            count = word_count(text)
            budget = cue.get(f"word_budget_{lang}")
            row = {
                "cue_id": cue.get("id"),
                "language": lang,
                "gap_seconds": round(float(cue.get("duration", 0)), 3),
                "words": count,
                "budget": budget,
                "within_budget": isinstance(budget, int) and count <= budget,
            }
            budgets.append(row)

    tracks = report.get("tracks", {})
    en_count = len(tracks.get("en", []))
    hi_count = len(tracks.get("hi", []))
    over_budget = [row for row in budgets if not row["within_budget"]]
    parity = {"en": en_count, "hi": hi_count, "equal": en_count == hi_count}
    return {
        "clip": clip,
        "cue_count": len(cues),
        "thresholds": {"repeat_jaccard": REPEAT_THRESHOLD},
        "repeat_flags": repeats,
        "banned_phrase_flags": banned,
        "word_budgets": budgets,
        "over_budget_flags": over_budget,
        "language_count_parity": parity,
        "passed": not repeats and not banned and not over_budget and parity["equal"],
    }


def render_markdown(result: dict[str, Any]) -> str:
    parity = result["language_count_parity"]
    lines = [
        f"# Offline quality metrics: {result['clip']}", "",
        f"Overall: **{'PASS' if result['passed'] else 'FLAGGED'}**", "",
        "| Metric | Result |", "| --- | --- |",
        f"| Cues | {result['cue_count']} |",
        f"| Adjacent repeats (Jaccard >= {REPEAT_THRESHOLD}) | {len(result['repeat_flags'])} |",
        f"| Banned phrases | {len(result['banned_phrase_flags'])} |",
        f"| Over word budget | {len(result['over_budget_flags'])} |",
        f"| EN / HI track count | {parity['en']} / {parity['hi']} ({'equal' if parity['equal'] else 'mismatch'}) |",
        "", "## Flags", "",
    ]
    flags: list[str] = []
    flags.extend(
        f"- Repeat: cues {row['previous_cue_id']} -> {row['cue_id']} (Jaccard {row['jaccard']:.3f})"
        for row in result["repeat_flags"]
    )
    flags.extend(
        f"- Banned phrase: cue {row['cue_id']} {row['language'].upper()} ({row['phrase']})"
        for row in result["banned_phrase_flags"]
    )
    flags.extend(
        f"- Word budget: cue {row['cue_id']} {row['language'].upper()} has {row['words']} / {row['budget']} words in {row['gap_seconds']:.3f}s"
        for row in result["over_budget_flags"]
    )
    if not parity["equal"]:
        flags.append(f"- Language count mismatch: EN {parity['en']} / HI {parity['hi']}")
    lines.extend(flags or ["- None."])
    lines.extend(["", "## Cue word budgets", "", "| Cue | Lang | Gap (s) | Words | Budget | Within |", "| ---: | :---: | ---: | ---: | ---: | :---: |"])
    lines.extend(
        f"| {row['cue_id']} | {row['language'].upper()} | {row['gap_seconds']:.3f} | {row['words']} | {row['budget']} | {'yes' if row['within_budget'] else 'no'} |"
        for row in result["word_budgets"]
    )
    return "\n".join(lines) + "\n"


def evaluate_directory(input_dir: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for report_path in sorted(input_dir.glob("*/report.json")):
        clip = report_path.parent.name
        result = evaluate_report(json.loads(report_path.read_text(encoding="utf-8")), clip)
        (output_dir / f"metrics_{clip}.md").write_text(render_markdown(result), encoding="utf-8")
        results.append(result)
    summary = {
        "source": input_dir.as_posix(),
        "thresholds": {"repeat_jaccard": REPEAT_THRESHOLD},
        "clip_count": len(results),
        "passed_clip_count": sum(result["passed"] for result in results),
        "clips": results,
    }
    (output_dir / "metrics_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("samples/cached_runs"))
    parser.add_argument("--output", type=Path, default=Path("eval"))
    args = parser.parse_args()
    summary = evaluate_directory(args.input, args.output)
    print(f"Evaluated {summary['clip_count']} clips; {summary['passed_clip_count']} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
