"""Re-voice a cached demo run with pre-rendered (e.g. Magnific / ElevenLabs) TTS clips.

The shipped cached demos (samples/cached_runs/*/narrated_{en,hi}.mp4) were voiced with
Magnific TTS (ElevenLabs eleven_turbo_v2_5). The clips are committed under
samples/cached_runs/<run>/tts_prerendered/{en,hi}-<cue id>.mp3 with a manifest.json
recording the Magnific creation id, voice and credits for each clip.

This script is OFFLINE: it never calls Magnific. It only fits each clip into its cue
(silence trim + loudness normalise to -16 LUFS + atempo <= agent.max_atempo, then hard trim as a last resort) and re-mixes
with the same ducking mix as the pipeline (narrate.tts.mix). Cue text and timings in
report.json are read, never modified. The live pipeline default stays espeak/piper.

To regenerate clips: call Magnific `audio_tts` (model eleven_turbo_v2_5, voiceId from
manifest.json) once per cue with the exact report.json text, download the mp3 into
tts_prerendered/ as <lang>-<cue id>.mp3, then run:
    python scripts/render_magnific_tts.py samples/cached_runs/<run>
"""
import argparse
import json
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from narrate.config import load_config
from narrate.media import ffmpeg, probe
from narrate.tts import mix
ROOT = Path(__file__).resolve().parents[1]
TRIM = 'silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.1,areverse,loudnorm=I=-16:TP=-1.5:LRA=11'


def fit(raw, available, max_speed, target):
    trimmed = target.with_suffix('.trim.wav')
    ffmpeg('-i', raw, '-af', TRIM, '-ar', 24000, '-ac', 1, trimmed)
    seconds, _ = probe(trimmed)
    speed = min(max_speed, max(1., seconds / available))
    spoken = seconds / speed
    ffmpeg('-i', trimmed, '-af', f'atempo={speed:.4f},atrim=duration={available},afade=t=out:st={max(0, min(spoken, available)-.03)}:d=0.03', '-ar', 24000, '-ac', 1, target)
    return dict(raw_s=round(seconds, 3), speed=round(speed, 4), spoken_s=round(min(spoken, available), 3), available_s=round(available, 3), overflow_s=round(max(0, spoken-available), 3))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('run', help='samples/cached_runs/<name>')
    p.add_argument('--langs', nargs='+', default=['en', 'hi'])
    args = p.parse_args()
    run = Path(args.run).resolve()
    cfg = load_config()
    report = json.loads((run/'report.json').read_text())
    meta = json.loads((run/'meta.json').read_text())
    source = ROOT/meta['input_path']
    duration, has_audio = probe(source)
    clips = run/'tts_prerendered'
    manifest = json.loads((clips/'manifest.json').read_text()) if (clips/'manifest.json').is_file() else {}
    stale = [k for k, v in manifest.items() for c in report['cues'] if f"{k.split('-')[0]}-{c['id']}" == k and c.get(k.split('-')[0]) != v['text']]
    if stale:
        raise SystemExit(f'Pre-rendered clips do not match report.json cue text (re-render them): {stale}')
    results = {}
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        for lang in args.langs:
            selected, wavs = [], []
            for c in sorted(report['cues'], key=lambda c: c['start']):
                raw = clips/f"{lang}-{c['id']}.mp3"
                if not c.get(lang) or not raw.is_file():
                    continue
                wav = work/f"{lang}-{c['id']}.wav"
                info = fit(raw, c['end']-c['start'], cfg['agent']['max_atempo'], wav)
                results[f"{lang}-{c['id']}"] = info
                # Duck only while the voice is audible, as the agent renderer does.
                selected.append({**c, 'end': c['start']+info['spoken_s']})
                wavs.append(wav)
            full = work/f'narrated_{lang}_full.mp4'
            mix(source, full, duration, has_audio, selected, wavs, cfg['ducking_level'])
            ffmpeg('-i', full, '-vf', 'scale=640:-2', '-c:v', 'libx264', '-crf', '30', '-threads', '1', '-c:a', 'aac', '-b:a', '64k', run/f'narrated_{lang}.mp4')
    (clips/'fit.json').write_text(json.dumps(results, indent=1))
    over = {k: v for k, v in results.items() if v['overflow_s'] > 0}
    print(json.dumps(dict(run=run.name, clips=len(results), overflow=over), indent=1))


if __name__ == '__main__':
    main()
