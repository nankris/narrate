"""Regression checks for the read-only cached demo artifacts."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
CACHED_RUNS = ROOT / "samples" / "cached_runs"
LANGUAGES = ("en",)
TIMING = re.compile(
    r"^(?P<start>\d{2,}:\d{2}:\d{2}\.\d{3}) --> "
    r"(?P<end>\d{2,}:\d{2}:\d{2}\.\d{3})$"
)


def _reports():
    reports = sorted(CACHED_RUNS.glob("*/report.json"))
    assert reports, "no cached reports were shipped"
    return reports


def _seconds(timestamp):
    hours, minutes, seconds = timestamp.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def _parse_vtt(path):
    """Parse the deliberately small WebVTT subset emitted by Narrate."""
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines and lines[0] == "WEBVTT", f"invalid WebVTT header: {path}"

    body = "\n".join(lines[1:]).strip()
    if not body:
        return []

    cues = []
    for block in re.split(r"\n\s*\n", body):
        cue_lines = block.splitlines()
        assert len(cue_lines) >= 3, f"incomplete cue in {path}: {block!r}"
        assert cue_lines[0].isdigit(), f"invalid cue identifier in {path}"
        match = TIMING.fullmatch(cue_lines[1])
        assert match, f"invalid cue timing in {path}: {cue_lines[1]!r}"
        assert any(line.strip() for line in cue_lines[2:]), f"empty cue in {path}"

        start = _seconds(match.group("start"))
        end = _seconds(match.group("end"))
        assert start < end, f"non-positive cue duration in {path}"
        cues.append((start, end))
    return cues


@pytest.mark.parametrize("report_path", _reports(), ids=lambda path: path.parent.name)
def test_cached_run_report_and_tracks(report_path):
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["provider"] == "nebius"

    usage = report["usage"]
    assert usage or not report["cues"], "cached run must record model usage (a refused clip makes no model calls)"
    for call in usage:
        host = call["base_url_host"]
        assert host == "tokenfactory.nebius.com" or host.endswith(
            ".tokenfactory.nebius.com"
        )

    duration = report["duration_s"]
    tracks = report["tracks"]
    for language in LANGUAGES:
        for cue in tracks[language]:
            assert 0 <= cue["start"] < cue["end"] <= duration


@pytest.mark.parametrize("report_path", _reports(), ids=lambda path: path.parent.name)
def test_cached_run_vtt_cues_are_inside_clip(report_path):
    report = json.loads(report_path.read_text(encoding="utf-8"))
    duration = report["duration_s"]
    parsed = {
        language: _parse_vtt(report_path.parent / f"ad_{language}.vtt")
        for language in LANGUAGES
    }
    for cues in parsed.values():
        assert all(0 <= start < end <= duration for start, end in cues)


@pytest.mark.skipif(shutil.which("ffprobe") is None, reason="ffprobe is not installed")
@pytest.mark.parametrize("report_path", _reports(), ids=lambda path: path.parent.name)
def test_cached_run_mp4_durations_match_clip(report_path):
    expected = json.loads(report_path.read_text(encoding="utf-8"))["duration_s"]
    for language in LANGUAGES:
        video = report_path.parent / f"narrated_{language}.mp4"
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(video),
            ],
            check=True,
            text=True,
            capture_output=True,
        )
        assert float(result.stdout.strip()) == pytest.approx(expected, abs=0.2)
