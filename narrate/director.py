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
from .perception import data_url, separate_frames, crop_frames
from . import director_prompts as P

DEFAULTS = {
    'window_s': 12, 'window_snap_s': 2, 'window_fps': 4, 'window_fallback_frames': 4,
    'ultra_stage': 'edit', 'bible_stage': 'edit', 'tighten_stage': 'fit', 'max_ultra_calls': 6, 'budget_usd': .15,
    'min_words': 4, 'target_fill': .7, 'target_fill_max': .9, 'similarity_prev': .5, 'similarity_any': .8,
    'narrator_wps_en': 2.6, 'word_tolerance': .15, 'tighten_attempts': 2, 'tighten_max_tokens': 240, 'coverage_target': .75,
    'verify_batch': 4, 'verify_frames': 2, 'max_repair_rounds': 2,
    'accept_uncertain': True, 'require_verification': True, 'calibrate_tts': True,
    'relook_max': 2, 'zoom_max': 3, 'zoom_frames': 5, 'cast_look_frames': 6, 'min_detail_words': 2, 'openings_max_share': .5, 'openings_min_cues': 3, 'hi_passive_share': .5,
    'max_silent_run_s': 20,
    'temperature': .2, 'verify_temperature': 0., 'fallback_word_tolerance': .35, 'rescue_strike_max': 4, 'rescue_verify_rounds': 2,
}
STOP = {'a', 'an', 'the', 'and', 'of', 'to', 'in', 'on', 'with', 'into', 'at', 'is', 'are', 'it', 'its', 'her', 'his', 'their', 'then', 'as', 'by', 'from'}
DIRECTOR_LINT = [
    (re.compile(r'(?:^|[.!?]\s+|,\s+)(?:a|the|one)?\s*person\b', re.I), 'generic "Person" opener or subject. Fix: use the cast descriptor or a pronoun'),
    (re.compile(r'\bcontinu(?:e|es|ing)\b', re.I), '"continues". Fix: say what is new or changed (the result, the next step), or skip the gap'),
    (re.compile(r'\b(?:in|on) (?:the|this|that) (?:shot|frame|footage)\b|\bscreen shows\b|\b(?:is|are) filmed\b|\bclose-up\b', re.I),
     'film-making jargon. Fix: describe what is visible and what the people do, e.g. "a crewmate photographs the pepper"'),
    (re.compile(r';'), 'headline fragments (";"). Fix: write one or two complete sentences with a subject; join actions with "and" or "then"'),
    # Round 5 (nasa_v2_r4 "The camera lowers from the board"): the camera as the SUBJECT of any verb is camera direction.
    (re.compile(r'(?:^|[.!?]\s+|,\s*|\b(?:and|as|while|then|when|before|after|until)\s+)(?:the|a)\s+camera\s+(?:is\s+|was\s+)?[a-z]+(?:s|ed)\b', re.I),
     'camera as the subject (camera direction). Fix: say what the people do (e.g. "the crewmate lowers the camera") or leave the camera out'),
    # Round 5 ("Applause sounds as ..."): the listener already hears the programme audio.
    (re.compile(r'\b(?:applause|sounds?|sounding|noises?|music|musical|audible|hears?|heard|laughter|voices?|beeps?)\b', re.I),
     'describes sound the listener already hears. Fix: describe only what is visible (e.g. "the crew claps and laughs"), never applause, laughter, music or voices'),
]
PRONOUNS = {'she', 'he', 'they', 'them', 'her', 'him', 'his', 'hers', 'their', 'theirs', 'it', 'its', 'this', 'that', 'now', 'then', 'again'}
REACTION = re.compile(r'\b(?:eat|bite|bit|tast|chew|mouth|lick|sip|drink|laugh|grimac|winc|react|smil|cheer|clap|celebrat|rais|hug|high-five|show)', re.I)
# A Hindi passive: perfective participle (…ा/…ी/…े) + जा- ("गूँधा जाता है", "बेली जा रही है"); compounds such as "ले जाता" excluded.
HI_PASSIVE = re.compile(r'(?:^|(?<=\s))(?!(?:ले|चला|चली|चले)\s)\S*[\u093e\u0940\u0947]\s+(?:जा(?:ता|ती|ते)|जा\s+रह[\u093e\u0940\u0947])(?=[\s।,.!?]|$)')
PERSON_NOUNS = {'chef', 'chefs', 'cook', 'cooks', 'man', 'men', 'woman', 'women', 'person', 'people',
                'astronaut', 'astronauts', 'crewmate', 'crewmates', 'photographer', 'photographers'}
VERB_OPENER_NOUNS = {'hands', 'eyes', 'glasses', 'clothes', 'leaves', 'pieces', 'slices', 'dishes', 'faces', 'spaces'}
VERB_OPENER_FOLLOWERS = {'a', 'an', 'the', 'one', 'each', 'this', 'that', 'these', 'those', 'his', 'her', 'their', 'its',
                         'it', 'them', 'him', 'and', 'to', 'into', 'onto', 'on', 'over', 'with', 'up', 'down', 'off', 'out', 'back'}
# Setting words too generic to establish WHERE a video takes place.
GENERIC_PLACE = {'crowded', 'bright', 'brightly', 'small', 'large', 'big', 'white', 'black', 'blue', 'wooden', 'lit', 'indoor', 'indoors',
                 'outdoor', 'room', 'area', 'space', 'inside', 'interior', 'modern', 'clean', 'busy', 'narrow', 'wide', 'dimly', 'well'}
NEUTRAL = 'not visible: use gender-neutral active constructions with a noun subject such as the hands ("हाथ ..."); at most one passive per line'
BUDGET_PROBLEMS = ('over budget', 'Word budget exceeded', 'TTS duration exceeds', 'cue too long')
PLACE_PROBLEM = 'establishing cue does not say where'
PUNCTUATION_PROBLEM = 'English cue must end with . ! or ?'
FINITE_VERBS = {'am', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'has', 'have', 'had', 'do', 'does', 'did',
                'can', 'could', 'may', 'might', 'must', 'shall', 'should', 'will', 'would'}
IRREGULAR_FINITE = {'holds', 'puts', 'sets', 'takes', 'makes', 'goes', 'shows', 'stands', 'sits', 'lies', 'reaches', 'eats',
                    'drinks', 'bites', 'cuts', 'rolls', 'kneads', 'pours', 'adds', 'opens', 'closes', 'moves', 'lifts', 'lowers',
                    'reads', 'wets'}
REGULAR_FINITE = {'acts', 'appears', 'arranges', 'bends', 'carries', 'claps', 'cleans', 'covers', 'flattens', 'folds',
                  'gestures', 'grabs', 'laughs', 'looks', 'mixes', 'photographs', 'places', 'points', 'presses', 'reacts',
                  'removes', 'smiles', 'stirs', 'touches', 'turns', 'uses', 'walks', 'watches', 'wears', 'wraps', 'dusts',
                  'heats'}
FINITE_BASE = {'act', 'add', 'appear', 'arrange', 'bend', 'bite', 'carry', 'clap', 'clean', 'close', 'cover', 'cut', 'drink',
               'dust', 'eat', 'flatten', 'fold', 'gesture', 'go', 'grab', 'heat', 'hold', 'knead', 'laugh', 'lift', 'look',
               'lower', 'make', 'mix', 'move', 'open', 'photograph', 'place', 'point', 'pour', 'press', 'put', 'reach',
               'react', 'remove', 'roll', 'set', 'show', 'sit', 'smile', 'stand', 'stir', 'take', 'touch', 'turn', 'use',
               'walk', 'watch', 'wear', 'wrap'}
TITLE_GENERIC = STOP | {'how', 'video', 'tutorial', 'making', 'make', 'made', 'with', 'from', 'about'}
# Round 7: two classes of checks. HARD problems (camera direction, "we see", title-only claims, subtitles, evidence, duplicates,
# measured TTS fit, the verifier) block a cue. SOFT problems are style: one repair attempt, then the best verified candidate
# that fits the time is kept. Length (over max_words) is repaired, but a candidate whose MEASURED speech fits the gap is kept
# within director.fallback_word_tolerance. Matching is by these markers in the problem text.
SOFT_MARKERS = ('Style:', PUNCTUATION_PROBLEM, 'no finite verb', 'headline fragments', 'no subject (headline-style',
                'no concrete detail', 'object identity', 'person descriptor drift', PLACE_PROBLEM, '"continues"',
                'generic "Person"', 'film-making jargon', 'describes sound', 'repeats the previous cue')
