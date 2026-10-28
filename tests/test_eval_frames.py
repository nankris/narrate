import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.eval_frames import generate_frame_sheet


FFMPEG = shutil.which("ffmpeg")


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg is not installed")
def test_generates_three_frames_per_cue_and_empty_rubric(tmp_path):
    video = tmp_path / "tiny.mp4"
    subprocess.run(
        [
            FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=size=96x64:rate=10:duration=2",
            "-c:v", "mpeg4", video,
        ],
        check=True,
        capture_output=True,
    )
    report_dir = tmp_path / "tiny_clip"
    report_dir.mkdir()
    report = report_dir / "report.json"
    report.write_text(json.dumps({"cues": [
        {"id": 7, "start": 0.25, "end": 1.75, "en": "A test pattern moves.", "hi": "परीक्षण चित्र चलता है।"}
    ]}), encoding="utf-8")

    sheet, rows = generate_frame_sheet(
        video, report, tmp_path / "eval", tmp_path / "frames"
    )

    assert [round(frame["timestamp"], 2) for frame in rows[0]["frames"]] == [0.55, 1.0, 1.45]
    assert all(Path(frame["path"]).is_file() and Path(frame["path"]).stat().st_size for frame in rows[0]["frames"])
    markdown = sheet.read_text(encoding="utf-8")
    assert sheet.name == "frames_tiny_clip.md"
    assert markdown.count("![Cue 7") == 3
    assert "| Cue | Accuracy | Timing | Redundancy | Rules | Notes |" in markdown
    assert "| 7 |  |  |  |  |  |" in markdown


@pytest.mark.skipif(FFMPEG is None, reason="ffmpeg is not installed")
def test_cli_writes_to_requested_locations(tmp_path):
    video = tmp_path / "tiny.mp4"
    subprocess.run(
        [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
         "testsrc=size=64x48:rate=5:duration=1", "-c:v", "mpeg4", video],
        check=True, capture_output=True,
    )
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"cues": [{"id": 0, "start": 0, "end": 0.9, "en": "Test."}]}))

    completed = subprocess.run(
        [sys.executable, "scripts/eval_frames.py", str(video), str(report),
         "--clip", "cli-test", "--output", str(tmp_path / "out"),
         "--frames-root", str(tmp_path / "frames")],
        check=True, capture_output=True, text=True,
    )

    assert completed.stdout.endswith("with 3 frames\n")
    assert (tmp_path / "out" / "frames_cli-test.md").is_file()
    assert len(list((tmp_path / "frames" / "cli-test").glob("*.jpg"))) == 3
