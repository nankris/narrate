"""Offline tests for the v2 director (DESIGN_v2.md). Model calls are replaced by a scripted fake; no network."""
import json
import sys
from types import SimpleNamespace as NS
import pytest
from narrate.config import load_config, resolve_provider
from narrate.director import (Director, run_director, assign_events, normalise_events, looks_like_subtitle, clean_bible,
                              parse_cues, parse_srt, parse_tightened)
from narrate.llm import SpendGuard, Client
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
    assert parse_tightened({'gap_id': 2, 'text': ' A shorter line. '}, 2) == 'A shorter line.'


def test_nano_call_options_cap_output_disable_thinking_and_stay_out_of_payload(monkeypatch):
    monkeypatch.setenv('NARRATE_TEST_KEY', 'fake-test-value')
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        return NS(usage=NS(prompt_tokens=20, completion_tokens=8), choices=[NS(message=NS(content='{"text":"Short line."}'))])
    cfg = load_config()
    cfg['key_env'] = 'NARRATE_TEST_KEY'
    cfg['models']['fit']['thinking'] = False
    client = Client(cfg, sdk_factory=lambda **kw: NS(chat=NS(completions=NS(create=create))))
    assert client.call('fit', {'cue': {'text': 'A line that is too long.'}, '_max_tokens': 160}) == {'text': 'Short line.'}
    assert calls[0]['max_tokens'] == 160
    assert calls[0]['extra_body']['chat_template_kwargs']['enable_thinking'] is False
    assert '/no_think' in calls[0]['messages'][0]['content']
    payload = json.loads(calls[0]['messages'][1]['content'][0]['text'])
    assert payload == {'cue': {'text': 'A line that is too long.'}} and '_max_tokens' not in payload


# ---------- full flow ----------
def test_happy_path_one_script_call_and_compatible_outputs(tmp_path, monkeypatch):
    d, report, fake = run(tmp_path, monkeypatch, hindi=lambda data, n: {'cues': [{'gap_id': c['gap_id'], 'hi': 'रसोइया आटा गूँधती है।'} for c in data['cues']]})
    assert report['status'] == 'complete' and report['mode'] == 'director'
    assert [c['en'] for c in report['cues']] == [GOOD[i][0] for i in range(3)]
    assert all(c['verdict'] == 'supported' and c['hi'] for c in report['cues'])
    assert len(fake.role('script')) == 1 and len(fake.role('timeline')) == 3 and report['director_stats']['ultra_calls'] == 3
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
    ok, problems = d.check_cue(0, 'In the kitchen, the cook pours water into flour.', ['e1', 'e3'])
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
    # English budgets assume a natural narrator (2.6 words/s) or the measured voice if slower; config 2.3 no longer caps them.
    assert d.budget_wps('en') == min(2.6, d.wps['en']) and g['director_words_en'] == int(d.cue_cap(g) * d.budget_wps('en')) - 1
    d2 = make(tmp_path / 'b', monkeypatch, gaps=[(4.0, 6.0)], langs=('en',), min_words=5)
    d2.st_gaps()
    assert not d2.scriptable() and 'too short' in d2.dropped[0]


