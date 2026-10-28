"""Offline tests for the v2 director (DESIGN_v2.md). Model calls are replaced by a scripted fake; no network."""
import json
import sys
import pytest
from narrate.config import load_config, resolve_provider
from narrate.director import (Director, run_director, assign_events, normalise_events, looks_like_subtitle, clean_bible,
                              parse_cues, parse_srt)
from narrate.llm import SpendGuard
from tests.test_fix3 import fake_detect

GAPS = [(4.0, 9.0), (12.0, 18.0), (20.0, 27.0)]
EVENTS = [
    {'t_start': 5.0, 't_end': 8.0, 'what': 'The cook pours water into a bowl of flour', 'importance': 4, 'confidence': .9},
    {'t_start': 9.5, 't_end': 11.5, 'what': 'The cook talks to the viewer', 'on_screen_text': 'and add it', 'importance': 2, 'confidence': .9},
    {'t_start': 13.0, 't_end': 17.0, 'what': 'The cook kneads the dough into a smooth ball', 'importance': 4, 'confidence': .9},
    {'t_start': 21.0, 't_end': 26.0, 'what': 'The cook rolls a dough ball flat with a rolling pin', 'importance': 5, 'confidence': .9},
]
GOOD = {0: ('In a kitchen, the cook pours water into flour.', ['e1']),
        1: ('She kneads it into a smooth ball.', ['e3']),
        2: ('She rolls a dough ball flat with a rolling pin.', ['e4'])}
BIBLE = {'setting': 'a home kitchen', 'cast': [{'id': 'c1', 'descriptor': 'the cook', 'first_seen': 5, 'notes': 'striped sleeves'}],
         'objects': ['flour', 'rolling pin'], 'story': 'making roti', 'beats': [{'t': 5, 'beat': 'water into flour'}],
         'on_screen_text': [], 'subtitles_present': True, 'tone': 'calm'}


def windows(data, n=None):
    s, e = data['window']
    return {'events': [ev for ev in EVENTS if s <= (ev['t_start'] + ev['t_end']) / 2 < e]}


def script(cues=GOOD, skip=()):
    def handler(data, n):
        out = []
        for g in data['gaps']:
            gid = g['gap_id']
            if gid in skip:
                out.append({'gap_id': gid, 'skip': True, 'reason': 'nothing new'})
            elif gid in cues:
                out.append({'gap_id': gid, 'text': cues[gid][0], 'evidence': cues[gid][1]})
        return {'cues': out}
    return handler


class Fake:
    """Replaces Director.submodel; dispatches on cost_role. Unhandled roles fall back to the director's own mock."""
    def __init__(self, **handlers):
        self.handlers, self.calls = handlers, []

    def install(self, monkeypatch):
        fake = self
        def submodel(self_, stage, data, media=None, mock_result=None, system=None):
            role = self_.cost_role
            fake.calls.append({'role': role, 'stage': stage, 'data': data, 'system': system})
            h = fake.handlers.get(role)
            n = sum(c['role'] == role for c in fake.calls)
            result = h(data, n) if callable(h) else h if h is not None else mock_result
            self_.trace('submodel', model='FAKE/' + stage, tokens_in=100, tokens_out=50, cost_usd=.001, cost_role=role, result={})
            if isinstance(result, Exception):
                raise result
            return json.loads(json.dumps(result, ensure_ascii=False))
        monkeypatch.setattr(Director, 'submodel', submodel)
        return self

    def role(self, name):
        return [c for c in self.calls if c['role'] == name]


def make(tmp_path, monkeypatch, gaps=GAPS, langs=('en', 'hi'), **director):
    cfg = resolve_provider(load_config(), 'mock')
    cfg['tts']['backend'] = 'silent'
    cfg['director'].update(director)
    monkeypatch.setattr('narrate.agent.core.detect', fake_detect(gaps))
    return Director('samples/sample_kitchen.mp4', tmp_path, cfg, list(langs), SpendGuard(.5))


def run(tmp_path, monkeypatch, langs=('en', 'hi'), director=None, **handlers):
    fake = Fake(**{'timeline': windows, 'bible': BIBLE, 'script': script(), **handlers}).install(monkeypatch)
    d = make(tmp_path, monkeypatch, langs=langs, **(director or {}))
    report = d.run()
    return d, report, fake


