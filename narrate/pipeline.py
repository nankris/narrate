import json
import os
import tempfile
import time
import warnings
from pathlib import Path
from .config import load_config
from .llm import Client, MockClient, SpendGuard, BudgetExceeded
from .media import probe, detect_gaps, word_budget, scheduled, write_texts
from .perception import perceive
from .tts import backend, render_cue, mix


def run(path, out_dir, langs=('en', 'hi'), client=None, budget=None, progress=None, config=None):
    """Run synchronously; progress receives stage/status dicts. Budget failures save report."""
    cfg = config or load_config()
    path, out = Path(path).resolve(), Path(out_dir).resolve()
    if isinstance(langs, str):
        langs = langs.split(',')
    if not langs or any(x not in ('en', 'hi') for x in langs):
        raise ValueError('Supported languages: en,hi')
    out.mkdir(parents=True, exist_ok=True)
    guard = budget if isinstance(budget, SpendGuard) else SpendGuard(cfg['budget_usd'] if budget is None else budget)
    if client is None:
        if not os.environ.get('NEBIUS_API_KEY'):
            warnings.warn('NEBIUS_API_KEY missing: using deterministic MOCK; descriptions are not visual analysis.')
            client = MockClient(cfg, guard)
        else:
            client = Client(cfg, guard)
    client.guard = guard
    report = {'status': 'running', 'mock': client.mock, 'models': {s: cfg['models'][s]['id'] for s in ('perceive', 'fit', 'edit')}, 'latency_s': {}, 'cues_dropped': 0, 'overlaps_with_speech': 0, 'issues': [], 'tts': []}
    def stage(name, fn):
        if progress:
            progress({'stage': name, 'status': 'started'})
        start = time.monotonic()
        try:
            return fn()
        finally:
            report['latency_s'][name] = time.monotonic() - start
            if progress:
                progress({'stage': name, 'status': 'finished'})
    try:
        duration, has_audio = stage('probe', lambda: probe(path))
        if duration > cfg['max_duration'] or duration <= 0:
            raise ValueError(f"Duration must be within 0..{cfg['max_duration']} seconds")
        report['duration_s'] = duration
        with tempfile.TemporaryDirectory(prefix='.narrate-', dir=out) as temp:
            work = Path(temp)
            events, strategy, fallback = stage('perceive', lambda: perceive(path, work, duration, cfg, client))
            report.update(perception_strategy=strategy, perception_fallback=fallback)
            gaps = stage('gaps', lambda: detect_gaps(path, duration, has_audio, cfg))
            report['gaps'] = gaps
            slots = []
            for i, g in enumerate(gaps):
                # Guard against detector rounding and frame-boundary audio transitions.
                start, end = g['start'] + .08, g['end'] - .08
                b = word_budget(end - start, cfg['words_per_second']['en'], cfg['word_margin'])
                if b < 1:
                    report['cues_dropped'] += 1
                    continue
                slots.append({'id': i, 'start': start, 'end': end, 'budget': b, 'hi_budget': word_budget(end-start, cfg['words_per_second']['hi'], cfg['word_margin']), 'events': sorted([e for e in events if e['t_start'] < end], key=lambda e: (e['importance'], e['t_end']), reverse=True)[:5]})
            def fit():
                if not slots:
                    return []
                request = {'instruction': 'Return JSON {cues:[{id,en}]}. Write concise audio description for each gap from supplied events, prioritize current/overlapping events. Never invent facts. At most budget whitespace-separated words. No we see.', 'gaps': slots}
                response = client.call('fit', request)
                by_id = {c['id']: c['en'] for c in response['cues'] if isinstance(c.get('en'), str)}
                invalid = [s for s in slots if len(by_id.get(s['id'], '').split()) > s['budget']]
                if invalid:
                    retry = client.call('fit', {**request, 'gaps': [{**s, 'budget': max(1, s['budget'] - 2)} for s in invalid]})
                    by_id.update({c['id']: c['en'] for c in retry['cues'] if isinstance(c.get('en'), str)})
                    report['issues'].append('Retried over-budget Nano cues')
                cues = []
                for s in slots:
                    words = by_id.get(s['id'], '').split()
                    if len(words) > s['budget']:
                        report['issues'].append(f"Truncated Nano cue {s['id']}")
                    text = ' '.join(words[:s['budget']]).replace('-->', '→')
                    if text:
                        cues.append({**s, 'en': text})
                    else:
                        report['cues_dropped'] += 1
                return cues
            cues = stage('fit', fit)
            def edit():
                if not cues:
                    return
                try:
                    response = client.call('edit', {'instruction': 'Return JSON {cues:[{id,en,hi}]}. Polish English, consistent names and present tense, no we see. Translate every cue into Hindi. Each en <= budget words; hi <= hi_budget whitespace-separated words. Preserve all ids.', 'cues': cues})
                    edited = {c['id']: c for c in response['cues']}
                    for c in cues:
                        e = edited[c['id']]
                        for lang, limit in (('en', c['budget']), ('hi', c['hi_budget'])):
                            if not isinstance(e[lang], str) or not 0 < len(e[lang].split()) <= limit or '\n' in e[lang] or '-->' in e[lang]:
                                raise ValueError('Invalid edited cue')
                    for c in cues:
                        c.update({lang: edited[c['id']][lang] for lang in ('en', 'hi')})
                except BudgetExceeded:
                    raise
                except Exception:
                    report['issues'].append('Ultra failed validation/request; retained English; Hindi cues unavailable')
            stage('edit', edit)
            report['overlaps_with_speech'] = sum(not scheduled(c, gaps) for c in cues)
            if report['overlaps_with_speech']:
                raise ValueError('Cue escaped its silent gap')
            engine = backend(cfg['tts'])
            coverage = {}
            for lang in langs:
                selected = [c for c in cues if c.get(lang)]
                if len(selected) < len(cues):
                    report['issues'].append(f'{lang}: {len(cues)-len(selected)} cues unavailable')
                wavs = []
                def speech():
                    for i, c in enumerate(selected):
                        wav, details = render_cue(engine, c, lang, work, i)
                        wavs.append(wav)
                        report['tts'].append(details)
                stage(f'tts_{lang}', speech)
                stage(f'mix_{lang}', lambda: mix(path, out / f'narrated_{lang}.mp4', duration, has_audio, selected, wavs, cfg['ducking_level']))
                write_texts(out, lang, selected)
                coverage[lang] = 100 * sum(c['end']-c['start'] for c in selected) / max(1e-9, sum(g['duration'] for g in gaps))
            report['gap_coverage_percent'] = coverage
            report['cues'] = [{k: v for k, v in c.items() if k != 'events'} for c in cues]
            report['status'] = 'complete'
    except BudgetExceeded:
        report['status'] = 'budget_exceeded'
        raise
    except Exception as exc:
        report['status'] = 'failed'
        report['error_type'] = type(exc).__name__
        raise
    finally:
        report['usage'] = client.usage
        report['estimated_cost_usd'] = guard.spent
        (out / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    return report