def test_english_fit_accepts_only_measured_fitting_overage_within_fifteen_percent(tmp_path, monkeypatch):
    d = postcheck_director(tmp_path, monkeypatch)
    g = d.gap(1)
    maximum, hard = g['director_words_en'], d.hard_words(g)
    assert hard == int(maximum * 1.15)
    text = ' '.join(['word'] * hard)
    d.tts_cache[(text, 'en')] = (d.allowed_seconds(g) - .1, tmp_path / 'fits.wav')
    assert d.check_fit(1, text, 'en')['ok']
    too_many = text + ' word'
    d.tts_cache[(too_many, 'en')] = (d.allowed_seconds(g) - .1, tmp_path / 'many.wav')
    assert any('over budget' in p for p in d.check_fit(1, too_many, 'en')['problems'])
    d.tts_cache[(text, 'en')] = (d.allowed_seconds(g) + .1, tmp_path / 'slow.wav')
    assert any('cue too long' in p for p in d.check_fit(1, text, 'en')['problems'])


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
    cues = {0: ('In the kitchen, a sign reads "Fresh Roti".', ['e1']), 1: GOOD[1], 2: GOOD[2]}
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
    fixed = 'In the kitchen, the cook pours water into flour.'
    d, report, fake = run(tmp_path, monkeypatch, langs=('en',), script=lambda data, n: ValueError('No valid JSON response'),
                          repair=lambda data, n: {'cues': [{'gap_id': g['gap_id'], 'text': fixed, 'evidence': ['e1']} for g in data['gaps']]})
    assert len(fake.role('script')) == 2 and report['fallback_finalize'] and 'script call failed' in report['fallback_reason']
    # Timeline text never names the place, so the first cue is repaired by Ultra under the establishing rule.
    assert 'does not say where' in ' '.join(fake.role('repair')[0]['data']['gaps'][0]['why_rejected'])
    assert [c['en'] for c in report['cues']] == [fixed, EVENTS[2]['what'], EVENTS[3]['what']]
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
    new = {'cues': [{'start': 6.2, 'end': 12.9, 'en': 'In a home kitchen, the cook wets the flour.'}, {'start': 42.4, 'end': 46, 'en': 'She divides the dough.'}],
           'estimated_cost_usd': .07, 'agent_stats': {'orchestrator_turns': 4}, 'mode': 'director', 'gaps_skipped_no_new_info': [2]}
    rows = align(old['cues'], new['cues'])
    assert [(r[1] is not None, r[2] is not None) for r in rows] == [(True, True), (True, False), (False, True)]
    (tmp_path / 'old.json').write_text(json.dumps(old)); (tmp_path / 'new.json').write_text(json.dumps(new))
    main([str(tmp_path / 'old.json'), str(tmp_path / 'new.json'), '--width', '40'])
    out = capsys.readouterr().out
    assert 'Person continues kneading.' in out and 'She divides the dough.' in out and '$0.3300' in out and '42' in out


class FakeTokenFactory:
    """Stands in for llm.Client on the NON-mock path (real ffmpeg windows, stills, usage/cost accounting); no network."""
    mock = False

    def __init__(self, fail_video=False):
        self.usage, self.requests, self.fail_video = [], [], fail_video

    def call(self, stage, data, media=None):
        system = data['_system']
        role = next(r for key, r in (('You log every visible event', 'timeline'), ('Establish the scene', 'scene'), ('scene bible', 'bible'),
                                     ('WHOLE English', 'script'), ('still frames taken INSIDE', 'verify'), ('You repair', 'repair'),
                                     ('Hindi audio-description track', 'hindi'), ('You shorten', 'tighten')) if key in system)
        kinds = [m['type'] for m in media or []]
        self.requests.append((role, stage, kinds))
        if role == 'timeline' and 'video_url' in kinds and self.fail_video:
            raise RuntimeError('video rejected')
        result = {'timeline': lambda: windows(data), 'scene': lambda: {'setting': 'home kitchen', 'burned_in_subtitles': True},
                  'bible': lambda: BIBLE, 'script': lambda: script()(data, 1),
                  'verify': lambda: {'verdicts': [{'gap_id': c['gap_id'], 'verdict': 'supported'} for c in data['cues']]},
                  'hindi': lambda: {'cues': [{'gap_id': c['gap_id'], 'hi': 'रसोइया आटा गूँधती है।'} for c in data['cues']]}}[role]()
        model = {'perceive': 'nvidia/Nemotron-3.5-Super-VL', 'edit': 'nvidia/Nemotron-3-Ultra-550b-a55b'}[stage]
        self.usage.append({'stage': stage, 'model': model, 'base_url_host': 'api.tokenfactory.nebius.com', 'input_tokens': 1000,
                           'output_tokens': 100, 'cost_usd': .002 if stage == 'edit' else .0005, 'latency_s': .01, 'cached_tokens': 0})
        return result