# ---------- assignment and time normalisation ----------
def test_assign_midpoint_overlap_and_edge_brush():
    gaps = [{'id': 0, 'start': 0, 'end': 10}, {'id': 1, 'start': 56.6, 'end': 67.9}, {'id': 2, 'start': 70, 'end': 74}]
    events = [{'id': 'a', 't_start': 2, 't_end': 4}, {'id': 'pepper', 't_start': 67.8, 't_end': 72.0},
              {'id': 'b', 't_start': 9, 't_end': 13}, {'id': 'long', 't_start': 60, 't_end': 90},
              {'id': 'gone', 't_start': 2, 't_end': 4, 'refuted': True}, {'id': 'speech', 't_start': 40, 't_end': 45}]
    out = assign_events(events, gaps)
    assert out['a'] == [0]
    assert out['pepper'] == [2]                      # NASA cue-6 bug: a 0.1 s edge brush no longer leaks into gap 1
    assert 'b' not in out                            # midpoint 11 is in speech and only 1 of its 4 s overlaps gap 0
    assert out['long'] == [1, 2]                     # no home (midpoint 75 s, < 50 % in any gap) but ongoing over most of gaps 1 and 2
    assert 'gone' not in out and 'speech' not in out


def test_normalise_relative_times_keys_and_subtitles():
    raw = {'events': [{'start': 2, 'end': 5, 'event': 'The cook divides the dough', 'importance': 4},
                      {'t_start': 6, 't_end': 9, 'action': 'She rolls a ball', 'on_screen_text': 'to 35 minutes', 'importance': '3'},
                      {'t_start': 1, 't_end': 3, 'what': '', 'importance': 3}]}
    events, base = normalise_events(raw, 40., 64., 120.)
    assert base == 'relative->absolute'
    assert [(e['t_start'], e['t_end']) for e in events] == [(42., 45.), (46., 49.)]
    assert events[0]['what'] == 'The cook divides the dough'
    assert events[1]['on_screen_text'] == '' and events[1]['subtitle_text'] == 'to 35 minutes'
    absolute, base = normalise_events([{'t_start': 50, 't_end': 52, 'what': 'x', 'on_screen_text': 'TEARS OF STEEL'},
                                       {'t_start': 90, 't_end': 95, 'what': 'outside'}], 40., 64., 120.)
    assert [e['what'] for e in absolute] == ['x'] and absolute[0]['on_screen_text'] == 'TEARS OF STEEL'
    assert looks_like_subtitle('and add it') and not looks_like_subtitle('Step 1: Knead') and not looks_like_subtitle('SIMULATION READY')
    assert looks_like_subtitle('Now we add the warm water slowly', burned=True) and not looks_like_subtitle('Now we add the warm water slowly')


def test_parsers_tolerate_model_shapes(tmp_path):
    cues = parse_cues({'cues': [{'id': '2', 'text': ' A  b ', 'evidence_ids': 'e1'}, {'gap_id': 3, 'text': 'SKIP'},
                                {'gap_id': 4, 'skip': 'true'}, {'gap_id': 'x', 'text': 'bad'}, 'junk']})
    assert cues[2] == {'text': 'A b', 'evidence': ['e1'], 'skip': False, 'reason': ''} and cues[3]['skip'] and cues[4]['skip'] and len(cues) == 3
    bible = clean_bible({'cast': [{'descriptor': 'the cook'}, {'descriptor': ''}], 'objects': 'flour'}, {'setting': 'kitchen', 'story': 's'})
    assert bible['cast'] == [{'id': 'c1', 'descriptor': 'the cook', 'first_seen': 0., 'notes': ''}] and bible['setting'] == 'kitchen' and bible['objects'] == []
    srt = tmp_path / 'x.srt'
    srt.write_text('1\n00:00:01,000 --> 00:00:02,500\nHello there\n\n2\n00:01:00,000 --> 00:01:01,000\nBye\n')
    assert parse_srt(srt) == [(1.0, 2.5, 'Hello there'), (60.0, 61.0, 'Bye')]


