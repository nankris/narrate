#!/usr/bin/env python3
"""Serve shipped cached samples on localhost; never runs inference."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"
ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "samples" / "cached_runs"


def discover() -> dict[str, Path]:
    return {
        path.name: path
        for path in sorted(CACHE.iterdir())
        if (path / "report.json").is_file() and (path / "meta.json").is_file()
    }


MODES = {
    "extended": ("Extended: video pauses while it is described", "extended_en.mp4", "ad_extended_en.vtt", "extended_report.json", "extended_trace.json"),
    "ingap": ("In-gap: described only in natural silences", "narrated_en.mp4", "ad_en.vtt", "report.json", "trace.json"),
}


def sample(name: str, mode: str):
    """(original video, narrated video, WebVTT cues, evidence files) for one cached run and mode."""
    folder = discover()[name]
    meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
    original = ROOT / meta["input_path"]
    _, video, cues, report, trace = MODES[mode]
    return (
        str(original),
        str(folder / video),
        (folder / cues).read_text(encoding="utf-8"),
        [str(folder / report), str(folder / trace)],
    )


def build_app():
    import gradio as gr

    runs = discover()
    first = "cooking_roti_0028-0148" if "cooking_roti_0028-0148" in runs else next(iter(runs))
    initial = sample(first, "extended")
    with gr.Blocks(title="Narrate · cached samples", analytics_enabled=False) as demo:
        gr.Markdown("# Narrate · cached samples\nLocal playback only. No API key, inference, upload, or network call. English narration.")
        with gr.Row():
            run = gr.Dropdown(list(runs), value=first, label="Cached run")
            mode = gr.Radio([(label, key) for key, (label, *_) in MODES.items()], value="extended", label="Description mode")
        with gr.Row():
            original = gr.Video(initial[0], label="Original", interactive=False)
            narrated = gr.Video(initial[1], label="With audio description", interactive=False)
        cues = gr.Textbox(initial[2], label="WebVTT cues", lines=10, interactive=False)
        files = gr.Files(initial[3], label="Evidence", interactive=False)
        for control in (run, mode):
            control.change(sample, [run, mode], [original, narrated, cues, files])
    return demo


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7860)
    args = parser.parse_args()
    build_app().launch(server_name=args.host, server_port=args.port, share=False, show_error=False)


if __name__ == "__main__":
    main()
