"""Nemotron-built, frame-dense ground truth for independent extended-AD scoring."""
from __future__ import annotations

import json
import math
from pathlib import Path

from .agent.vad import detect
from .config import load_config, resolve_provider
from .director import parse_srt
from . import director_prompts as P
from .extended import normalise_speech, snap_pause_time
from .llm import Client, SpendGuard, normalize_json
from .media import probe, scene_cuts, timestamp
from .perception import separate_frames


def _text(value, limit=1000):
    return ' '.join(str(value or '').split())[:limit]


def _number(value, default=0.):
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def _strings(value, limit=20, chars=240):
    if isinstance(value, str):
        value = [value]
    return [_text(x, chars) for x in (value if isinstance(value, list) else [])[:limit]
            if isinstance(x, (str, int, float)) and _text(x, chars)]


def sample_times(duration, fps=1., cuts=(), after_cut=.05):
    """Dense regular timestamps plus one still immediately after each scene cut."""
    if not math.isfinite(float(fps)) or fps <= 0:
        raise ValueError('fps must be positive')
    duration = max(0., float(duration))
    regular = [i / fps for i in range(int(math.floor(duration * fps)) + 1)]
    extra = [min(max(0., float(c) + after_cut), max(0., duration - .001)) for c in cuts]
    return sorted({round(t, 3) for t in regular + extra if 0 <= t < duration})


def normalise_frame_descriptions(raw, requested_times):
    """Accept common VL response shapes while keeping only model-written text."""
    raw = normalize_json(raw)
    rows = raw.get('frames', raw.get('descriptions', [])) if isinstance(raw, dict) else raw
    rows = rows if isinstance(rows, list) else []
    out, remaining = [], list(requested_times)
    for i, item in enumerate(rows):
        if not isinstance(item, dict):
            continue
        requested = remaining.pop(0) if remaining else (requested_times[min(i, len(requested_times) - 1)] if requested_times else 0.)
        t = _number(item.get('t', item.get('timestamp', requested)), requested)
        out.append({'t': round(t, 3), 'setting': _text(item.get('setting'), 240),
                    'present': _strings(item.get('present', item.get('visible', item.get('who')))),
                    'objects': _strings(item.get('objects')),
                    'action': _text(item.get('action', item.get('what', item.get('description'))), 500),
                    'on_screen_text': _strings(item.get('on_screen_text', item.get('text_on_screen'))),
                    'subtitle_text': _strings(item.get('subtitle_text', item.get('subtitles')))})
    return sorted(out, key=lambda r: r['t'])


