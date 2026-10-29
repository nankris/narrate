#!/usr/bin/env python3
"""Apply human frame-review corrections to one cached run's text artifacts."""
from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from narrate.config import load_config
from narrate.extended import write_extended_texts

def apply(run, corrections, config=None):
    run, corrections = Path(run), Path(corrections)
    data = json.loads(corrections.read_text(encoding='utf-8'))
    rows = data.get('corrections') or data.get('runs', {}).get(run.name)
    if not data.get('human_reviewed') or not isinstance(rows, dict):
        raise ValueError('corrections must be human-reviewed data for this run')
    voice = load_config(config)['tts']['reviewed_voice']
    path = run / 'pause_plan.json'
    plan = json.loads(path.read_text(encoding='utf-8'))
    cues = []
    for pause in plan['pauses']:
        row, cue_id = rows[str(pause['cue_id'])], pause['cue_id']
        pause['cue_text'] = row['text']
        pause['evidence'] = [item[0] for item in row['evidence']]
        pause['evidence_times'] = [{'id': item[0], 't_end': item[1]} for item in row['evidence']]
        cues.append({'id': cue_id, 'out_start': pause['cue_out_start'], 'out_end': pause['cue_out_end'], 'text': row['text']})
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    write_extended_texts(run, cues)
    manifest = json.loads((run / 'tts_prerendered/manifest.json').read_text(encoding='utf-8'))
    needed, previous = [], {}
    for pause in plan['pauses']:
        key = f"en-p{pause['cue_id']}"
        if manifest.get(key, {}).get('text') != pause['cue_text']:
            clip = run / 'tts_prerendered' / f'{key}.mp3'
            if clip.is_file(): previous[key] = hashlib.sha256(clip.read_bytes()).hexdigest()
            needed.append({'key': key, 'cue_id': pause['cue_id'], 'text': pause['cue_text'], **voice,
                           'target_file': f'tts_prerendered/{key}.mp3'})
    (run / 'tts_needed.json').write_text(json.dumps(needed, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (run / 'tts_previous_sha256.json').write_text(json.dumps(previous, indent=2) + '\n', encoding='utf-8')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', required=True); parser.add_argument('--corrections', required=True); parser.add_argument('--config')
    args = parser.parse_args(); apply(args.run, args.corrections, args.config)
