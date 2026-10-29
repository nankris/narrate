"""One-command readiness check for a real provider (default: Nebius Token Factory).

    NEBIUS_API_KEY=... python scripts/smoke_provider.py            # nebius
    python scripts/smoke_provider.py --provider nvidia-dev          # dev only

Runs the real code paths (narrate.llm.Client, agent Orchestrator) with tiny inputs:
  1. model list: every configured model id is served by the endpoint
  2. fit/fit_alt: JSON drafting call (Nano / Lightning)
  3. orchestrate: tool-calling turn (Ultra) - must return a tool call
  4. perceive: Super VL with a 4 s synthetic MP4 as video_url, then a frame-grid fallback
Spend cap $0.05 (expected ~$0.01). Prints PASS/FAIL per check and never prints the key.
Exit code 0 only if all required checks pass.
"""
import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from narrate.config import load_config, resolve_provider
from narrate.llm import Client, SpendGuard, sanitize


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--provider', default='nebius', choices=['nebius', 'nvidia-dev'])
    p.add_argument('--skip-video', action='store_true', help='skip the Super VL checks')
    args = p.parse_args()
    cfg = resolve_provider(load_config(), args.provider)
    key = os.environ.get(cfg['key_env'])
    if not key:
        p.exit(2, f"{cfg['key_env']} is not set; no calls made. export {cfg['key_env']}=<your key> and re-run.\n")
    print(f"provider={args.provider} base_url={cfg['base_url']}")
    for stage, m in cfg['models'].items():
        print(f"  {stage:16s} {m['id']}")
    results, required_fail = {}, False

    def record(name, ok, required=True, **info):
        nonlocal required_fail
        results[name] = {'ok': ok, **info}
        required_fail |= (required and not ok)
        print(f"{'PASS' if ok else 'FAIL'} {name} " + json.dumps(info, ensure_ascii=False)[:300])

    # 1. model list
    try:
        from openai import OpenAI
        served = {m.id for m in OpenAI(api_key=key, base_url=cfg['base_url'], timeout=30, max_retries=0).models.list()}
        missing = sorted({m['id'] for m in cfg['models'].values()} - served)
        hints = {mid: sorted(s for s in served if mid.split('/')[-1].lower()[:12] in s.lower())[:3] for mid in missing}
        record('models_listed', not missing, missing=missing, similar_served=hints, served_nemotron=len([s for s in served if 'nemotron' in s.lower()]))
    except Exception as exc:
        record('models_listed', False, error=sanitize(exc).replace(key, '[KEY]'))

    client = Client(cfg, guard=SpendGuard(0.05))
    # 2. drafting JSON
    for stage in ('fit', 'fit_alt'):
        t = time.monotonic()
        try:
            out = client.call(stage, {'instruction': 'Draft one English audio-description cue of at most 8 words. Return {"text": string}.',
                                      'events': [{'what': 'Title card reads "STEP 1 - chop onions"'}], 'max_words': 8})
            text = str(out.get('text', ''))
            record(stage, bool(text) and len(text.split()) <= 12, required=(stage == 'fit'), text=text, latency_s=round(time.monotonic()-t, 2))
        except Exception as exc:
            record(stage, False, required=(stage == 'fit'), error=sanitize(exc).replace(key, '[KEY]'))
    # 3. orchestrator tool call
    try:
        from narrate.agent.models import Orchestrator
        t = time.monotonic()
        msg = Orchestrator(client).next([
            {'role': 'system', 'content': 'You are an audio-description agent. Use tools.'},
            {'role': 'user', 'content': 'New 30 s video loaded. Start by finding the speech-free gaps.'}], None)
        calls = [c['function']['name'] for c in msg.get('tool_calls', [])]
        record('orchestrate_tool_call', bool(calls), tool_calls=calls, latency_s=round(time.monotonic()-t, 2))
    except Exception as exc:
        record('orchestrate_tool_call', False, error=sanitize(exc).replace(key, '[KEY]'))
    # 4. Super VL
    if not args.skip_video:
        from narrate.media import ffmpeg, drawtext_font
        from narrate.perception import data_url, frame_grids
        with tempfile.TemporaryDirectory() as td:
            clip = Path(td) / 'tiny.mp4'
            font = drawtext_font()
            vf = (f"drawtext=text='RED SQUARE'{font}:x=30:y=30:fontsize=40:fontcolor=white:enable='lt(t,2)',"
                  f"drawtext=text='BLUE CIRCLE'{font}:x=30:y=30:fontsize=40:fontcolor=white:enable='gte(t,2)'")
            ffmpeg('-f', 'lavfi', '-i', 'color=teal:s=640x360:r=4:d=4', '-vf', vf, '-an', '-c:v', 'libx264', clip)
            for name, media, required in (
                    ('perceive_video_url', [{'type': 'video_url', 'video_url': {'url': data_url(clip.read_bytes(), 'video/mp4')}}], False),
                    ('perceive_frames', frame_grids(clip, [0, 2.5]), True)):
                t = time.monotonic()
                try:
                    out = client.call('perceive', {'duration': 4, 'instruction': 'Transcribe all on-screen text verbatim. Return {"events":[{"t_start","t_end","what","on_screen_text"}]}.'}, media)
                    blob = json.dumps(out).upper()
                    seen = [s for s in ('RED SQUARE', 'BLUE CIRCLE') if s in blob]
                    record(name, bool(seen), required=required, text_read=seen, latency_s=round(time.monotonic()-t, 2))
                except Exception as exc:
                    record(name, False, required=required, error=sanitize(exc).replace(key, '[KEY]'))
    cost = sum(u['cost_usd'] for u in client.usage)
    cached = sum(u.get('cached_tokens') or 0 for u in client.usage)
    print(f"total_cost_usd={cost:.4f} calls={len(client.usage)} cached_tokens={cached}")
    out = Path('runs/smoke'); out.mkdir(parents=True, exist_ok=True)
    path = out / f"provider-{args.provider}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    path.write_text(json.dumps({'provider': args.provider, 'base_url': cfg['base_url'], 'results': results, 'usage': client.usage, 'total_cost_usd': cost}, indent=2, ensure_ascii=False).replace(key, '[KEY]'))
    print(('READY' if not required_fail else 'NOT READY') + f" -> {path}")
    if not results.get('perceive_video_url', {}).get('ok', True):
        print('note: video_url not accepted; set perception_strategy: frames in config.yaml (frames path passed)' if results.get('perceive_frames', {}).get('ok') else '')
    sys.exit(1 if required_fail else 0)


if __name__ == '__main__':
    main()