def normalise_groundtruth(raw, clip, duration, speech_intervals=(), cuts=()):
    """Validate the Ultra timeline and snap proposed pauses out of speech."""
    raw = normalize_json(raw) if isinstance(raw, dict) else {}
    val = lambda k, n=500: _text(raw.get(k), n)
    segments = []
    for i, item in enumerate(raw.get('segments', []) if isinstance(raw.get('segments'), list) else []):
        if not isinstance(item, dict):
            continue
        start = min(duration, max(0., _number(item.get('t_start', item.get('start')))))
        end = min(duration, max(start, _number(item.get('t_end', item.get('end')), start)))
        confusing = item.get('confusing') if isinstance(item.get('confusing'), dict) else None
        if confusing:
            confusing = {'is_confusing': confusing.get('is_confusing') in (True, 1, 'true', 'yes'),
                         'why': _text(confusing.get('why'), 300),
                         'what_to_explain': _text(confusing.get('what_to_explain'), 300)}
        recommendation = str(item.get('recommendation') or 'none').lower()
        if recommendation not in ('pause_extended', 'in_gap_short', 'none'):
            recommendation = 'none'
        try:
            importance = max(1, min(5, int(round(_number(item.get('importance'), 3)))))
        except (TypeError, ValueError):
            importance = 3
        segments.append({'id': _text(item.get('id'), 40) or f's{i+1}', 't_start': round(start, 3),
                         't_end': round(end, 3), 'setting': _text(item.get('setting'), 240),
                         'present': _strings(item.get('present')), 'action_steps': _strings(item.get('action_steps', item.get('actions'))),
                         'on_screen_text': _strings(item.get('on_screen_text')), 'importance': importance,
                         'confusing': confusing, 'recommendation': recommendation, 'reason': _text(item.get('reason'), 300)})

    def claims(key, what_keys):
        out = []
        for i, item in enumerate(raw.get(key, []) if isinstance(raw.get(key), list) else []):
            if not isinstance(item, dict):
                continue
            what = next((_text(item.get(k), 500) for k in what_keys if _text(item.get(k), 500)), '')
            row = {'id': _text(item.get('id'), 40) or f'{key[:1]}{i+1}',
                   't': round(min(duration, max(0., _number(item.get('t', item.get('time'))))), 3), 'what': what}
            if key == 'key_events':
                row['importance'] = max(1, min(5, int(round(_number(item.get('importance'), 3)))))
            else:
                row.update(why=_text(item.get('why'), 300), what_to_explain=_text(item.get('what_to_explain'), 300))
            out.append(row)
        return out

    speech = normalise_speech(speech_intervals, duration)
    pauses = []
    for item in raw.get('pause_points', []) if isinstance(raw.get('pause_points'), list) else []:
        if not isinstance(item, dict):
            continue
        original = min(duration, max(0., _number(item.get('t', item.get('time')))))
        inside = next((s for s in speech if s['start'] < original < s['end']), None)
        if inside:
            nearest = min((inside['start'], inside['end']), key=lambda t: (abs(t - original), t))
            snap = {'t': round(nearest, 3), 'snapped': True, 'from_t': round(original, 3),
                    'snap_seconds': round(nearest - original, 3),
                    'snap_reason': 'nearest_speech_free_instant'}
        else:
            snap = snap_pause_time(original, speech, duration, margin=0., max_snap=duration)
            if snap is None:
                continue
        # Prefer a nearby scene cut when it is already speech-free; ties go earlier.
        available_cuts = [float(c) for c in cuts if not any(s['start'] < float(c) < s['end'] for s in speech)]
        nearby = min(available_cuts, key=lambda c: (abs(c - original), c), default=None)
        if nearby is not None and abs(nearby - original) <= .25:
            snap = {'t': round(nearby, 3), 'snapped': abs(nearby-original) > 1e-6,
                    'from_t': round(original, 3), 'snap_seconds': round(nearby-original, 3),
                    'snap_reason': 'nearest_scene_cut'}
        pauses.append({**snap, 'why': _text(item.get('why'), 300)})

    cast = []
    for i, item in enumerate(raw.get('cast', []) if isinstance(raw.get('cast'), list) else []):
        if isinstance(item, dict):
            desc = _text(item.get('description', item.get('descriptor')), 240)
            cast.append({'id': _text(item.get('id'), 40) or f'c{i+1}', 'description': desc,
                         **({'notes': _text(item.get('notes'), 240)} if _text(item.get('notes'), 240) else {})})
        elif _text(item):
            cast.append({'id': f'c{i+1}', 'description': _text(item, 240)})
    return {'clip': val('clip', 200) or str(clip), 'duration': round(duration, 3), 'setting': val('setting', 500),
            'cast': cast, 'objects': _strings(raw.get('objects'), 40), 'segments': segments,
            'key_events': claims('key_events', ('what', 'event', 'claim')),
            'confusing_parts': claims('confusing_parts', ('what', 'claim', 'description')),
            'pause_points': pauses}


def normalise_verdicts(raw):
    raw = normalize_json(raw)
    rows = raw.get('verdicts', raw.get('claims', [])) if isinstance(raw, dict) else raw
    out = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        verdict = str(row.get('verdict') or '').lower().strip()
        if verdict not in ('supported', 'contradicted', 'uncertain'):
            verdict = 'uncertain'
        key = _text(row.get('id', row.get('claim_id')), 40)
        if key:
            out[key] = {'verdict': verdict, 'wrong': _text(row.get('wrong'), 200),
                        'verification_reason': _text(row.get('reason'), 300)}
    return out


