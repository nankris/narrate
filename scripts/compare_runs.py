"""Print two runs' cue tables side by side, aligned by time, plus cost / Ultra-call totals.

usage: python scripts/compare_runs.py OLD/report.json NEW/report.json [--lang en|hi] [--width 48]
"""
import argparse
import json
import textwrap
from pathlib import Path


def overlap(a, b):
    return max(0., min(a['end'], b['end']) - max(a['start'], b['start']))


def align(old, new):
    """[(start, old_cue|None, new_cue|None)]: each old cue pairs with the overlapping new cue it shares most time with."""
    old, new = sorted(old, key=lambda c: c['start']), sorted(new, key=lambda c: c['start'])
    used, rows = set(), []
    for o in old:
        best = max((i for i, n in enumerate(new) if i not in used and overlap(o, n) > 0), key=lambda i: overlap(o, new[i]), default=None)
        if best is not None:
            used.add(best)
        rows.append((o['start'], o, new[best] if best is not None else None))
    rows += [(n['start'], None, n) for i, n in enumerate(new) if i not in used]
    return sorted(rows, key=lambda r: r[0])


def stamp(c):
    return f"{c['start']:6.1f}-{c['end']:5.1f}" if c else ' ' * 12


def summary(r):
    stats = r.get('agent_stats') or {}
    ultra = (r.get('director_stats') or {}).get('ultra_calls', stats.get('orchestrator_turns', '?'))
    return (f"mode {r.get('mode', 'agent')} · cues {len(r.get('cues', []))} · Ultra calls {ultra} · cost ${float(r.get('estimated_cost_usd', 0)):.4f}"
            f" · fallback {bool(r.get('fallback_finalize'))} · silent by choice {len(r.get('gaps_skipped_no_new_info', []))}")


def table(old_report, new_report, lang='en', width=48):
    rows = align(old_report.get('cues', []), new_report.get('cues', []))
    text = lambda c: (c or {}).get(lang) or ('' if c else '—')
    out = [f"{'time':12} | {'OLD':{width}} | {'time':12} | NEW", '-' * (31 + 2 * width)]
    for _, o, n in rows:
        left, right = textwrap.wrap(text(o), width) or [''], textwrap.wrap(text(n), width) or ['']
        for i in range(max(len(left), len(right))):
            out.append(f"{stamp(o) if i == 0 else '':12} | {left[i] if i < len(left) else '':{width}} | {stamp(n) if i == 0 else '':12} | {right[i] if i < len(right) else ''}")
    return '\n'.join(out + ['', 'OLD: ' + summary(old_report), 'NEW: ' + summary(new_report)])


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('old')
    p.add_argument('new')
    p.add_argument('--lang', choices=['en', 'hi'], default='en')
    p.add_argument('--width', type=int, default=48)
    args = p.parse_args(argv)
    load = lambda x: json.loads((Path(x) / 'report.json' if Path(x).is_dir() else Path(x)).read_text(encoding='utf-8'))
    print(table(load(args.old), load(args.new), args.lang, args.width))


if __name__ == '__main__':
    main()
