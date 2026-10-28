"""Narrate v2 "director" mode (DESIGN_v2.md).

Cheap models look at the WHOLE clip (shot cuts + Super VL timeline windows), Ultra writes a scene bible and then the whole
English track in one call, deterministic checks and Super VL stills verify every cue, Nano tightens cues that are only over
budget, Ultra repairs only lint/evidence/verification failures (<= 2 rounds; anything still failing is dropped), and Ultra
writes the Hindi track natively. Bounded: <= 6 Ultra calls.

It reuses the agent's infrastructure (Agent: VAD gaps/slots, scene pass, TTS measurement/check_fit, render, report/trace
saving) so outputs stay compatible with app/app.py and scripts/build_cached_runs.py. All mock execution is offline."""
import json
import math
import os
import re
import time
from collections import Counter
from .agent.core import Agent, absolute_times, lint_with_hints, is_skip, similarity, tokens, risky_text, scene_brief
from .config import load_config, resolve_provider
from .llm import SpendGuard, BudgetExceeded, sanitize
from .media import ffmpeg, scene_cuts, split_slots, write_texts, word_budget
from .perception import data_url, separate_frames
from . import director_prompts as P

DEFAULTS = {
    'window_s': 12, 'window_snap_s': 2, 'window_fps': 4, 'window_fallback_frames': 4,
    'ultra_stage': 'edit', 'bible_stage': 'edit', 'tighten_stage': 'fit', 'max_ultra_calls': 6, 'budget_usd': .15,
    'min_words': 4, 'target_fill': .7, 'target_fill_max': .9, 'similarity_prev': .5, 'similarity_any': .8,
    'narrator_wps_en': 2.6, 'word_tolerance': .15, 'tighten_attempts': 2, 'tighten_max_tokens': 160, 'coverage_target': .75,
    'verify_batch': 4, 'verify_frames': 2, 'max_repair_rounds': 2,
    'accept_uncertain': True, 'require_verification': True, 'calibrate_tts': True,
}
STOP = {'a', 'an', 'the', 'and', 'of', 'to', 'in', 'on', 'with', 'into', 'at', 'is', 'are', 'it', 'its', 'her', 'his', 'their', 'then', 'as', 'by', 'from'}
DIRECTOR_LINT = [
    (re.compile(r'(?:^|[.!?]\s+|,\s+)(?:a|the|one)?\s*person\b', re.I), 'generic "Person" opener or subject. Fix: use the cast descriptor or a pronoun'),
    (re.compile(r'\bcontinu(?:e|es|ing)\b', re.I), '"continues". Fix: say what is new or changed (the result, the next step), or skip the gap'),
    (re.compile(r'\b(?:in|on) (?:the|this|that) (?:shot|frame|footage)\b|\bscreen shows\b|\b(?:is|are) filmed\b|\bclose-up\b', re.I),
     'film-making jargon. Fix: describe what is visible and what the people do, e.g. "a crewmate photographs the pepper"'),
    (re.compile(r';'), 'headline fragments (";"). Fix: write one or two complete sentences with a subject; join actions with "and" or "then"'),
    # "Cuts dough...", "Gestures to bowl", "Flattens a ball": a verb with no subject (telegraphic headline style).
    (re.compile(r'^\s*[A-Z][a-z]+s\s+(?:a|an|the|his|her|their|its|each|it|them|to|into|onto|on|over|with|up|down|off|out|back)\b'),
     'no subject (headline style). Fix: start with who acts, e.g. "The cook flattens...", "She rolls..."'),
]
# Setting words too generic to establish WHERE a video takes place.
GENERIC_PLACE = {'crowded', 'bright', 'brightly', 'small', 'large', 'big', 'white', 'black', 'blue', 'wooden', 'lit', 'indoor', 'indoors',
                 'outdoor', 'room', 'area', 'space', 'inside', 'interior', 'modern', 'clean', 'busy', 'narrow', 'wide', 'dimly', 'well'}
BUDGET_PROBLEMS = ('over budget', 'Word budget exceeded', 'TTS duration exceeds', 'cue too long')
PLACE_PROBLEM = 'establishing cue does not say where'


class UltraCapReached(RuntimeError):
    pass


def content_tokens(text):
    return tokens(text) - STOP


def looks_like_subtitle(text, burned=False):
    """Burned-in subtitles transcribe speech: lower-case fragments ("to 35 minutes", "and add it") or, when the scene
    pass saw subtitles, sentence-like lines. Titles, labels and signs are short and capitalised."""
    t = str(text or '').strip().strip('"\'“”')
    if not t:
        return False
    if t[0].islower():
        return True
    words = t.split()
    return bool(burned and len(words) >= 4 and ':' not in t and not t.isupper() and sum(w[0].isupper() for w in words) <= 1)


def stem(word):
    return word[:-1] if len(word) > 3 and word.endswith('s') and not word.endswith('ss') else word


def place_terms(bible):
    """Words that name WHERE the video is: any content word of the bible's `place` or `setting` ("space station module",
    "a home kitchen with a white table" -> station, module, home, kitchen, table), minus generic adjectives. The establishing
    cue must contain one of them. Deliberately lenient: a missing place never drops the establishing cue (establish_fallback)."""
    return {stem(w) for w in content_tokens(str(bible.get('place') or '') + ' ' + str(bible.get('setting') or '')) if not w.isdigit()} - GENERIC_PLACE


def clean_context(text, limit=200):
    """Optional user title/one-line description (UNVERIFIED context; never evidence)."""
    text = ' '.join(str(text or '').split())
    return text[:limit] or None


def normalise_events(raw, start, end, duration, burned=False):
    """Validate one window's VL answer into events with ABSOLUTE times inside [start, end].

    Accepts {"events": [...]} or a bare list, the keys what/action/event/description and start/end, and segment-relative
    times (shifted by absolute_times). Subtitle-like on-screen text is demoted to subtitle_text. Returns (events, time_base)."""
    items = raw.get('events', []) if isinstance(raw, dict) else raw if isinstance(raw, list) else []
    items = [dict(e) for e in items if isinstance(e, dict)]
    for e in items:
        for a, b in (('start', 't_start'), ('end', 't_end')):
            if b not in e and a in e:
                e[b] = e[a]
    items, base = absolute_times(items, start, end)
    out = []
    for e in items:
        try:
            s, t = float(e['t_start']), float(e['t_end'])
        except (KeyError, TypeError, ValueError):
            continue
        if not (math.isfinite(s) and math.isfinite(t)) or t <= start - .5 or s >= end + .5:
            continue
        s, t = max(start, 0., s), min(end, duration, t)
        if t - s < .05:
            continue
        what = next((e[k] for k in ('what', 'action', 'event', 'description', 'text') if isinstance(e.get(k), str) and e[k].strip()), '')
        if not what:
            continue
        try:
            importance = int(max(1, min(5, round(float(e.get('importance', 3))))))
        except (TypeError, ValueError):
            importance = 3
        try:
            confidence = max(0., min(1., float(e.get('confidence', .7))))
        except (TypeError, ValueError):
            confidence = .7
        ost = ' '.join(str(e.get('on_screen_text') or '').split())
        sub = ' '.join(str(e.get('subtitle_text') or '').split())
        if ost and looks_like_subtitle(ost, burned):
            sub, ost = sub or ost, ''
        change = e.get('change') if isinstance(e.get('change'), str) else ''
        ev = {'t_start': round(s, 3), 't_end': round(t, 3), 'what': ' '.join(what.split())[:240], 'on_screen_text': ost[:120],
              'subtitle_text': sub[:160], 'importance': importance, 'confidence': confidence}
        if change.strip():
            ev['change'] = ' '.join(change.split())[:160]
        if isinstance(e.get('hi'), str):
            ev['hi'] = e['hi']   # mock sidecar only
        out.append(ev)
    return out, base


def assign_events(events, gaps):
    """event id -> [gap ids], home gap first (P0-3).

    Home: the gap containing the event midpoint, else a gap overlapping >= 50 % of the event. A long, ongoing event is
    also evidence for any other gap it covers >= 50 % of. An event that only brushes a gap edge is never assigned there,
    and an event with no gap is 'in speech' (story context only, never evidence). Refuted events are never assigned."""
    out = {}
    for e in events:
        if e.get('refuted'):
            continue
        s, t = float(e['t_start']), float(e['t_end'])
        mid, length = (s + t) / 2, max(t - s, 1e-6)
        overlap = lambda g: max(0., min(t, g['end']) - max(s, g['start']))
        home = next((g['id'] for g in gaps if g['start'] <= mid <= g['end']), None)
        if home is None:
            best = max(gaps, key=overlap, default=None)
            if best is not None and overlap(best) >= .5 * length:
                home = best['id']
        ids = ([home] if home is not None else []) + [g['id'] for g in gaps if g['id'] != home and overlap(g) >= .5 * max(g['end'] - g['start'], 1e-6)]
        if ids:
            out[e['id']] = ids
    return out


