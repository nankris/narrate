"""Time-aware scoring for an extended-AD run against independent ground truth."""
import argparse
import json
import math
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from narrate.config import load_config, resolve_provider
from narrate.extended import pause_overlaps_speech
from narrate.llm import Client, SpendGuard


SCORE_EXTENDED_TIME_AWARE = '''Judge English extended audio description using ONLY the ground truth attached to each cue's
source window. Return exactly one strict JSON object with this shape:
{"cues":[{"cue_id":1,
"key_events":[{"id":"","coverage":"yes|partial|no","reason":""}],
"action_steps":[{"id":"","coverage":"yes|partial|no","reason":""}],
"unsupported_claims":["exact quoted cue claim"],
"chronology_errors":[{"claim":"exact quoted cue claim","reason":"correct source window/order"}],
"confusing_parts":[{"id":"","explained":"yes|partial|no","reason":""}],
"fluency":{"score":1,"reason":""}}]}.
Rules:
- Assess every supplied key event and action step for that cue. "yes" requires the SAME visible action and SAME object;
  shared clothing, setting, ingredient, or a different occurrence of a similar action is not coverage. Use "partial" only
  when the cue names the correct action/object vaguely or incompletely. Otherwise use "no".
- A target can be covered only in a cue window where it is supplied. Never use a cue from another window to cover it.
- Quote every concrete cue claim not supported by that cue window's ground truth in unsupported_claims. Ordinary connective
  language is not a concrete claim. A true action narrated from another window, anticipated, repeated as current, or placed
  out of order is unsupported here AND must also appear in chronology_errors with the correct timing/order in the reason.
- For every supplied confusing part, explained is yes when the cue clearly resolves what_to_explain, partial when it only
  hints at the resolution, otherwise no. Judge it only in the cue at or after that visual ambiguity.
- Fluency is native spoken-English fluency from 1 (poor) to 5 (excellent), independent of factual accuracy.
- unsupported_claims and chronology_errors may ONLY quote words that appear in that cue's text. Never list a ground-truth
  step there; a ground-truth step the cue does not mention is just coverage "no".
- Static scene facts (setting, people, clothing, objects present) are supported when clip_ground_truth setting, cast or
  objects, or any ground truth in this window, supports them. They are not chronology errors.
- The cue is spoken while the video is frozen at source_end, so describing the frozen frame and events within tolerance_s
  of source_end is current, not a chronology error.
Do not use general world knowledge or ground truth assigned to any other cue. Do not omit supplied targets or cues.'''


def _norm_words(text):
    return re.findall(r"[a-z0-9']+", str(text or '').lower())


def _quoted_from(claim, cue_words):
    """Round 8c: keep a judge claim only if most of its words come from the cue (drops echoed ground-truth steps)."""
    words = _norm_words(claim)
    if not words:
        return False
    vocab = set(cue_words)
    return sum(w in vocab for w in words) / len(words) >= .7


def _choice(value, allowed, default):
    value = str(value or '').lower().strip()
    return value if value in allowed else default