NOT_VERB_S = {'its', 'this', 'his', 'hers', 'theirs', 'ours', 'yours', 'yes', 'us', 'thus', 'plus', 'always', 'perhaps', 'as',
              'across', 'towards', 'afterwards', 'sometimes', 'news', 'series', 'lens', 'canvas', 'bus', 'gas', 'chaos', 'jeans',
              'pants', 'tongs', 'scissors', 'glasses', 'clothes', 'whereas', 'besides', 'various', 'previous', 'famous', 'nervous'}
NOUN_BEFORE = {'a', 'an', 'the', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'some', 'many',
               'several', 'few', 'both', 'all', 'these', 'those', 'his', 'her', 'their', 'its', 'our', 'my', 'your', 'of', 'on',
               'in', 'into', 'onto', 'with', 'at', 'from', 'to', 'by', 'for', 'over', 'under', 'between', 'more', 'other', 'each',
               'small', 'large', 'little', 'big', 'round', 'flat', 'green', 'red', 'white', 'black', 'blue', 'dough', 'flour'}


def is_soft(problem):
    return any(m in problem for m in SOFT_MARKERS)


def is_length(problem):
    return any(b in problem for b in BUDGET_PROBLEMS) and 'measured' not in problem and 'TTS duration' not in problem


def classify(problems):
    """(hard, length, soft) problem lists. Measured-time failures stay hard; a word count over max_words is 'length'."""
    hard, length, soft = [], [], []
    for p in problems:
        (soft if is_soft(p) else length if is_length(p) else hard).append(p)
    return hard, length, soft


def normalise_en(text):
    """Punctuation-only normalisation (the words stay Nemotron's): one line, ';' becomes a sentence break, a trailing comma or
    colon is removed and a missing final period is appended. Round 6 dropped cues for a missing period or a semicolon."""
    t = ' '.join(str(text or '').split())
    if not t:
        return t
    t = re.sub(r'\s*;\s*([a-z])', lambda m: '. ' + m.group(1).upper(), t)
    t = re.sub(r'\s*;\s*', '. ', t).strip()
    t = re.sub(r'[\s,:;\u2013\u2014-]+$', '', t)
    if t and not re.search(r'[.!?]["\u201d\']?$', t):
        t += '.'
    return t


class UltraCapReached(RuntimeError):
    pass


def content_tokens(text):
    return tokens(text) - STOP


def opening(text):
    """The first two words, lower-cased ("the cook"): the unit of the track-level opening-variety check."""
    return ' '.join(re.findall(r"[a-z'-]+", str(text).lower())[:2])


