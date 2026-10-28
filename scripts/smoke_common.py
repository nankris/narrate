"""Helpers for explicit real-provider diagnostics. Never executed by offline tests."""
import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from narrate.config import load_config, resolve_provider
from narrate.llm import Client, sanitize  # noqa: F401  # re-exported for smoke scripts


def setup():
    parser = argparse.ArgumentParser(description='Real provider diagnostic (Nebius calls incur charges)')
    parser.add_argument('--provider', required=True, choices=['nebius', 'nvidia-dev'])
    args = parser.parse_args()
    cfg = resolve_provider(load_config(), args.provider)
    if not os.environ.get(cfg['key_env']):
        parser.exit(2, cfg['key_env'] + ' missing; no calls made.\n')
    out = Path('runs/smoke')
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    return cfg, out / f'{args.provider}-{stamp}.json'


def trial(client, stage, data, media=None):
    started = time.monotonic()
    before = len(client.usage)
    result = {'http':'error', 'json_parsed':False}
    try:
        answer = client.call(stage, data, media)
        result.update(http='ok', json_parsed=True, answer=answer)
    except Exception as exc:
        result['error'] = sanitize(exc)
        if len(client.usage) > before:
            result['http'] = 'ok'
    result.update(latency_s=time.monotonic()-started, usage=client.usage[before:])
    return result


def save(path, cfg, results):
    payload = {'provider':cfg['provider'], 'dev_only':cfg['provider']=='nvidia-dev', 'results':results}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    # Print diagnostics, not raw server responses.
    for name, result in results.items():
        print(name, json.dumps({k:v for k,v in result.items() if k != 'answer'}, ensure_ascii=False))
    print(path)
