"""English-only WCAG 1.2.7 extended audio-description director."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .agent.core import Agent, lint_with_hints, risky_text, similarity
from .agent.vad import detect
from .config import load_config, resolve_provider
from .director import Director, UltraCapReached, normalise_en, has_finite_verb
from .llm import SpendGuard, BudgetExceeded, sanitize
from .media import (micro_silences, probe, scene_cuts, sensitive_visual_changes,
                    split_slots)
from .perception import separate_frames
from . import director_prompts as P
from .extended import (DEFAULTS as EXT_DEFAULTS, build_extended_timeline, plan_pauses,
                       render_extended, write_extended_texts)


DEFAULTS = {**EXT_DEFAULTS, 'max_repair_rounds': 2, 'verify_batch': 4,
            'verify_temperature': 0., 'temperature': .2, 'budget_usd': .10,
            'micro_silence_db': -30., 'micro_silence_min_s': .08,
            'micro_speech_min_s': 8.,
            'visual_change_threshold': 1., 'visual_change_fps': 2.,
            'redundancy_previous': .48, 'rescue_rounds': 1}


def split_speech_at_silences(intervals, silences):
    """Subtract confirmed acoustic silences from broad VAD speech intervals."""
    out = []
    for speech in intervals or []:
        start, end = float(speech['start']), float(speech['end'])
        cursor = start
        for gap in silences or []:
            lo, hi = max(start, float(gap['start'])), min(end, float(gap['end']))
            if hi <= lo:
                continue
            if lo > cursor:
                out.append({'start': cursor, 'end': lo})
            cursor = max(cursor, hi)
        if cursor < end:
            out.append({'start': cursor, 'end': end})
    return out


def event_in_window(event, previous, current):
    """Assign an event to the pause where its visible action finishes."""
    return float(event['t_end']) > previous + 1e-6 and float(event['t_end']) <= current + 1e-6


def normalise_pause_frames(raw, requested_times):
    """Normalise pause-frame facts locally, keeping production independent of evaluation artifacts."""
    rows = raw.get('frames', raw.get('descriptions', [])) if isinstance(raw, dict) else raw
    out = []
    for i, row in enumerate(rows if isinstance(rows, list) else []):
        if not isinstance(row, dict):
            continue
        fallback = requested_times[min(i, len(requested_times) - 1)] if requested_times else 0.
        try:
            t = float(row.get('t', row.get('timestamp', fallback)))
        except (TypeError, ValueError):
            t = fallback
        def strings(value):
            values = value if isinstance(value, list) else [value] if isinstance(value, str) else []
            return [' '.join(str(x).split())[:240] for x in values if str(x).strip()]
        out.append({'t': round(t, 3), 'setting': ' '.join(str(row.get('setting') or '').split())[:240],
                    'present': strings(row.get('present', row.get('visible', row.get('who')))),
                    'objects': strings(row.get('objects')),
                    'action': ' '.join(str(row.get('action', row.get('what', ''))).split())[:500],
                    'on_screen_text': strings(row.get('on_screen_text')),
                    'subtitle_text': strings(row.get('subtitle_text'))})
    return out


def parse_extended_cues(raw):
    rows = raw.get('cues', raw.get('pauses', [])) if isinstance(raw, dict) else raw
    out = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        try:
            cue_id = int(row.get('pause_id', row.get('cue_id', row.get('id'))))
        except (TypeError, ValueError):
            continue
        text = row.get('text', row.get('en'))
        evidence = row.get('evidence', row.get('evidence_ids', []))
        evidence = evidence if isinstance(evidence, list) else [evidence]
        if isinstance(text, str) and text.strip():
            out[cue_id] = {'text': normalise_en(text),
                           'evidence': [str(x) for x in evidence if isinstance(x, (str, int))]}
    return out


def _sentences(text):
    return len([s for s in re.split(r'(?<=[.!?])\s+', text.strip()) if s])


class ExtendedDirector(Director):
    def __init__(self, path, out, cfg, guard, on_step=None, client=None, context=None):
        super().__init__(path, out, cfg, ['en'], guard, on_step, client, context=context)
        self.x = {**DEFAULTS, **(cfg.get('extended') or {})}
        self.pause_rows, self.pause_frames, self.extended_cues = [], {}, {}
        self.ext_history, self.ext_dropped = {}, {}
        self.ext_candidates, self.micro_gaps, self.visual_changes = {}, [], []
        self.report.update(mode='director', ad_mode='extended', input_path=str(Path(path).resolve()))

    def log_ext(self, cue_id, **row):
        self.ext_history.setdefault(str(cue_id), []).append(row)

    def detect_extended_speech(self):
        result = detect(self.path, self.duration, self.has_audio, self.cfg)
        found = ([] if self.mock or not self.has_audio else
                 micro_silences(self.path, self.duration, self.x['micro_silence_db'],
                                self.x['micro_silence_min_s']))
        long_speech = [s for s in result['speech']
                       if s['end'] - s['start'] >= float(self.x['micro_speech_min_s'])]
        self.micro_gaps = [g for g in found if any(s['start'] <= g['midpoint'] <= s['end']
                                                  for s in long_speech)]
        self.speech = split_speech_at_silences(result['speech'], self.micro_gaps)
        self.report.update(detector=result['detector'], speech_ratio=result['speech_ratio'],
                           detector_fallback_reason=result['fallback_reason'],
                           micro_silences=self.micro_gaps)
        return (f"{len(self.speech)} speech intervals; {100*result['speech_ratio']:.0f}% speech; "
                f"{len(self.micro_gaps)} between-sentence micro-silences")

    def st_shots(self):
        self.shots = scene_cuts(self.path)
        # The low-threshold pass is a fallback for slide/text videos whose
        # ordinary scene detector found nothing; on live-action motion it would
        # deliberately be too sensitive.
        self.visual_changes = ([] if self.mock or self.shots else
                               sensitive_visual_changes(self.path, self.x['visual_change_threshold'],
                                                        self.x['visual_change_fps']))
        boundaries = sorted(set(self.shots + self.visual_changes))
        self.windows = split_slots(0., self.duration, self.d['window_s'], boundaries,
                                   self.d['window_snap_s'], min(8., self.d['window_s'] / 2))
        return (f'{len(self.shots)} scene cuts; {len(self.visual_changes)} sensitive visual changes; '
                f'{len(self.windows)} perception windows; est. Super VL timeline cost '
                f'${self.window_cost_estimate():.4f}')

    def st_plan_pauses(self):
        self.pause_rows = plan_pauses(self.duration, self.speech, self.shots, self.timeline,
                                      self.bible.get('beats', []),
                                      safety_margin=self.x['speech_margin_s'], snap_max_s=self.x['snap_max_s'],
                                      min_spacing_s=self.x['min_pause_spacing_s'],
                                      max_pauses_per_minute=self.x['max_pauses_per_minute'],
                                      max_coverage_gap_s=self.x['max_coverage_gap_s'],
                                      final_pause_within_s=self.x['final_pause_within_s'],
                                      micro_silences=self.micro_gaps,
                                      visual_changes=self.visual_changes)
        points = [0.] + [p['t'] for p in self.pause_rows] + [self.duration]
        largest = max((b - a for a, b in zip(points, points[1:])), default=0.)
        return (f"{len(self.pause_rows)} pauses; largest source gap {largest:.2f} s "
                f"(hard max {self.x['max_coverage_gap_s']} s); final at {self.pause_rows[-1]['t']:.2f} s")

    def mock_pause_frames(self):
        rows = []
        for pause in self.pause_rows:
            t = pause['t']
            event = min(self.timeline, key=lambda e: abs((e['t_start'] + e['t_end']) / 2 - t), default={})
            rows.append({'t': t, 'setting': self.bible.get('setting', ''),
                         'present': [c['descriptor'] for c in self.bible.get('cast', [])],
                         'objects': self.bible.get('objects', []), 'action': event.get('what', ''),
                         'on_screen_text': [event['on_screen_text']] if event.get('on_screen_text') else [],
                         'subtitle_text': [event['subtitle_text']] if event.get('subtitle_text') else []})
        return {'frames': rows}

    def st_pause_frames(self):
        if not self.pause_rows:
            return 'no pause frames'
        times = [p['t'] for p in self.pause_rows]
        frame_times = [min(max(0., self.duration - .04), t) for t in times]
        media = None if self.mock else separate_frames(self.path, frame_times)
        raw = self.model('pause_frames', 'perceive', P.GROUNDTRUTH_FRAMES,
                         {'duration': 0, 'timestamps': frame_times, 'pause_timestamps': times}, media,
                         self.mock_pause_frames() if self.mock else None)
        frames = normalise_pause_frames(raw, times)
        for pause in self.pause_rows:
            self.pause_frames[pause['id']] = min(frames, key=lambda f: abs(f['t'] - pause['t']), default={})
        return f'{len(self.pause_frames)} current frames described by Super VL'

    def events_between(self, previous, current):
        return sorted((e for e in self.timeline if event_in_window(e, previous, current)),
                      key=lambda e: (e['t_end'], e['t_start'], e['id']))

    def confusing_between(self, previous, current):
        return [{'id': e['id'], 'what': e['what'], 'why': 'low-confidence visual event'}
                for e in self.events_between(previous, current) if e.get('confidence', 1.) < .65]

    def pause_payload(self, pause, previous):
        events = self.events_between(previous, pause['t'])
        frame = {'id': f"frame-p{pause['id']}", **self.pause_frames.get(pause['id'], {})}
        return {'pause_id': pause['id'], 'source_t': pause['t'], 'previous_pause': previous,
                'window_bounds': {'exclusive_start': previous, 'inclusive_end': pause['t']},
                'why': pause['reason'], 'max_words': int(self.x['max_words']),
                'establish': pause['id'] == self.pause_rows[0]['id'] or 'scene cut' in pause['reason'],
                'events': [{'id': e['id'], 't_start': e['t_start'], 't_end': e['t_end'], 'what': e['what'],
                            'on_screen_text': e.get('on_screen_text', ''),
                            'subtitle_text': e.get('subtitle_text', ''), 'importance': e.get('importance', 3)} for e in events],
                'current_frame_facts': frame,
                'confusing_parts': self.confusing_between(previous, pause['t'])}

    def mock_script(self, payloads):
        rows = []
        for p in payloads:
            facts = [e['what'] for e in p['events'] if e.get('what')]
            current = p['current_frame_facts'].get('action', '')
            ordered = list(dict.fromkeys(facts or ([current] if current else [])))
            text = ordered[-1] if ordered else ''
            if text:
                rows.append({'pause_id': p['pause_id'], 'text': text,
                             'evidence': ([e['id'] for e in p['events'] if e.get('what')][-2:] or
                                          [p['current_frame_facts']['id']])[:2]})
        return {'cues': rows}

    def st_write(self):
        previous, payloads = 0., []
        for pause in self.pause_rows:
            payloads.append(self.pause_payload(pause, previous))
            previous = pause['t']
        data = {'bible': self.bible, 'pauses': payloads, '_temperature': self.x['temperature']}
        raw = self.model('extended_write', 'edit', P.EXTENDED_SCRIPT, data, None,
                         self.mock_script(payloads) if self.mock else None, ultra=True)
        self.extended_cues = parse_extended_cues(raw)
        written = len(self.extended_cues)
        for pause in self.pause_rows:
            if pause['id'] not in self.extended_cues:
                self.ext_dropped[pause['id']] = 'writer returned no cue'
                self.extended_cues[pause['id']] = {'text': '', 'evidence': []}
            else:
                self.ext_candidates.setdefault(pause['id'], []).append(self.extended_cues[pause['id']])
        return f"{written} of {len(self.pause_rows)} pauses written in one Ultra call"

    def cue_problems(self, cue_id, entry, accepted=None):
        text = entry['text']
        pause = next(p for p in self.pause_rows if p['id'] == cue_id)
        index = next(i for i, p in enumerate(self.pause_rows) if p['id'] == cue_id)
        previous = self.pause_rows[index - 1]['t'] if index else 0.
        allowed = {e['id'] for e in self.events_between(previous, pause['t'])}
        allowed.add(f'frame-p{cue_id}')
        problems = []
        words = len(text.split())
        if words > int(self.x['max_words']):
            problems.append(f'over budget: {words} words, hard max {self.x["max_words"]}')
        if words < int(self.x['min_words']):
            problems.append(f'Style: only {words} words; aim for {self.x["min_words"]}-{self.x["max_words"]}')
        if not has_finite_verb(text):
            problems.append('Style: cue has no finite verb')
        if not 2 <= _sentences(text) <= 3:
            problems.append(('Style: ' if getattr(self, 'mock', False) else '') +
                            'cue must be 2-3 fluent sentences')
        if cue_id == self.pause_rows[0]['id'] and (re.search(r'\bonly\b.{0,50}\bvisible\b', text, re.I)
                                                   or re.search(r'\b(no one|nothing) else\b', text, re.I)):
            problems.append('unsupported global visibility claim from one establishing frame')
        problems += lint_with_hints(text)
        subtitles = [e.get('subtitle_text', '') for e in self.timeline if e.get('subtitle_text')]
        for quoted in re.findall(r'["“]([^"”]+)["”]', text):
            if any(quoted.lower() in s.lower() for s in subtitles):
                problems.append(f'reads a burned-in subtitle ("{quoted}")')
        cited = list(dict.fromkeys(entry.get('evidence', [])))
        valid = [e for e in cited if e in allowed]
        invalid = [e for e in cited if e not in allowed]
        known = {e['id']: e for e in self.timeline}
        future = [e for e in invalid if e in known and known[e]['t_end'] > pause['t'] + 1e-6]
        stale = [e for e in invalid if e in known and known[e]['t_end'] <= previous + 1e-6]
        unknown = [e for e in invalid if e not in known and e != f'frame-p{cue_id}']
        if future:
            problems.append('future event evidence outside this window: ' + ', '.join(future))
        if stale:
            problems.append('earlier event evidence outside this window: ' + ', '.join(stale))
        if unknown:
            problems.append('unknown evidence ids: ' + ', '.join(unknown))
        if not valid:
            problems.append('no cited evidence in (previous pause, this pause]')
        if accepted:
            prior_ids = [i for i in accepted if i < cue_id]
            previous_entry = accepted[max(prior_ids)] if prior_ids else None
            if previous_entry and similarity(text, previous_entry['text']) >= float(self.x['redundancy_previous']):
                problems.append('repeats or paraphrases the previous extended cue')
            duplicate = next((other for other in accepted.values() if other is not previous_entry and
                              similarity(text, other['text']) >= .65), None)
            if duplicate:
                problems.append('duplicate or redundant with another extended cue')
        return valid, problems

    @staticmethod
    def hard_problems(problems):
        return [p for p in problems if not p.startswith('Style:')]

    def repair(self, failed, round_no):
        payloads = []
        for cue_id, info in failed.items():
            pause = next(p for p in self.pause_rows if p['id'] == cue_id)
            index = next(i for i, p in enumerate(self.pause_rows) if p['id'] == cue_id)
            previous = self.pause_rows[index - 1]['t'] if index else 0.
            payloads.append({**self.pause_payload(pause, previous), 'rejected_text': info['entry']['text'],
                             'why_rejected': info['problems'], 'trusted_evidence': info['valid'],
                             'previous_extended_cues': [self.extended_cues[k]['text'] for k in sorted(self.extended_cues)
                                                       if k < cue_id and self.extended_cues[k].get('text')][-2:]})
        raw = self.model('extended_repair', 'edit', P.EXTENDED_REPAIR,
                         {'bible': self.bible, 'round': round_no, 'cues': payloads,
                          '_temperature': self.x['temperature']}, None,
                         self.mock_script(payloads) if self.mock else None, ultra=True)
        return parse_extended_cues(raw)

    def verify(self, entries):
        verdicts = {}
        ids = sorted(entries)
        for offset in range(0, len(ids), int(self.x['verify_batch'])):
            batch = ids[offset:offset + int(self.x['verify_batch'])]
            data = {'duration': 0, 'cues': [], '_temperature': self.x['verify_temperature']}
            media = []
            for cue_id in batch:
                t = next(p['t'] for p in self.pause_rows if p['id'] == cue_id)
                times = [round(max(0., t - .2), 3), round(min(max(0., self.duration - .001), t), 3)]
                data['cues'].append({'gap_id': cue_id, 'text': entries[cue_id]['text'], 'frame_times': times})
                if not self.mock:
                    media.append({'type': 'text', 'text': f'Frames for cue gap_id {cue_id}:'})
                    media += separate_frames(self.path, times)
            mock = {'verdicts': [{'gap_id': cue_id, 'verdict': 'supported', 'wrong': '', 'reason': ''} for cue_id in batch]}
            try:
                raw = self.model('verify', 'perceive', P.VERIFY, data, media or None, mock if self.mock else None)
                rows = raw.get('verdicts', []) if isinstance(raw, dict) else []
            except (BudgetExceeded, TimeoutError):
                raise
            except Exception as exc:
                self.report['issues'].append('Extended verification unavailable: ' + sanitize(exc))
                rows = []
            for row in rows:
                try:
                    cue_id = int(row.get('gap_id', row.get('id')))
                except (TypeError, ValueError, AttributeError):
                    continue
                verdict = str(row.get('verdict') or '').lower()
                if verdict not in ('supported', 'contradicted', 'uncertain'):
                    verdict = 'uncertain'
                verdicts[cue_id] = {'verdict': verdict, 'wrong': str(row.get('wrong') or '')[:160],
                                    'reason': str(row.get('reason') or '')[:240]}
        return verdicts

    def st_check_repair_verify(self):
        entries, accepted = dict(self.extended_cues), {}
        soft_tried, repair_round = set(), 0
        while entries:
            failed, ready = {}, {}
            for cue_id in sorted(entries):
                entry = entries[cue_id]
                earlier = {**accepted, **{k: v for k, v in entries.items() if k < cue_id}}
                valid, problems = self.cue_problems(cue_id, entry, earlier)
                self.log_ext(cue_id, step='check', text=entry['text'], evidence=entry['evidence'], problems=problems)
                hard = self.hard_problems(problems)
                if problems and (hard or cue_id not in soft_tried) and repair_round < int(self.x['max_repair_rounds']):
                    failed[cue_id] = {'entry': entry, 'valid': valid, 'problems': problems}
                    soft_tried.add(cue_id)
                elif hard:
                    self.ext_dropped[cue_id] = '; '.join(hard)
                else:
                    ready[cue_id] = {**entry, 'evidence': valid, 'soft_kept': bool(problems)}
            if failed:
                repair_round += 1
                replacements = self.repair(failed, repair_round)
                for cue_id, info in failed.items():
                    if cue_id in replacements:
                        entries[cue_id] = replacements[cue_id]
                        self.ext_candidates.setdefault(cue_id, []).append(replacements[cue_id])
                        self.log_ext(cue_id, step=f'repair_{repair_round}', text=replacements[cue_id]['text'])
                    else:
                        self.ext_dropped[cue_id] = 'repair returned no cue'
                        entries.pop(cue_id, None)
                # Ready cues can be verified now; failed cues loop through checks.
            verdicts = self.verify(ready) if ready else {}
            contradicted = {}
            for cue_id, entry in ready.items():
                verdict = verdicts.get(cue_id, {'verdict': 'uncertain', 'wrong': '', 'reason': 'no verdict'})
                self.log_ext(cue_id, step='verify', **verdict)
                risky = risky_text(entry['text'])
                if verdict['verdict'] == 'supported' or verdict['verdict'] == 'uncertain' and not risky:
                    accepted[cue_id] = {**entry, 'verification': verdict}
                    self.ext_dropped.pop(cue_id, None)
                    entries.pop(cue_id, None)
                elif repair_round < int(self.x['max_repair_rounds']):
                    reason = f"verifier {verdict['verdict']}: {verdict['reason']}"
                    if verdict['wrong']:
                        reason += f"; remove or correct only \"{verdict['wrong']}\""
                    contradicted[cue_id] = {'entry': entry, 'valid': entry['evidence'], 'problems': [reason]}
                else:
                    self.ext_dropped[cue_id] = f"verification {verdict['verdict']}: {verdict['reason']}"
                    entries.pop(cue_id, None)
            if contradicted:
                repair_round += 1
                replacements = self.repair(contradicted, repair_round)
                for cue_id in contradicted:
                    if cue_id in replacements:
                        entries[cue_id] = replacements[cue_id]
                        self.ext_candidates.setdefault(cue_id, []).append(replacements[cue_id])
                    else:
                        self.ext_dropped[cue_id] = 'verification repair returned no cue'
                        entries.pop(cue_id, None)
            if not failed and not contradicted and not ready:
                break
            if repair_round >= int(self.x['max_repair_rounds']) and not ready:
                # One final check/verify loop is still allowed for the last repair.
                continue
        self.extended_cues = accepted
        return f"{len(accepted)} verified extended cues; {len(self.ext_dropped)} dropped; {repair_round} repair rounds"

    def st_rescue_extended(self):
        """One model-written final retry for every planned pause still missing."""
        missing = [p['id'] for p in self.pause_rows if p['id'] not in self.extended_cues]
        if not missing or int(self.x['rescue_rounds']) <= 0:
            return f'{len(missing)} pauses still missing; rescue not needed or disabled'
        failed = {}
        for cue_id in missing:
            candidates = self.ext_candidates.get(cue_id, [])
            entry = candidates[-1] if candidates else {'text': '', 'evidence': []}
            failed[cue_id] = {'entry': entry, 'valid': [],
                              'problems': [self.ext_dropped.get(cue_id, 'missing cue'),
                                           'Coverage rescue: write this planned pause; do not skip it']}
            self.log_ext(cue_id, step='rescue_retry', reason=failed[cue_id]['problems'])
        replacements = self.repair(failed, int(self.x['max_repair_rounds']) + 1)
        ready = {}
        accepted_so_far = dict(self.extended_cues)
        for cue_id in missing:
            replacement = replacements.get(cue_id)
            if not replacement:
                self.ext_dropped[cue_id] = 'rescue returned no cue'
                continue
            self.ext_candidates.setdefault(cue_id, []).append(replacement)
            earlier = {k: v for k, v in accepted_so_far.items() if k < cue_id}
            valid, problems = self.cue_problems(cue_id, replacement, earlier)
            self.log_ext(cue_id, step='rescue_check', text=replacement['text'], problems=problems)
            if not self.hard_problems(problems):
                ready[cue_id] = {**replacement, 'evidence': valid, 'soft_kept': bool(problems)}
                accepted_so_far[cue_id] = ready[cue_id]
            else:
                self.ext_dropped[cue_id] = '; '.join(self.hard_problems(problems))
        verdicts = self.verify(ready) if ready else {}
        rescued = 0
        for cue_id, entry in ready.items():
            verdict = verdicts.get(cue_id, {'verdict': 'uncertain', 'wrong': '', 'reason': 'no verdict'})
            self.log_ext(cue_id, step='rescue_verify', **verdict)
            if verdict['verdict'] == 'supported' or verdict['verdict'] == 'uncertain' and not risky_text(entry['text']):
                self.extended_cues[cue_id] = {**entry, 'verification': verdict, 'rescued': True}
                self.ext_dropped.pop(cue_id, None)
                rescued += 1
            elif verdict['wrong']:
                struck = self.strike_extended(cue_id, entry, verdict['wrong'])
                earlier = {k: v for k, v in self.extended_cues.items() if k < cue_id}
                valid, problems = self.cue_problems(cue_id, struck, earlier) if struck else ([], ['strike failed'])
                self.log_ext(cue_id, step='rescue_strike_check',
                             text=struck['text'] if struck else '', problems=problems)
                if struck and not self.hard_problems(problems):
                    struck = {**struck, 'evidence': valid, 'soft_kept': bool(problems)}
                    second = self.verify({cue_id: struck}).get(
                        cue_id, {'verdict': 'uncertain', 'wrong': '', 'reason': 'no strike verdict'})
                    self.log_ext(cue_id, step='rescue_strike_verify', **second)
                    if second['verdict'] == 'supported' or second['verdict'] == 'uncertain' and not risky_text(struck['text']):
                        self.extended_cues[cue_id] = {**struck, 'verification': second,
                                                       'rescued': True, 'struck': True}
                        self.ext_dropped.pop(cue_id, None)
                        rescued += 1
                        continue
                self.ext_dropped[cue_id] = f"rescue verification {verdict['verdict']}: {verdict['reason']}"
            else:
                self.ext_dropped[cue_id] = f"rescue verification {verdict['verdict']}: {verdict['reason']}"
        return f'{rescued} of {len(missing)} missing planned pauses rescued with model-written text'

    def strike_extended(self, cue_id, entry, wrong):
        """Ask Nano to remove one verifier-quoted detail; never author replacement prose."""
        text = entry['text']
        mock_text = normalise_en(text.replace(wrong, '').replace('  ', ' '))
        raw = self.model('extended_strike', 'fit', P.STRIKE,
                         {'cue': {'gap_id': cue_id, 'text': text, 'wrong': wrong,
                                  'max_words': int(self.x['max_words']), 'keep_place': []},
                          '_temperature': self.x['temperature']}, None,
                         {'text': mock_text, 'words': len(mock_text.split())} if self.mock else None)
        replacement = raw.get('text') if isinstance(raw, dict) else None
        if not isinstance(replacement, str) or not replacement.strip():
            return None
        replacement = normalise_en(replacement)
        if wrong.lower() in replacement.lower() or len(replacement.split()) >= len(text.split()):
            return None
        return {'text': replacement, 'evidence': list(entry.get('evidence', []))}

    def st_render_extended(self):
        missing = [p['id'] for p in self.pause_rows if p['id'] not in self.extended_cues]
        described = [p['t'] for p in self.pause_rows if p['id'] in self.extended_cues]
        points = [0.] + described + [self.duration]
        largest_gap = max((b - a for a, b in zip(points, points[1:])), default=self.duration)
        self.report['extended_coverage'] = {'planned': len(self.pause_rows),
                                            'described': len(described),
                                            'largest_source_gap_s': round(largest_gap, 3),
                                            'max_source_gap_s': self.x['max_coverage_gap_s'],
                                            'missing_pause_ids': missing}
        if missing or largest_gap > float(self.x['max_coverage_gap_s']) + 1e-6:
            raise RuntimeError('extended coverage guarantee failed after model rescue: '
                               f'missing pauses {missing}; largest source gap {largest_gap:.2f} s')
        narration_files, measured = {}, {}
        for cue_id, entry in sorted(self.extended_cues.items()):
            target = self.work / f'extended-en-p{cue_id}.wav'
            self.engine.render(entry['text'], 'en', target)
            seconds, _ = probe(target)
            narration_files[str(cue_id)] = target
            measured[cue_id] = seconds
        pauses = [{**p, 'cue_id': p['id'], 'narration_seconds': measured[p['id']]}
                  for p in self.pause_rows if p['id'] in self.extended_cues]
        timeline = build_extended_timeline(self.duration, pauses, self.speech,
                                           self.x['pad_before_s'], self.x['pad_after_s'])
        render_extended(self.path, self.out / 'extended_en.mp4', self.out / 'extended_en.m4a', timeline,
                        narration_files)
        by_id = {str(p['cue_id']): p for p in timeline.pauses}
        cues, plan = [], []
        for pause in self.pause_rows:
            cue_id = pause['id']
            if cue_id not in self.extended_cues:
                continue
            timing = by_id[str(cue_id)]
            entry = self.extended_cues[cue_id]
            cues.append({'id': cue_id, 'source_t': pause['t'], 'out_start': timing['cue_start'],
                         'out_end': timing['cue_end'], 'text': entry['text']})
            plan.append({**pause, 'cue_id': cue_id, 'cue_text': entry['text'],
                         'narration_seconds': round(timing['narration_seconds'], 3),
                         'freeze_seconds': round(timing['freeze_seconds'], 3),
                         'out_start': timing['out_start'], 'out_end': timing['out_end'],
                         'cue_out_start': timing['cue_start'], 'cue_out_end': timing['cue_end'],
                         'verification': entry['verification']})
        write_extended_texts(self.out, cues)
        (self.out / 'pause_plan.json').write_text(json.dumps({'source_duration': self.duration,
                    'output_duration': timeline.total_duration, 'speech_intervals': self.speech,
                    'pad_before': self.x['pad_before_s'], 'pad_after': self.x['pad_after_s'],
                    'pauses': plan, 'segments': list(timeline)}, ensure_ascii=False, indent=2), encoding='utf-8')
        self.report.update(status='complete', cues=cues, pauses=plan, speech=self.speech,
                           cues_committed=len(cues), cues_dropped=len(self.ext_dropped), dropped_cues=self.ext_dropped,
                           overlaps_with_speech=0, total_added_seconds=round(timeline.total_duration - self.duration, 3),
                           output_duration_s=timeline.total_duration,
                           extended_stats={'pauses': len(plan), 'total_added_seconds': round(timeline.total_duration-self.duration, 3),
                                           'overlaps_with_speech': 0})
        return f"{len(plan)} freezes rendered; +{timeline.total_duration-self.duration:.2f} seconds"

    def save_extended(self):
        self.report.update(bible=self.bible, timeline=self.timeline, shots=self.shots,
                           stages=self.stage_log, cue_history=self.ext_history,
                           director_stats={'ultra_calls': self.ultra_calls, 'max_ultra_calls': self.d['max_ultra_calls']})
        Agent.save(self)
        source = self.client.usage or [{'cost_role': s.get('cost_role'), 'cost_usd': s.get('cost_usd', 0.)}
                                       for s in self.steps if s.get('model')]
        roles = sorted({str(row.get('cost_role') or row.get('stage') or 'unknown') for row in source})
        self.report['cost_by_role'] = {role: sum(row.get('cost_usd', 0.) for row in source
                                                 if str(row.get('cost_role') or row.get('stage') or 'unknown') == role)
                                       for role in roles}
        report_path = self.out / 'report.json'
        report_path.write_text(json.dumps(self.report, ensure_ascii=False, indent=2), encoding='utf-8')
        trace_path = self.out / 'trace.json'
        trace = json.loads(trace_path.read_text())
        trace['metadata'].update(mode='director', ad_mode='extended')
        trace['stages'] = self.stage_log
        trace_path.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding='utf-8')

    def run(self):
        stop = None
        try:
            self.preflight_tts()
            self.stage('speech', self.detect_extended_speech, 'Silero VAD speech intervals')
            self.stage('shots', self.st_shots, 'ffmpeg scene cuts')
            self.stage('scene', self.st_scene, 'Super VL scene context')
            self.stage('timeline', self.st_timeline, 'Super VL whole-clip windows')
            self.stage('bible', self.st_bible, 'Ultra scene/story bible')
            self.stage('pause_plan', self.st_plan_pauses, 'cuts + speech ends + key events + story beats')
            self.stage('pause_frames', self.st_pause_frames, 'Super VL current frames at pauses')
            self.stage('extended_write', self.st_write, 'one Ultra call for every pause')
            self.stage('extended_check_verify', self.st_check_repair_verify, 'Round 7 hard/soft checks and still verification')
            self.stage('extended_rescue', self.st_rescue_extended, 'retry every dropped planned pause before rendering')
            self.stage('render', self.st_render_extended, 'freeze video, silence programme audio, mix narration')
        except (BudgetExceeded, UltraCapReached, TimeoutError) as exc:
            stop = str(exc)
        except Exception as exc:
            stop = 'extended director stopped: ' + sanitize(exc)
        if stop:
            self.report.update(status='failed', stopped_reason=stop)
            self.report['issues'].append(stop)
        self.save_extended()
        return self.report


def run_extended_director(path, out_dir, provider=None, langs=('en',), budget_usd=None,
                          on_step=None, *, config=None, client=None, context=None):
    cfg = resolve_provider(config or load_config(), provider)
    if client is None and cfg['provider'] != 'mock' and not os.environ.get(cfg['key_env']):
        raise RuntimeError(f"Provider '{cfg['provider']}' needs env {cfg['key_env']}; use provider='mock' offline")
    if isinstance(langs, str):
        langs = [x for x in langs.split(',') if x]
    if any(lang != 'en' for lang in langs):
        import warnings
        warnings.warn('Extended AD is English-only; running en only.', RuntimeWarning)
    cap = (cfg.get('extended') or {}).get('budget_usd', DEFAULTS['budget_usd']) if budget_usd is None else budget_usd
    return ExtendedDirector(path, out_dir, cfg, SpendGuard(cap), on_step, client, context).run()
