"""Offline extended-AD re-render from pre-rendered Magnific/ElevenLabs clips."""
import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from narrate.extended import build_extended_timeline, render_extended, write_extended_texts
from narrate.media import ffmpeg, probe

TRIM = ('silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,'
        'areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.1,'
        'areverse,loudnorm=I=-16:TP=-1.5:LRA=11')


def fit(raw, target):
    ffmpeg('-i', raw, '-af', TRIM, '-ar', 48000, '-ac', 2, target)
    seconds, _ = probe(target)
    return {'raw_s': round(probe(raw)[0], 3), 'spoken_s': round(seconds, 3), 'speed': 1.0}


def manifest_entries(raw):
    if isinstance(raw, dict) and isinstance(raw.get('clips'), list):
        return {str(x.get('id', x.get('key'))): x for x in raw['clips'] if isinstance(x, dict)}
    return raw if isinstance(raw, dict) else {}


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('run_dir')
    p.add_argument('--clips', default='tts_prerendered')
    args = p.parse_args(argv)
    run = Path(args.run_dir).resolve()
    clips = run / args.clips
    plan = json.loads((run / 'pause_plan.json').read_text())
    report = json.loads((run / 'report.json').read_text())
    source = Path(report['input_path'])
    manifest = manifest_entries(json.loads((clips / 'manifest.json').read_text()))
    pauses = plan.get('pauses', [])
    stale = []
    for pause in pauses:
        key = f"en-p{pause['cue_id']}"
        entry = manifest.get(key, manifest.get(str(pause['cue_id']), {}))
        if not isinstance(entry, dict) or entry.get('text') != pause['cue_text']:
            stale.append(key)
    if stale:
        raise SystemExit(f'Pre-rendered clips do not match pause_plan.json cue text: {stale}')

    results, narration = {}, {}
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        for pause in pauses:
            cue_id = pause['cue_id']
            raw = clips / f'en-p{cue_id}.mp3'
            if not raw.is_file():
                raise SystemExit(f'Missing pre-rendered clip: {raw}')
            wav = work / f'en-p{cue_id}.wav'
            results[f'en-p{cue_id}'] = fit(raw, wav)
            narration[str(cue_id)] = wav
        timeline = build_extended_timeline(plan['source_duration'],
            [{**p, 'narration_seconds': results[f"en-p{p['cue_id']}"]['spoken_s']} for p in pauses],
            plan.get('speech_intervals', []), plan.get('pad_before', .3), plan.get('pad_after', .4))
        render_extended(source, run / 'extended_en.mp4', run / 'extended_en.m4a', timeline, narration)
        by_id = {str(p['cue_id']): p for p in timeline.pauses}
        cues = [{'id': p['cue_id'], 'text': p['cue_text'],
                 'out_start': by_id[str(p['cue_id'])]['cue_start'],
                 'out_end': by_id[str(p['cue_id'])]['cue_end']} for p in pauses]
        write_extended_texts(run, cues)
    output = {'source_duration': plan['source_duration'], 'output_duration': timeline.total_duration,
              'total_added_seconds': round(timeline.total_duration - plan['source_duration'], 3), 'clips': results}
    (run / 'fit.json').write_text(json.dumps(output, indent=2))
    (clips / 'fit.json').write_text(json.dumps(output, indent=2))
    print(json.dumps(output, indent=2))


if __name__ == '__main__':
    main()