# ---------- full flow ----------
def test_happy_path_one_script_call_and_compatible_outputs(tmp_path, monkeypatch):
    d, report, fake = run(tmp_path, monkeypatch, hindi=lambda data, n: {'cues': [{'gap_id': c['gap_id'], 'hi': 'रसोइया आटा गूँधती है।'} for c in data['cues']]})
    assert report['status'] == 'complete' and report['mode'] == 'director'
    assert [c['en'] for c in report['cues']] == [GOOD[i][0] for i in range(3)]
    assert all(c['verdict'] == 'supported' and c['hi'] for c in report['cues'])
    assert len(fake.role('script')) == 1 and len(fake.role('timeline')) == 2 and report['director_stats']['ultra_calls'] == 3
    # The script call sees the bible, the WHOLE timeline (incl. speech-region events) and every gap with measured budgets.
    data = fake.role('script')[0]['data']
    assert data['bible']['story'] == 'making roti' and [r['id'] for r in data['timeline']] == ['e1', 'e2', 'e3', 'e4']
    assert data['timeline'][1]['gap'] == 'speech' and data['timeline'][1]['said'] == 'and add it'
    assert [g['evidence'] for g in data['gaps']] == [['e1'], ['e3'], ['e4']] and all(g['max_words'] >= 3 for g in data['gaps'])
    assert data['gaps'][1]['said_before'] == 'and add it'
    for f in ('ad_en.vtt', 'ad_hi.vtt', 'narrated_en.mp4', 'narrated_hi.mp4', 'transcript_en.txt', 'transcript_hi.txt', 'report.json', 'trace.json', 'trace.md'):
        assert (tmp_path / f).is_file(), f
    assert 'kneads it into a smooth ball' in (tmp_path / 'ad_en.vtt').read_text()


def test_skip_leaves_gap_silent_and_out_of_coverage(tmp_path, monkeypatch):
    d, report, fake = run(tmp_path, monkeypatch, langs=('en',), script=script(skip=(1,)))
    assert [c['id'] for c in report['cues']] == [0, 2]
    assert report['gaps_skipped_no_new_info'] == [1] and 'silent' in report['dropped_gaps'][1]
    assert report['high_importance_covered_percent'] == 100   # a skipped gap's events are not counted as uncovered


def test_postchecks_reject_budget_lint_subtitle_similarity_and_foreign_evidence(tmp_path, monkeypatch):
    Fake(timeline=windows, bible=BIBLE).install(monkeypatch)
    d = make(tmp_path, monkeypatch, langs=('en',))
    d.st_gaps(); d.st_shots(); d.st_timeline(); d.bible = BIBLE; d.st_assign()
    ok, problems = d.check_cue(0, 'The cook pours water into a bowl of flour.', ['e1', 'e3'])
    assert ok == ['e1'] and problems == [] and d.stats['evidence_stripped'] == 1
    assert any('over budget' in p for p in d.check_cue(0, 'word ' * 30, ['e1'])[1])
    assert any('camera' in p for p in d.check_cue(0, 'The camera pans over the flour.', ['e1'])[1])
    assert any('"Person"' in p for p in d.check_cue(0, 'Person pours water into flour.', ['e1'])[1])
    assert any('continues' in p for p in d.check_cue(0, 'The cook continues mixing flour.', ['e1'])[1])
    assert any('subtitle' in p for p in d.check_cue(0, 'Text reads "and add it".', ['e1'])[1])
    assert any('no cited evidence inside this gap' in p for p in d.check_cue(0, 'The cook rolls dough flat.', ['e4'])[1])
    d.pending[0] = {'text': 'The cook pours water into a bowl of flour.', 'evidence': ['e1']}
    assert any('repeats the previous cue' in p for p in d.check_cue(1, 'The cook pours water into the bowl of flour.', ['e3'])[1])
    d.tts_cache[('She kneads it into a smooth ball.', 'en')] = (30., tmp_path / 'x.wav')   # measured TTS far over the gap
    assert any('measured 30.0 s' in p for p in d.check_cue(1, 'She kneads it into a smooth ball.', ['e3'])[1])


def test_budgets_come_from_measured_voice(tmp_path, monkeypatch):
    Fake().install(monkeypatch)
    d = make(tmp_path, monkeypatch, langs=('en',))
    d.st_gaps()
    assert d.wps['en'] == pytest.approx(2.5, abs=.05)        # silent test backend speaks 2.5 words/s
    g = d.gap(0)
    assert g['director_words_en'] == min(d.max_words(g, 'en'), int(d.cue_cap(g) * d.wps['en']) - 1)
    d2 = make(tmp_path / 'b', monkeypatch, gaps=[(4.0, 6.0)], langs=('en',), min_words=5)
    d2.st_gaps()
    assert not d2.scriptable() and 'too short' in d2.dropped[0]


