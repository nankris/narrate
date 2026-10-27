import json
import os
import tempfile
import time
import warnings
from pathlib import Path
from .config import load_config, resolve_provider
from .llm import Client, MockClient, SpendGuard, BudgetExceeded
from .media import probe, detect_gaps, word_budget, scheduled, write_texts
from .perception import perceive
from .tts import backend, render_cue, mix


def run(path, out_dir, langs=('en', 'hi'), client=None, budget=None, progress=None, config=None, provider=None, strict=False):
    """Run synchronously; progress receives stage/status dicts. Budget failures save report."""
    cfg = resolve_provider(config or load_config(), provider)
    path, out = Path(path).resolve(), Path(out_dir).resolve()
    if isinstance(langs, str):
        langs = langs.split(',')
    if not langs or any(x not in ('en', 'hi') for x in langs):
        raise ValueError('Supported languages: en,hi')
    out.mkdir(parents=True, exist_ok=True)
    guard = budget if isinstance(budget, SpendGuard) else SpendGuard(cfg['budget_usd'] if budget is None else budget)
    requested_provider = cfg['provider']
    if client is None:
        if requested_provider == 'mock':
            client = MockClient(cfg, guard)
        elif not os.environ.get(cfg['key_env']):
            if strict:
                raise RuntimeError(cfg['key_env'] + ' missing in strict mode')
            warnings.warn(cfg['key_env'] + ' missing: using deterministic MOCK; descriptions are not visual analysis.')
            client = MockClient(cfg, guard)
        else:
            client = Client(cfg, guard)
    client.guard = guard
    client.config = cfg
    client.raw_dir = out / 'raw'
    from urllib.parse import urlparse
    report = {'status': 'running', 'mock': client.mock, 'provider': 'mock' if client.mock else requested_provider, 'requested_provider':requested_provider, 'dev_only':requested_provider == 'nvidia-dev', 'base_url_host':None if client.mock else urlparse(cfg['base_url']).hostname, 'models': {}, 'latency_s': {}, 'cues_dropped': 0, 'overlaps_with_speech': 0, 'issues': [], 'tts': []}
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
            report.update(perception_strategy=strategy, perception_fallback=fallback, **getattr(client, "perception_details", {}))
            gaps = stage('gaps', lambda: detect_gaps(path, duration, has_audio, cfg))
            report['gaps'] = gaps
            slots = []
            assigned = set()
            for i, g in enumerate(gaps):
                # Guard against detector rounding and frame-boundary audio transitions.
                start, end = g['start'] + .08, g['end'] - .08
                b = word_budget(end - start, cfg['words_per_second']['en'], cfg['word_margin'])
                if b < 1:
                    report['cues_dropped'] += 1
                    continue
                relevant = [{**e, 'event_index': j, 'already_described': j in assigned} for j, e in enumerate(events) if (e['t_start'] < end and e['t_end'] > start) or start - 6 <= e['t_end'] <= start or e['on_screen_text']]
                relevant.sort(key=lambda e: (not (e['t_start'] < end and e['t_end'] >= start - 6), e['already_described'], -e['importance']))
                fresh = [e['event_index'] for e in relevant if not e['already_described'] and e['t_start'] < end and e['t_end'] >= start - 6][:1]
                assigned.update(fresh)
                slots.append({'id': i, 'start': start, 'end': end, 'budget': b, 'hi_budget': word_budget(end-start, cfg['words_per_second']['hi'], cfg['word_margin']), 'events': relevant, 'assigned_event_indices':fresh})
            def fit():
                if not slots:
                    return []
                request = {'instruction': 'Return JSON {cues:[{id,en}]}. Write concise audio description for each gap from supplied events, prioritize current/overlapping events. Never invent facts. At most budget whitespace-separated words. No we see.', 'gaps': slots, 'previous_cues': [], 'described_event_indices': [], 'dedupe_rule':'Prefer assigned event indices; track described indices and previous cues within this batch.'}
                response = client.call('fit', request)
                by_id = {c['id']: c['en'] for c in response['cues'] if isinstance(c.get('en'), str)}
                invalid = [s for s in slots if len(by_id.get(s['id'], '').split()) > s['budget']]
                if invalid:
                    retry = client.call('fit', {**request, 'previous_cues': [{'id':k, 'en':v} for k,v in by_id.items()], 'gaps': [{**s, 'budget': max(1, s['budget'] - 2)} for s in invalid]})
                    by_id.update({c['id']: c['en'] for c in retry['cues'] if isinstance(c.get('en'), str)})
                    report['issues'].append('Retried over-budget Nano cues')
                cues = []
                described = set()
                for s in slots:
                    words = by_id.get(s['id'], '').split()
                    if len(words) > s['budget']:
                        report['issues'].append(f"Truncated Nano cue {s['id']}")
                    text = ' '.join(words[:s['budget']]).replace('-->', '→')
                    if text:
                        described.update(s['assigned_event_indices'])
                        cues.append({**s, 'en': text})
                    else:
                        report['cues_dropped'] += 1
                report['described_event_indices'] = sorted(described)
                return cues
            cues = stage('fit', fit)
            def edit():
                if not cues:
                    return
                try:
                    response = client.call('edit', {'instruction': 'Return JSON {cues:[{id,en,hi}]}. Polish English, consistent names and present tense, no we see. Translate every cue into Hindi. Each en <= budget words; hi <= hi_budget whitespace-separated words. Preserve all ids.', 'cues': cues, 'events': events})
                    edited = {c['id']: c for c in response['cues'] if isinstance(c, dict) and isinstance(c.get('id'), int)}
                    apply_edits(cues, edited, report['issues'])
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
        report.update(getattr(client, 'perception_details', {}))
        report['usage'] = client.usage
        report['models'] = {u['stage']:u['model'] for u in client.usage}
        report['would_be_token_factory_cost_usd'] = sum(u.get('cost_usd', 0) for u in client.usage)
        report['estimated_cost_usd'] = 0 if client.mock else report['would_be_token_factory_cost_usd']
        report['billed_to'] = 'nvidia-dev free tier (dev only)' if requested_provider=='nvidia-dev' else 'mock (offline)' if client.mock else 'nebius token factory'
        report['cost_per_minute_usd'] = report['estimated_cost_usd'] / max(.001,report.get('duration_s',0)/60)
        (out / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    return report


def apply_edits(cues, edited, issues):
    import re
    for c in cues:
        e = edited.get(c['id'], {})
        for lang, limit in (('en', c['budget']), ('hi', c['hi_budget'])):
            value = e.get(lang)
            valid = isinstance(value, str) and 0 < len(value.split()) <= limit and '\n' not in value and '-->' not in value
            if lang == 'hi':
                valid = valid and bool(re.search('[\u0900-\u097f]', value))
            if valid:
                c[lang] = value
            else:
                if lang == 'hi':
                    c.pop('hi', None)
                issues.append(f"Ultra cue {c['id']} {lang} invalid; " + ('retained Nano English' if lang == 'en' else 'Hindi unavailable'))
