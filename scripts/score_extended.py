"""Score an extended-AD run against independent Nemotron ground truth."""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from narrate import director_prompts as P
from narrate.config import load_config, resolve_provider
from narrate.extended import pause_overlaps_speech
from narrate.llm import Client, SpendGuard


def _choice(value, allowed, default):
    value = str(value or '').lower().strip()
    return value if value in allowed else default


def normalise_judge(raw, event_ids=(), cue_ids=(), confusing_ids=()):
    raw = raw if isinstance(raw, dict) else {}
    def rows(key):
        return raw.get(key, []) if isinstance(raw.get(key), list) else []
    events = {}
    for row in rows('key_events'):
        if isinstance(row, dict):
            key = str(row.get('id', ''))
            if key in set(map(str, event_ids)):
                events[key] = {'id': key, 'coverage': _choice(row.get('coverage'), {'yes', 'partial', 'no'}, 'no'),
                               'reason': str(row.get('reason') or '')[:400]}
    for key in map(str, event_ids):
        events.setdefault(key, {'id': key, 'coverage': 'no', 'reason': 'judge omitted target'})
    claims = {}
    for row in rows('cue_claims'):
        if not isinstance(row, dict):
            continue
        try: cue_id = int(row.get('cue_id', row.get('id')))
        except (TypeError, ValueError): continue
        if cue_id in set(map(int, cue_ids)):
            unsupported = row.get('unsupported_claims', [])
            claims[cue_id] = {'cue_id': cue_id, 'unsupported_claims':
                              [str(x)[:400] for x in unsupported if isinstance(x, str)] if isinstance(unsupported, list) else []}
    for cue_id in map(int, cue_ids):
        claims.setdefault(cue_id, {'cue_id': cue_id, 'unsupported_claims': []})
    confusing = {}
    for row in rows('confusing_parts'):
        if isinstance(row, dict):
            key = str(row.get('id', ''))
            if key in set(map(str, confusing_ids)):
                confusing[key] = {'id': key, 'explained': _choice(row.get('explained'), {'yes', 'no'}, 'no'),
                                  'reason': str(row.get('reason') or '')[:400]}
    for key in map(str, confusing_ids):
        confusing.setdefault(key, {'id': key, 'explained': 'no', 'reason': 'judge omitted target'})
    fluency = {}
    for row in rows('fluency'):
        if not isinstance(row, dict): continue
        try: cue_id = int(row.get('cue_id', row.get('id'))); score = int(round(float(row.get('score'))))
        except (TypeError, ValueError): continue
        if cue_id in set(map(int, cue_ids)):
            fluency[cue_id] = {'cue_id': cue_id, 'score': max(1, min(5, score)),
                               'reason': str(row.get('reason') or '')[:400]}
    for cue_id in map(int, cue_ids):
        fluency.setdefault(cue_id, {'cue_id': cue_id, 'score': 1, 'reason': 'judge omitted cue'})
    return {'key_events': list(events.values()), 'cue_claims': list(claims.values()),
            'confusing_parts': list(confusing.values()), 'fluency': list(fluency.values())}


def aggregate_score(deterministic, judge):
    events = judge['key_events']
    points = sum({'yes': 1., 'partial': .5, 'no': 0.}[row['coverage']] for row in events)
    confusing = judge['confusing_parts']
    fluency = judge['fluency']
    return {**deterministic,
            'key_event_coverage_percent': round(100 * points / len(events), 2) if events else 100.,
            'hallucinated_claims': sum(len(row['unsupported_claims']) for row in judge['cue_claims']),
            'confusing_explained_percent': round(100 * sum(row['explained'] == 'yes' for row in confusing) / len(confusing), 2) if confusing else 100.,
            'fluency_mean': round(sum(row['score'] for row in fluency) / len(fluency), 2) if fluency else 0.}