def test_verify_contradiction_refutes_repairs_and_drops(tmp_path, monkeypatch):
    first = {0: GOOD[0], 1: ('She kneads a blue dough ball.', ['e3']), 2: GOOD[2]}
    def verify(data, n):
        out = []
        for c in data['cues']:
            if 'blue' in c['text']:
                out.append({'gap_id': c['gap_id'], 'verdict': 'contradicted', 'wrong': 'blue dough ball', 'reason': 'the dough is cream-coloured'})
            elif 'rolling pin' in c['text']:
                out.append({'gap_id': c['gap_id'], 'verdict': 'contradicted', 'wrong': 'rolling pin', 'reason': 'she uses a glass'})
            else:
                out.append({'gap_id': c['gap_id'], 'verdict': 'supported', 'reason': 'visible'})
        return {'verdicts': out}
    def repair(data, n):
        return {'cues': [{'gap_id': g['gap_id'], 'text': 'She kneads the dough into a smooth ball.' if g['gap_id'] == 1 else 'She flattens the dough with a rolling pin.',
                          'evidence': ['e3'] if g['gap_id'] == 1 else ['e4']} for g in data['gaps']]}
    d, report, fake = run(tmp_path, monkeypatch, langs=('en',), script=script(first), verify=verify, repair=repair)
    assert [(c['id'], c['en']) for c in report['cues']] == [(0, GOOD[0][0]), (1, 'She kneads the dough into a smooth ball.')]
    # "blue" was the writer's addition: e3 stays trusted. "rolling pin" came from e4: refuted, so the repair citing it fails.
    events = {e['id']: e for e in report['timeline']}
    assert not events['e3'].get('refuted') and events['e4']['refuted']
    first_repair = fake.role('repair')[0]['data']['gaps']
    assert {g['gap_id'] for g in first_repair} == {1, 2}
    why = {g['gap_id']: ' '.join(g['why_rejected']) for g in first_repair}
    assert '"blue dough ball" is wrong' in why[1] and 'glass' in why[2]
    assert next(g for g in first_repair if g['gap_id'] == 2)['trusted_evidence'] == []
    assert len(fake.role('repair')) == 2 and 'no cited evidence' in ' '.join(fake.role('repair')[1]['data']['gaps'][0]['why_rejected'])
    assert 2 in report['dropped_gaps'] and 'dropped after repair' in report['dropped_gaps'][2]
    assert report['director_stats']['ultra_calls'] == 4 and report['director_stats']['contradicted'] == 2
    verdict_rows = [s for s in json.loads((tmp_path / 'trace.json').read_text())['steps'] if s['tool_name'] == 'verify_claim']
    assert {s['result']['verdict'] for s in verdict_rows} == {'supported', 'contradicted'}
    history = report['cue_history']['2']
    assert [h['step'] for h in history] == ['script', 'verify', 'repair_1', 'repair_2', 'drop']


def test_uncertain_policy_depends_on_risky_detail(tmp_path, monkeypatch):
    cues = {0: ('A sign reads "Fresh Roti".', ['e1']), 1: GOOD[1], 2: GOOD[2]}
    verify = lambda data, n: {'verdicts': [{'gap_id': c['gap_id'], 'verdict': 'uncertain', 'reason': 'cannot tell'} for c in data['cues']]}
    d, report, fake = run(tmp_path, monkeypatch, langs=('en',), script=script(cues), verify=verify,
                          repair=lambda data, n: {'cues': [{'gap_id': g['gap_id'], 'skip': True} for g in data['gaps']]})
    assert [c['id'] for c in report['cues']] == [1, 2] and all(c['verdict'] == 'uncertain-consistent' for c in report['cues'])
    assert 'risky details: quoted text' in ' '.join(fake.role('repair')[0]['data']['gaps'][0]['why_rejected'])


def test_failed_verification_commits_nothing(tmp_path, monkeypatch):
    d, report, fake = run(tmp_path, monkeypatch, langs=('en',), verify=lambda data, n: RuntimeError('provider down'))
    assert report['cues'] == [] and report['cues_committed'] == 0
    assert any('Verification unavailable' in i for i in report['issues']) and not fake.role('repair')
    assert all('never committed unverified' in report['dropped_gaps'][g] for g in (0, 1, 2))