def clean_bible(raw, fallback):
    raw = raw if isinstance(raw, dict) else {}
    short = lambda v, n: ' '.join(str(v).split())[:n] if isinstance(v, (str, int, float)) and not isinstance(v, bool) else ''
    num = lambda v: round(float(v), 2) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else 0.
    def items(key):
        v = raw.get(key, [])
        return v if isinstance(v, list) else []
    cast = [{'id': short(c.get('id') or f'c{i+1}', 8), 'descriptor': short(c.get('descriptor'), 60), 'first_seen': num(c.get('first_seen')),
             'notes': short(c.get('notes', ''), 140)} for i, c in enumerate(items('cast')[:6]) if isinstance(c, dict) and short(c.get('descriptor'), 60)]
    bible = {'setting': short(raw.get('setting', ''), 160), 'place': short(raw.get('place', ''), 40), 'cast': cast,
             'objects': list(dict.fromkeys(x for x in (short(o, 40) for o in items('objects')[:15]) if x)),
             'goal': short(raw.get('goal', ''), 80), 'story': short(raw.get('story', ''), 240),
             'beats': [{'t': num(b.get('t')), 'beat': short(b.get('beat'), 120)} for b in items('beats')[:12] if isinstance(b, dict) and short(b.get('beat'), 120)],
             'on_screen_text': [{'t': num(x.get('t')), 'text': short(x.get('text'), 120), 'kind': short(x.get('kind', 'title'), 10)}
                                for x in items('on_screen_text')[:10] if isinstance(x, dict) and short(x.get('text'), 120)],
             'subtitles_present': raw.get('subtitles_present') in (True, 'true', 'yes', 1), 'tone': short(raw.get('tone', ''), 60)}
    for k in ('setting', 'place', 'story', 'cast', 'objects'):
        if not bible[k]:
            bible[k] = fallback.get(k, bible[k])
    bible['subtitles_present'] = bible['subtitles_present'] or fallback.get('subtitles_present', False)
    bible['source'] = 'model' if raw else 'fallback'
    return bible


def parse_cues(response):
    """{"cues":[...]} -> {gap_id: {'text','evidence','skip','reason'}} tolerating id/evidence_ids/bare lists."""
    items = response.get('cues', []) if isinstance(response, dict) else response if isinstance(response, list) else []
    out = {}
    for c in items:
        if not isinstance(c, dict):
            continue
        gid = c.get('gap_id', c.get('id'))
        try:
            gid = int(gid)
        except (TypeError, ValueError):
            continue
        text = c.get('text') if isinstance(c.get('text'), str) else ''
        ev = c.get('evidence', c.get('evidence_ids', []))
        ev = [str(x) for x in (ev if isinstance(ev, list) else [ev]) if isinstance(x, (str, int))]
        skip = c.get('skip') in (True, 'true', 'yes', 1) or is_skip(text) or not text.strip() and bool(c.get('reason'))
        out[gid] = {'text': ' '.join(text.split()), 'evidence': ev, 'skip': skip, 'reason': str(c.get('reason') or '')[:160]}
        words = c.get('words')
        if isinstance(words, (int, float)) and not isinstance(words, bool):
            out[gid]['words_claimed'] = int(words)   # the writer's self-count; the post-check counts anyway
    return out


def parse_tightened(response, gid):
    """Nano's one shorter version: {"text"}, a bare {"gap_id","text"} object or {"cues":[...]} (round 2 saw the bare object
    and dropped it as unanswered)."""
    if isinstance(response, dict) and isinstance(response.get('text'), str) and str(response.get('gap_id', gid)) == str(gid):
        return ' '.join(response['text'].split())
    entry = parse_cues(response).get(gid)
    return entry['text'] if entry and not entry['skip'] else ''


def parse_srt(path):
    """[(start, end, text)] from a simple .srt sidecar (speech context only; never narrated)."""
    rows = []
    stamp = r'(\d+):(\d+):(\d+)[,.](\d+)'
    for block in re.split(r'\n\s*\n', path.read_text(encoding='utf-8', errors='replace')):
        m = re.search(stamp + r'\s*-->\s*' + stamp, block)
        if not m:
            continue
        v = [int(x) for x in m.groups()]
        s, e = v[0]*3600+v[1]*60+v[2]+v[3]/1000, v[4]*3600+v[5]*60+v[6]+v[7]/1000
        text = ' '.join(block[m.end():].split())
        if text:
            rows.append((s, e, text))
    return rows