def hi_passives(text):
    return len(HI_PASSIVE.findall(str(text or '')))


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
    cue must contain one of them."""
    return {stem(w) for w in content_tokens(str(bible.get('place') or '') + ' ' + str(bible.get('setting') or '')) if not w.isdigit()} - GENERIC_PLACE


def clean_context(text, limit=200):
    """Optional user title/one-line description (UNVERIFIED context; never evidence)."""
    text = ' '.join(str(text or '').split())
    return text[:limit] or None


def has_finite_verb(text):
    """Cheap English fragment check: auxiliaries, past tense, listed verbs and (Round 7) any other -s word that does not
    follow a determiner, number or preposition. Round 6's closed list rejected "The crew cheers", "They brush oil" and
    "White lid seals the bowl"; "A ball on the mats." is still a fragment."""
    words = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", str(text).lower())
    for i, w in enumerate(words):
        if w in FINITE_VERBS or w in FINITE_BASE or w in IRREGULAR_FINITE or w in REGULAR_FINITE or w.endswith('ed'):
            return True
        prev = words[i - 1] if i else ''
        if (i and len(w) > 3 and w.endswith('s') and not w.endswith(('ss', "'s", 'us', 'is')) and w not in NOT_VERB_S
                and w not in VERB_OPENER_NOUNS and prev not in NOUN_BEFORE and not prev.endswith("'s")):
            return True
        # A base verb after "they/we/you/i" or a plural noun ("They brush oil", "crewmates ... cheer").
        if (i and (prev in ('they', 'we', 'you', 'i') or (len(prev) > 3 and prev.endswith('s') and not prev.endswith('ss')))
                and w not in NOUN_BEFORE and w not in STOP and w not in PRONOUNS and not w.endswith(('s', 'ing', 'ly'))):
            return True
    return False


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
             'beats': [{'t': num(b.get('t')), 'beat': short(b.get('beat'), 120),
                        **({'why': short(b.get('why'), 80)} if short(b.get('why'), 80) else {}),
                        **({'events': [str(x) for x in b['events'][:6] if isinstance(x, (str, int))]} if isinstance(b.get('events'), list) else {})}
                       for b in items('beats')[:12] if isinstance(b, dict) and short(b.get('beat'), 120)],
             'names': [{'name': short(n.get('name'), 40), 'aliases': [a for a in (short(x, 30).lower() for x in n['aliases'][:4]) if a and a != short(n.get('name'), 40).lower()],
                        'from_t': num(n.get('from_t'))}
                       for n in items('names')[:6] if isinstance(n, dict) and short(n.get('name'), 40) and isinstance(n.get('aliases'), list)],
             'look_for': [{'t_start': num(x.get('t_start')), 't_end': num(x.get('t_end')), 'what': short(x.get('what'), 120)}
                          for x in items('look_for')[:2] if isinstance(x, dict) and short(x.get('what'), 120) and num(x.get('t_end')) > num(x.get('t_start'))],
             'on_screen_text': [{'t': num(x.get('t')), 'text': short(x.get('text'), 120), 'kind': short(x.get('kind', 'title'), 10)}
                                for x in items('on_screen_text')[:10] if isinstance(x, dict) and short(x.get('text'), 120)],
             'subtitles_present': raw.get('subtitles_present') in (True, 'true', 'yes', 1), 'tone': short(raw.get('tone', ''), 60)}
    for k in ('setting', 'place', 'story', 'cast', 'objects'):
        if not bible[k]:
            bible[k] = fallback.get(k, bible[k])
    bible['subtitles_present'] = bible['subtitles_present'] or fallback.get('subtitles_present', False)
    bible['names'] = [n for n in bible['names'] if n['aliases']]
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


def parse_tightened_options(response, gid):
    """Round 7: Nano returns up to three shorter versions ({"options":[{"text"}]}); a single {"text"} still works."""
    if isinstance(response, dict) and isinstance(response.get('options'), list):
        out = [' '.join(o['text'].split()) for o in response['options'] if isinstance(o, dict) and isinstance(o.get('text'), str)]
        out += [' '.join(o.split()) for o in response['options'] if isinstance(o, str)]
        return [t for t in dict.fromkeys(out) if t]
    one = parse_tightened(response, gid)
    return [one] if one else []


def lemma(word):
    """Crude inflection strip for the "adds no new words" test (round 6 rejected "pressing" vs "presses" as new)."""
    for suffix in ('ing', 'ed', 'es', 's'):
        if len(word) > len(suffix) + 2 and word.endswith(suffix):
            return word[:-len(suffix)]
    return word


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
        self.gap_beats, self.restyle, self.restyle_keep, self.restyle_pair = {}, set(), {}, ''
        self.stage_log, self.ultra_calls, self.call_role, self.wps = [], 0, None, {}
        self.stats = Counter()
        self.pool, self.soft_tried, self.silence_rescued, self.last_fit = {}, set(), {}, None
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
        if '_temperature' not in data:   # Round 7: low, repeatable sampling (run-to-run variance hid the r5 -> r6 regression)
            data = {**data, '_temperature': self.d['verify_temperature'] if cost_role == 'verify' else self.d['temperature']}
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

    # ---------- TTS preflight (before any paid call) ----------
    def preflight_tts(self):
        """Round 7 (r6a spent $0.058 and then failed because piper's dependencies were missing): render one short phrase per
        language with the configured voice before any model call, and abort with a clear error if it fails."""
        for lang in self.langs:
            try:
                seconds = self.measure_tts_duration(P.CALIBRATION[lang], lang)['seconds']
                if not seconds or seconds <= 0:
                    raise ValueError('empty audio')
            except Exception as exc:
                raise RuntimeError(f'TTS preflight failed for {lang} ({type(self.engine).__name__}): {sanitize(exc)}. '
                                   'Fix the voice (install the piper dependencies and voice models, or set tts.backend: espeak); '
                                   'no paid API call was made.') from None
        return True

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

    def perceive_window(self, i, start, end, previous=(), focus=None):
        burned = bool((self.scene_context or {}).get('burned_in_subtitles'))
        data = {'window': [round(start, 2), round(end, 2)], 'duration': round(end - start, 2), **({'look_for': focus} if focus else {}),
                **({'scene_context': scene_brief(self.scene_context)} if scene_brief(self.scene_context) else {}),
                **({'previous_events': [{'t': [round(e['t_start'], 1), round(e['t_end'], 1)], 'what': e['what']} for e in previous]} if previous else {})}
        fmt = dict(start=start, end=end, duration=self.duration)
        extra = P.RELOOK.format(what=focus) if focus else ''
        mock = {'events': self.mock_events(start, end)} if self.mock else None
        modality = 'mock' if self.mock else 'video'
        if self.mock:
            raw = self.model('timeline', 'perceive', P.TIMELINE.format(**fmt) + extra, data, None, mock)
        else:
            try:
                clip = self.work / f'window_{i}.mp4'
                ffmpeg('-ss', start, '-i', self.path, '-t', end - start, '-an', '-vf', f"scale=-2:360,fps={self.d['window_fps']}",
                       '-c:v', 'libx264', '-crf', 30, clip)
                raw = self.model('timeline', 'perceive', P.TIMELINE.format(**fmt) + extra, data, [{'type': 'video_url', 'video_url': {'url': data_url(clip.read_bytes(), 'video/mp4')}}])
                if not focus and not normalise_events(raw, start, end, self.duration, burned)[0]:
                    raise ValueError('no events')   # a focused re-look may legitimately find nothing
            except (BudgetExceeded, TimeoutError):
                raise
            except Exception:
                modality = 'frames'
                n = max(2, int(self.d['window_fallback_frames']))
                times = [round(start + (end - start) * (k + .5) / n, 2) for k in range(n)]
                raw = self.model('timeline', 'perceive', P.TIMELINE_FRAMES.format(**fmt) + extra, {**data, 'duration': 0, 'timestamps': times}, separate_frames(self.path, times))
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

    # ---------- stage: relook (Super VL, only for beats the bible expects but no event shows) ----------
    def st_relook(self):
        """Round 5 (nasa_v2_r4 never logged the tasting at ~94-97 s): for each bible look_for item (<= director.relook_max)
        one focused Super VL call on that window. Only new, non-duplicate events are added (ids continue after eN); they are
        evidence like any other event and still pass verification on stills."""
        added, asked = [], []
        for k, item in enumerate((self.bible.get('look_for') or [])[:int(self.d['relook_max'])]):
            s, e = max(0., item['t_start']), min(self.duration, item['t_end'])
            if e - s < 4:   # at least 4 s around the expected moment
                mid = (s + e) / 2
                s, e = max(0., mid - 2), min(self.duration, mid + 2)
            if e - s > self.d['window_s']:
                mid = (s + e) / 2
                s, e = mid - self.d['window_s'] / 2, mid + self.d['window_s'] / 2
            if e - s < 1:
                continue
            asked.append(f"{s:.0f}-{e:.0f}s {item['what'][:60]}")
            try:
                events, _, _ = self.perceive_window(f'relook{k}', s, e, focus=item['what'])
            except (BudgetExceeded, TimeoutError):
                raise
            except Exception as exc:
                self.report['issues'].append(f'Re-look {s:.0f}-{e:.0f}s unavailable: {sanitize(exc)}')
                continue
            for ev in events:
                if any(similarity(ev['what'], x['what']) >= .5 and ev['t_start'] <= x['t_end'] and ev['t_end'] >= x['t_start'] for x in self.timeline):
                    continue
                n = 1 + max((int(x['id'][1:]) for x in self.timeline if x['id'][1:].isdigit()), default=0)
                ev = {'id': f'e{n}', **ev, 'importance': max(4, ev['importance']), 'relook': True}
                self.timeline.append(ev)
                added.append(ev['id'])
        self.timeline.sort(key=lambda x: (x['t_start'], x['t_end']))
        self.events = self.timeline
        self.stats['relook_events'] += len(added)
        return f"{len(asked)} focused re-looks ({'; '.join(asked) or 'none'}): {len(added)} new events {added}"

    # ---------- stage: zoom (Super VL; small hand actions that a wide shot hides, e.g. a chili being cut) ----------
    ZOOM_CANDIDATE = re.compile(r'\b(pass\w*|handing|inspect\w*|examin\w*|gather\w*|object|item|bag|container|thing|together)\b', re.I)

    def zoom_windows(self):
        """Up to zoom_max windows (<= window_s) where an event describes vague handling of an object, most important first."""
        picks = [e for e in self.timeline if e.get('importance', 0) >= 3 and self.ZOOM_CANDIDATE.search(e['what'])
                 and not e.get('zoom') and not e.get('relook')]
        windows = []
        for e in sorted(picks, key=lambda x: x['t_start']):
            if windows and e['t_start'] - windows[-1][1] <= 3 and e['t_end'] - windows[-1][0] <= self.d['window_s']:
                windows[-1][1] = max(windows[-1][1], e['t_end'])
                windows[-1][2] = max(windows[-1][2], e.get('importance', 0))
            else:
                windows.append([e['t_start'], e['t_end'], e.get('importance', 0)])
        windows.sort(key=lambda w: (-w[2], w[0]))
        return sorted((w[0], min(w[1], w[0] + self.d['window_s'])) for w in windows[:int(self.d['zoom_max'])] if w[1] - w[0] >= 1)

    def st_zoom(self):
        """Two Super VL calls per window: locate the hand-and-object activity, then re-look at frames cropped to it. The result is
        added as ordinary events (importance >= 4) and still passes the same verification on stills as every other claim."""
        if self.mock or not self.d['zoom_max']:
            return 'skipped'
        burned = bool((self.scene_context or {}).get('burned_in_subtitles'))
        added, notes = [], []
        for s, e in self.zoom_windows():
            n = max(2, int(self.d['zoom_frames']))
            times = [round(s + (e - s) * (i + .5) / n, 2) for i in range(n)]
            what = ''
            try:
                located = self.model('timeline', 'perceive', P.ZOOM_LOCATE, {'duration': 0, 'timestamps': times[::2][:3]},
                                     separate_frames(self.path, times[::2][:3]))
                box = located.get('box') if isinstance(located, dict) else None
                what = str(located.get('what', ''))[:80] if isinstance(located, dict) else ''
                if not (isinstance(box, list) and len(box) == 4 and all(isinstance(v, (int, float)) for v in box)):
                    notes.append(f'{s:.0f}-{e:.0f}s no hand activity located')
                    continue
                raw = self.model('timeline', 'perceive', P.ZOOM_LOOK.format(start=s, end=e, duration=self.duration),
                                 {'window': [round(s, 2), round(e, 2)], 'duration': 0, 'timestamps': times},
                                 crop_frames(self.path, times, box))
                events, _ = normalise_events(raw, s, e, self.duration, burned)
            except (BudgetExceeded, TimeoutError):
                raise
            except Exception as exc:
                self.report['issues'].append(f'Zoom {s:.0f}-{e:.0f}s unavailable: {sanitize(exc)}')
                continue
            for ev in events:
                if any(similarity(ev['what'], x['what']) >= .6 and ev['t_start'] <= x['t_end'] and ev['t_end'] >= x['t_start'] for x in self.timeline):
                    continue
                num = 1 + max((int(x['id'][1:]) for x in self.timeline if x['id'][1:].isdigit()), default=0)
                self.timeline.append({'id': f'e{num}', **ev, 'importance': max(4, ev['importance']), 'zoom': True})
                added.append(f'e{num}')
            notes.append(f'{s:.0f}-{e:.0f}s {what[:40]}')
        self.timeline.sort(key=lambda x: (x['t_start'], x['t_end']))
        self.events = self.timeline
        self.stats['zoom_events'] += len(added)
        return f"{len(notes)} zoom looks ({'; '.join(notes) or 'none'}): {len(added)} new events {added}"

    # ---------- stage: cast_look (Super VL; apparent gender from frames, only when clearly visible) ----------
    def st_cast_look(self):
        """The bible is written from text events, which rarely say who is a woman or a man. Ask Super VL, on frames spread over the
        clip (and at each person's first appearance), for each cast member's apparent gender, only when clearly visible. The cast
        notes are rewritten so the writer uses she/he when it is clear and keeps they otherwise (cast_gender reads these notes)."""
        cast = self.bible.get('cast') or []
        if self.mock or not cast or not self.d['cast_look_frames']:
            return 'skipped'
        n = int(self.d['cast_look_frames'])
        # One frame per shot: a person is often identifiable in a single wide or medium shot among close-ups of hands.
        edges = [0.] + [t for t in self.shots if 0 < t < self.duration] + [self.duration]
        mids = [round((a + b) / 2, 2) for a, b in zip(edges, edges[1:]) if b - a >= .5]
        firsts = [round(min(self.duration - .3, max(0., float(c.get('first_seen') or 0.))), 2) for c in cast]
        times = sorted({t for t in firsts if all(abs(t - m) > .5 for m in mids)} | set(mids))
        cap = 2 * n
        if len(times) > cap:
            times = [times[round(i * (len(times) - 1) / (cap - 1))] for i in range(cap)]
        people = [{k: c.get(k) for k in ('id', 'descriptor', 'notes', 'first_seen')} for c in cast]
        found = {}   # id -> decided answers over all batches of frames
        for b in range(0, len(times), n):
            batch = times[b:b + n]
            try:
                raw = self.model('scene', 'perceive', P.CAST_LOOK, {'cast': people, 'duration': 0, 'timestamps': batch},
                                 separate_frames(self.path, batch))
            except (BudgetExceeded, TimeoutError):
                raise
            except Exception as exc:   # gender stays "not visible" (they / the descriptor); never fail the run for this
                self.report['issues'].append(f'Cast look unavailable for frames {batch[0]:.0f}-{batch[-1]:.0f}s: {sanitize(exc)}')
                continue
            for r in ((raw.get('cast') if isinstance(raw, dict) else None) or []):
                if isinstance(r, dict) and str(r.get('gender', '')).strip().lower() in ('woman', 'man') and str(r.get('evidence', '')).strip():
                    found.setdefault(str(r.get('id')), []).append(r)
        out = []
        for c in cast:
            answers = found.get(str(c.get('id'))) or []
            genders = {str(r['gender']).strip().lower() for r in answers}
            if len(genders) != 1:   # nothing clear, or the frames disagree: keep gender-neutral wording
                out.append(f"{c['descriptor']}: unclear" + (' (frames disagree)' if genders else ''))
                continue
            r, gender = answers[0], genders.pop()
            notes = re.sub(r';?\s*gender (?:is )?not (?:clearly )?visible\.?', '', c.get('notes') or '', flags=re.I).strip(' ;.')
            seen = f"clearly visible at {float(r.get('t') or 0):.0f} s: {str(r['evidence'])[:60]}"
            c['notes'] = f"{notes}; apparent gender: {gender} ({seen})".lstrip('; ')
            out.append(f"{c['descriptor']}: {gender}")
        return '; '.join(out)

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
        self.gap_beats = self.map_beats()
        per = Counter(g for ids in self.assignment.values() for g in ids)
        return f"{len(self.gap_beats)} gaps carry a story beat; {len(self.assignment)} of {len(self.timeline)} events inside narratable gaps; {len(self.timeline)-len(self.assignment)} in speech (context only); per gap {dict(sorted(per.items()))}"

    def map_beats(self):
        """Story arc -> gaps: a beat belongs to the home gap of its cited events, else to the gap containing its time.
        {gap_id: 'beat (why)'}; the script narrates that beat in story terms."""
        out = {}
        gaps = self.scriptable()
        for b in self.bible.get('beats', []):
            homes = [self.assignment[i][0] for i in b.get('events', []) if self.assignment.get(i)]
            if not homes:
                homes = [g['id'] for g in gaps if g['start'] - .5 <= b['t'] <= g['end'] + .5][:1]
            text = b['beat'] + (f" ({b['why']})" if b.get('why') else '')
            for gid in dict.fromkeys(homes):
                out[gid] = (out[gid] + '; ' + text) if gid in out else text
        return out

    def key_event(self, gid):
        """The gap's most distinctive event: importance, then a visible reaction/result, then a stated change."""
        ev = self.evidence_for(gid)
        best = max(ev, key=lambda e: (e['importance'], bool(REACTION.search(e['what'] + ' ' + e.get('change', ''))), bool(e.get('change'))), default=None)
        return best['id'] if best else None

    def is_routine(self, gid):
        """Its events only repeat the previous scriptable gap's activity: no beat, no stated change, no reaction, <= 3."""
        gaps = sorted(self.scriptable(), key=lambda g: g['start'])
        i = next((k for k, g in enumerate(gaps) if g['id'] == gid), 0)
        ev, prev = self.evidence_for(gid), self.evidence_for(gaps[i - 1]['id']) if i else []
        if not ev or not prev or gid in self.gap_beats:
            return False
        if any(e['importance'] > 3 or e.get('change') or REACTION.search(e['what']) for e in ev):
            return False
        here = {stem(w) for e in ev for w in content_tokens(e['what'])}
        there = {stem(w) for e in prev for w in content_tokens(e['what'])}
        return len(here & there) / max(1, len(here | there)) >= .5

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

    def word_limits(self, gids):
        """Round 7: one prominent line per gap ("gap 7 (2.1 s): 3-4 words, HARD max 4"); the writer overshot 24-29 for 19."""
        return [f"gap {g}: {self.target_words(self.gap(g))} words, HARD max {self.gap(g)['director_words_en']} "
                f"({self.gap(g)['end'] - self.gap(g)['start']:.1f} s)" for g in gids]

    def gap_payload(self, g, establish=None):
        return {'gap_id': g['id'], 'words': f"{self.target_words(g)} (HARD max {g['director_words_en']})",
                'start': round(g['start'], 2), 'end': round(g['end'], 2), 'max_words': g['director_words_en'],
                'target_words': self.target_words(g), 'evidence': [e['id'] for e in self.evidence_for(g['id'])],
                **({'establish': True} if (self.is_establishing(g['id']) if establish is None else establish) else {}),
                **({'beat': self.gap_beats[g['id']]} if g['id'] in self.gap_beats else {}),
                **({'key_event': k} if (k := self.key_event(g['id'])) else {}), **({'routine': True} if self.is_routine(g['id']) else {}),
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
        if not re.search(r'[.!?]["”\']?\s*$', text):
            problems.append(PUNCTUATION_PROBLEM + '. Fix: write a complete spoken sentence and add final punctuation')
        if not has_finite_verb(text):
            problems.append('English cue has no finite verb. Fix: write a complete sentence with who or what does the visible action')
        if words > self.hard_words(g):   # up to word_tolerance over max_words is judged by measured seconds (check_fit)
            problems.append(f"over budget: {words} words, max {g['director_words_en']}. Fix: cut at least {words - g['director_words_en']} words "
                            '(keep the subject and the main action; drop a secondary action, colours or positions)')
        problems += lint_with_hints(text) + [f'Banned phrasing: {why}' for rx, why in DIRECTOR_LINT if rx.search(text)]
        first = re.match(r'^\s*["“\']?([A-Za-z]+)\b(?:\s+)([A-Za-z]+)\b', text)
        if first:
            opener, following = first.group(1).lower(), first.group(2).lower()
            descriptors = tokens(' '.join(c.get('descriptor', '') for c in self.bible.get('cast', [])))
            objects = tokens(' '.join(str(o) for o in self.bible.get('objects', [])))
            known_nouns = VERB_OPENER_NOUNS | PERSON_NOUNS | descriptors | objects
            if opener.endswith(('s', 'es')) and following in VERB_OPENER_FOLLOWERS and opener not in known_nouns:
                problems.append('Banned phrasing: no subject (headline-style bare verb opener). Fix: start with who acts, '
                                'using the bible cast descriptor or a pronoun, and write a complete sentence')
        # Round 5 ("The cook rolls."): a cue must carry a concrete detail beyond who and the verb.
        cast_words = {stem(w) for w in tokens(' '.join(c.get('descriptor', '') for c in self.bible.get('cast', [])))}
        detail = {stem(w) for w in content_tokens(text)} - cast_words - PRONOUNS - {stem(w) for w in PERSON_NOUNS}
        if len(detail) < self.d['min_detail_words']:
            problems.append('Banned phrasing: no concrete detail (bare subject and verb). Fix: add what is acted on and the visible '
                            'result (the object, its new state), or skip the gap if nothing new is visible')
        problems += self.identity_problems(g, text)
        leaked = self.context_only_claims(text)
        if leaked:
            problems.append('Unverified title-only claim (' + ', '.join(leaked) + '). Fix: remove claims taken only from the title')
        if gid in self.restyle and opening(text) == self.restyle_pair:
            problems.append(f'Style: still opens with "{self.restyle_pair}". Fix: vary the opening (a pronoun, the object first, '
                            '"Now ...", or a participial phrase), keeping the same facts')
        cast = self.bible.get('cast') or []
        if len(cast) == 1:
            allowed = tokens(cast[0].get('descriptor', ''))
            drift = sorted((tokens(text) & PERSON_NOUNS) - allowed)
            if drift:
                problems.append(f'Banned phrasing: person descriptor drift ({", ".join(drift)}). Fix: refer to this person '
                                f'only as "{cast[0].get("descriptor", "the cast member")}" or with a pronoun')
        place_problem = []
        if self.is_establishing(gid):
            terms = place_terms(self.bible)
            if terms and not {stem(w) for w in tokens(text)} & terms:
                place = self.bible.get('place') or re.sub(r'^\s*(?:a|an|the)\s+', '', re.split(r'\b(?:with|where|in|inside|of|on|at)\b|,', self.bible.get('setting', ''), maxsplit=1)[0]).strip()
                who = ((self.bible.get('cast') or [{}])[0].get('descriptor')) or 'who is there'
                place_problem.append(f'{PLACE_PROBLEM}. Fix: open with where we are, e.g. idiomatic "Aboard ..." / "In a ..."; '
                                     f'name "{place}" and {who}, then the action, all within {g["director_words_en"]} words '
                                     '(drop a detail of the action rather than exceed it)')
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
        problems += place_problem
        hard, length, _ = classify(problems)
        self.last_fit = None
        if not hard:
            fit = self.check_fit(gid, text, 'en')   # renders with the real TTS voice: measured seconds, speech overlap
            measured = [p for p in fit['problems'] if not is_length(p)]
            self.last_fit = {'gid': gid, 'text': text, 'seconds': fit['seconds'], 'fits': not measured}
            new = measured if length else fit['problems']
            problems += [p if 'measured' in p or ('exceeds' not in p and 'too long' not in p) else f"{p} (measured {fit['seconds']:.1f} s)" for p in new]
        return valid, problems

    def context_only_claims(self, text):
        """Flag distinctive title words absent from perception; bible place/object nouns are accepted context."""
        if not self.context:
            return []
        title = {stem(w) for w in content_tokens(self.context)} - TITLE_GENERIC
        visible = {stem(w) for w in tokens(' '.join(e.get('what', '') + ' ' + e.get('on_screen_text', '') for e in self.timeline))}
        allowed = place_terms(self.bible) | {stem(w) for w in tokens(' '.join(map(str, self.bible.get('objects', []))))}
        used = {stem(w) for w in content_tokens(text)}
        return sorted(w for w in title & used - visible - allowed if len(w) >= 5 or w in {'first', 'last'})

    def identity_problems(self, g, text):
        """Bible object identity (Round 5, nasa_v2_r4 passed "the plant" around after the pepper harvest): from from_t on,
        an alias's head noun without the canonical name is flagged with the name to use."""
        out, words = [], {stem(w) for w in tokens(text)}
        for n in self.bible.get('names', []):
            if g['end'] < n['from_t']:
                continue
            head = [w for w in re.findall(r'\w+', n['name'].lower()) if w not in STOP][-1:]
            canon = {stem(w) for w in head}
            if not canon or canon & words:
                continue
            heads = sorted({stem(a.split()[-1]) for a in n['aliases'] if a.split()} - {stem(w) for w in re.findall(r'\w+', n['name'].lower())})
            used = [h for h in heads if h in words]
            if used:
                out.append(f'Banned phrasing: object identity ("{used[0]}" is "{n["name"]}" in the bible). Fix: call it "{n["name"]}"')
        return out

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
        """Apply a script/repair entry to one gap: skip, pending (passes every check, awaits verification) or failed.

        Round 7: punctuation is normalised first (never a drop). A text with no HARD problem whose measured speech fits the
        gap joins the gap's candidate pool even when it fails a soft (style) check or is somewhat over max_words; the final
        pass (st_rescue) verifies and keeps the best pooled candidate when repairs do not produce a clean cue."""
        if entry['skip']:
            if step != 'script' and self.pool_candidates(gid):
                self.log(gid, step=step, reason='writer skipped; the earlier candidate stays for the final pass')
                self.stats['skip_kept_candidate'] += 1
                return 'failed'
            self.skip_gap(gid, entry['reason'] or 'writer: nothing new')
            return 'skip'
        text = normalise_en(entry['text'])
        if text != ' '.join(str(entry['text']).split()):
            self.stats['punctuation_fixed'] += 1
        entry = {**entry, 'text': text}
        valid, problems = self.check_cue(gid, entry['text'], entry['evidence'])
        words, claimed = len(entry['text'].split()), entry.get('words_claimed')
        self.log(gid, step=step, text=entry['text'], evidence=entry['evidence'], problems=problems, words=words,
                 **({'words_claimed': claimed} if claimed is not None else {}))
        if claimed is not None and claimed != words:
            self.stats['self_count_mismatch'] += 1
        hard, length, soft = classify(problems)
        if not hard:
            self.add_candidate(gid, entry['text'], valid, length, soft)
        if problems:
            self.failed[gid] = {'text': entry['text'], 'evidence': entry['evidence'], 'valid': valid, 'reasons': problems}
            self.pending.pop(gid, None)
            self.stats['postcheck_failures'] += 1
            self.stats['hard_failures' if hard else 'length_failures' if length else 'soft_failures'] += 1
            return 'failed'
        if words > self.gap(gid)['director_words_en']:
            self.stats['accepted_within_tolerance'] += 1   # <= word_tolerance over max_words and the measured TTS fits
        self.pending[gid] = {'text': entry['text'], 'evidence': valid}
        self.failed.pop(gid, None)
        return 'pending'

    # ---------- candidate pool (Round 7) ----------
    def fallback_words(self, g):
        return math.floor(g['director_words_en'] * (1 + self.d['fallback_word_tolerance']) + 1e-9)

    def add_candidate(self, gid, text, evidence, length, soft):
        """Pool a text with no hard problem when its MEASURED speech fits the gap and it is within fallback_word_tolerance."""
        fit = self.last_fit or {}
        if fit.get('text') != text or fit.get('gid') != gid or not fit.get('fits') or not evidence:
            return False
        if len(text.split()) > self.fallback_words(self.gap(gid)):
            return False
        pool = self.pool.setdefault(gid, [])
        if all(c['text'] != text for c in pool):
            pool.append({'text': text, 'evidence': list(evidence), 'soft': list(soft), 'over': bool(length),
                         'words': len(text.split()), 'order': sum(len(v) for v in self.pool.values())})
        return True

    def pool_candidates(self, gid):
        """Unrefuted candidates, best first: fewest soft problems, within max_words, then the most recent."""
        bad = set(self.rejected.get(gid, []))
        return sorted((c for c in self.pool.get(gid, []) if c['text'] not in bad), key=lambda c: (len(c['soft']), c['over'], -c['order']))

    # ---------- stage: script ----------
    def mock_script(self, gaps):
        cues = []
        for g in gaps:
            ev = sorted(self.evidence_for(g['gap_id']), key=lambda e: -e['importance'])
            if not ev:
                cues.append({'gap_id': g['gap_id'], 'skip': True, 'reason': 'MOCK: no evidence'})
                continue
            e = ev[0]
            text = f'A sign reads "{e["on_screen_text"]}".' if e['on_screen_text'] else e['what']
            cues.append({'gap_id': g['gap_id'], 'text': ' '.join(text.split()[:g['max_words']]), 'evidence': [e['id']]})
        return {'cues': cues}

    def st_script(self):
        todo = sorted((g for g in self.scriptable() if g['id'] not in self.skipped), key=lambda g: g['start'])
        gaps = [self.gap_payload(g, establish=i == 0) for i, g in enumerate(todo)]
        if not gaps:
            return 'no gaps to script'
        data = {'WORD_LIMITS': self.word_limits([g['gap_id'] for g in gaps]), 'bible': self.bible, **self.title_payload(),
                'timeline': self.timeline_rows(self.assignment), 'gaps': gaps}
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

    def enforce_max_silence(self):
        """Route one informative writer-skipped gap per overlong silent run into the normal Ultra repair."""
        ordered = sorted((g for g in self.narratable() if g.get('director_words_en', 0) >= self.d['min_words']),
                         key=lambda g: g['start'])
        runs, current = [], []
        for g in ordered + [None]:
            if g is not None and g['id'] in self.skipped:
                current.append(g)
            else:
                if current:
                    runs.append(current)
                current = []
        rescued = []
        hint = ('write one cue adding a concrete, not-yet-mentioned visible detail (appearance, setting, object, result); '
                'never repeat earlier cues')
        mentioned = {eid for c in (*self.cues.values(), *self.pending.values()) for eid in c.get('evidence', [])}
        for run in runs:
            span = run[-1]['end'] - run[0]['start']
            if span <= self.d['max_silent_run_s']:
                continue
            candidates = [g for g in run if self.evidence_for(g['id'])]
            if not candidates:
                continue
            g = max(candidates, key=lambda x: (sum(e['id'] not in mentioned for e in self.evidence_for(x['id'])),
                                                x['end'] - x['start']))
            gid = g['id']
            evidence = [e['id'] for e in self.evidence_for(gid)]
            self.silence_rescued[gid] = self.dropped.get(gid, 'silent: writer: nothing new')
            self.skipped.pop(gid, None)
            self.dropped.pop(gid, None)
            self.failed[gid] = {'text': '', 'evidence': evidence, 'valid': evidence,
                                'reasons': [f'Maximum silent run exceeded ({span:.1f}s > {self.d["max_silent_run_s"]}s). Fix: {hint}']}
            self.log(gid, step='max_silence', problems=self.failed[gid]['reasons'])
            self.stats['max_silence_rescued'] += 1
            rescued.append(gid)
        return rescued

    # ---------- stage: tighten (Nano; before any Ultra repair) ----------
    def budget_only(self, gid):
        """Over max_words and nothing HARD (soft style problems may ride along): Nano can shorten it."""
        hard, length, _ = classify((self.failed.get(gid) or {}).get('reasons') or [])
        measured = [p for p in hard if any(b in p for b in BUDGET_PROBLEMS)]   # measured too long: also fixed by shortening
        return bool(length or measured) and len(measured) == len(hard)

    def tighten_reject(self, gid, old, text):
        """Why a Nano rewrite is unusable (None if usable): not shorter, invents content, or loses the establishing place."""
        if not text:
            return 'no shorter version returned'
        if len(text.split()) >= len(old.split()):
            return f'not shorter ({len(text.split())} words, was {len(old.split())}); rejected'
        added = {lemma(w) for w in content_tokens(text)} - {lemma(w) for w in content_tokens(old)}
        if len(added) > 1:
            return f'tighten added new words {sorted(added)}; rejected'
        terms = place_terms(self.bible) if self.is_establishing(gid) else set()
        if terms & {stem(w) for w in tokens(old)} and not terms & {stem(w) for w in tokens(text)}:
            return 'tighten dropped the place from the establishing cue; rejected'
        return None

    def tighten_target(self, gid, text):
        """Words Nano must reach: max_words, or fewer when the measured voice says the text cannot fit even at max_words."""
        g, words = self.gap(gid), len(text.split())
        fit = self.last_fit if (self.last_fit or {}).get('text') == text else None
        target = g['director_words_en']
        if fit and fit['seconds'] > 0:
            target = min(target, max(self.d['min_words'], int(words * self.allowed_seconds(g) / fit['seconds'])))
        return max(1, target)

    def st_tighten(self, step):
        """Cues whose only blocking problem is length go to Nemotron Nano first, one cue per call, with the cue's word count, the
        exact target (max_words, or fewer if the measured voice needs it) and the measured seconds. Round 7: Nano returns up to
        three shorter options; the best one (no hard problem, then within max_words, then fewest soft problems) is applied.
        An option that is not shorter, adds content words or loses the establishing place is rejected. Up to
        director.tighten_attempts calls per cue; still over budget afterwards -> Ultra repair (verify_and_repair)."""
        outcome = Counter()
        for g in sorted((g for g in self.failed if self.budget_only(g)), key=lambda g: self.gap(g)['start']):
            for attempt in range(max(1, int(self.d['tighten_attempts']))):
                old = self.failed[g]['text']
                evidence = self.failed[g]['evidence']
                words = len(old.split())
                self.check_cue(g, old, evidence)   # refresh the measured seconds of the current text
                max_w = self.tighten_target(g, old)
                terms = sorted(place_terms(self.bible) & {stem(w) for w in tokens(old)}) if self.is_establishing(g) else []
                fit = self.last_fit if (self.last_fit or {}).get('text') == old else None
                cue = {'gap_id': g, 'text': old, 'words': words, 'max_words': max_w, 'remove_at_least': max(1, words - max_w),
                       **({'measured_seconds': round(fit['seconds'], 2), 'allowed_seconds': self.allowed_seconds(self.gap(g))} if fit else {}),
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
                best = None
                for option in parse_tightened_options(raw, g) or ['']:
                    text = normalise_en(option)
                    why = self.tighten_reject(g, old, text)
                    if why:
                        self.log(g, step=step, text=text, problems=[why])
                        continue
                    hard, length, soft = classify(self.check_cue(g, text, evidence)[1])
                    rank = (len(hard), len(length), len(soft))
                    if best is None or rank < best[0]:
                        best = (rank, text)
                if best is None:
                    outcome['rejected'] += 1
                    continue
                result = self.consider(g, {'text': best[1], 'evidence': evidence, 'skip': False, 'reason': ''}, step)
                if result != 'failed' or not self.budget_only(g):
                    outcome[result] += 1   # pending, or a non-length problem now: Ultra repair / the final pass handles it
                    break
            else:
                outcome['still_over'] += 1
        self.stats['tightened'] += outcome['pending']
        return f'over-budget cues shortened by Nano (one cue per call, up to 3 options, <= {self.d["tighten_attempts"]} attempts): {dict(outcome)}'

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
        if p.get('rescued'):
            self.stats['rescued'] += 1
            self.stats['soft_kept'] += bool(p.get('soft'))
            self.stats['length_fallback'] += bool(p.get('over'))
        self.cues[gid] = {**self.gap(gid), 'en': p['text'], 'evidence': p['evidence'], 'verdict': verdict}
        self.verified[gid] = verdict
        self.dropped.pop(gid, None)
        self.log(gid, step='commit', verdict=verdict, reason=reason)

    def st_verify(self, gids):
        gids = [g for g in gids if g in self.pending]
        tally = Counter()
        for k in range(0, len(gids), max(1, self.d['verify_batch'])):
            batch = gids[k:k + self.d['verify_batch']]
            def verify_payload(ids):
                data = {'duration': 0, 'cues': [{'gap_id': g, 'text': self.pending[g]['text'], 'frame_times': self.frame_times(g)} for g in ids],
                        **({'object_names': self.bible['names']} if self.bible.get('names') else {})}
                media = None
                if not self.mock:
                    media = []
                    for g in ids:
                        media.append({'type': 'text', 'text': f'Frames for cue gap_id {g}:'})
                        media += separate_frames(self.path, self.frame_times(g))
                return data, media
            data, media = verify_payload(batch)
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
                missing = [g for g in batch if g not in verdicts]
                if missing:
                    retry_data, retry_media = verify_payload(missing)
                    retry_mock = {'verdicts': [r for r in mock['verdicts'] if r['gap_id'] in missing]}
                    try:
                        retry_raw = self.model('verify', 'perceive', P.VERIFY, retry_data, retry_media, retry_mock if self.mock else None)
                        retry_rows = retry_raw.get('verdicts', retry_raw.get('cues', [])) if isinstance(retry_raw, dict) else retry_raw if isinstance(retry_raw, list) else []
                        for r in retry_rows:
                            try:
                                rgid = int(r.get('gap_id', r.get('id')))
                                if rgid in missing:
                                    verdicts[rgid] = r
                            except (TypeError, ValueError, AttributeError):
                                pass
                    except (BudgetExceeded, TimeoutError):
                        raise
                    except Exception as exc:
                        self.report['issues'].append(f'Verification retry unavailable for gaps {missing}: {sanitize(exc)}')
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
                    if wrong:   # Round 7: repair only the wrong detail (roti r6b lost its establishing cue over "black gloves")
                        why += f'. Fix: remove or correct only "{wrong}" and keep the rest of the cue' + (' (keep the place)' if self.is_establishing(g) else '')
                    self.failed[g] = {**self.pending.pop(g), 'reasons': [why], 'refuted': refuted, 'wrong': wrong}
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

    def repairable(self):
        """Failed gaps worth an Ultra repair: anything with a hard or length problem, and soft-only (style) failures once."""
        return sorted((g for g, f in self.failed.items() if not (g in self.soft_tried and all(is_soft(r) for r in f['reasons']))),
                      key=lambda i: self.gap(i)['start'])

    def st_repair(self, round_no):
        gids = self.repairable()
        self.soft_tried.update(g for g in gids if all(is_soft(r) for r in self.failed[g]['reasons']))
        items = [{**self.gap_payload(self.gap(g)), 'rejected_text': self.failed[g]['text'], 'rejected_words': len(self.failed[g]['text'].split()),
                  'why_rejected': self.failed[g]['reasons'],
                  'trusted_evidence': [r for r in self.timeline_rows() if g in self.assignment.get(r['id'], ())], **self.neighbours(g),
                  **({'other_openings': self.other_openings(g)} if g in self.restyle else {})} for g in gids]
        bible = {k: self.bible.get(k) for k in ('setting', 'place', 'cast', 'objects', 'names', 'goal', 'story')}
        mock = {'cues': [{'gap_id': g, 'skip': True, 'reason': 'MOCK repair: nothing reliable'} for g in gids]}
        data = {'WORD_LIMITS': self.word_limits(gids), 'bible': bible, **self.title_payload(), 'round': round_no, 'gaps': items}
        parsed = parse_cues(self.model('repair', self.d['ultra_stage'], P.REPAIR, data, None, mock if self.mock else None, ultra=True))
        outcome = Counter()
        for g in gids:
            if g in parsed:
                outcome[self.consider(g, parsed[g], f'repair_{round_no}')] += 1
            else:
                outcome['unanswered'] += 1
        self.stats['repair_rounds'] = round_no
        return f'round {round_no}: {len(gids)} failed cues sent to Ultra: {dict(outcome)}'

    def other_openings(self, gid):
        return [opening(t) for _, g, t in self.accepted_texts(gid)][:12]

    def restyle_openings(self):
        """Track-level opening variety (Round 5, roti_v2_r4: 9 of 10 cues began "The cook ..."). When one two-word opening
        starts more than director.openings_max_share of the committed cues, every other later occurrence (the first is kept)
        goes back to Ultra in the existing batched repair with a "vary the opening" hint. Soft: the verified original is
        restored if the rewrite does not pass every check and verification. Returns the gap ids sent."""
        cues = sorted(self.cues.values(), key=lambda c: c['start'])
        if len(cues) < self.d['openings_min_cues']:
            return []
        pairs = [opening(c['en']) for c in cues]
        pair, n = Counter(pairs).most_common(1)[0]
        allowed = math.floor(len(cues) * self.d['openings_max_share'])
        if not pair or n <= allowed:
            return []
        later = [c['id'] for c, p in zip(cues, pairs) if p == pair][1:]
        pick = (later[::2] + later[1::2])[:n - allowed]
        self.restyle_pair = pair
        why = (f'Style: {n} of {len(cues)} cues open with "{pair}". Fix: vary the opening - a pronoun, the object or result first, '
               '"Now ..." or a participial phrase; keep the same facts, or skip if the cue only repeats its neighbours')
        for g in pick:
            c = self.cues.pop(g)
            self.restyle.add(g)
            self.restyle_keep[g] = c
            self.failed[g] = {'text': c['en'], 'evidence': c['evidence'], 'valid': c['evidence'], 'reasons': [why]}
            self.log(g, step='restyle', text=c['en'], problems=[why])
        self.stats['restyled'] += len(pick)
        return pick

    def restore_restyled(self, include_pending=False):
        """A restyle that still fails keeps the verified original (style is never worth losing a verified cue)."""
        for g in [g for g in (*self.failed, *(self.pending if include_pending else ())) if g in self.restyle_keep and g not in self.cues]:
            self.failed.pop(g, None)
            self.pending.pop(g, None)
            self.cues[g] = self.restyle_keep[g]
            self.dropped.pop(g, None)
            self.log(g, step='restyle_kept', text=self.cues[g]['en'], reason='rewrite did not pass; verified original kept')
            self.stats['restyle_kept'] += 1

    def verify_and_repair(self):
        self.enforce_max_silence()
        todo = list(self.pending)
        for round_no in range(self.d['max_repair_rounds'] + 1):
            if todo:
                self.stage('verify' if round_no == 0 else f'verify_{round_no}', lambda: self.st_verify(todo), f'{len(todo)} cues, {self.d["verify_frames"]} stills each')
            # One Ultra call is kept for the Hindi track: a style-only repair must not starve it.
            reserve = 1 if 'hi' in self.langs else 0
            if round_no == 0 and self.d['max_repair_rounds'] and self.ultra_calls + 1 + reserve <= self.d['max_ultra_calls']:
                self.restyle_openings()
            if not self.repairable() or round_no == self.d['max_repair_rounds']:
                break
            # Length failures Nano could not fix ARE repairable: Ultra rewrites them with the word count and the Fix hint.
            if self.ultra_calls >= self.d['max_ultra_calls']:
                self.report['issues'].append('Ultra call cap reached: no further repair')
                break
            before = set(self.pending)
            self.stage(f'repair_{round_no+1}', lambda: self.st_repair(round_no + 1), f'{len(self.repairable())} failed cues')
            self.maybe_tighten(f'tighten_{round_no+1}')
            todo = [g for g in self.pending if g not in before]
        self.restore_restyled()
        if self.failed:
            self.stage('rescue', self.st_rescue, f'{len(self.failed)} gaps still failing -> best pooled candidate / Nano strike, Super VL verify')
        for g, f in list(self.failed.items()):
            prefix = 'dropped (still over budget after Nano tighten and Ultra repair): ' if self.budget_only(g) else 'dropped after repair: '
            self.failed.pop(g)
            if g in self.silence_rescued:   # a failed max-silence rescue is soft: the gap stays silent by choice
                self.skipped[g] = True
                self.drop_gap(g, self.silence_rescued[g])
                self.log(g, step='silence_kept', reason='max-silence rescue did not produce a verified cue')
                self.stats['silence_rescue_failed'] += 1
                continue
            self.drop_gap(g, prefix + '; '.join(f['reasons'])[:200])
            self.log(g, step='drop', reason='; '.join(f['reasons']))
            self.stats['dropped_after_repair'] += 1
        long_enough = [g for g in self.narratable() if g.get('director_words_en', 0) >= self.d['min_words'] and g['id'] not in self.skipped]
        first = min(long_enough, key=lambda g: g['start'], default=None)
        if first and first['id'] not in self.cues:
            self.report['issues'].append(f"Establishing gap {first['id']} has no verified cue")

    def strike(self, gid):
        """Nano removes the phrase the verifier quoted as wrong; the rest stays Nemotron's words. Accepted only if it adds no
        content word and the wrong phrase is gone."""
        f = self.failed[gid]
        old, wrong = f.get('text') or '', f.get('wrong') or ''
        if not old or not wrong:
            return None
        cue = {'gap_id': gid, 'text': old, 'wrong': wrong, 'max_words': self.gap(gid)['director_words_en'],
               **({'keep_place': sorted(place_terms(self.bible) & {stem(w) for w in tokens(old)})} if self.is_establishing(gid) else {})}
        mock = {'text': re.sub(r'\s+([,.!?])', r'\1', old.replace(wrong, '').replace(', .', '.')).strip()}
        try:
            raw = self.model('tighten', self.d['tighten_stage'], P.STRIKE, {'cue': cue, '_max_tokens': self.d['tighten_max_tokens']},
                             None, mock if self.mock else None)
        except (BudgetExceeded, TimeoutError):
            raise
        except Exception as exc:
            self.report['issues'].append(f'Nano strike unavailable for gap {gid}: ' + sanitize(exc))
            return None
        text = normalise_en(parse_tightened(raw, gid))
        added = {lemma(w) for w in content_tokens(text)} - {lemma(w) for w in content_tokens(old)}
        wt = {lemma(w) for w in content_tokens(wrong)}
        kept = wt & {lemma(w) for w in content_tokens(text)}
        if not text or added or (wt and len(kept) / len(wt) > .5) or len(text.split()) >= len(old.split()):
            self.log(gid, step='strike', text=text, problems=[f'strike rejected (added {sorted(added)}, kept {sorted(kept)})'])
            return None
        return text

    def st_rescue(self):
        """Round 7 final pass, no Ultra call. For every gap still failing after the repair rounds: (1) if the last text was
        contradicted on a quoted detail and no candidate is pooled, Nano strikes just that detail; (2) the best pooled
        candidate (no hard problem, measured speech fits, fewest soft problems) is re-checked against the current track and
        verified on stills. Supported cues are committed; up to director.rescue_verify_rounds verification rounds."""
        outcome, strikes, before = Counter(), 0, set(self.cues)
        for g in sorted(self.failed, key=lambda i: self.gap(i)['start']):
            if not self.pool_candidates(g) and self.failed[g].get('wrong') and strikes < self.d['rescue_strike_max']:
                strikes += 1
                text = self.strike(g)
                if text:
                    outcome['strike_' + self.consider(g, {'text': text, 'evidence': self.failed[g]['evidence'], 'skip': False, 'reason': ''}, 'strike')] += 1
        tried = {}
        for _ in range(max(1, int(self.d['rescue_verify_rounds']))):
            batch = [g for g in self.pending]
            for g in sorted(self.failed, key=lambda i: self.gap(i)['start']):
                for c in self.pool_candidates(g):
                    if c['text'] in tried.setdefault(g, set()):
                        continue
                    tried[g].add(c['text'])
                    valid, problems = self.check_cue(g, c['text'], c['evidence'])
                    hard, length, soft = classify(problems)
                    fits = (self.last_fit or {}).get('fits') and len(c['text'].split()) <= self.fallback_words(self.gap(g))
                    if hard or not valid or (length and not fits):
                        continue
                    self.failed.pop(g)
                    self.pending[g] = {'text': c['text'], 'evidence': valid, 'soft': soft, 'over': bool(length), 'rescued': True}
                    self.log(g, step='rescue', text=c['text'], problems=soft + length)
                    batch.append(g)
                    break
            if not batch:
                break
            self.st_verify(batch)
            outcome['verified'] += len(batch)
        outcome['committed'] = len(set(self.cues) - before)
        for g in list(self.pending):   # never left pending after the last round
            self.failed[g] = {**self.pending.pop(g), 'reasons': ['not verified in the final pass']}
        return f'final pass (no Ultra): {strikes} Nano strikes; {dict(outcome)}; soft-kept {self.stats["soft_kept"]}, length fallback {self.stats["length_fallback"]}'

    # ---------- stage: hindi ----------
    def hi_problems(self, gid, text):
        if not isinstance(text, str) or not text.strip():
            return ['missing Hindi'], 0, None
        if not re.search('[\u0900-\u097f]', text):
            return ['Hindi must be Devanagari, no Latin words'], 0, None
        latin = re.findall(r'[A-Za-z]{3,}(?:\s+[A-Za-z]+)*', text)
        if latin:   # nasa_v2_r4 gap 5: an on-screen label ("HATCH CHILE") kept in Latin letters, mis-reported as over budget
            return [f'Latin letters ("{latin[0].strip()}"). Fix: write these words in Devanagari letters (transliterate the label or sign)'], 0, None
        if '\n' in text or '-->' in text:
            return ['must be one line'], 0, None
        fit = self.check_fit(gid, text, 'hi')
        return ([] if fit['ok'] else fit['problems']), fit['seconds'], fit['suggested_max_words']

    @staticmethod
    def normalise_hindi(text):
        """Punctuation-only normalisation; model-written words remain untouched."""
        text = str(text or '').strip()
        return text if not text or text.endswith('।') else text + '।'

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
        texts = {g: self.normalise_hindi(v['text']) for g, v in parse_hi(got).items()}
        failing, kinds = [], Counter()
        for r in rows:
            problems, seconds, suggested = self.hi_problems(r['gap_id'], texts.get(r['gap_id']))
            if problems:
                kinds.update(self.hi_kind(p) for p in problems)
                failing.append({**r, 'hi_previous': texts.get(r['gap_id'], ''), 'problem': problems, 'measured_seconds': round(seconds, 2),
                                'allowed_seconds': allowed(self.cues[r['gap_id']]), 'max_words': max(1, min(r['max_words'], suggested or r['max_words']))})
            else:
                self.cues[r['gap_id']]['hi'] = texts[r['gap_id']]
        style = self.hi_style_failures(cues)
        kinds['passive'] += len(style)
        failing += [{**r, 'hi_previous': self.cues[r['gap_id']]['hi'], 'problem': [style[r['gap_id']]], 'soft': True,
                     'allowed_seconds': allowed(self.cues[r['gap_id']])} for r in rows if r['gap_id'] in style]
        refit = 0
        if failing:
            try:
                send = [{k: v for k, v in r.items() if k != 'soft'} for r in failing]
                got = self.model('hindi', self.d['ultra_stage'], P.HINDI_REFIT, {'bible': bible, 'cast_gender': gender, 'cues': send}, None, mock_hi(failing) if self.mock else None, ultra=True)
                texts = {g: self.normalise_hindi(v['text']) for g, v in parse_hi(got).items()}
                for r in failing:
                    new = texts.get(r['gap_id'])
                    problems = self.hi_problems(r['gap_id'], new)[0]
                    # A soft (passive-chain) refit must also be less passive; otherwise the fitting original stays.
                    if not problems and (not r.get('soft') or hi_passives(new) < hi_passives(r['hi_previous'])):
                        self.cues[r['gap_id']]['hi'] = new
                        refit += 1
            except (BudgetExceeded, TimeoutError):
                raise
            except Exception as exc:
                self.report['issues'].append('Hindi refit unavailable: ' + (str(exc) if isinstance(exc, UltraCapReached) else sanitize(exc)))
        missing = [c['id'] for c in cues if not c.get('hi')]
        if missing:
            self.report['issues'].append(f'hi: no fitting Hindi for gaps {missing}; English kept')
        self.translation_done = True
        self.stats['hi_refit'] += refit
        why = ', '.join(f'{k} {v}' for k, v in sorted(kinds.items()) if v) or 'none'
        return f'{len(cues)} cues written in Hindi in one call; {len(failing)} failed checks ({why}) -> {refit} refit; {len(missing)} without Hindi'

    @staticmethod
    def hi_kind(problem):
        p = problem.lower()
        return 'latin' if 'latin' in p else 'missing' if 'missing' in p else 'over budget' if any(k in p for k in ('exceed', 'too long', 'budget', 'overlap')) else 'other'

    def hi_style_failures(self, cues):
        """Soft Hindi style (Round 5, roti_v2_r4 was ten passive lines): a line with more than one passive, and, when more
        than director.hi_passive_share of the lines use a passive, every other further passive line. {gap_id: problem}."""
        lines = [(c['id'], c['hi']) for c in cues if c.get('hi')]
        fix = 'Fix: active voice with a noun subject - the hands ("हाथ ..."), the object or a group - at most one passive per line'
        out = {g: f'passive chain ({hi_passives(t)} passives). {fix}' for g, t in lines if hi_passives(t) > 1}
        passive = [g for g, t in lines if hi_passives(t)]
        allowed = math.floor(len(lines) * self.d['hi_passive_share'])
        if len(lines) >= 3 and len(passive) > allowed:
            rest = [g for g in passive if g not in out]   # lines already flagged above count as being fixed
            for g in (rest[1::2] + rest[::2])[:len(passive) - allowed - (len(passive) - len(rest))]:
                out[g] = f'too many passive lines ({len(passive)} of {len(lines)}). {fix}'
        return out

    def cast_gender(self):
        """Per cast member: the visible gender from the bible notes, or 'not visible -> gender-neutral Hindi'."""
        out = {}
        for c in self.bible.get('cast', []):
            notes = (c.get('notes') or '').lower()
            m = None if re.search(r'not (?:clearly )?visible|unknown|unclear', notes) else re.search(r'\b(woman|female|girl|man|male|boy)\b', notes)
            out[c['descriptor']] = (('feminine' if m.group(1) in ('woman', 'female', 'girl') else 'masculine') + ' (visible)') if m else \
                NEUTRAL
        return out or {'people': NEUTRAL}

    # ---------- stage: render + report ----------
    def st_render(self):
        for gid, c in list(self.cues.items()):
            # Measured speech is authoritative here: a final-pass cue may be within fallback_word_tolerance over max_words.
            if [p for p in self.check_fit(gid, c['en'], 'en')['problems'] if not is_length(p)] or len(c['en'].split()) > self.fallback_words(c):
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
        self.preflight_tts()   # raises before any paid API call
        try:
            self.stage('gaps', self.st_gaps, 'Silero VAD speech intervals; slots <= max_slot_s; budgets from measured TTS')
            if self.scriptable():
                self.stage('shots', self.st_shots, 'ffmpeg scene-change detection')
                self.stage('scene', self.st_scene, f"Super VL on {self.cfg['agent'].get('scene_frames', 6)} stills across the clip")
                self.stage('timeline', self.st_timeline, 'Super VL video windows covering the whole clip')
                self.stage('zoom', self.st_zoom, 'Super VL crops to hand-and-object activity where the wide shot is vague')
                self.stage('bible', self.st_bible, 'scene + shots + timeline')
                self.stage('cast_look', self.st_cast_look, 'Super VL apparent gender per cast member, only when clearly visible')
                if self.bible.get('look_for') and self.d['relook_max']:
                    self.stage('relook', self.st_relook, 'Super VL on windows where the bible expects an unseen beat')
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
            self.restore_restyled(include_pending=True)
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
        L.append(f"- **Round 7 robustness:** punctuation fixed {self.stats.get('punctuation_fixed', 0)} · final pass rescued {self.stats.get('rescued', 0)} "
                 f"(soft-kept {self.stats.get('soft_kept', 0)}, length fallback {self.stats.get('length_fallback', 0)}) · failed silence rescues back to silent {self.stats.get('silence_rescue_failed', 0)}")
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
              '- **Beats:** ' + '; '.join(f"{x['t']:.0f}s {x['beat']}" + (f" ({x['why']})" if x.get('why') else '') + (f" [{', '.join(x['events'])}]" if x.get('events') else '')
                                          for x in b.get('beats', [])),
              '- **Object names:** ' + ('; '.join(f"{n['name']} (not {', '.join(n['aliases'])}; from {n['from_t']:.0f}s)" for n in b.get('names', [])) or '—'),
              '- **Looked for again:** ' + ('; '.join(f"{x['t_start']:.0f}-{x['t_end']:.0f}s {x['what']}" for x in b.get('look_for', [])) or '—'),
              '- **Beats per gap:** ' + ('; '.join(f'gap {g}: {t}' for g, t in sorted(self.gap_beats.items())) or '—')]
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