def _cue_id(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _supported(row):
    return row.get('scoring_target') is True or row.get('verdict') == 'supported'


def build_cue_windows(pauses, duration, tolerance_s=2.):
    """Build exact preceding-source windows; tolerance is only for target membership."""
    duration = max(0., float(duration))
    ordered = sorted(enumerate(pauses), key=lambda item: (float(item[1].get('t', 0.)), item[0]))
    windows, previous = [], 0.
    for order, (_, pause) in enumerate(ordered):
        end = min(duration, max(previous, float(pause.get('t', previous))))
        cue_id = _cue_id(pause.get('cue_id', pause.get('id', order + 1)))
        if cue_id is None:
            cue_id = order + 1
        windows.append({'cue_id': cue_id, 'source_start': round(previous, 3),
                        'source_end': round(end, 3), 'start_inclusive': order == 0,
                        'tolerance_s': float(tolerance_s),
                        'text': str(pause.get('cue_text', ''))})
        previous = end
    return windows


def target_in_window(target, window, tolerance_s=None):
    """Whether a point/range target intersects a cue's source window, with boundary tolerance."""
    tolerance = window.get('tolerance_s', 2.) if tolerance_s is None else tolerance_s
    tolerance = max(0., float(tolerance))
    start, end = float(window['source_start']), float(window['source_end'])
    target_start = float(target.get('t_start', target.get('t', 0.)))
    target_end = float(target.get('t_end', target.get('t', target_start)))
    if tolerance == 0 and target_start == target_end == start and not window.get('start_inclusive'):
        return False
    return target_end >= start - tolerance and target_start <= end + tolerance


_RANGE_TIME = re.compile(r'(?<![\d.])(\d+(?:\.\d+)?)\s*(?:-|–|—|to)\s*'
                         r'(\d+(?:\.\d+)?)\s*(?:s|sec(?:ond)?s?)\b', re.I)
_POINT_TIME = re.compile(r'(?<![\d.])(\d+(?:\.\d+)?)\s*(?:s|sec(?:ond)?s?)\b', re.I)


def groundtruth_action_steps(gt):
    """Give free-text segment action steps deterministic ids and source times."""
    targets = []
    for segment_index, segment in enumerate(gt.get('segments', [])):
        steps = segment.get('action_steps', []) if isinstance(segment, dict) else []
        steps = steps if isinstance(steps, list) else []
        seg_start = float(segment.get('t_start', 0.))
        seg_end = max(seg_start, float(segment.get('t_end', seg_start)))
        segment_id = str(segment.get('id') or f's{segment_index + 1}')
        for step_index, value in enumerate(steps):
            text = ' '.join(str(value or '').split())[:500]
            if not text:
                continue
            ranged = _RANGE_TIME.search(text)
            pointed = None if ranged else _POINT_TIME.search(text)
            if ranged:
                start, end = map(float, ranged.groups())
                if end < start:
                    start, end = end, start
            elif pointed:
                start = end = float(pointed.group(1))
            else:
                midpoint = seg_start + (seg_end - seg_start) * (step_index + .5) / max(1, len(steps))
                start = end = midpoint
            targets.append({'id': f'{segment_id}.a{step_index + 1}', 'segment_id': segment_id,
                            't_start': round(start, 3), 't_end': round(end, 3), 'what': text})
    return targets


def attach_window_groundtruth(windows, gt):
    """Attach only deterministically eligible targets to each cue window."""
    events = [dict(row) for row in gt.get('key_events', []) if isinstance(row, dict) and _supported(row)]
    actions = groundtruth_action_steps(gt)
    confusing = [dict(row) for row in gt.get('confusing_parts', []) if isinstance(row, dict) and _supported(row)]
    enriched = []
    confusing_window = {}
    for target in confusing:
        eligible = [w for w in windows if float(w['source_end']) + 1e-9 >= float(target.get('t', 0.))]
        if eligible:
            confusing_window[str(target.get('id'))] = eligible[0]['cue_id']
    for window in windows:
        row = dict(window)
        row['key_events'] = [e for e in events if target_in_window(e, window)]
        row['action_steps'] = [a for a in actions if target_in_window(a, window)]
        row['confusing_parts'] = [c for c in confusing
                                  if confusing_window.get(str(c.get('id'))) == window['cue_id']]
        enriched.append(row)
    return enriched, events, actions, confusing


def _reason(row, default=''):
    return str(row.get('reason') or default)[:400]


def normalise_judge(raw, event_ids=(), cue_ids=(), confusing_ids=(), action_step_ids=(), windows=None):
    """Constrain model verdicts to deterministic target/cue membership."""
    raw = raw if isinstance(raw, dict) else {}
    cue_text = {_cue_id(w.get('cue_id')): w.get('text', '') for w in (windows or [])}
    cue_ids = [_cue_id(x) for x in cue_ids]
    cue_ids = [x for x in cue_ids if x is not None]
    expected = {'key_events': {}, 'action_steps': {}, 'confusing_parts': {}}
    if windows is not None:
        for window in windows:
            cue_id = window['cue_id']
            for kind in expected:
                expected[kind][cue_id] = {str(x.get('id')) for x in window.get(kind, [])}

    nested = raw.get('cues', []) if isinstance(raw.get('cues'), list) else []
    model_rows = {'key_events': [], 'action_steps': [], 'confusing_parts': []}
    claim_rows = []
    fluency_rows = []
    for cue in nested:
        if not isinstance(cue, dict):
            continue
        cue_id = _cue_id(cue.get('cue_id', cue.get('id')))
        for kind in model_rows:
            for target in cue.get(kind, []) if isinstance(cue.get(kind), list) else []:
                if isinstance(target, dict):
                    model_rows[kind].append({**target, 'cue_id': cue_id})
        claim_rows.append({'cue_id': cue_id,
                           'unsupported_claims': cue.get('unsupported_claims', []),
                           'chronology_errors': cue.get('chronology_errors', [])})
        fluency = cue.get('fluency') if isinstance(cue.get('fluency'), dict) else {}
        fluency_rows.append({**fluency, 'cue_id': cue_id})

    for kind in model_rows:
        flat = raw.get(kind, []) if isinstance(raw.get(kind), list) else []
        model_rows[kind].extend(row for row in flat if isinstance(row, dict))
    if isinstance(raw.get('cue_claims'), list):
        claim_rows.extend(row for row in raw['cue_claims'] if isinstance(row, dict))
    if isinstance(raw.get('fluency'), list):
        fluency_rows.extend(row for row in raw['fluency'] if isinstance(row, dict))

    allowed_ids = {'key_events': set(map(str, event_ids)),
                   'action_steps': set(map(str, action_step_ids)),
                   'confusing_parts': set(map(str, confusing_ids))}
    target_results = {}
    for kind, rows in model_rows.items():
        values = {}
        answer_key = 'explained' if kind == 'confusing_parts' else 'coverage'
        choices = {'yes', 'partial', 'no'}
        for row in rows:
            target_id = str(row.get('id', ''))
            cue_id = _cue_id(row.get('cue_id'))
            if target_id not in allowed_ids[kind]:
                continue
            if windows is not None:
                possible = [cid for cid, ids in expected[kind].items() if target_id in ids]
                if cue_id is None and len(possible) == 1:
                    cue_id = possible[0]
                if cue_id not in possible:
                    continue
            values[(target_id, cue_id)] = {'id': target_id, 'cue_id': cue_id,
                                            answer_key: _choice(row.get(answer_key), choices, 'no'),
                                            'reason': _reason(row)}
        if windows is not None:
            for cue_id, ids in expected[kind].items():
                for target_id in ids:
                    values.setdefault((target_id, cue_id), {'id': target_id, 'cue_id': cue_id,
                                      answer_key: 'no', 'reason': 'judge omitted target for this window'})
        else:
            for target_id in allowed_ids[kind]:
                values.setdefault((target_id, None), {'id': target_id, 'cue_id': None,
                                  answer_key: 'no', 'reason': 'judge omitted target'})
        represented = {target_id for target_id, _ in values}
        for target_id in allowed_ids[kind] - represented:
            values[(target_id, None)] = {'id': target_id, 'cue_id': None, answer_key: 'no',
                                         'reason': 'no cue window contains target'}
        target_results[kind] = list(values.values())

    claims = {}
    for row in claim_rows:
        cue_id = _cue_id(row.get('cue_id', row.get('id')))
        if cue_id not in cue_ids:
            continue
        unsupported = row.get('unsupported_claims', [])
        unsupported = [str(x)[:400] for x in unsupported if isinstance(x, str)] if isinstance(unsupported, list) else []
        chronology = []
        for item in row.get('chronology_errors', []) if isinstance(row.get('chronology_errors'), list) else []:
            if isinstance(item, str):
                chronology.append({'claim': item[:400], 'reason': ''})
            elif isinstance(item, dict) and str(item.get('claim') or '').strip():
                chronology.append({'claim': str(item.get('claim'))[:400], 'reason': _reason(item)})
        text = _norm_words(cue_text.get(cue_id, ''))
        unsupported = [c for c in unsupported if not text or _quoted_from(c, text)]
        chronology = [c for c in chronology if not text or _quoted_from(c['claim'], text)]
        claims[cue_id] = {'cue_id': cue_id, 'unsupported_claims': unsupported,
                          'chronology_errors': chronology}
    for cue_id in cue_ids:
        claims.setdefault(cue_id, {'cue_id': cue_id, 'unsupported_claims': [], 'chronology_errors': []})

    fluency = {}
    for row in fluency_rows:
        cue_id = _cue_id(row.get('cue_id', row.get('id')))
        try:
            score = int(round(float(row.get('score'))))
        except (TypeError, ValueError):
            continue
        if cue_id in cue_ids:
            fluency[cue_id] = {'cue_id': cue_id, 'score': max(1, min(5, score)), 'reason': _reason(row)}
    for cue_id in cue_ids:
        fluency.setdefault(cue_id, {'cue_id': cue_id, 'score': 1, 'reason': 'judge omitted cue'})
    return {**target_results, 'cue_claims': list(claims.values()), 'fluency': list(fluency.values())}


def _coverage_percent(rows, field):
    by_id = {}
    points = {'yes': 1., 'partial': .5, 'no': 0.}
    for row in rows:
        by_id[row['id']] = max(by_id.get(row['id'], 0.), points.get(row.get(field), 0.))
    return round(100 * sum(by_id.values()) / len(by_id), 2) if by_id else 100.


def aggregate_score(deterministic, judge):
    fluency = judge.get('fluency', [])
    claims = judge.get('cue_claims', [])
    return {**deterministic,
            'key_event_coverage_percent': _coverage_percent(judge.get('key_events', []), 'coverage'),
            'action_step_coverage_percent': _coverage_percent(judge.get('action_steps', []), 'coverage'),
            'hallucinated_claims': sum(len(row.get('unsupported_claims', [])) for row in claims),
            'chronology_errors': sum(len(row.get('chronology_errors', [])) for row in claims),
            'confusing_explained_percent': _coverage_percent(judge.get('confusing_parts', []), 'explained'),
            'fluency_mean': round(sum(row['score'] for row in fluency) / len(fluency), 2) if fluency else 0.}


def _deterministic_metrics(pauses, speech, gt, duration):
    micro_silences = gt.get('micro_silences', [])
    inside = [p.get('cue_id', p.get('id')) for p in pauses
              if pause_overlaps_speech(float(p.get('t', 0.)), speech)
              and not any(float(g.get('start', 0.)) <= float(p.get('t', 0.)) <= float(g.get('end', 0.))
                          for g in micro_silences)]
    boundaries = [float(x) for x in gt.get('scene_cuts', [])]
    boundaries += [float(s[k]) for s in speech for k in ('start', 'end')]
    boundaries += [float(g[k]) for g in micro_silences for k in ('start', 'end')]
    at_boundary = sum(any(abs(float(p.get('t', 0.)) - b) <= .2 for b in boundaries) for p in pauses)
    words = [len(str(p.get('cue_text', '')).split()) for p in pauses]
    pause_times = sorted({min(duration, max(0., float(p.get('t', 0.)))) for p in pauses})
    bounds = [0.] + pause_times + [duration]
    max_gap = max((right - left for left, right in zip(bounds, bounds[1:])), default=duration)
    return {'pauses_inside_speech': len(inside), 'pause_ids_inside_speech': inside,
            'pause_at_cut_or_speech_boundary_percent': round(100 * at_boundary / len(pauses), 2) if pauses else 0.,
            'max_undescribed_gap_s': round(max_gap, 3),
            'total_added_seconds': round(sum(float(p.get('freeze_seconds', 0)) for p in pauses), 3),
            'words_per_cue': words,
            'words_per_cue_mean': round(sum(words) / len(words), 2) if words else 0.}


def score_extended(run_dir, groundtruth_path, provider='nebius', *, config=None, client=None, budget_usd=.05,
                   frame_audit=False):
    run, gt_path = Path(run_dir), Path(groundtruth_path)
    plan = json.loads((run / 'pause_plan.json').read_text())
    gt = json.loads(gt_path.read_text())
    pauses = plan.get('pauses', [])
    duration = float(gt.get('duration', plan.get('source_duration', 0.)))
    speech = gt.get('speech_intervals', plan.get('speech_intervals', []))
    deterministic = _deterministic_metrics(pauses, speech, gt, duration)
    windows = build_cue_windows(pauses, duration)
    windows, key_events, action_steps, confusing = attach_window_groundtruth(windows, gt)

    data = {'clip_ground_truth': {'setting': gt.get('setting'), 'cast': gt.get('cast'),
                                  'objects': gt.get('objects')},
            'cue_windows': windows, '_temperature': 0., '_max_tokens': 5000,
            '_system': SCORE_EXTENDED_TIME_AWARE}
    cfg = resolve_provider(config or load_config(), provider)
    if not math.isfinite(float(budget_usd)) or float(budget_usd) < 0:
        raise ValueError('budget_usd must be finite and nonnegative')
    budget_usd = min(.08 if frame_audit else .05, float(budget_usd))
    guard = SpendGuard(budget_usd)
    if client is None:
        if cfg['provider'] != 'mock' and not os.environ.get(cfg['key_env']):
            raise RuntimeError(f"Provider '{cfg['provider']}' needs env {cfg['key_env']}")
        client = None if cfg['provider'] == 'mock' else Client(cfg, guard)
    mock = {'cues': [{'cue_id': w['cue_id'],
                      'key_events': [{'id': e['id'], 'coverage': 'no', 'reason': ''}
                                     for e in w['key_events']],
                      'action_steps': [{'id': e['id'], 'coverage': 'no', 'reason': ''}
                                       for e in w['action_steps']],
                      'unsupported_claims': [], 'chronology_errors': [],
                      'confusing_parts': [{'id': e['id'], 'explained': 'no', 'reason': ''}
                                          for e in w['confusing_parts']],
                      'fluency': {'score': 3, 'reason': ''}} for w in windows]}
    if client is None:
        raw, usage = mock, []
    else:
        client.guard, client.config = guard, cfg
        before = len(getattr(client, 'usage', []))
        # Round 8c: one judge call per cue window. A single call over 8 roti windows hit the 5000-token output
        # cap, the JSON was cut off, and every target scored 'judge omitted' (0% coverage, fluency 1.0).
        raw = {'cues': []}
        for window in windows:
            part = client.call('orchestrate', {**data, 'cue_windows': [window], '_max_tokens': 3000})
            rows = part.get('cues', []) if isinstance(part, dict) and isinstance(part.get('cues'), list) else []
            for row in rows:
                if isinstance(row, dict):
                    row.setdefault('cue_id', window['cue_id'])
                    raw['cues'].append(row)
        usage = getattr(client, 'usage', [])[before:]
    judge = normalise_judge(raw, [e['id'] for e in key_events], [w['cue_id'] for w in windows],
                            [e['id'] for e in confusing], [e['id'] for e in action_steps], windows)
    aggregate = aggregate_score(deterministic, judge)
    if client is not None and frame_audit:
        audit = audit_flags_on_frames(client, run, windows, judge, duration)
        usage = getattr(client, 'usage', [])[before:]
        aggregate['judge_flagged_claims'] = aggregate['hallucinated_claims']
        aggregate['judge_flagged_chronology'] = aggregate['chronology_errors']
        aggregate['frame_contradicted_claims'] = sum(1 for x in audit if x['verdict'] == 'contradicted')
        aggregate['frame_uncertain_claims'] = sum(1 for x in audit if x['verdict'] == 'uncertain')
        aggregate['frame_supported_claims'] = sum(1 for x in audit if x['verdict'] == 'supported')
        judge['frame_audit'] = audit
    result = {'run': str(run), 'groundtruth': str(gt_path), 'cue_windows': windows,
              'deterministic': deterministic, 'judge': judge, 'aggregate': aggregate,
              'usage': {'cost_usd': sum(x.get('cost_usd', 0.) for x in usage), 'budget_usd': budget_usd,
                        'input_tokens': sum(x.get('input_tokens', 0) for x in usage),
                        'output_tokens': sum(x.get('output_tokens', 0) for x in usage)}}
    (run / 'score.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    (run / 'score.md').write_text(score_markdown(result), encoding='utf-8')
    return result


FRAME_AUDIT = '''A text judge flagged claims in an audio-description cue as unsupported or out of order. You see stills
spread across that cue's source window (labelled with timestamps; the last is the frozen frame the cue is spoken over).
For EACH flagged claim return {"claims":[{"claim":"","verdict":"supported|contradicted|uncertain","reason":""}]}.
supported: the stills show it (an action counts if its start, middle or result is visible, in a plausible order).
contradicted: the stills clearly show something else (wrong object, hand, count, text, action or order).
uncertain: the stills cannot settle it. Use only the stills.'''


def audit_flags_on_frames(client, run, windows, judge, duration, n_frames=5):
    """Round 8c: second pass on stills for every judge-flagged claim. The text judge compares a cue with a sparse
    ground truth, so a true detail the ground truth omits is 'unsupported'; stills separate real errors from that."""
    from narrate.perception import separate_frames
    source = json.loads((Path(run) / 'report.json').read_text())['input_path']
    flagged = {}
    for row in judge.get('cue_claims', []):
        items = list(row.get('unsupported_claims', [])) + [c['claim'] for c in row.get('chronology_errors', [])]
        items = list(dict.fromkeys(i for i in items if i))
        if items:
            flagged[row['cue_id']] = items
    out = []
    for window in windows:
        items = flagged.get(window['cue_id'])
        if not items:
            continue
        start, end = float(window['source_start']), min(float(window['source_end']), max(0., duration - .3))
        times = sorted({round(start + (end - start) * (i + .5) / n_frames, 3) for i in range(n_frames - 1)} | {round(end, 3)})
        try:
            raw = client.call('perceive', {'cue_text': window.get('text', ''), 'flagged_claims': items,
                                           '_system': FRAME_AUDIT, '_temperature': 0., '_max_tokens': 1500},
                              separate_frames(source, times))
        except Exception as exc:
            raw = {'claims': [], 'error': str(exc)[:200]}
        rows = raw.get('claims', []) if isinstance(raw, dict) and isinstance(raw.get('claims'), list) else []
        by_claim = {str(r.get('claim', '')).strip().lower(): r for r in rows if isinstance(r, dict)}
        for i, item in enumerate(items):
            r = by_claim.get(item.strip().lower()) or (rows[i] if i < len(rows) and isinstance(rows[i], dict) else {})
            out.append({'cue_id': window['cue_id'], 'claim': item, 'frame_times': times,
                        'verdict': _choice(r.get('verdict'), ('supported', 'contradicted', 'uncertain'), 'uncertain'),
                        'reason': str(r.get('reason') or '')[:300]})
    return out


def score_markdown(result):
    a, d, judge = result['aggregate'], result['deterministic'], result['judge']
    lines = ['# Extended AD score', '',
             f"- Key-event coverage: {a['key_event_coverage_percent']:.2f}%",
             f"- Action-step coverage: {a['action_step_coverage_percent']:.2f}%",
             f"- Hallucinated claims: {a['hallucinated_claims']}",
             f"- Chronology errors: {a['chronology_errors']}",
             f"- Confusing parts explained: {a['confusing_explained_percent']:.2f}%",
             f"- Mean fluency: {a['fluency_mean']:.2f}/5",
             f"- Maximum source span without a pause: {d['max_undescribed_gap_s']:.3f} s",
             f"- Pauses inside speech: {d['pauses_inside_speech']}",
             f"- Pause at cut/speech boundary: {d['pause_at_cut_or_speech_boundary_percent']:.2f}%",
             f"- Total added time: {d['total_added_seconds']:.3f} s"]
    if 'frame_contradicted_claims' in a:
        lines += [f"- Frame audit of judge flags: {a['frame_contradicted_claims']} contradicted, "
                  f"{a['frame_uncertain_claims']} uncertain, {a['frame_supported_claims']} supported on stills"]
    lines += ['', '## Cue windows', '']
    claims = {x['cue_id']: x for x in judge.get('cue_claims', [])}
    fluency = {x['cue_id']: x for x in judge.get('fluency', [])}
    coverage = {'key_events': {}, 'action_steps': {}, 'confusing_parts': {}}
    for kind in coverage:
        for row in judge.get(kind, []):
            coverage[kind][(row.get('cue_id'), row['id'])] = row
    for window in result.get('cue_windows', []):
        cue_id = window['cue_id']
        bracket = '[' if window.get('start_inclusive') else '('
        lines += [f"### Cue {cue_id}: {bracket}{window['source_start']:.3f}, {window['source_end']:.3f}] s", '',
                  window.get('text') or '*Empty cue.*', '']
        matched = []
        for kind, label in (('key_events', 'event'), ('action_steps', 'step')):
            for target in window.get(kind, []):
                verdict = coverage[kind].get((cue_id, str(target.get('id'))), {})
                if verdict.get('coverage') in ('yes', 'partial'):
                    matched.append(f"{label} `{target['id']}` ({verdict['coverage']}): {target.get('what', '')}")
        lines.append('Matched GT steps: ' + ('; '.join(matched) if matched else 'none'))
        cue_claims = claims.get(cue_id, {})
        unsupported = cue_claims.get('unsupported_claims', [])
        lines.append('Unsupported claims: ' + ('; '.join(unsupported) if unsupported else 'none'))
        chronology = cue_claims.get('chronology_errors', [])
        chronology_text = '; '.join(f"{x['claim']} ({x['reason']})" if x.get('reason') else x['claim']
                                    for x in chronology)
        lines.append('Chronology errors: ' + (chronology_text or 'none'))
        audited = [x for x in judge.get('frame_audit', []) if x['cue_id'] == cue_id]
        if audited:
            lines.append('Frame audit: ' + '; '.join(f"{x['verdict'].upper()}: {x['claim']} ({x['reason']})" for x in audited))
        cue_fluency = fluency.get(cue_id, {'score': 1, 'reason': 'judge omitted cue'})
        lines += [f"Fluency: {cue_fluency['score']}/5 — {cue_fluency['reason']}", '']
    return '\n'.join(lines).rstrip() + '\n'


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('run_dir')
    parser.add_argument('groundtruth')
    parser.add_argument('--provider', choices=['nebius', 'nvidia-dev', 'mock'], default='nebius')
    parser.add_argument('--frame-audit', action='store_true', help='check every judge flag on window stills (Super VL)')
    args = parser.parse_args(argv)
    result = score_extended(args.run_dir, args.groundtruth, args.provider, budget_usd=.08 if args.frame_audit else .05,
                            frame_audit=args.frame_audit)
    print(json.dumps(result['aggregate'], indent=2))


if __name__ == '__main__':
    main()
