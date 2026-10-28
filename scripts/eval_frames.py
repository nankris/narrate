#!/usr/bin/env python3
"""Extract three review frames per narration cue and write a Markdown sheet."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any


POSITIONS = (("20%", 0.2), ("50%", 0.5), ("80%", 0.8))
DEFAULT_FRAMES_ROOT = Path("/tmp/narrate_eval")


def safe_clip_name(name: str) -> str:
    """Return a filesystem-safe clip name without allowing path traversal."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    if not cleaned:
        raise ValueError(f"clip name has no safe characters: {name!r}")
    return cleaned


def cue_times(cue: dict[str, Any]) -> list[float]:
    start = float(cue["start"])
    end = float(cue["end"])
    if start < 0 or end <= start:
        raise ValueError(f"invalid cue interval: {start} to {end}")
    return [start + (end - start) * fraction for _, fraction in POSITIONS]


def extract_frame(video: Path, timestamp: float, destination: Path) -> None:
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-ss", f"{timestamp:.6f}", "-i", str(video),
            "-frames:v", "1", "-q:v", "2", str(destination),
        ],
        check=True,
        capture_output=True,
    )


def render_markdown(clip: str, rows: list[dict[str, Any]]) -> str:
    lines = [f"# Frame review: {clip}", ""]
    for row in rows:
        lines.extend([
            f"## Cue {row['id']}: {row['start']:.3f}s–{row['end']:.3f}s",
            "",
            f"**English:** {row['en']}",
            "",
        ])
        if row["hi"]:
            lines.extend([f"**Hindi:** {row['hi']}", ""])
        for frame in row["frames"]:
            lines.extend([
                f"### {frame['position']} ({frame['timestamp']:.3f}s)",
                "",
                f"![Cue {row['id']} at {frame['position']}](<{frame['path']}>)",
                "",
                f"Image: `{frame['path']}`",
                "",
            ])

    lines.extend([
        "## Rubric",
        "",
        "Leave cells empty until a human or vision review is performed.",
        "",
        "| Cue | Accuracy | Timing | Redundancy | Rules | Notes |",
        "| ---: | :---: | :---: | :---: | :---: | --- |",
    ])
    lines.extend(f"| {row['id']} |  |  |  |  |  |" for row in rows)
    return "\n".join(lines) + "\n"


def generate_frame_sheet(
    video: Path,
    report_path: Path,
    output_dir: Path = Path("eval"),
    frames_root: Path = DEFAULT_FRAMES_ROOT,
    clip: str | None = None,
) -> tuple[Path, list[dict[str, Any]]]:
    if not video.is_file():
        raise FileNotFoundError(f"video not found: {video}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    clip_name = safe_clip_name(clip or report_path.parent.name)
    frame_dir = frames_root / clip_name
    frame_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for index, cue in enumerate(report.get("cues", [])):
        times = cue_times(cue)
        cue_id = cue.get("id", index)
        filename_id = safe_clip_name(str(cue_id))
        frames = []
        for (position, _), timestamp in zip(POSITIONS, times):
            destination = (frame_dir / f"cue_{filename_id}_{position[:-1]}.jpg").resolve()
            extract_frame(video, timestamp, destination)
            frames.append({"position": position, "timestamp": timestamp, "path": destination.as_posix()})
        rows.append({
            "id": cue_id,
            "start": float(cue["start"]),
            "end": float(cue["end"]),
            "en": str(cue.get("en", "")),
            "hi": str(cue.get("hi", "")),
            "frames": frames,
        })

    sheet = output_dir / f"frames_{clip_name}.md"
    sheet.write_text(render_markdown(clip_name, rows), encoding="utf-8")
    return sheet, rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path, help="source video to sample")
    parser.add_argument("report", type=Path, help="report.json containing narration cues")
    parser.add_argument("--output", type=Path, default=Path("eval"), help="Markdown output directory")
    parser.add_argument("--frames-root", type=Path, default=DEFAULT_FRAMES_ROOT, help=argparse.SUPPRESS)
    parser.add_argument("--clip", help="override the clip name inferred from the report directory")
    args = parser.parse_args()
    sheet, rows = generate_frame_sheet(
        args.video, args.report, args.output, args.frames_root, args.clip
    )
    print(f"Wrote {sheet} with {len(rows) * len(POSITIONS)} frames")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