@pytest.mark.parametrize('fail_video', [False, True])
def test_provider_path_with_fake_client(tmp_path, monkeypatch, fail_video):
    monkeypatch.setattr('narrate.agent.core.detect', fake_detect(GAPS))
    cfg = load_config()
    cfg['tts']['backend'] = 'silent'
    client = FakeTokenFactory(fail_video)
    report = run_director('samples/sample_kitchen.mp4', tmp_path, provider='nebius', config=cfg, client=client)
    assert report['status'] == 'complete' and not report['mock'] and report['billed_to'] == 'nebius token factory'
    assert len(report['cues']) == 3 and all(c['hi'] for c in report['cues'])
    timeline = [r for r in client.requests if r[0] == 'timeline']
    if fail_video:   # each window falls back to labelled stills
        assert [k for _, _, k in timeline] == [['video_url'], ['text', 'image_url'] * 4] * 3   # 30 s clip -> 3 windows of ~10 s
    else:
        assert [k for _, _, k in timeline] == [['video_url']] * 3
    verify = next(k for r, _, k in client.requests if r == 'verify')
    assert verify.count('image_url') == 2 * 3                        # 2 stills inside each of the 3 gaps, one batched call
    assert sum(r[1] == 'edit' for r in client.requests) == report['director_stats']['ultra_calls'] == 3
    ultra = report['cost_by_role']['bible'] + report['cost_by_role']['script'] + report['cost_by_role']['hindi']
    assert ultra == pytest.approx(.006) and report['estimated_cost_usd'] == pytest.approx(sum(u['cost_usd'] for u in client.usage))
    stages = {s['stage']: s for s in report['stages']}
    assert stages['script']['models'] == ['nvidia/Nemotron-3-Ultra-550b-a55b'] and stages['script']['tokens_in'] == 1000
    assert 'Nemotron-3-Ultra' in (tmp_path / 'trace.md').read_text()


# ---------- round 2 (real-run findings) ----------
def postcheck_director(tmp_path, monkeypatch, **director):
    Fake(timeline=windows, bible=BIBLE).install(monkeypatch)
    d = make(tmp_path, monkeypatch, langs=('en',), **director)
    d.st_gaps(); d.st_shots(); d.st_timeline(); d.bible = BIBLE; d.st_assign()
    return d


def test_camera_as_object_allowed_but_camera_direction_banned_with_fix_hint(tmp_path, monkeypatch):
    from narrate.agent.core import lint
    d = postcheck_director(tmp_path, monkeypatch)
    d.pending[0] = {'text': 'In the kitchen, the cook pours water into flour.', 'evidence': ['e1']}
    # NASA gap 9: a crewmate who puts down a camera is part of the scene (burned 2 repairs in run nasa_v2_r1).
    assert lint('A crewmate sets down the camera and joins the group.') == []
    assert lint('A crewmate photographs the pepper with a camera.') == []
    assert d.check_fit(1, 'She sets down the camera and kneads.', 'en')['ok']
    for bad in ('The camera pans across the table.', 'As the camera follows her, she kneads.', 'She smiles on camera.', 'We see the dough.'):
        problems = d.check_cue(1, bad, ['e3'])[1]
        assert problems and all('Fix:' in p for p in problems if p.startswith('Banned')), (bad, problems)
    assert any('a crewmate films with a camera' in p for p in d.check_cue(1, 'The camera pans over the dough.', ['e3'])[1])
    assert any('film-making jargon' in p for p in d.check_cue(1, 'The dough is filmed close-up.', ['e3'])[1])
    assert lint('The cook heats oil in a pan over the flame.') == []


def test_headline_fragments_rejected_full_sentences_pass(tmp_path, monkeypatch):
    d = postcheck_director(tmp_path, monkeypatch)
    d.pending[0] = {'text': 'In the kitchen, the cook pours water into flour.', 'evidence': ['e1']}
    for frag in ('Cuts dough into portions; rolls each into a ball.', 'Gestures to the bowl and the flour.', 'Flattens a ball with her palms.'):
        assert any('Fix:' in p and ('headline' in p or 'subject' in p) for p in d.check_cue(1, frag, ['e3'])[1]), frag
    assert d.check_cue(1, 'Now she kneads the dough into a smooth ball.', ['e3'])[1] == []
    assert any('"continues"' in p for p in d.check_cue(1, 'They continue kneading the dough.', ['e3'])[1])


def test_establishing_cue_must_name_the_place(tmp_path, monkeypatch):
    d = postcheck_director(tmp_path, monkeypatch)
    assert d.is_establishing(0)
    problems = d.check_cue(0, 'The cook pours water into flour.', ['e1'])[1]
    assert any('does not say where' in p and 'home kitchen' in p for p in problems)
    assert d.check_cue(0, 'In a home kitchen, the cook wets the flour.', ['e1'])[1] == []
    d.pending[0] = {'text': 'In a home kitchen, the cook wets the flour.', 'evidence': ['e1']}
    assert not d.is_establishing(1) and d.check_cue(1, 'Now she kneads the dough into a smooth ball.', ['e3'])[1] == []
    # Bible `place` (e.g. from an unverified title the visuals agree with) counts too.
    d.bible = {**BIBLE, 'setting': 'a crowded spacecraft module with equipment panels', 'place': 'space station'}
    d.pending.clear()
    assert d.check_cue(0, 'Aboard the space station, an astronaut adds water.', ['e1'])[1] == []
    assert d.check_cue(0, 'Inside the module, an astronaut adds water.', ['e1'])[1] == []
    assert d.check_cue(0, 'An astronaut pours water into a bowl.', ['e1'])[1]


