#!/usr/bin/env python3
"""Update a prerecorded manifest after requested replacement MP3s are supplied."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('run_dir', type=Path)
    args = parser.parse_args()
    run = args.run_dir.resolve()
    needed = json.loads((run / 'tts_needed.json').read_text(encoding='utf-8'))
    previous = json.loads((run / 'tts_previous_sha256.json').read_text(encoding='utf-8'))
    path = run / 'tts_prerendered' / 'manifest.json'
    manifest = json.loads(path.read_text(encoding='utf-8'))
    missing = [x['target_file'] for x in needed if not (run / x['target_file']).is_file()]
    if missing:
        raise SystemExit('Missing replacement MP3s: ' + ', '.join(missing))
    stale = []
    for item in needed:
        digest = hashlib.sha256((run / item['target_file']).read_bytes()).hexdigest()
        if digest == previous.get(item['key']):
            stale.append(item['target_file'])
    if stale:
        raise SystemExit('Replacement MP3s still contain the previous files: ' + ', '.join(stale))
    for item in needed:
        mp3 = run / item['target_file']
        manifest[item['key']] = {
            'voice_id': item['voice'], 'model': item['model'],
            'stability': item['stability'], 'similarity_boost': item['similarity'],
            'speaker_boost': item['speaker_boost'], 'text': item['text'],
            'sha256': hashlib.sha256(mp3.read_bytes()).hexdigest(),
        }
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Updated {path} ({len(needed)} replacement clips)')


if __name__ == '__main__':
    main()