class GroundTruthBuilder:
    def __init__(self, path, out, provider='nebius', budget_usd=.4, fps=1., batch_size=6,
                 *, config=None, client=None):
        self.path, self.out = Path(path), Path(out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.cfg = resolve_provider(config or load_config(), provider)
        self.guard = SpendGuard(budget_usd)
        self.client = client or (None if self.cfg['provider'] == 'mock' else Client(self.cfg, self.guard))
        if self.client is not None:
            self.client.guard, self.client.config = self.guard, self.cfg
        self.fps, self.batch_size = fps, max(1, int(batch_size))
        self.duration, self.has_audio = probe(self.path)
        self.usage = []

    def call(self, role, stage, system, data, media=None, mock=None):
        if self.client is None:
            result = mock
            self.usage.append({'cost_role': role, 'stage': stage, 'model': 'MOCK/' + stage,
                               'input_tokens': 0, 'output_tokens': 0, 'cost_usd': 0., 'latency_s': 0.})
            return result
        before = len(getattr(self.client, 'usage', []))
        result = self.client.call(stage, {**data, '_system': system}, media)
        new = getattr(self.client, 'usage', [])[before:]
        for row in new:
            row['cost_role'] = role
        self.usage.extend(dict(row) for row in new)
        return result

    def mock_frames(self, times):
        sidecar = self.path.with_suffix('.scenes.json')
        scenes = json.loads(sidecar.read_text()) if sidecar.is_file() else []
        rows = []
        for t in times:
            scene = next((s for s in scenes if _number(s.get('t_start')) <= t <= _number(s.get('t_end'))), {})
            rows.append({'t': t, 'setting': _text(scene.get('setting')), 'present': _strings(scene.get('who')),
                         'objects': _strings(scene.get('objects')), 'action': _text(scene.get('action')),
                         'on_screen_text': _strings(scene.get('on_screen_text')), 'subtitle_text': []})
        return {'frames': rows}

    def consolidate_mock(self, frames, cuts):
        segments, events = [], []
        for i, frame in enumerate(frames):
            end = frames[i + 1]['t'] if i + 1 < len(frames) else self.duration
            segments.append({'id': f's{i+1}', 't_start': frame['t'], 't_end': end, 'setting': frame['setting'],
                             'present': frame['present'], 'action_steps': [frame['action']] if frame['action'] else [],
                             'on_screen_text': frame['on_screen_text'], 'importance': 3,
                             'confusing': None, 'recommendation': 'none', 'reason': ''})
            if frame['action']:
                events.append({'id': f'k{i+1}', 't': frame['t'], 'what': frame['action'], 'importance': 3})
        return {'clip': self.path.name, 'duration': self.duration,
                'setting': next((f['setting'] for f in frames if f['setting']), ''), 'cast': [],
                'objects': list(dict.fromkeys(o for f in frames for o in f['objects'])),
                'segments': segments, 'key_events': events, 'confusing_parts': [],
                'pause_points': [{'t': c, 'why': ''} for c in cuts]}

    def build(self):
        cuts = scene_cuts(self.path)
        times = sample_times(self.duration, self.fps, cuts)
        frames = []
        for offset in range(0, len(times), self.batch_size):
            batch = times[offset:offset + self.batch_size]
            media = None if self.client is None else separate_frames(self.path, batch)
            raw = self.call('frames', 'perceive', P.GROUNDTRUTH_FRAMES,
                            {'duration': 0, 'clip_duration': self.duration, 'timestamps': batch,
                             '_temperature': 0.}, media, self.mock_frames(batch))
            frames.extend(normalise_frame_descriptions(raw, batch))

        vad = detect(self.path, self.duration, self.has_audio, self.cfg)
        srt = self.path.with_suffix('.en.srt')
        subtitles = [{'start': s, 'end': e, 'text': text} for s, e, text in parse_srt(srt)] if srt.is_file() else []
        raw = self.call('consolidate', 'orchestrate', P.GROUNDTRUTH_CONSOLIDATE,
                        {'duration': 0, 'clip': self.path.name, 'clip_duration': self.duration,
                         'frames': frames, 'speech_intervals': vad['speech'], 'scene_cuts': cuts,
                         'subtitle_speech_context': subtitles, '_temperature': 0., '_max_tokens': 6000},
                        None, self.consolidate_mock(frames, cuts))
        gt = normalise_groundtruth(raw, self.path.name, self.duration, vad['speech'], cuts)
        gt.update(frame_descriptions=frames, speech_intervals=vad['speech'], scene_cuts=cuts,
                  detector=vad['detector'], fps=self.fps)

        claims = [('key_events', c) for c in gt['key_events']] + [('confusing_parts', c) for c in gt['confusing_parts']]
        for offset in range(0, len(claims), 4):
            batch = claims[offset:offset + 4]
            payload, media = [], []
            for _, claim in batch:
                t = claim['t']
                stills = [round(max(0., t - .12), 3), round(min(max(0., self.duration - .001), t + .12), 3)]
                payload.append({'id': claim['id'], 't': t, 'claim': claim['what'], 'frame_times': stills})
                if self.client is not None:
                    media.append({'type': 'text', 'text': f"Frames for claim {claim['id']}:"})
                    media += separate_frames(self.path, stills)
            mock = {'verdicts': [{'id': c['id'], 'verdict': 'supported', 'wrong': '', 'reason': ''} for _, c in batch]}
            raw = self.call('verify', 'perceive', P.GROUNDTRUTH_VERIFY,
                            {'duration': 0, 'claims': payload, '_temperature': 0.}, media or None, mock)
            verdicts = normalise_verdicts(raw)
            for _, claim in batch:
                verdict = verdicts.get(claim['id'], {'verdict': 'uncertain', 'wrong': '',
                                                     'verification_reason': ''})
                claim.update(verdict, scoring_target=verdict['verdict'] == 'supported')

        stage = {}
        for row in self.usage:
            slot = stage.setdefault(row.get('cost_role', row.get('stage', 'unknown')),
                                    {'calls': 0, 'tokens_in': 0, 'tokens_out': 0, 'cost_usd': 0.})
            slot['calls'] += 1
            slot['tokens_in'] += row.get('input_tokens', 0)
            slot['tokens_out'] += row.get('output_tokens', 0)
            slot['cost_usd'] += row.get('cost_usd', 0.)
        gt['usage'] = {'stages': stage, 'total_cost_usd': sum(r.get('cost_usd', 0.) for r in self.usage),
                       'budget_usd': self.guard.cap}
        target = self.out / (self.path.stem + '.json')
        target.write_text(json.dumps(gt, ensure_ascii=False, indent=2), encoding='utf-8')
        (self.out / (self.path.stem + '.md')).write_text(groundtruth_markdown(gt), encoding='utf-8')
        return gt


def groundtruth_markdown(gt):
    esc = lambda v: _text(v).replace('|', '\\|')
    lines = [f"# Ground truth: {esc(gt.get('clip'))}", '',
             f"Duration: {gt.get('duration', 0):.3f} s · Setting: {esc(gt.get('setting'))}", '',
             '## Timeline', '', '| Time | Setting / present | Action steps | Text | Importance | Recommendation |',
             '|---|---|---|---|---:|---|']
    for row in gt.get('segments', []):
        lines.append(f"| {timestamp(row['t_start'])}–{timestamp(row['t_end'])} | {esc(row['setting'])}; {esc(', '.join(row['present']))} | "
                     f"{esc('; '.join(row['action_steps']))} | {esc('; '.join(row['on_screen_text']))} | {row['importance']} | "
                     f"{esc(row['recommendation'])}: {esc(row['reason'])} |")
    lines += ['', '## Key events', '']
    lines += [f"- `{e['id']}` {timestamp(e['t'])} — {esc(e['what'])} (importance {e['importance']}; {e.get('verdict', 'unverified')})"
              for e in gt.get('key_events', [])]
    lines += ['', '## Confusing parts', '']
    lines += [f"- `{e['id']}` {timestamp(e['t'])} — {esc(e['what'])}; explain: {esc(e['what_to_explain'])} ({e.get('verdict', 'unverified')})"
              for e in gt.get('confusing_parts', [])] or ['- None.']
    lines += ['', '## Pause recommendations', '']
    lines += [f"- {timestamp(p['t'])} — {esc(p['why'])}" +
              (f" (snapped from {timestamp(p['from_t'])}: {esc(p['snap_reason'])})" if p.get('snapped') else '')
              for p in gt.get('pause_points', [])] or ['- None.']
    lines += ['', '## Cost and tokens', '', '| Stage | Calls | Input tokens | Output tokens | Cost USD |',
              '|---|---:|---:|---:|---:|']
    for name, row in gt.get('usage', {}).get('stages', {}).items():
        lines.append(f"| {name} | {row['calls']} | {row['tokens_in']} | {row['tokens_out']} | {row['cost_usd']:.6f} |")
    lines.append(f"| **Total** |  |  |  | **{gt.get('usage', {}).get('total_cost_usd', 0):.6f}** |")
    return '\n'.join(lines) + '\n'


def build_groundtruth(path, out, provider='nebius', budget_usd=.4, fps=1., *, config=None, client=None):
    return GroundTruthBuilder(path, out, provider, budget_usd, fps, config=config, client=client).build()