def test_script_payload_marks_establishing_gap_and_target_words(tmp_path, monkeypatch):
    d, report, fake = run(tmp_path, monkeypatch, langs=('en',))
    gaps = fake.role('script')[0]['data']['gaps']
    assert gaps[0].get('establish') is True and not any(g.get('establish') for g in gaps[1:])
    for g in gaps:   # round 3: a 70-90 % range, so the writer does not overshoot max_words
        lo, hi = (int(x) for x in g['target_words'].split('-'))
        assert 4 <= lo <= hi <= g['max_words'] and lo >= .7 * g['max_words'] and hi <= .9 * g['max_words']
    system = fake.role('script')[0]['system']
    assert 'HARD limit' in system and 'Count the words' in system and '"words":0' in system and 'compact opening' in system


def test_writer_word_self_count_is_audited_not_trusted(tmp_path, monkeypatch):
    counted = {g: (text, ev) for g, (text, ev) in GOOD.items()}
    def with_bad_count(data, n):
        return {'cues': [{'gap_id': g['gap_id'], 'text': counted[g['gap_id']][0], 'words': 999,
                          'evidence': counted[g['gap_id']][1]} for g in data['gaps']]}
    d, report, fake = run(tmp_path, monkeypatch, langs=('en',), script=with_bad_count)
    assert len(report['cues']) == 3 and report['director_stats']['self_count_mismatch'] == 3
    assert report['cue_history']['0'][0]['words'] == len(GOOD[0][0].split())
    assert report['cue_history']['0'][0]['words_claimed'] == 999


def test_nano_tightens_over_budget_cue_before_any_ultra_repair(tmp_path, monkeypatch):
    long = 'Now she kneads the soft dough firmly with both hands on the wooden table into a smooth round ball today.'
    cues = {0: GOOD[0], 1: (long, ['e3']), 2: GOOD[2]}
    tight = 'Now she kneads the dough into a smooth ball.'
    d, report, fake = run(tmp_path, monkeypatch, langs=('en',), script=script(cues),
                          tighten=lambda data, n: {'text': tight, 'words': 9})
    assert len(long.split()) > d.hard_words(d.gap(1))
    assert len(fake.role('tighten')) == 1 and fake.role('tighten')[0]['stage'] == 'fit' and not fake.role('repair')
    sent = fake.role('tighten')[0]['data']
    assert sent['cue']['gap_id'] == 1 and sent['cue']['max_words'] == d.gap(1)['director_words_en'] and sent['cue']['words'] == 20
    assert sent['cue']['remove_at_least'] == 20 - d.gap(1)['director_words_en'] and sent['_max_tokens'] <= 200
    assert {c['id']: c['en'] for c in report['cues']}[1] == tight
    assert report['director_stats']['ultra_calls'] == 2 and report['director_stats']['tightened'] == 1   # bible + script only
    assert [h['step'] for h in report['cue_history']['1']][:2] == ['script', 'tighten']
    assert 'tighten' in [s['stage'] for s in report['stages']] and report['cost_by_role']['tighten'] == pytest.approx(.001)


LONG = 'Now she kneads the soft dough firmly with both hands on the wooden table into a smooth round ball today.'


