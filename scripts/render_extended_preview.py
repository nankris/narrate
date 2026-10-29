#!/usr/bin/env python3
"""Render a clearly labelled extended-AD preview with local Piper narration."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from narrate.config import load_config
from narrate.extended import build_extended_timeline, render_extended, write_extended_texts
from narrate.media import ffmpeg, probe
from narrate.tts import PiperBackend

TRIM = ('silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,'
        'areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.1,'
        'areverse,loudnorm=I=-16:TP=-1.5:LRA=11')


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('run_dir', type=Path)
    args = parser.parse_args(argv)
    run = args.run_dir.resolve()
    plan = json.loads((run / 'pause_plan.json').read_text(encoding='utf-8'))
    report = json.loads((run / 'report.json').read_text(encoding='utf-8'))
    needed = {int(x['cue_id']) for x in json.loads((run / 'tts_needed.json').read_text(encoding='utf-8'))}
    config = load_config(Path(__file__).resolve().parents[1] / 'config.yaml')
    engine = PiperBackend(config['tts'])
    preview = run / 'preview'
    work = preview / 'work'
    work.mkdir(parents=True, exist_ok=True)
    narration, durations = {}, {}
    manifest = json.loads((run / 'tts_prerendered' / 'manifest.json').read_text(encoding='utf-8'))
    for pause in plan['pauses']:
        cue_id = int(pause['cue_id'])
        raw = work / f'en-p{cue_id}-raw.wav'
        if cue_id in needed:
            engine.render(pause['cue_text'], 'en', raw)
        else:
            key = f'en-p{cue_id}'
            if manifest.get(key, {}).get('text') != pause['cue_text']:
                raise SystemExit(f'Unchanged clip is stale: {key}')
            ffmpeg('-i', run / 'tts_prerendered' / f'{key}.mp3', raw)
        fitted = work / f'en-p{cue_id}.wav'
        ffmpeg('-i', raw, '-af', TRIM, '-ar', 48000, '-ac', 2, fitted)
        durations[cue_id] = round(probe(fitted)[0], 3)
        narration[str(cue_id)] = fitted
    timeline = build_extended_timeline(
        plan['source_duration'],
        [{**p, 'narration_seconds': durations[int(p['cue_id'])]} for p in plan['pauses']],
        plan.get('speech_intervals', []), plan.get('pad_before', .3), plan.get('pad_after', .4))
    render_extended(Path(report['input_path']), preview / 'preview_extended_en.mp4',
                    preview / 'preview_extended_en.m4a', timeline, narration)
    by_id = {int(p['cue_id']): p for p in timeline.pauses}
    cues = [{'id': p['cue_id'], 'text': p['cue_text'],
             'out_start': by_id[int(p['cue_id'])]['cue_start'],
             'out_end': by_id[int(p['cue_id'])]['cue_end']} for p in plan['pauses']]
    write_extended_texts(preview, cues)
    print(f'PREVIEW {preview / "preview_extended_en.mp4"}')


if __name__ == '__main__':
    main()
