#!/usr/bin/env python3
"""Apply reviewed, deterministic text/evidence corrections to final cached runs.

These are human frame-review corrections, not regenerated model output.  The
script intentionally edits only text-side artifacts; cached narration media is
left untouched and must not be represented as containing the corrected script.
"""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from narrate.extended import write_extended_texts


CORRECTIONS = {
    'roti': {
        1: ('A wooden mixing bowl holds flour on a white countertop. A cook in a striped shirt and black apron stands behind it.', [('frame-p1', .5)]),
        2: ('The cook poured water from a glass pitcher into the flour, mixed it by hand, and kneaded the mixture with a gloved hand.', [('e2', 5.99), ('e7', 20.99)]),
        3: ('A second person holds a small white dish and a spoon above the wooden mixing bowl.', [('frame-p3', 25.666)]),
        4: ('The cook kneaded the dough smooth, moved it to a floured silicone mat, divided it with a knife, and rolled the portions into balls.', [('e10', 32.98), ('e14', 47.968)]),
        5: ('The cook pressed a dough ball flat and rolled it into a long, thin oval with a wooden pin. More flour was spread over the dough.', [('e15', 50.96), ('e19', 66.0)]),
        6: ('The cook rolled the long strip into a thin rope, then coiled it into a spiral and pressed the end down.', [('e21', 71.95), ('e25', 83.94)]),
        7: ('The dough coils were placed in a brown bowl and covered with a white plate to rest. The plate was lifted, and one coil was placed on the floured mat and rolled into a disc.', [('e26', 86.94), ('e33', 107.927)]),
        8: ('The cook rolled the dough back and forth into a larger round, flipped it over, and continued rolling it thinner. The clip ends while the dough is still being rolled.', [('e34', 111.0), ('e37', 119.919)]),
    },
    'lecture': {
        1: ('A dark blue slide displays the white title "CONTINUOUS SPEECH - SLIDE 1" in the upper left.', [('e1', 3.0)]),
        2: ('A second dark blue slide now displays the white title "SLIDE 2 - NO ROOM FOR AD" in the upper left.', [('frame-p2', 18.131)]),
        3: ('The second slide remains on screen with the full title "SLIDE 2 - NO ROOM FOR AD".', [('frame-p3', 30.0)]),
    },
}


def correct(name):
    run = ROOT / 'runs' / 'ext' / 'final' / name
    path = run / 'pause_plan.json'
    plan = json.loads(path.read_text(encoding='utf-8'))
    by_id = CORRECTIONS[name]
    cues = []
    for pause in plan['pauses']:
        text, evidence = by_id[int(pause['cue_id'])]
        pause['cue_text'] = text
        pause['evidence'] = [item[0] for item in evidence]
        pause['evidence_times'] = [{'id': evidence_id, 't_end': end} for evidence_id, end in evidence]
        cues.append({'id': pause['cue_id'], 'out_start': pause['cue_out_start'],
                     'out_end': pause['cue_out_end'], 'text': text})
    path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    write_extended_texts(run, cues)

    manifest_path = run / 'tts_prerendered' / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    needed = []
    previous_sha256 = {}
    for pause in plan['pauses']:
        key = f"en-p{pause['cue_id']}"
        entry = manifest.get(key, {})
        if entry.get('text') != pause['cue_text']:
            clip_path = run / 'tts_prerendered' / f'{key}.mp3'
            if clip_path.is_file():
                previous_sha256[key] = hashlib.sha256(clip_path.read_bytes()).hexdigest()
            needed.append({
                'key': key,
                'cue_id': pause['cue_id'],
                'text': pause['cue_text'],
                'voice': 1076,
                'model': 'eleven_turbo_v2_5',
                'stability': 0.45,
                'similarity': 0.85,
                'speaker_boost': True,
                'target_file': f'tts_prerendered/{key}.mp3',
            })
    (run / 'tts_needed.json').write_text(
        json.dumps(needed, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (run / 'tts_previous_sha256.json').write_text(
        json.dumps(previous_sha256, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    for run_name in CORRECTIONS:
        correct(run_name)