def score_extended(run_dir, groundtruth_path, provider='nebius', *, config=None, client=None, budget_usd=.05):
    run, gt_path = Path(run_dir), Path(groundtruth_path)
    plan = json.loads((run / 'pause_plan.json').read_text())
    gt = json.loads(gt_path.read_text())
    pauses = plan.get('pauses', [])
    speech = gt.get('speech_intervals', plan.get('speech_intervals', []))
    inside = [p['cue_id'] for p in pauses if pause_overlaps_speech(p['t'], speech)]
    boundaries = [float(x) for x in gt.get('scene_cuts', [])]
    boundaries += [float(s[k]) for s in speech for k in ('start', 'end')]
    at_boundary = sum(any(abs(p['t'] - b) <= .2 for b in boundaries) for p in pauses)
    words = [len(str(p.get('cue_text', '')).split()) for p in pauses]
    deterministic = {'pauses_inside_speech': len(inside), 'pause_ids_inside_speech': inside,
                     'pause_at_cut_or_speech_boundary_percent': round(100 * at_boundary / len(pauses), 2) if pauses else 0.,
                     'total_added_seconds': round(sum(float(p.get('freeze_seconds', 0)) for p in pauses), 3),
                     'words_per_cue': words,
                     'words_per_cue_mean': round(sum(words) / len(words), 2) if words else 0.}
    key_events = [e for e in gt.get('key_events', []) if e.get('verdict') == 'supported' or e.get('scoring_target') is True]
    confusing = [e for e in gt.get('confusing_parts', []) if e.get('verdict') == 'supported' or e.get('scoring_target') is True]
    data = {'ground_truth': {'setting': gt.get('setting'), 'cast': gt.get('cast'), 'objects': gt.get('objects'),
                             'segments': gt.get('segments'), 'key_events': key_events, 'confusing_parts': confusing},
            'cues': [{'cue_id': p['cue_id'], 'source_t': p['t'], 'text': p.get('cue_text', '')} for p in pauses],
            '_temperature': 0.}
    cfg = resolve_provider(config or load_config(), provider)
    guard = SpendGuard(budget_usd)
    if client is None:
        if cfg['provider'] != 'mock' and not os.environ.get(cfg['key_env']):
            raise RuntimeError(f"Provider '{cfg['provider']}' needs env {cfg['key_env']}")
        client = None if cfg['provider'] == 'mock' else Client(cfg, guard)
    mock = {'key_events': [{'id': e['id'], 'coverage': 'no', 'reason': ''} for e in key_events],
            'cue_claims': [{'cue_id': p['cue_id'], 'unsupported_claims': []} for p in pauses],
            'confusing_parts': [{'id': e['id'], 'explained': 'no', 'reason': ''} for e in confusing],
            'fluency': [{'cue_id': p['cue_id'], 'score': 3, 'reason': ''} for p in pauses]}
    if client is None:
        raw, usage = mock, []
    else:
        client.guard, client.config = guard, cfg
        before = len(getattr(client, 'usage', []))
        raw = client.call('orchestrate', {**data, '_system': P.SCORE_EXTENDED})
        usage = getattr(client, 'usage', [])[before:]
    judge = normalise_judge(raw, [e['id'] for e in key_events], [p['cue_id'] for p in pauses], [e['id'] for e in confusing])
    aggregate = aggregate_score(deterministic, judge)
    result = {'run': str(run), 'groundtruth': str(gt_path), 'deterministic': deterministic,
              'judge': judge, 'aggregate': aggregate,
              'usage': {'cost_usd': sum(x.get('cost_usd', 0.) for x in usage), 'budget_usd': budget_usd,
                        'input_tokens': sum(x.get('input_tokens', 0) for x in usage),
                        'output_tokens': sum(x.get('output_tokens', 0) for x in usage)}}
    (run / 'score.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    (run / 'score.md').write_text(score_markdown(result), encoding='utf-8')
    return result


def score_markdown(result):
    a, d, j = result['aggregate'], result['deterministic'], result['judge']
    lines = ['# Extended AD score', '',
             f"- Key-event coverage: {a['key_event_coverage_percent']:.2f}%",
             f"- Hallucinated claims: {a['hallucinated_claims']}",
             f"- Confusing parts explained: {a['confusing_explained_percent']:.2f}%",
             f"- Mean fluency: {a['fluency_mean']:.2f}/5",
             f"- Pauses inside speech: {d['pauses_inside_speech']}",
             f"- Pause at cut/speech boundary: {d['pause_at_cut_or_speech_boundary_percent']:.2f}%",
             f"- Total added time: {d['total_added_seconds']:.3f} s", '', '## Key events', '']
    lines += [f"- `{x['id']}`: {x['coverage']} — {x['reason']}" for x in j['key_events']] or ['- No verified targets.']
    lines += ['', '## Cue fluency and unsupported claims', '']
    claims = {x['cue_id']: x['unsupported_claims'] for x in j['cue_claims']}
    lines += [f"- Cue {x['cue_id']}: {x['score']}/5 — {x['reason']}; unsupported: {claims.get(x['cue_id']) or 'none'}" for x in j['fluency']]
    return '\n'.join(lines) + '\n'


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('run_dir')
    p.add_argument('groundtruth')
    p.add_argument('--provider', choices=['nebius', 'nvidia-dev', 'mock'], default='nebius')
    args = p.parse_args(argv)
    result = score_extended(args.run_dir, args.groundtruth, args.provider)
    print(json.dumps(result['aggregate'], indent=2))


if __name__ == '__main__':
    main()
