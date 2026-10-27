"""Explicit opt-in paid provider smoke test; never imported by tests."""
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from narrate.config import load_config
from narrate.llm import Client
from narrate.media import ffmpeg
from narrate.perception import data_url, frame_grids


def main():
    if not os.environ.get('NEBIUS_API_KEY'):
        print('No key; smoke test skipped.')
        return
    if '--allow-paid' not in sys.argv:
        print('Real calls incur charges. Explicitly pass --allow-paid to run.')
        return
    out = Path('runs/smoke')
    out.mkdir(parents=True, exist_ok=True)
    clip = out / 'tiny.mp4'
    ffmpeg('-f', 'lavfi', '-i', 'color=blue:s=160x90:r=2:d=3', '-an', '-c:v', 'libx264', '-threads', 2, clip)
    client = Client(load_config())
    for strategy, media in [('video', [{'type': 'video_url', 'video_url': {'url': data_url(clip.read_bytes(), 'video/mp4')}}]), ('frames', frame_grids(clip, [0, 1, 2]))]:
        try:
            result = client.call('perceive', {'instruction': 'Describe visible content. Return JSON object.', 'duration': 3}, media)
        except Exception as exc:
            result = {'error_type': type(exc).__name__}
        (out / f'{strategy}.json').write_text(json.dumps(result, indent=2))
        print(strategy, result)


if __name__ == '__main__':
    main()