class Director(Agent):
    def __init__(self, path, out, cfg, langs, guard, on_step=None, client=None, context=None):
        super().__init__(path, out, cfg, langs, guard, on_step, client)
        self.d = {**DEFAULTS, **(cfg.get('director') or {})}
        self.context = clean_context(context)
        self.timeline, self.shots, self.windows, self.bible = [], [], [], {}
        self.assignment, self.pending, self.failed, self.history = {}, {}, {}, {}
        self.establish_candidates = {}
        self.stage_log, self.ultra_calls, self.call_role, self.wps = [], 0, None, {}
        self.stats = Counter()
        self.speech_text = []
        self.report.update(mode='director', video_title=self.context)
        srt = self.path.with_suffix('.en.srt')
        if srt.is_file():
            try:
                self.speech_text = parse_srt(srt)
            except OSError:
                pass

    # ---------- plumbing ----------
    def trace(self, role, **kw):
        if role == 'submodel' and self.call_role:
            role = self.call_role
        return super().trace(role, **kw)

    def model(self, cost_role, stage, system, data, media=None, mock=None, ultra=False):
        if ultra:
            if self.ultra_calls >= self.d['max_ultra_calls']:
                raise UltraCapReached(f"Ultra call cap ({self.d['max_ultra_calls']}) reached")
            self.ultra_calls += 1
        self.cost_role, self.call_role = cost_role, 'orchestrator' if ultra else None
        try:
            return self.submodel(stage, data, media, mock, system=system)
        finally:
            self.cost_role = self.call_role = None

    def stage(self, name, fn, inputs=''):
        """Run one pipeline stage; record model ids, calls, tokens, cost, latency and in/out summaries."""
        first, t0, ok, output = len(self.steps), time.monotonic(), True, ''
        try:
            output = fn() or ''
            return output
        except Exception as exc:
            ok, output = False, 'failed: ' + ('budget exceeded' if isinstance(exc, BudgetExceeded) else str(exc)[:160] if isinstance(exc, UltraCapReached) else sanitize(exc))
            raise
        finally:
            calls = [s for s in self.steps[first:] if s.get('model')]
            rec = {'stage': name, 'ok': ok, 'models': sorted({s['model'] for s in calls}), 'calls': len(calls),
                   'ultra_calls': sum(s['role'] == 'orchestrator' for s in calls),
                   'tokens_in': sum(s.get('tokens_in', 0) for s in calls), 'tokens_out': sum(s.get('tokens_out', 0) for s in calls),
                   'cost_usd': sum(s.get('cost_usd', 0) for s in calls), 'latency_s': round(time.monotonic() - t0, 3),
                   'input': inputs[:300], 'output': str(output)[:400]}
            self.stage_log.append(rec)
            self.trace('tool', tool_name='stage:' + name, note=f'{name}: {str(output)[:200]}', ok=ok,
                       result={k: rec[k] for k in ('models', 'calls', 'tokens_in', 'tokens_out', 'cost_usd')}, latency_s=rec['latency_s'])

    def event(self, eid):
        return next((e for e in self.timeline if e['id'] == eid), None)

    def live_events(self):
        return [e for e in self.timeline if not e.get('refuted')]

    def narratable(self):
        return [g for g in self.gaps if g.get('narratable', True)]

    def scriptable(self):
        return [g for g in self.narratable() if g.get('director_words_en', 0) >= self.d['min_words'] and g['id'] not in self.dropped]

    # ---------- stage: gaps + measured budgets ----------
    def calibrate(self):
        for lang in ('en', 'hi'):
            configured = self.cfg['words_per_second'][lang]
            wps = configured
            if self.d['calibrate_tts']:
                try:
                    text = P.CALIBRATION[lang]
                    wps = len(text.split()) / max(.1, self.measure_tts_duration(text, lang)['seconds'])
                    wps = max(.5 * configured, min(2 * configured, wps))
                except Exception as exc:
                    self.report['issues'].append(f'TTS calibration ({lang}) unavailable: {sanitize(exc)}')
            self.wps[lang] = round(wps, 3)
        self.report['tts_wps_measured'] = dict(self.wps)

    def budget_wps(self, lang):
        """Speaking rate the word budgets assume. English: a natural human narrator (director.narrator_wps_en, 2.6 words/s;
        the demo ElevenLabs narrator speaks ~2.6-2.8), never faster than the measured pipeline voice (espeak measures ~3.7,
        so 2.6 applies). Hindi: the measured Hindi voice, capped by the config budget as before."""
        return min(self.d['narrator_wps_en'], self.wps['en']) if lang == 'en' else self.wps[lang]

    def budget(self, g, lang):
        """max_words = floor(cue_cap * budget_wps) - word_margin. English is no longer capped by config words_per_second
        (2.3, the legacy agent's estimate): fit is judged by measured seconds (check_fit)."""
        n = math.floor(self.cue_cap(g) * self.budget_wps(lang)) - self.cfg['word_margin']
        return max(0, n if lang == 'en' else min(n, self.max_words(g, lang)))

    def hard_words(self, g):
        """Words a cue may use when its measured TTS still fits: max_words + director.word_tolerance (15 %)."""
        return math.floor(g['director_words_en'] * (1 + self.d['word_tolerance']) + 1e-9)

    def allowed_seconds(self, g):
        """Seconds one English cue may speak: the single-cue cap with up to agent.max_atempo speed-up."""
        return round(self.cue_cap(g) * self.cfg['agent']['max_atempo'], 2)

    def check_fit(self, gap_id, text, lang):
        """Director English fit is judged in SECONDS: the measured TTS must fit allowed_seconds and the text may exceed
        max_words by <= word_tolerance. The agent's config-rate word checks (2.3 words/s) do not apply here."""
        fit = super().check_fit(gap_id, text, lang)
        g = self.gap(gap_id)
        if lang != 'en' or 'director_words_en' not in g or not g.get('narratable', True):
            return fit
        problems = [p for p in fit['problems'] if not p.startswith(('Word budget exceeded', 'cue too long'))]
        allowed, words = self.allowed_seconds(g), len(text.split())
        if fit['seconds'] > allowed and not any(p.startswith('TTS duration exceeds') for p in problems):
            problems.append(f"cue too long: measured {fit['seconds']:.1f} s, allowed {allowed:.1f} s")
        if words > self.hard_words(g):
            problems.append(f"over budget: {words} words, max {g['director_words_en']}")
        suggested = min(g['director_words_en'], max(1, int(words * allowed / max(fit['seconds'], .001))))
        return {**fit, 'ok': not problems, 'problems': problems, 'suggested_max_words': suggested}

    def st_gaps(self):
        wanted = self.cfg['agent'].get('scene_context', True)
        self.cfg['agent']['scene_context'] = False
        try:
            self.detect_speech_gaps()
        finally:
            self.cfg['agent']['scene_context'] = wanted
        self.calibrate()
        for g in self.narratable():
            g['director_words_en'], g['director_words_hi'] = self.budget(g, 'en'), self.budget(g, 'hi')
            if g['director_words_en'] < self.d['min_words']:
                self.drop_gap(g['id'], f"too short for a useful cue (< {self.d['min_words']} words)")
        n = self.narratable()
        return (f"{len(n)} narratable slots of {len(self.gaps)}, {len(self.scriptable())} long enough; detector {self.report.get('detector')}; "
                f"speech {100*self.report.get('speech_ratio', 0):.0f}%; measured voice wps en {self.wps['en']} hi {self.wps['hi']}; "
                f"English budgets at {self.budget_wps('en')} words/s (natural narrator), fit judged by measured seconds")

    # ---------- stage: shots + scene + timeline ----------
    def st_shots(self):
        self.shots = scene_cuts(self.path)
        self.windows = split_slots(0., self.duration, self.d['window_s'], self.shots, self.d['window_snap_s'], min(8., self.d['window_s'] / 2))
        return (f'{len(self.shots)} shot cuts; {len(self.windows)} perception windows of ~{self.d["window_s"]} s ' + ', '.join(f'{s:.0f}-{e:.0f}s' for s, e in self.windows)
                + f'; est. Super VL timeline cost ${self.window_cost_estimate():.4f} (upper bound from config prices)')

    def window_cost_estimate(self):
        """Rough timeline cost from config prices: video tokens + ~1.2 k prompt tokens in, ~350 tokens out per window."""
        price = self.cfg.get('prices', {}).get('perceive', {})
        tokens_in = sum((e - s) * self.cfg.get('video_tokens_per_second', 600) * self.d['window_fps'] / 4 + 1200 for s, e in self.windows)
        return (tokens_in * price.get('input_price', 0) + 350 * len(self.windows) * price.get('output_price', 0)) / 1e6

    def st_scene(self):
        ctx = self.establish_scene()
        return scene_brief(ctx, 300) or 'scene pass unavailable'

    def perceive_window(self, i, start, end, previous=()):
        burned = bool((self.scene_context or {}).get('burned_in_subtitles'))
        data = {'window': [round(start, 2), round(end, 2)], 'duration': round(end - start, 2),
                **({'scene_context': scene_brief(self.scene_context)} if scene_brief(self.scene_context) else {}),
                **({'previous_events': [{'t': [round(e['t_start'], 1), round(e['t_end'], 1)], 'what': e['what']} for e in previous]} if previous else {})}
        fmt = dict(start=start, end=end, duration=self.duration)
        mock = {'events': self.mock_events(start, end)} if self.mock else None
        modality = 'mock' if self.mock else 'video'
        if self.mock:
            raw = self.model('timeline', 'perceive', P.TIMELINE.format(**fmt), data, None, mock)
        else:
            try:
                clip = self.work / f'window_{i}.mp4'
                ffmpeg('-ss', start, '-i', self.path, '-t', end - start, '-an', '-vf', f"scale=-2:360,fps={self.d['window_fps']}",
                       '-c:v', 'libx264', '-crf', 30, clip)
                raw = self.model('timeline', 'perceive', P.TIMELINE.format(**fmt), data, [{'type': 'video_url', 'video_url': {'url': data_url(clip.read_bytes(), 'video/mp4')}}])
                if not normalise_events(raw, start, end, self.duration, burned)[0]:
                    raise ValueError('no events')
            except (BudgetExceeded, TimeoutError):
                raise
            except Exception:
                modality = 'frames'
                n = max(2, int(self.d['window_fallback_frames']))
                times = [round(start + (end - start) * (k + .5) / n, 2) for k in range(n)]
                raw = self.model('timeline', 'perceive', P.TIMELINE_FRAMES.format(**fmt), {**data, 'duration': 0, 'timestamps': times}, separate_frames(self.path, times))
        events, base = normalise_events(raw, start, end, self.duration, burned)
        return events, base, modality

    def st_timeline(self):
        merged, notes = [], Counter()
        for i, (s, e) in enumerate(self.windows):
            try:
                events, base, modality = self.perceive_window(i, s, e, [x for x in merged if x['t_end'] <= s + .5][-2:])
            except (BudgetExceeded, TimeoutError):
                raise
            except Exception as exc:
                self.report['issues'].append(f'Timeline window {s:.0f}-{e:.0f}s unavailable: {sanitize(exc)}')
                notes['failed'] += 1
                continue
            notes[modality] += 1
            notes[base] += 1
            for ev in events:
                # The same action seen from both sides of a window boundary becomes one event.
                same = next((x for x in merged if similarity(ev['what'], x['what']) >= .8 and ev['t_start'] <= x['t_end'] + .3 and ev['t_end'] >= x['t_start'] - .3), None)
                if same:
                    same['t_start'], same['t_end'] = min(same['t_start'], ev['t_start']), max(same['t_end'], ev['t_end'])
                    same['importance'], same['confidence'] = max(same['importance'], ev['importance']), max(same['confidence'], ev['confidence'])
                else:
                    merged.append(ev)
        merged.sort(key=lambda x: (x['t_start'], x['t_end']))
        self.timeline = [{'id': f'e{i+1}', **ev} for i, ev in enumerate(merged)]
        self.events = self.timeline   # the agent helpers (mock_line, coverage) read self.events
        subs = sum(bool(e['subtitle_text']) for e in self.timeline)
        return f"{len(self.timeline)} events from {len(self.windows)} windows ({dict(notes)}); {subs} with subtitles (speech, never read)"

    # ---------- stage: bible ----------
    def fallback_bible(self):
        ctx = self.scene_context or {}
        return {'setting': ctx.get('setting', ''), 'place': '', 'goal': ctx.get('dish', ''), 'cast': [{'id': f'c{i+1}', 'descriptor': p[:60], 'first_seen': 0., 'notes': ''} for i, p in enumerate(ctx.get('people', [])[:3])],
                'objects': (ctx.get('ingredients', []) + ctx.get('tools', []) + ctx.get('objects', []))[:15],
                'story': ctx.get('activity', ''), 'beats': [{'t': e['t_start'], 'beat': e['what'][:120]} for e in self.timeline if e['importance'] >= 4][:10],
                'on_screen_text': [{'t': e['t_start'], 'text': e['on_screen_text'], 'kind': 'title'} for e in self.timeline if e['on_screen_text']][:10],
                'subtitles_present': bool(ctx.get('burned_in_subtitles')) or any(e['subtitle_text'] for e in self.timeline), 'tone': ''}

    def timeline_rows(self, gap_of=None):
        rows = []
        for e in self.live_events():
            row = {'id': e['id'], 't': [round(e['t_start'], 1), round(e['t_end'], 1)], 'what': e['what'], 'importance': e['importance']}
            if e.get('change'):
                row['change'] = e['change']
            if e['on_screen_text']:
                row['on_screen_text'] = e['on_screen_text']
            if e['subtitle_text']:
                row['said'] = e['subtitle_text']
            if gap_of is not None:
                row['gap'] = gap_of.get(e['id']) or 'speech'
            rows.append(row)
        return rows

    def st_bible(self):
        fallback = self.fallback_bible()
        data = {'duration': 0, 'video_seconds': round(self.duration, 1), 'scene': self.scene_context or {}, 'shot_cuts': self.shots[:60],
                'timeline': self.timeline_rows(), **self.title_payload()}
        try:
            raw = self.model('bible', self.d['bible_stage'], P.BIBLE, data, None, fallback if self.mock else None, ultra=self.d['bible_stage'] in ('edit', 'orchestrate'))
        except (BudgetExceeded, TimeoutError):
            raise
        except Exception as exc:
            self.report['issues'].append('Scene bible unavailable; using the scene pass: ' + (str(exc) if isinstance(exc, UltraCapReached) else sanitize(exc)))
            raw = {}
        self.bible = clean_bible(raw, fallback)
        cast = ', '.join(c['descriptor'] for c in self.bible['cast']) or 'no recurring people'
        return (f"place: {self.bible['place']} | setting: {self.bible['setting']} | cast: {cast} | goal: {self.bible.get('goal') or '?'} | "
                f"story: {self.bible['story']} | {len(self.bible['beats'])} beats")

    def title_payload(self):
        return {'video_title': {'text': self.context, 'note': P.VIDEO_TITLE_NOTE}} if self.context else {}

    # ---------- stage: assignment ----------
    def st_assign(self):
        self.assignment = assign_events(self.timeline, self.scriptable())
        for e in self.timeline:
            e['gap_ids'] = self.assignment.get(e['id'], [])
        for g in self.scriptable():
            if not self.evidence_for(g['id']):
                self.skip_gap(g['id'], 'no events inside this gap')
        per = Counter(g for ids in self.assignment.values() for g in ids)
        return f"{len(self.assignment)} of {len(self.timeline)} events inside narratable gaps; {len(self.timeline)-len(self.assignment)} in speech (context only); per gap {dict(sorted(per.items()))}"

    def evidence_for(self, gid):
        return [e for e in self.live_events() if gid in self.assignment.get(e['id'], ())]

    def said_near(self, g, before=True, span=6.):
        lo, hi = (g['start'] - span, g['start'] + .2) if before else (g['end'] - .2, g['end'] + span)
        said = [e['subtitle_text'] for e in self.timeline if e['subtitle_text'] and e['t_end'] >= lo and e['t_start'] <= hi]
        said += [t for s, e, t in self.speech_text if e >= lo and s <= hi]
        return ' / '.join(dict.fromkeys(said))[:200]

    def target_words(self, g):
        """'lo-hi', about 70-90 % of max_words (told 70-100 %, the writer overshot max_words in round 2)."""
        m = g['director_words_en']
        lo = min(m, max(self.d['min_words'], math.ceil(self.d['target_fill'] * m)))
        hi = min(m, max(lo, math.floor(self.d['target_fill_max'] * m)))
        return f'{lo}-{hi}'

    def gap_payload(self, g, establish=None):
        return {'gap_id': g['id'], 'start': round(g['start'], 2), 'end': round(g['end'], 2), 'max_words': g['director_words_en'],
                'target_words': self.target_words(g), 'evidence': [e['id'] for e in self.evidence_for(g['id'])],
                **({'establish': True} if (self.is_establishing(g['id']) if establish is None else establish) else {}),
                **({'said_before': s} if (s := self.said_near(g, True)) else {}), **({'said_after': s} if (s := self.said_near(g, False)) else {})}

    # ---------- cue checks ----------
    def accepted_texts(self, exclude=None):
        rows = [(self.gap(gid)['start'], gid, c['en']) for gid, c in self.cues.items() if gid != exclude]
        rows += [(self.gap(gid)['start'], gid, p['text']) for gid, p in self.pending.items() if gid != exclude]
        return sorted(rows)

    def subtitles(self):
        return [e['subtitle_text'] for e in self.timeline if e['subtitle_text']] + [t for _, _, t in self.speech_text]

    def check_cue(self, gid, text, evidence):
        """Deterministic post-checks (DESIGN 2d). Returns (valid evidence ids, problems)."""
        g = self.gap(gid)
        problems = []
        words = len(text.split())
        if not text.strip():
            return [], ['empty cue']
        if '\n' in text or '-->' in text:
            problems.append('cue must be one line')
        if words > self.hard_words(g):   # up to word_tolerance over max_words is judged by measured seconds (check_fit)
            problems.append(f"over budget: {words} words, max {g['director_words_en']}. Fix: cut at least {words - g['director_words_en']} words "
                            '(keep the subject and the main action; drop a secondary action, colours or positions)')
        problems += lint_with_hints(text) + [f'Banned phrasing: {why}' for rx, why in DIRECTOR_LINT if rx.search(text)]
        place_problem = []
        if self.is_establishing(gid):
            terms = place_terms(self.bible)
            if terms and not {stem(w) for w in tokens(text)} & terms:
                place = self.bible.get('place') or re.sub(r'^\s*(?:a|an|the)\s+', '', re.split(r'\b(?:with|where|in|inside|of|on|at)\b|,', self.bible.get('setting', ''), maxsplit=1)[0]).strip()
                who = ((self.bible.get('cast') or [{}])[0].get('descriptor')) or 'who is there'
                place_problem.append(f'{PLACE_PROBLEM}. Fix: fold the place into a compact opening, e.g. "In the {place}, {who} ...", then the '
                                     f"action, all within {g['director_words_en']} words (drop a detail of the action rather than exceed it)")
        for quoted in re.findall(r'["“]([^"”]+)["”]', text):
            if any(quoted.lower().strip() in s.lower() or similarity(quoted, s) >= .6 for s in self.subtitles()):
                problems.append(f'reads a burned-in subtitle ("{quoted}"): subtitles are speech, never narrate them')
        known = {e['id']: e for e in self.timeline}
        valid = [i for i in dict.fromkeys(evidence) if i in known and not known[i].get('refuted') and gid in self.assignment.get(i, ())]
        outside = [i for i in dict.fromkeys(evidence) if i not in valid]
        if not valid:
            problems.append('no cited evidence inside this gap' + (f' (cited {outside}: refuted, unknown or from another time)' if outside else ''))
        elif outside:
            self.stats['evidence_stripped'] += len(outside)
        before = [r for r in self.accepted_texts(gid) if r[0] < g['start']]
        if before and similarity(text, before[-1][2]) >= self.d['similarity_prev']:
            problems.append(f'repeats the previous cue (gap {before[-1][1]}): say only what is new, or skip')
        dup = next((r for r in self.accepted_texts(gid) if similarity(text, r[2]) >= self.d['similarity_any']), None)
        if dup and not (before and dup == before[-1]):
            problems.append(f'duplicate of gap {dup[1]}')
        if not problems:
            fit = self.check_fit(gid, text, 'en')   # renders with the real TTS voice: measured seconds, speech overlap
            if not fit['ok']:
                problems += [p if 'measured' in p or ('exceeds' not in p and 'too long' not in p) else f"{p} (measured {fit['seconds']:.1f} s)" for p in fit['problems']]
        # Last, so a place-only failure means every other check (incl. the measured fit) passed: see establish_fallback.
        return valid, problems + place_problem

    def is_establishing(self, gid):
        """The first narrated cue: no earlier gap holds a pending, failed or committed cue."""
        start = self.gap(gid)['start']
        return not any(self.gap(g)['start'] < start for g in (*self.pending, *self.failed, *self.cues) if g != gid)

    def log(self, gid, **row):
        self.history.setdefault(gid, []).append(row)

    def skip_gap(self, gid, reason):
        self.skipped[gid] = True
        self.pending.pop(gid, None)
        self.failed.pop(gid, None)
        self.drop_gap(gid, 'silent: ' + reason)
        self.log(gid, step='skip', reason=reason)

    def consider(self, gid, entry, step):
        """Apply a script/repair entry to one gap: skip, pending (passes checks, awaits verification) or failed."""
        if entry['skip']:
            self.skip_gap(gid, entry['reason'] or 'writer: nothing new')
            return 'skip'
        valid, problems = self.check_cue(gid, entry['text'], entry['evidence'])
        words, claimed = len(entry['text'].split()), entry.get('words_claimed')
        self.log(gid, step=step, text=entry['text'], evidence=entry['evidence'], problems=problems, words=words,
                 **({'words_claimed': claimed} if claimed is not None else {}))
        if claimed is not None and claimed != words:
            self.stats['self_count_mismatch'] += 1
        if problems:
            self.failed[gid] = {'text': entry['text'], 'evidence': entry['evidence'], 'valid': valid, 'reasons': problems}
            # Keep model-written prose that misses only the lexical place check. A later repair may return skip, but Round 3
            # requires this otherwise-valid establishing cue to survive as the last-resort candidate.
            if valid and all(r.startswith(PLACE_PROBLEM) for r in problems):
                self.establish_candidates[gid] = {'text': entry['text'], 'evidence': valid}
            self.pending.pop(gid, None)
            self.stats['postcheck_failures'] += 1
            return 'failed'
        if words > self.gap(gid)['director_words_en']:
            self.stats['accepted_within_tolerance'] += 1   # <= word_tolerance over max_words and the measured TTS fits
        self.pending[gid] = {'text': entry['text'], 'evidence': valid}
        self.failed.pop(gid, None)
        return 'pending'

    # ---------- stage: script ----------
    def mock_script(self, gaps):
        cues = []
        for g in gaps:
            ev = sorted(self.evidence_for(g['gap_id']), key=lambda e: -e['importance'])
            if not ev:
                cues.append({'gap_id': g['gap_id'], 'skip': True, 'reason': 'MOCK: no evidence'})
                continue
            e = ev[0]
            text = f'On screen: "{e["on_screen_text"]}"' if e['on_screen_text'] else e['what']
            cues.append({'gap_id': g['gap_id'], 'text': ' '.join(text.split()[:g['max_words']]), 'evidence': [e['id']]})
        return {'cues': cues}

    def st_script(self):
        todo = sorted((g for g in self.scriptable() if g['id'] not in self.skipped), key=lambda g: g['start'])
        gaps = [self.gap_payload(g, establish=i == 0) for i, g in enumerate(todo)]
        if not gaps:
            return 'no gaps to script'
        data = {'bible': self.bible, **self.title_payload(), 'timeline': self.timeline_rows(self.assignment), 'gaps': gaps}
        parsed, error = None, None
        for attempt in range(2):
            try:
                parsed = parse_cues(self.model('script', self.d['ultra_stage'], P.SCRIPT, data, None, self.mock_script(gaps) if self.mock else None, ultra=True))
                if parsed:
                    break
                error = 'no cues in response'
            except (BudgetExceeded, TimeoutError, UltraCapReached):
                raise
            except Exception as exc:
                error = sanitize(exc)
        if not parsed:
            # Fallback: model-written timeline text (Super VL), trimmed; it still passes every check and verification.
            self.report['fallback_finalize'], self.report['fallback_reason'] = True, f'script call failed ({error}); used timeline text'
            parsed = parse_cues(self.mock_script(gaps))
        outcome = Counter()
        for g in sorted(gaps, key=lambda x: x['start']):
            entry = parsed.get(g['gap_id'])
            if entry is None:
                self.skip_gap(g['gap_id'], 'writer returned nothing for this gap')
                outcome['missing'] += 1
                continue
            outcome[self.consider(g['gap_id'], entry, 'script')] += 1
        return f"{len(gaps)} gaps scripted in one call: {dict(outcome)}" + (' (FALLBACK)' if self.report['fallback_finalize'] else '')

    # ---------- stage: tighten (Nano; before any Ultra repair) ----------
    def budget_only(self, gid):
        reasons = (self.failed.get(gid) or {}).get('reasons') or []
        return bool(reasons) and all(any(b in r for b in BUDGET_PROBLEMS) for r in reasons)

    def tighten_reject(self, gid, old, text):
        """Why a Nano rewrite is unusable (None if usable): not shorter, invents content, or loses the establishing place."""
        if not text:
            return 'no shorter version returned'
        if len(text.split()) >= len(old.split()):
            return f'not shorter ({len(text.split())} words, was {len(old.split())}); rejected'
        added = {stem(w) for w in content_tokens(text)} - {stem(w) for w in content_tokens(old)}
        if len(added) > 1:
            return f'tighten added new words {sorted(added)}; rejected'
        terms = place_terms(self.bible) if self.is_establishing(gid) else set()
        if terms & {stem(w) for w in tokens(old)} and not terms & {stem(w) for w in tokens(text)}:
            return 'tighten dropped the place from the establishing cue; rejected'
        return None

    def st_tighten(self, step):
        """Cues that fail ONLY on length go to Nemotron Nano first: ONE shorter version per call, given the cue's current word
        count and the exact max. Up to director.tighten_attempts calls per cue; a rewrite that is not shorter, adds content
        words or loses the establishing place is rejected. Small max_tokens: round 2 saw Nano run to the 2000-token cap after
        a bare JSON object (thinking was already off). Still over budget afterwards -> Ultra repair (verify_and_repair)."""
        outcome = Counter()
        for g in sorted((g for g in self.failed if self.budget_only(g)), key=lambda g: self.gap(g)['start']):
            max_w = self.gap(g)['director_words_en']
            for attempt in range(max(1, int(self.d['tighten_attempts']))):
                old = self.failed[g]['text']
                words = len(old.split())
                terms = sorted(place_terms(self.bible) & {stem(w) for w in tokens(old)}) if self.is_establishing(g) else []
                cue = {'gap_id': g, 'text': old, 'words': words, 'max_words': max_w, 'remove_at_least': max(1, words - max_w),
                       **({'keep_place': terms} if terms else {})}
                mock = {'text': ' '.join(old.split()[:max_w]), 'words': min(words, max_w)}
                try:
                    raw = self.model('tighten', self.d['tighten_stage'], P.TIGHTEN, {'cue': cue, '_max_tokens': self.d['tighten_max_tokens']},
                                     None, mock if self.mock else None)
                except (BudgetExceeded, TimeoutError):
                    raise
                except Exception as exc:
                    self.report['issues'].append(f'Nano tighten unavailable for gap {g}: ' + sanitize(exc))
                    outcome['error'] += 1
                    break
                text = parse_tightened(raw, g)
                why = self.tighten_reject(g, old, text)
                if why:
                    self.log(g, step=step, text=text, problems=[why])
                    outcome['rejected'] += 1
                    continue
                result = self.consider(g, {'text': text, 'evidence': self.failed[g]['evidence'], 'skip': False, 'reason': ''}, step)
                if result != 'failed' or not self.budget_only(g):
                    outcome[result] += 1   # pending, or a non-length problem now: Ultra repair handles it
                    break
            else:
                outcome['still_over'] += 1
        self.stats['tightened'] += outcome['pending']
        return f'over-budget cues shortened by Nano (one cue per call, <= {self.d["tighten_attempts"]} attempts): {dict(outcome)}'

    def maybe_tighten(self, name):
        n = sum(self.budget_only(g) for g in self.failed)
        if n:
            self.stage(name, lambda: self.st_tighten(name), f'{n} cues over budget only -> Nemotron Nano (no Ultra)')

    # ---------- stage: verify ----------
    def frame_times(self, gid):
        g = self.gap(gid)
        lo, hi = g['start'] + .15, max(g['start'] + .15, g['end'] - .15)
        times = []
        for e in (self.event(i) for i in self.pending[gid]['evidence']):
            if e:
                times.append(min(hi, max(lo, (e['t_start'] + e['t_end']) / 2)))
        times += [g['start'] + f * (g['end'] - g['start']) for f in (.5, .25, .75)]   # spread samples when evidence is sparse
        out = []
        for t in times:
            if all(abs(t - x) >= .5 for x in out):
                out.append(round(t, 2))
        return sorted(out[:self.d['verify_frames']])

    def refute_evidence(self, gid, wrong):
        """Mark cited evidence that a contradicted phrase rests on as refuted (P0-2): it leaves assignment, script,
        repair and coverage. Returns refuted ids."""
        wt, low, out = content_tokens(wrong), wrong.lower(), []
        for i in self.pending.get(gid, {}).get('evidence', []):
            e = self.event(i)
            if not e or e.get('refuted') or not wt:
                continue
            et = content_tokens(e['what'] + ' ' + e['on_screen_text'])
            # Refute only when the false phrase comes from the event itself (perception error); a detail the writer
            # added (e.g. "blue" in "a blue dough ball") leaves the evidence trusted for the repair.
            if (e['on_screen_text'] and e['on_screen_text'].lower() in low) or len(et & wt) / len(wt) >= .75:
                e['refuted'] = True
                self.assignment.pop(i, None)
                out.append(i)
        return out

    def commit(self, gid, verdict, reason=''):
        p = self.pending.pop(gid)
        self.cues[gid] = {**self.gap(gid), 'en': p['text'], 'evidence': p['evidence'], 'verdict': verdict}
        self.verified[gid] = verdict
        self.dropped.pop(gid, None)
        self.log(gid, step='commit', verdict=verdict, reason=reason)

    def st_verify(self, gids):
        gids = [g for g in gids if g in self.pending]
        tally = Counter()
        for k in range(0, len(gids), max(1, self.d['verify_batch'])):
            batch = gids[k:k + self.d['verify_batch']]
            data = {'duration': 0, 'cues': [{'gap_id': g, 'text': self.pending[g]['text'], 'frame_times': self.frame_times(g)} for g in batch]}
            media = None
            if not self.mock:
                media = []
                for g in batch:
                    media.append({'type': 'text', 'text': f'Frames for cue gap_id {g}:'})
                    media += separate_frames(self.path, self.frame_times(g))
            mock = {'verdicts': [{'gap_id': g, 'verdict': 'contradicted' if 'blue dot' in self.pending[g]['text'] else 'supported',
                                  'wrong': 'blue dot' if 'blue dot' in self.pending[g]['text'] else '', 'reason': 'MOCK verdict'} for g in batch]}
            try:
                raw = self.model('verify', 'perceive', P.VERIFY, data, media, mock if self.mock else None)
                rows = raw.get('verdicts', raw.get('cues', [])) if isinstance(raw, dict) else raw if isinstance(raw, list) else []
                verdicts = {}
                for r in rows:
                    try:
                        verdicts[int(r.get('gap_id', r.get('id')))] = r
                    except (TypeError, ValueError, AttributeError):
                        pass
            except (BudgetExceeded, TimeoutError):
                raise
            except Exception as exc:
                verdicts, why = {}, sanitize(exc)
                self.report['issues'].append(f'Verification unavailable for gaps {batch}: {why}')
            for g in batch:
                r = verdicts.get(g) or {}
                verdict = str(r.get('verdict', '')).strip().lower()
                reason, wrong = str(r.get('reason') or '')[:200], str(r.get('wrong') or '')[:120]
                text = self.pending[g]['text']
                if verdict not in ('supported', 'contradicted', 'uncertain'):
                    if self.d['require_verification']:
                        self.pending.pop(g)
                        self.drop_gap(g, 'not verified (no verdict); never committed unverified')
                        self.log(g, step='verify', verdict='none')
                        tally['unverified-dropped'] += 1
                        self.trace('tool', tool_name='verify_claim', note=f'gap {g}: no verdict; cue dropped', ok=False, args={'gap_id': g, 'claim': text}, result={'verdict': 'none'})
                        continue
                    verdict = 'uncertain'
                risky = risky_text(text)
                if verdict == 'supported' or (verdict == 'uncertain' and self.d['accept_uncertain'] and not risky):
                    self.commit(g, 'supported' if verdict == 'supported' else 'uncertain-consistent', reason)
                else:
                    # No quoted wrong phrase: the whole cue is wrong, so the evidence it rests on is refuted.
                    refuted = self.refute_evidence(g, wrong or text) if verdict == 'contradicted' else []
                    if verdict == 'contradicted':
                        self.contradicted += 1
                        self.rejected.setdefault(g, []).append(text)
                    why = f'verifier ({verdict}) on frames {self.frame_times(g)}: ' + (f'"{wrong}" is wrong; ' if wrong else '') + (reason or 'unsupported') + (f'; risky details: {", ".join(risky)}' if verdict == 'uncertain' else '')
                    self.failed[g] = {**self.pending.pop(g), 'reasons': [why], 'refuted': refuted}
                    self.log(g, step='verify', verdict=verdict, reason=why, refuted=refuted)
                tally[verdict] += 1
                self.trace('tool', tool_name='verify_claim', note=f'gap {g}: {verdict}' + (f' ({reason[:120]})' if reason else ''), ok=verdict != 'contradicted',
                           args={'gap_id': g, 'claim': text}, result={'verdict': verdict, 'evidence': reason, 'wrong': wrong})
        return f'{len(gids)} cues checked on stills inside their gaps: {dict(tally)}'

    # ---------- stage: repair ----------
    def neighbours(self, gid):
        rows = self.accepted_texts(gid)
        start = self.gap(gid)['start']
        prev = [r[2] for r in rows if r[0] < start][-1:]
        nxt = [r[2] for r in rows if r[0] > start][:1]
        return {**({'previous_cue': prev[0]} if prev else {}), **({'next_cue': nxt[0]} if nxt else {})}

    def st_repair(self, round_no):
        gids = sorted(self.failed, key=lambda i: self.gap(i)['start'])
        items = [{**self.gap_payload(self.gap(g)), 'rejected_text': self.failed[g]['text'], 'rejected_words': len(self.failed[g]['text'].split()),
                  'why_rejected': self.failed[g]['reasons'],
                  'trusted_evidence': [r for r in self.timeline_rows() if g in self.assignment.get(r['id'], ())], **self.neighbours(g)} for g in gids]
        bible = {k: self.bible.get(k) for k in ('setting', 'place', 'cast', 'objects', 'goal', 'story')}
        mock = {'cues': [{'gap_id': g, 'skip': True, 'reason': 'MOCK repair: nothing reliable'} for g in gids]}
        parsed = parse_cues(self.model('repair', self.d['ultra_stage'], P.REPAIR, {'bible': bible, **self.title_payload(), 'round': round_no, 'gaps': items}, None, mock if self.mock else None, ultra=True))
        outcome = Counter()
        for g in gids:
            if g in parsed:
                outcome[self.consider(g, parsed[g], f'repair_{round_no}')] += 1
            else:
                outcome['unanswered'] += 1
        self.stats['repair_rounds'] = round_no
        return f'round {round_no}: {len(gids)} failed cues sent to Ultra: {dict(outcome)}'

    def verify_and_repair(self):
        todo = list(self.pending)
        for round_no in range(self.d['max_repair_rounds'] + 1):
            if todo:
                self.stage('verify' if round_no == 0 else f'verify_{round_no}', lambda: self.st_verify(todo), f'{len(todo)} cues, {self.d["verify_frames"]} stills each')
            if not self.failed or round_no == self.d['max_repair_rounds']:
                break
            # Length failures Nano could not fix ARE repairable: Ultra rewrites them with the word count and the Fix hint.
            if self.ultra_calls >= self.d['max_ultra_calls']:
                self.report['issues'].append('Ultra call cap reached: no further repair')
                break
            before = set(self.pending)
            self.stage(f'repair_{round_no+1}', lambda: self.st_repair(round_no + 1), f'{len(self.failed)} failed cues')
            self.maybe_tighten(f'tighten_{round_no+1}')
            todo = [g for g in self.pending if g not in before]
        self.establish_fallback()
        for g, f in list(self.failed.items()):
            prefix = 'dropped (still over budget after Nano tighten and Ultra repair): ' if self.budget_only(g) else 'dropped after repair: '
            self.failed.pop(g)
            self.drop_gap(g, prefix + '; '.join(f['reasons'])[:200])
            self.log(g, step='drop', reason='; '.join(f['reasons']))
            self.stats['dropped_after_repair'] += 1

    def establish_fallback(self):
        """Never drop the establishing cue only because it does not name the place: after the repair rounds, the best attempt
        that passed every other check is verified on stills and committed if supported, with an issue recorded."""
        rescue = [g for g in sorted(self.establish_candidates, key=lambda i: self.gap(i)['start']) if g not in self.cues][:1]
        if not rescue:
            return
        for g in rescue:
            candidate = self.establish_candidates[g]
            self.failed.pop(g, None)
            self.skipped.pop(g, None)
            self.pending[g] = dict(candidate)
            self.log(g, step='establish_fallback', text=candidate['text'],
                     reason='place still not named after repairs; verifying the best otherwise-valid model-written attempt')
        self.stage('verify_establish', lambda: self.st_verify(rescue), f'{len(rescue)} establishing cue(s) that only miss the place')
        for g in rescue:
            if g in self.cues:
                self.stats['establish_without_place'] += 1
                self.report['issues'].append(f'Establishing cue (gap {g}) committed without naming the place after repairs; verified on stills')

    # ---------- stage: hindi ----------
    def hi_problems(self, gid, text):
        if not isinstance(text, str) or not text.strip():
            return ['missing Hindi'], 0, None
        if not re.search('[\u0900-\u097f]', text) or re.search('[A-Za-z]{3,}', text):
            return ['Hindi must be Devanagari, no Latin words'], 0, None
        if '\n' in text or '-->' in text:
            return ['must be one line'], 0, None
        fit = self.check_fit(gid, text, 'hi')
        return ([] if fit['ok'] else fit['problems']), fit['seconds'], fit['suggested_max_words']

    def st_hindi(self):
        cues = sorted(self.cues.values(), key=lambda c: c['start'])
        if not cues:
            return 'no cues'
        allowed = lambda c: round(c['duration'] * self.cfg['agent']['max_atempo'], 2)
        rows = [{'gap_id': c['id'], 'start': round(c['start'], 1), 'end': round(c['end'], 1), 'en': c['en'], 'max_words': max(1, c.get('director_words_hi') or self.max_words(c, 'hi'))} for c in cues]
        def mock_hi(rows):
            out = []
            for r in rows:
                ev = [self.event(i) for i in self.cues[r['gap_id']].get('evidence', [])]
                hi = next((e['hi'] for e in ev if e and e.get('hi')), 'दृश्य बदलता है।')
                out.append({'gap_id': r['gap_id'], 'hi': hi if len(hi.split()) <= r['max_words'] else 'दृश्य बदलता है।'})
            return {'cues': out}
        bible = {k: self.bible.get(k) for k in ('setting', 'place', 'cast', 'objects', 'goal', 'story')}
        gender = self.cast_gender()
        got = self.model('hindi', self.d['ultra_stage'], P.HINDI, {'bible': bible, 'cast_gender': gender, 'cues': rows}, None, mock_hi(rows) if self.mock else None, ultra=True)
        texts = {g: v['text'] for g, v in parse_hi(got).items()}
        failing = []
        for r in rows:
            problems, seconds, suggested = self.hi_problems(r['gap_id'], texts.get(r['gap_id']))
            if problems:
                failing.append({**r, 'hi_previous': texts.get(r['gap_id'], ''), 'problem': problems, 'measured_seconds': round(seconds, 2),
                                'allowed_seconds': allowed(self.cues[r['gap_id']]), 'max_words': max(1, min(r['max_words'], suggested or r['max_words']))})
            else:
                self.cues[r['gap_id']]['hi'] = texts[r['gap_id']]
        refit = 0
        if failing:
            try:
                got = self.model('hindi', self.d['ultra_stage'], P.HINDI_REFIT, {'cast_gender': gender, 'cues': failing}, None, mock_hi(failing) if self.mock else None, ultra=True)
                texts = {g: v['text'] for g, v in parse_hi(got).items()}
                for r in failing:
                    problems = self.hi_problems(r['gap_id'], texts.get(r['gap_id']))[0]
                    if not problems:
                        self.cues[r['gap_id']]['hi'] = texts[r['gap_id']]
                        refit += 1
            except (BudgetExceeded, TimeoutError):
                raise
            except Exception as exc:
                self.report['issues'].append('Hindi refit unavailable: ' + (str(exc) if isinstance(exc, UltraCapReached) else sanitize(exc)))
        missing = [c['id'] for c in cues if not c.get('hi')]
        if missing:
            self.report['issues'].append(f'hi: no fitting Hindi for gaps {missing}; English kept')
        self.translation_done = True
        return f'{len(cues)} cues written in Hindi in one call; {len(failing)} over budget -> {refit} refit; {len(missing)} without Hindi'

    def cast_gender(self):
        """Per cast member: the visible gender from the bible notes, or 'not visible -> gender-neutral Hindi'."""
        out = {}
        for c in self.bible.get('cast', []):
            notes = (c.get('notes') or '').lower()
            m = None if re.search(r'not (?:clearly )?visible|unknown|unclear', notes) else re.search(r'\b(woman|female|girl|man|male|boy)\b', notes)
            out[c['descriptor']] = (('feminine' if m.group(1) in ('woman', 'female', 'girl') else 'masculine') + ' (visible)') if m else \
                'not visible: use gender-neutral constructions (passive or noun-focused)'
        return out or {'people': 'not visible: use gender-neutral constructions (passive or noun-focused)'}

    # ---------- stage: render + report ----------
    def st_render(self):
        for gid, c in list(self.cues.items()):
            if not self.check_fit(gid, c['en'], 'en')['ok']:
                self.cues.pop(gid)
                self.drop_gap(gid, 'Final validation rejected English cue')
            elif c.get('hi') and not self.check_fit(gid, c['hi'], 'hi')['ok']:
                c.pop('hi')
        tracks = {}
        for lang in self.langs:
            tracks[lang] = self.render(lang, self.out / f'narrated_{lang}.mp4')
            write_texts(self.out, lang, tracks[lang])
        narratable = self.narratable()
        total = max(.001, sum(g['duration'] for g in narratable if g['id'] not in self.skipped))
        live = self.live_events()
        high = [e for e in live if e['importance'] >= 4 and any(g not in self.skipped for g in e.get('gap_ids', []))]
        in_speech = [e for e in live if e['importance'] >= 4 and not e.get('gap_ids')]
        uncovered = [e for e in high if not any(g in self.cues for g in e['gap_ids'])]
        first = min(self.cues.values(), key=lambda c: c['start'], default=None)
        terms = place_terms(self.bible)
        if first and terms and not {stem(w) for w in tokens(first['en'])} & terms and not self.stats.get('establish_without_place'):
            self.report['issues'].append(f"First committed cue (gap {first['id']}) does not name the place")
        use = [len(c['en'].split()) / max(1, c.get('director_words_en') or 1) for c in self.cues.values()]
        self.stats['budget_use_percent'] = round(100 * sum(use) / len(use)) if use else 0
        coverage = self.coverage()
        self.report['coverage'] = coverage
        if not coverage['meets_target']:
            self.report['issues'].append(f"Coverage guard: {coverage['narrated']} of {coverage['narratable']} narratable gaps narrated "
                                         f"({coverage['percent_excluding_silent_by_choice']} % excluding silent-by-choice; target {coverage['target_percent']} %)")
        self.report.update(status='complete', cues=sorted(self.cues.values(), key=lambda c: c['start']), tracks=tracks, gaps=self.gaps, speech=self.speech,
            cues_committed=len(self.cues), cues_dropped=len(self.dropped), dropped_gaps=self.dropped, gaps_skipped_no_new_info=sorted(self.skipped),
            overlaps_with_speech=sum(self.check_fit(c['id'], c[l], l)['overlap_seconds'] > 0 for c in self.cues.values() for l in self.langs if c.get(l)),
            gap_coverage_percent={l: 100 * sum(c['end'] - c['start'] for c in track) / total for l, track in tracks.items()},
            high_importance_covered_percent=100 * (len(high) - len(uncovered)) / len(high) if high else 100,
            events_in_speech_regions={'count': len(in_speech), 'events': in_speech, 'note': 'informational: important events while someone speaks; known to the writer as story context, may need extended AD'},
            coverage_method='event->gap assignment (midpoint / >=50% overlap); writer may skip gaps with nothing new', uncovered_events=uncovered)
        self.done = True
        return f"{len(self.cues)} cues rendered ({', '.join(f'{l}: {len(t)}' for l, t in tracks.items())}); {len(self.skipped)} gaps silent by choice"

    def silence_category(self, gid):
        reason = self.dropped.get(gid, 'not scripted')
        if reason.startswith('too short'):
            return 'too_short'
        if gid in self.skipped:
            return {'no events inside this gap': 'no_events', 'writer returned nothing for this gap': 'writer_missing'}.get(reason.replace('silent: ', ''), 'no_new_info')
        return 'dropped'

    def coverage(self):
        """Coverage guard: narrated / narratable (gaps long enough for a cue) and why each silent gap is silent. Only a stated
        no-new-info skip (or no events at all) is an accepted silence; the target applies to the rest."""
        long_enough = [g for g in self.narratable() if g.get('director_words_en', 0) >= self.d['min_words']]
        silent = {g['id']: {'why': self.silence_category(g['id']), 'reason': self.dropped.get(g['id'], 'not scripted')[:200]}
                  for g in self.narratable() if g['id'] not in self.cues}
        narrated = sum(g['id'] in self.cues for g in long_enough)
        by_choice = sum(silent.get(g['id'], {}).get('why') in ('no_new_info', 'no_events') for g in long_enough)
        expected = len(long_enough) - by_choice
        pct = round(100 * narrated / expected) if expected else 100
        return {'narratable': len(long_enough), 'narrated': narrated, 'silent_by_choice': by_choice,
                'dropped': sum(v['why'] in ('dropped', 'writer_missing') for v in silent.values()),
                'too_short': sum(v['why'] == 'too_short' for v in silent.values()),
                'percent_of_narratable': round(100 * narrated / len(long_enough)) if long_enough else 100,
                'percent_excluding_silent_by_choice': pct, 'target_percent': round(100 * self.d['coverage_target']),
                'meets_target': pct >= 100 * self.d['coverage_target'], 'silent': {str(k): v for k, v in sorted(silent.items())}}

    def run(self):
        stop = None
        try:
            self.stage('gaps', self.st_gaps, 'Silero VAD speech intervals; slots <= max_slot_s; budgets from measured TTS')
            if self.scriptable():
                self.stage('shots', self.st_shots, 'ffmpeg scene-change detection')
                self.stage('scene', self.st_scene, f"Super VL on {self.cfg['agent'].get('scene_frames', 6)} stills across the clip")
                self.stage('timeline', self.st_timeline, 'Super VL video windows covering the whole clip')
                self.stage('bible', self.st_bible, 'scene + shots + timeline')
                self.stage('assign', self.st_assign, 'midpoint / >=50% overlap; refuted excluded')
                self.stage('script', self.st_script, 'bible + timeline + all gaps -> whole English track')
                self.maybe_tighten('tighten')
                self.verify_and_repair()
                if 'hi' in self.langs and self.cues:
                    self.stage('hindi', self.st_hindi, 'bible + English meaning + measured Hindi budgets')
            elif not self.narratable():
                self.report['issues'].append('Cannot narrate safely without extended AD (pause-the-video): no usable speech-free gaps.')
            else:
                self.report['issues'].append(f"Every speech-free gap is too short for a {self.d['min_words']}-word cue; extended AD is needed.")
        except BudgetExceeded:
            stop = 'budget exceeded'
        except UltraCapReached as exc:
            stop = str(exc)
        except Exception as exc:
            stop = 'director stopped: ' + sanitize(exc)
        if stop:
            self.report['issues'].append(stop + '; rendering verified cues only')
            self.report['stopped_reason'] = stop
            for g in list(self.pending) + list(self.failed):
                self.pending.pop(g, None)
                self.failed.pop(g, None)
                self.drop_gap(g, 'not verified before stop')
        try:
            self.stage('render', self.st_render, 'TTS, ducking mix, VTT, transcripts')
        except Exception as exc:
            self.report['status'] = 'failed'
            self.report['issues'].append('Render failed: ' + sanitize(exc))
        finally:
            self.save()
        return self.report

    def save(self):
        self.report.update(bible=self.bible, timeline=self.timeline, shots=self.shots, windows=[list(w) for w in self.windows], stages=self.stage_log,
                           cue_history={str(k): v for k, v in sorted(self.history.items())},
                           director_stats={'ultra_calls': self.ultra_calls, 'max_ultra_calls': self.d['max_ultra_calls'], **self.stats,
                                           'verdicts': dict(Counter(c.get('verdict') for c in self.cues.values())), 'contradicted': self.contradicted,
                                           'events': len(self.timeline), 'events_refuted': sum(bool(e.get('refuted')) for e in self.timeline)})
        super().save()
        roles = ('scene', 'timeline', 'bible', 'script', 'tighten', 'verify', 'repair', 'hindi')
        source = self.client.usage or [{'cost_role': s.get('cost_role'), 'cost_usd': s['cost_usd']} for s in self.steps if s.get('model')]
        self.report['cost_by_role'] = {r: sum(u.get('cost_usd', 0) for u in source if u.get('cost_role') == r) for r in roles}
        (self.out / 'report.json').write_text(json.dumps(self.report, ensure_ascii=False, indent=2))
        trace = json.loads((self.out / 'trace.json').read_text())
        trace['metadata']['mode'] = 'director'
        trace['stages'] = self.stage_log
        (self.out / 'trace.json').write_text(json.dumps(trace, ensure_ascii=False, indent=2))
        (self.out / 'trace.md').write_text(self.trace_md(), encoding='utf-8')

    def run_summary(self):
        """Five lines a judge reads first: model calls, cost, cues, silence by choice, drops with reasons (+ the user title)."""
        calls = Counter(s.get('cost_role') for s in self.steps if s.get('model'))
        cost = self.report.get('cost_by_role') or {}
        ultra = sum(cost.get(r, 0) for r in ('bible', 'script', 'repair', 'hindi'))
        silent = sorted(self.skipped)
        dropped = {g: r for g, r in self.dropped.items() if g not in self.skipped and g in {x['id'] for x in self.narratable()}}
        short = lambda r: r.replace('silent: ', '')[:90]
        L = ['## Run summary', '',
             f"- **Model calls:** Ultra {self.ultra_calls}/{self.d['max_ultra_calls']} · Super VL {calls['timeline'] + calls['scene'] + calls['verify']} · Nano tighten {calls['tighten']}",
             f"- **Cost:** ${self.report.get('estimated_cost_usd', 0):.4f} (Ultra ${ultra:.4f}, timeline ${cost.get('timeline', 0):.4f}, verify ${cost.get('verify', 0):.4f}, Nano ${cost.get('tighten', 0):.4f})",
             f"- **Cues:** {len(self.cues)} committed of {len(self.narratable())} narratable gaps · average budget use {self.stats.get('budget_use_percent', 0)} % · repairs {self.stats.get('repair_rounds', 0)} · Nano-tightened {self.stats.get('tightened', 0)} · within word tolerance {self.stats.get('accepted_within_tolerance', 0)}",
             '- **Silent by choice:** ' + ('; '.join(f'gap {g} ({short(self.dropped.get(g, ""))})' for g in silent) or 'none'),
             '- **Dropped:** ' + ('; '.join(f'gap {g} ({short(r)})' for g, r in sorted(dropped.items())) or 'none')]
        cov = self.coverage()
        L.append(f"- **Coverage:** {cov['narrated']}/{cov['narratable']} narratable gaps narrated ({cov['percent_of_narratable']} %; "
                 f"{cov['percent_excluding_silent_by_choice']} % excluding {cov['silent_by_choice']} silent by choice; target {cov['target_percent']} %"
                 + ('' if cov['meets_target'] else ' — BELOW TARGET') + ')')
        if self.context:
            L.append(f'- **Video title (UNVERIFIED user context, never evidence):** “{self.context}”')
        return L

    def trace_md(self):
        cell = lambda v: str(v).replace('|', '/').replace('\n', ' ')
        L = [f"# Narrate director trace (v2){' — MOCK (synthetic, no visual analysis)' if self.mock else ''}", '',
             f"Clip: `{self.path.name}` · {self.duration:.1f} s · provider `{self.cfg['provider']}` · "
             f"Ultra calls {self.ultra_calls}/{self.d['max_ultra_calls']} · cost ${self.report.get('estimated_cost_usd', 0):.4f}", '',
             *self.run_summary(), '',
             '## Stages', '', '| stage | model(s) | calls | tokens in / out | cost $ | s | output |', '|---|---|---|---|---|---|---|']
        for r in self.stage_log:
            L.append(f"| {'✓' if r['ok'] else '✗'} {r['stage']} | {cell(', '.join(m.split('/')[-1] for m in r['models']) or '—')} | {r['calls']} | "
                     f"{r['tokens_in']} / {r['tokens_out']} | {r['cost_usd']:.4f} | {r['latency_s']:.1f} | {cell(r['output'])} |")
        b = self.bible or {}
        L += ['', '## Scene bible', '', f"- **Place:** {b.get('place', '')} · **Goal:** {b.get('goal', '') or '—'}", f"- **Setting:** {b.get('setting', '')}", f"- **Cast:** " + '; '.join(f"{c['descriptor']} ({c.get('notes', '')})" for c in b.get('cast', [])),
              f"- **Story:** {b.get('story', '')}", f"- **Objects:** {', '.join(b.get('objects', []))}", f"- **Subtitles present (never read):** {b.get('subtitles_present', False)}",
              '- **Beats:** ' + '; '.join(f"{x['t']:.0f}s {x['beat']}" for x in b.get('beats', []))]
        L += ['', f'## Timeline ({len(self.timeline)} events; ~~refuted~~)', '', '| id | time | gap | what | on screen | said |', '|---|---|---|---|---|---|']
        for e in self.timeline:
            what = f"~~{cell(e['what'])}~~" if e.get('refuted') else cell(e['what'])
            L.append(f"| {e['id']} | {e['t_start']:.1f}-{e['t_end']:.1f} | {','.join(map(str, e.get('gap_ids') or [])) or 'speech'} | {what} | {cell(e['on_screen_text'])} | {cell(e['subtitle_text'])} |")
        L += ['', '## Script, verification and repairs', '', '| gap | time | words | outcome | English | evidence | Hindi |', '|---|---|---|---|---|---|---|']
        for g in self.narratable():
            gid = g['id']
            c = self.cues.get(gid)
            outcome = c['verdict'] if c else self.dropped.get(gid, 'not scripted')
            used = f"{len(c['en'].split())}/" if c else ''
            L.append(f"| {gid} | {g['start']:.1f}-{g['end']:.1f} | {used}{g.get('director_words_en', '')} | {cell(outcome)} | {cell(c['en']) if c else ''} | "
                     f"{', '.join(c.get('evidence', [])) if c else ''} | {cell(c.get('hi', '')) if c else ''} |")
        steps = [(gid, h) for gid, rows in sorted(self.history.items()) for h in rows if h['step'] not in ('commit',)]
        if steps:
            L += ['', '### Cue history (script → verify → repair)', '']
            for gid, h in steps:
                detail = h.get('text') or ''
                why = '; '.join(h.get('problems') or []) or h.get('reason') or h.get('verdict') or ''
                L.append(f"- gap {gid} · {h['step']}: " + (f'"{detail}" ' if detail else '') + (f'→ {why}' if why else '→ ok'))
        if self.report.get('issues'):
            L += ['', '## Issues', ''] + [f'- {i}' for i in self.report['issues']]
        return '\n'.join(L) + '\n'