def test_ultra_cap_is_hard(tmp_path, monkeypatch):
    bad = {i: ('The camera pans across the table.', [e]) for i, e in ((0, 'e1'), (1, 'e3'), (2, 'e4'))}
    d, report, fake = run(tmp_path, monkeypatch, director={'max_ultra_calls': 3}, script=script(bad),
                          repair=lambda data, n: {'cues': [{'gap_id': g['gap_id'], 'text': 'The camera zooms in.', 'evidence': ['e1']} for g in data['gaps']]})
    assert d.ultra_calls == 3 and len(fake.role('repair')) == 1
    assert report['status'] == 'complete' and report['cues'] == [] and any('cap' in i for i in report['issues'])
    steps = json.loads((tmp_path / 'trace.json').read_text())['steps']
    assert sum(s['role'] == 'orchestrator' for s in steps) == 3 == report['agent_stats']['orchestrator_turns']


def test_default_run_stays_within_six_ultra_calls(tmp_path, monkeypatch):
    long_hi = lambda data, n: {'cues': [{'gap_id': c['gap_id'], 'hi': 'बहुत ' * 40} for c in data['cues']]}
    d, report, fake = run(tmp_path, monkeypatch, hindi=long_hi, script=script({i: ('The camera pans.', ['e1']) for i in range(3)}),
                          repair=lambda data, n: {'cues': [{'gap_id': g['gap_id'], 'text': 'The camera pans again.', 'evidence': ['e1']} for g in data['gaps']]})
    assert d.ultra_calls <= 6


def test_script_failure_falls_back_to_verified_timeline_text(tmp_path, monkeypatch):
    d, report, fake = run(tmp_path, monkeypatch, langs=('en',), script=lambda data, n: ValueError('No valid JSON response'))
    assert len(fake.role('script')) == 2 and report['fallback_finalize'] and 'script call failed' in report['fallback_reason']
    assert [c['en'] for c in report['cues']] == [EVENTS[0]['what'], EVENTS[2]['what'], EVENTS[3]['what']]
    assert all(c['verdict'] == 'supported' for c in report['cues'])


def test_hindi_native_call_refit_and_omission(tmp_path, monkeypatch):
    def hindi(data, n):
        texts = {0: 'रसोइया आटे में पानी डालती है।', 1: 'वह आटा ' + 'बहुत ' * 30 + 'गूँधती है।', 2: 'She rolls it'}
        return {'cues': [{'gap_id': c['gap_id'], 'hi': texts[c['gap_id']]} for c in data['cues']]}
    refit = []
    def hindi_role(data, n):
        if n == 1:
            return hindi(data, n)
        refit.append(data)
        return {'cues': [{'gap_id': c['gap_id'], 'hi': 'वह लोई गूँधती है।' if c['gap_id'] == 1 else 'still English'} for c in data['cues']]}
    d, report, fake = run(tmp_path, monkeypatch, hindi=hindi_role)
    first = fake.role('hindi')[0]
    assert len(first['data']['cues']) == 3 and 'आटा' in first['system'] and 'not a literal translation' in first['system']
    assert all(c['max_words'] >= 1 and c['en'] for c in first['data']['cues'])
    assert len(refit) == 1 and {c['gap_id'] for c in refit[0]['cues']} == {1, 2}
    over = next(c for c in refit[0]['cues'] if c['gap_id'] == 1)
    assert over['measured_seconds'] > over['allowed_seconds'] and over['max_words'] < 30
    hi = {c['id']: c.get('hi') for c in report['cues']}
    assert hi[0] == 'रसोइया आटे में पानी डालती है।' and hi[1] == 'वह लोई गूँधती है।' and hi[2] is None
    assert any('no fitting Hindi for gaps [2]' in i for i in report['issues'])
    assert 'She rolls' not in (tmp_path / 'ad_hi.vtt').read_text() and len(report['tracks']['hi']) == 2


def test_trace_stages_and_markdown(tmp_path, monkeypatch):
    d, report, fake = run(tmp_path, monkeypatch)
    trace = json.loads((tmp_path / 'trace.json').read_text())
    names = [s['stage'] for s in trace['stages']]
    assert names == ['gaps', 'shots', 'scene', 'timeline', 'bible', 'assign', 'script', 'verify', 'hindi', 'render']
    for s in trace['stages']:
        assert {'models', 'calls', 'tokens_in', 'tokens_out', 'cost_usd', 'latency_s', 'input', 'output'} <= set(s)
    script_stage = next(s for s in trace['stages'] if s['stage'] == 'script')
    assert script_stage['models'] == ['FAKE/edit'] and script_stage['ultra_calls'] == 1 and script_stage['cost_usd'] == pytest.approx(.001)
    assert trace['metadata']['mode'] == 'director' and report['cost_by_role']['script'] == pytest.approx(.001)
    md = (tmp_path / 'trace.md').read_text()
    for heading in ('## Stages', '## Scene bible', '## Timeline', '## Script, verification and repairs'):
        assert heading in md
    assert '| ✓ script | edit | 1 |' in md and 'making roti' in md