def test_nano_tighten_that_invents_is_rejected_then_ultra_repairs_the_length(tmp_path, monkeypatch):
    cues = {0: GOOD[0], 1: (LONG, ['e3']), 2: GOOD[2]}
    fixed = 'Now she kneads the dough into a smooth ball.'
    d, report, fake = run(tmp_path, monkeypatch, langs=('en',), script=script(cues),
                          tighten=lambda data, n: {'text': 'She adds sugar and purple berries.'},
                          repair=lambda data, n: {'cues': [{'gap_id': g['gap_id'], 'text': fixed, 'words': 9, 'evidence': ['e3']} for g in data['gaps']]})
    assert len(fake.role('tighten')) == 2                                   # 2 Nano attempts for the one cue, both rejected
    assert any('tighten added new words' in ' '.join(h.get('problems') or []) for h in report['cue_history']['1'])
    # Round 3: a length failure Nano cannot fix IS repairable by Ultra (round 2 dropped 5 of 12 roti gaps this way).
    sent = fake.role('repair')[0]['data']['gaps']
    assert [g['gap_id'] for g in sent] == [1] and sent[0]['rejected_words'] == 20 and 'over budget' in sent[0]['why_rejected'][0]
    assert 'cut at least' in sent[0]['why_rejected'][0] and 'rejected_words - max_words' in fake.role('repair')[0]['system']
    assert {c['id']: c['en'] for c in report['cues']}[1] == fixed and report['director_stats']['ultra_calls'] == 3


def test_length_failure_dropped_only_after_nano_and_ultra(tmp_path, monkeypatch):
    cues = {0: GOOD[0], 1: (LONG, ['e3']), 2: GOOD[2]}
    d, report, fake = run(tmp_path, monkeypatch, langs=('en',), script=script(cues), tighten=lambda data, n: {'text': data['cue']['text']},
                          repair=lambda data, n: {'cues': [{'gap_id': g['gap_id'], 'text': LONG, 'evidence': ['e3']} for g in data['gaps']]})
    assert len(fake.role('repair')) == 2 and 1 not in {c['id'] for c in report['cues']}
    assert 'still over budget after Nano tighten and Ultra repair' in report['dropped_gaps'][1]
    assert any('not shorter' in ' '.join(h.get('problems') or []) for h in report['cue_history']['1'])


def test_missing_place_establishing_candidate_survives_repair_skip(tmp_path, monkeypatch):
    no_place = {**GOOD, 0: ('The cook pours water into flour.', ['e1'])}
    d, report, fake = run(tmp_path, monkeypatch, langs=('en',), script=script(no_place),
                          repair=lambda data, n: {'cues': [{'gap_id': g['gap_id'], 'skip': True, 'reason': 'cannot add place'}
                                                           for g in data['gaps']]})
    cues = {c['id']: c for c in report['cues']}
    assert cues[0]['en'] == no_place[0][0] and cues[0]['verdict'] == 'supported'
    assert any('committed without naming the place' in issue for issue in report['issues'])
    assert any(h['step'] == 'establish_fallback' for h in report['cue_history']['0'])
    assert 'module' in __import__('narrate.director', fromlist=['place_terms']).place_terms(
        {**BIBLE, 'place': 'space station', 'setting': 'a crowded spacecraft module with equipment panels'})


def test_coverage_report_explains_silence_and_enforces_target(tmp_path, monkeypatch):
    d, report, fake = run(tmp_path, monkeypatch, langs=('en',), script=script(skip=(1,)))
    coverage = report['coverage']
    assert coverage['narratable'] == 3 and coverage['narrated'] == 2 and coverage['silent_by_choice'] == 1
    assert coverage['percent_of_narratable'] == 67 and coverage['percent_excluding_silent_by_choice'] == 100
    assert coverage['meets_target'] and coverage['silent']['1']['why'] == 'no_new_info'
    assert '**Coverage:** 2/3' in (tmp_path / 'trace.md').read_text()


def test_context_title_is_unverified_context_for_bible_and_script(tmp_path, monkeypatch):
    fake = Fake(timeline=windows, bible=BIBLE, script=script()).install(monkeypatch)
    cfg = resolve_provider(load_config(), 'mock')
    cfg['tts']['backend'] = 'silent'
    monkeypatch.setattr('narrate.agent.core.detect', fake_detect(GAPS))
    title = 'How To Make Soft Layered Roti - Paratha'
    report = Director('samples/sample_kitchen.mp4', tmp_path, cfg, ['en'], SpendGuard(.5), context='  ' + title + '\n').run()
    for role in ('bible', 'script'):
        vt = fake.role(role)[0]['data']['video_title']
        assert vt['text'] == title and 'UNVERIFIED' in vt['note'] and 'never evidence' in vt['note']
    assert 'video_title' not in fake.role('timeline')[0]['data']       # perception never sees the title
    assert 'UNVERIFIED' in fake.role('script')[0]['system'] and report['video_title'] == title
    assert json.loads((tmp_path / 'report.json').read_text())['video_title'] == title
    assert title in (tmp_path / 'trace.md').read_text()
    d2, report2, fake2 = run(tmp_path / 'none', monkeypatch, langs=('en',))
    assert 'video_title' not in fake2.role('script')[-1]['data'] and report2['video_title'] is None