def parse_hi(response):
    items = response.get('cues', []) if isinstance(response, dict) else response if isinstance(response, list) else []
    out = {}
    for c in items:
        if isinstance(c, dict) and isinstance(c.get('hi', c.get('text')), str):
            try:
                out[int(c.get('gap_id', c.get('id')))] = {'text': ' '.join(c.get('hi', c.get('text')).split())}
            except (TypeError, ValueError):
                pass
    return out


def run_director(path, out_dir, provider=None, langs=('en', 'hi'), budget_usd=None, on_step=None, *, config=None, client=None, context=None):
    """v2 entry point (DESIGN_v2.md); same outputs as run_agent. budget_usd caps total spend (SpendGuard). context is an optional
    user title/one-line description, passed to the bible and script as UNVERIFIED context (never evidence)."""
    cfg = resolve_provider(config or load_config(), provider)
    if client is None and cfg['provider'] != 'mock' and not os.environ.get(cfg['key_env']):
        raise RuntimeError(f"Provider '{cfg['provider']}' needs env {cfg['key_env']}; use provider='mock' offline")
    if isinstance(langs, str):
        langs = langs.split(',')
    if not langs or any(l not in ('en', 'hi') for l in langs):
        raise ValueError('Supported languages: en,hi')
    cap = (cfg.get('director') or {}).get('budget_usd', DEFAULTS['budget_usd']) if budget_usd is None else budget_usd
    director = Director(path, out_dir, cfg, list(langs), SpendGuard(cap), on_step, client, context=context)
    return director.run()