def test_report_compatible_with_app_and_mock_end_to_end(tmp_path):
    from app.app import trace_html, results_html, files_for
    cfg = load_config()
    cfg['tts']['backend'] = 'silent'
    report = run_director('samples/sample_kitchen.mp4', tmp_path, provider='mock', config=cfg)
    for key in ('status', 'mock', 'provider', 'cues', 'tracks', 'gaps', 'speech', 'cues_committed', 'cues_dropped', 'gap_coverage_percent',
                'high_importance_covered_percent', 'overlaps_with_speech', 'usage', 'cost_by_role', 'estimated_cost_usd', 'agent_stats',
                'latency_s', 'issues', 'fallback_finalize', 'cost_per_minute_usd', 'billed_to', 'detector'):
        assert key in report, key
    assert report['status'] == 'complete' and report['mock'] and report['cues'] and report['overlaps_with_speech'] == 0
    on_disk = json.loads((tmp_path / 'report.json').read_text())
    assert on_disk['cues_committed'] == report['cues_committed'] and on_disk['mode'] == 'director'
    html = trace_html(json.loads((tmp_path / 'trace.json').read_text()))
    assert 'Turns' in html and 'stage:script' in html and 'supported' in html
    assert 'Cues committed' in results_html(on_disk) and len(files_for(tmp_path)) == 5


def test_no_gaps_means_no_model_calls(tmp_path, monkeypatch):
    fake = Fake().install(monkeypatch)
    cfg = resolve_provider(load_config(), 'mock')
    cfg['tts']['backend'] = 'silent'
    monkeypatch.setattr('narrate.agent.core.detect', fake_detect([]))
    report = Director('samples/sample_kitchen.mp4', tmp_path, cfg, ['en'], SpendGuard(.5)).run()
    assert fake.calls == [] and report['cues'] == [] and any('extended AD' in i for i in report['issues'])


def test_cli_defaults_to_director(monkeypatch, tmp_path):
    import narrate.__main__ as main
    import narrate.director as director
    seen = {}
    def fake_run(*args, **kw):
        seen['args'], seen['kw'] = args, kw
        return {'estimated_cost_usd': 0}
    monkeypatch.setattr(director, 'run_director', fake_run)
    monkeypatch.setattr(sys, 'argv', ['narrate', 'agent', 'samples/sample_kitchen.mp4', '--out', str(tmp_path), '--mock'])
    main.main()
    assert seen['kw']['provider'] == 'mock' and seen['args'][0] == 'samples/sample_kitchen.mp4'


def test_compare_runs_aligns_cues(tmp_path, capsys):
    from scripts.compare_runs import align, main
    old = {'cues': [{'start': 6.2, 'end': 12.9, 'en': 'Person kneads dough.'}, {'start': 15.8, 'end': 20, 'en': 'Person continues kneading.'}],
           'estimated_cost_usd': .33, 'agent_stats': {'orchestrator_turns': 42}}
    new = {'cues': [{'start': 6.2, 'end': 12.9, 'en': 'In a home kitchen, the cook pours water into flour.'}, {'start': 42.4, 'end': 46, 'en': 'She divides the dough.'}],
           'estimated_cost_usd': .07, 'agent_stats': {'orchestrator_turns': 4}, 'mode': 'director', 'gaps_skipped_no_new_info': [2]}
    rows = align(old['cues'], new['cues'])
    assert [(r[1] is not None, r[2] is not None) for r in rows] == [(True, True), (True, False), (False, True)]
    (tmp_path / 'old.json').write_text(json.dumps(old)); (tmp_path / 'new.json').write_text(json.dumps(new))
    main([str(tmp_path / 'old.json'), str(tmp_path / 'new.json'), '--width', '40'])
    out = capsys.readouterr().out
    assert 'Person continues kneading.' in out and 'She divides the dough.' in out and '$0.3300' in out and '42' in out