def test_context_reaches_run_director_from_cli_and_cache_builder(monkeypatch, tmp_path):
    import narrate.__main__ as main
    import narrate.director as director
    from scripts.build_cached_runs import title_from_attribution
    seen = {}
    monkeypatch.setattr(director, 'run_director', lambda *a, **kw: seen.update(kw) or {'estimated_cost_usd': 0})
    monkeypatch.setattr(sys, 'argv', ['narrate', 'agent', 'samples/sample_kitchen.mp4', '--out', str(tmp_path), '--mock', '--context', 'Harvest on the ISS'])
    main.main()
    assert seen['context'] == 'Harvest on the ISS'
    rows = {}
    for line in open('samples/SOURCES.md', encoding='utf-8'):
        f = [x.strip() for x in line.split('|')]
        if len(f) > 6 and f[1].endswith('.mp4'):
            rows[f[1]] = title_from_attribution(f[4])
    assert rows['nasa_chile_harvest_0000-0150.mp4'] == 'Astronauts harvest, eat first chile pepper crop on space station'
    assert rows['cooking_roti_0028-0148.mp4'] == 'How To Make Soft Layered Roti - Paratha'
    assert rows['sample_kitchen.mp4'] is None


def test_shorter_windows_with_previous_events_and_climax_prompt(tmp_path, monkeypatch):
    from narrate.media import split_slots
    from narrate.director import DEFAULTS
    from narrate import director_prompts as P
    assert DEFAULTS['window_s'] == 12 and load_config()['director']['window_s'] == 12
    wins = split_slots(0., 110., 12, [57.], 2, 6)                       # NASA clip length: ~10 windows (log estimate)
    assert len(wins) == 10 and all(e - s <= 12 for s, e in wins)
    d, report, fake = run(tmp_path, monkeypatch, langs=('en',))
    calls = fake.role('timeline')
    assert len(calls) == 3 and 'previous_events' not in calls[0]['data']
    assert calls[1]['data']['previous_events'][-1]['what'] == EVENTS[0]['what']
    for needle in ('eating, drinking', 'facial reactions', 'interactions between people', 'changes of state', 'NEW'):
        assert needle in P.TIMELINE
    assert 'est. Super VL timeline cost' in next(s for s in report['stages'] if s['stage'] == 'shots')['output']
    ev, _ = normalise_events({'events': [{'t_start': 1, 't_end': 3, 'what': 'An astronaut bites the pepper', 'change': 'first taste'}]}, 0, 12, 30)
    assert ev[0]['change'] == 'first taste'


def test_hindi_gets_gender_neutral_instruction_when_gender_not_visible(tmp_path, monkeypatch):
    bible = {**BIBLE, 'cast': [{'id': 'c1', 'descriptor': 'the cook', 'first_seen': 5, 'notes': 'striped sleeves; gender not visible'}]}
    d, report, fake = run(tmp_path, monkeypatch, bible=bible, hindi=lambda data, n: {'cues': [{'gap_id': c['gap_id'], 'hi': 'आटा गूँधा जा रहा है।'} for c in data['cues']]})
    call = fake.role('hindi')[0]
    assert 'gender-neutral' in call['data']['cast_gender']['the cook'] and 'आटा गूँधा जा रहा है' in call['system']
    d.bible = {**BIBLE, 'cast': [{'id': 'c1', 'descriptor': 'the cook', 'notes': 'a woman in a striped shirt'}]}
    assert d.cast_gender() == {'the cook': 'feminine (visible)'}


def test_trace_opens_with_run_summary(tmp_path, monkeypatch):
    d, report, fake = run(tmp_path, monkeypatch, langs=('en',), script=script(skip=(1,)))
    md = (tmp_path / 'trace.md').read_text().splitlines()
    i = md.index('## Run summary')
    assert i < 6 and md.index('## Stages') > i
    summary = md[i + 2:i + 7]
    assert [l.split(':**')[0] for l in summary] == ['- **Model calls', '- **Cost', '- **Cues', '- **Silent by choice', '- **Dropped']
    assert 'Ultra 2/6' in summary[0] and 'gap 1' in summary[3] and summary[4].endswith('none')
