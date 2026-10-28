"""Build dense Nemotron ground truth for one clip."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from narrate.groundtruth import build_groundtruth


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('clip')
    p.add_argument('--out', default='groundtruth/')
    p.add_argument('--provider', choices=['nebius', 'nvidia-dev', 'mock'], default='nebius')
    p.add_argument('--budget-usd', type=float, default=.4)
    p.add_argument('--fps', type=float, default=1.)
    args = p.parse_args(argv)
    result = build_groundtruth(args.clip, args.out, args.provider, args.budget_usd, args.fps)
    print(json.dumps({'clip': result['clip'], 'segments': len(result['segments']),
                      'key_events': len(result['key_events']), 'cost_usd': result['usage']['total_cost_usd']}, indent=2))


if __name__ == '__main__':
    main()
