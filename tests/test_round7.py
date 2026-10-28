"""Round 7 (DESIGN_v2.md section 11): robustness, not more rules. HARD vs SOFT checks, punctuation normalisation, the candidate
pool and the no-Ultra final pass (Nano strike + Super VL verify), budget shortening with options, max-silence rescue as a soft
step, low temperature and the TTS preflight. Offline: scripted fake models only, no network, no real API calls."""
import json
from types import SimpleNamespace as NS
import pytest
from narrate import director_prompts as P
from narrate.config import load_config
from narrate.director import Director, classify, has_finite_verb, normalise_en, parse_tightened_options
from narrate.llm import Client
from tests.test_director import BIBLE, GOOD, Fake, make, postcheck_director, run, script, windows


def supported_unless(*phrases):
    """Fake verifier: a cue containing one of the phrases is contradicted on exactly that phrase."""
    def verify(data, n):
        out = []
        for c in data['cues']:
            bad = next((p for p in phrases if p in c['text']), '')
            out.append({'gap_id': c['gap_id'], 'verdict': 'contradicted' if bad else 'supported', 'wrong': bad,
                        'reason': 'frames show otherwise' if bad else 'visible'})
        return {'verdicts': out}
    return verify


# ---------- deterministic pieces ----------
def test_round6_false_fragments_now_have_a_finite_verb_and_real_fragments_do_not():
    for ok in ('The crew cheers and raises their arms in celebration, laughing and gesturing.', 'They brush oil over the long dough strip.',
               'White lid seals the bowl.', 'A woman in a green shirt passes a small white object to a man in a blue shirt.',
               'Crewmates in black and blue shirts cheer and raise their arms, laughing.', 'The cook twists the dough into a spiral on the mat.'):
        assert has_finite_verb(ok), ok
    for frag in ('A ball on the mat.', 'A ball on the mats.', 'Two balls on the mat.', 'Six risen dough balls.', 'Rolling the dough flat.'):
        assert not has_finite_verb(frag), frag


def test_normalise_en_changes_punctuation_only():
    assert normalise_en('They press the dough flat') == 'They press the dough flat.'
    assert normalise_en('She rolls it; the strip is long,') == 'She rolls it. The strip is long.'
    assert normalise_en('A sign reads "OPEN"') == 'A sign reads "OPEN".'
    assert normalise_en('Done!') == 'Done!' and normalise_en('') == ''


def test_problem_classes_hard_length_soft():
    hard, length, soft = classify(['Banned phrasing: camera direction. Fix: x', 'Unverified title-only claim (first). Fix: y',
                                   'over budget: 20 words, max 12. Fix: cut', 'TTS duration exceeds allowed speedup (measured 9.0 s)',
                                   'English cue has no finite verb. Fix: z', 'Banned phrasing: object identity ("plant" is "pepper")',
                                   'establishing cue does not say where. Fix: w', 'Style: still opens with "the cook"'])
    assert len(hard) == 3 and 'measured' in hard[2]          # camera, title claim, measured time: hard
    assert length == ['over budget: 20 words, max 12. Fix: cut']
    assert len(soft) == 4


def test_object_alias_that_is_part_of_the_canonical_name_is_not_flagged(tmp_path, monkeypatch):
    d = postcheck_director(tmp_path, monkeypatch)
    d.bible = {**BIBLE, 'names': [{'name': 'white label marked VEGG-03 CABBAGE', 'aliases': ['label', 'sticker'], 'from_t': 0}]}
    assert d.identity_problems(d.gap(1), 'She sets the pepper beside the white label.') == []    # nasa r6b gap 5
    assert d.identity_problems(d.gap(1), 'She sets the pepper beside the sticker.')


def test_tighten_options_parser():
    assert parse_tightened_options({'options': [{'text': ' A b. '}, {'text': 'A b.'}, 'C d.']}, 1) == ['A b.', 'C d.']
    assert parse_tightened_options({'text': 'One.'}, 1) == ['One.'] and parse_tightened_options({}, 1) == []


# ---------- flows ----------
def test_missing_period_and_semicolon_never_cost_a_cue_or_a_repair(tmp_path, monkeypatch):
    cues = {0: ('In a kitchen, the cook pours water into flour', ['e1']), 1: ('She kneads it; the ball turns smooth', ['e3']), 2: GOOD[2]}
    d, report, fake = run(tmp_path, monkeypatch, langs=('en',), script=script(cues))
    texts = {c['id']: c['en'] for c in report['cues']}
    assert texts[0] == 'In a kitchen, the cook pours water into flour.' and texts[1] == 'She kneads it. The ball turns smooth.'
    assert not fake.role('repair') and report['director_stats']['punctuation_fixed'] == 2


def test_soft_problem_gets_one_repair_then_the_verified_original_is_kept(tmp_path, monkeypatch):
    frag = 'The smooth dough ball beside the flour.'
    cues = {**GOOD, 1: (frag, ['e3'])}
    repair = lambda data, n: {'cues': [{'gap_id': g['gap_id'], 'text': 'A round dough ball on the wooden table.', 'evidence': ['e3']} for g in data['gaps']]}
    d, report, fake = run(tmp_path, monkeypatch, langs=('en',), script=script(cues), repair=repair)
    texts = {c['id']: c['en'] for c in report['cues']}
    assert len(fake.role('repair')) == 1                           # one soft attempt, never a second Ultra call for style
    assert texts[1] in (frag, 'A round dough ball on the wooden table.') and 1 not in report['dropped_gaps']
    assert report['director_stats']['soft_kept'] == 1 and report['coverage']['narrated'] == 3
    assert any(h['step'] == 'rescue' for h in report['cue_history']['1'])


def test_contradicted_establishing_detail_is_struck_by_nano_and_verified(tmp_path, monkeypatch):
    bad = 'In a kitchen, gloved hands pour water into flour.'
    cues = {**GOOD, 0: (bad, ['e1'])}
    repair = lambda data, n: {'cues': [{'gap_id': g['gap_id'], 'text': bad, 'evidence': ['e1']} for g in data['gaps']]}
    def tighten(data, n):
        assert data['cue']['wrong'] == 'gloved' and data['cue']['keep_place'] == ['kitchen']
        return {'text': 'In a kitchen, hands pour water into flour.'}
    d, report, fake = run(tmp_path, monkeypatch, langs=('en',), script=script(cues), repair=repair, tighten=tighten,
                          verify=supported_unless('gloved'))
    texts = {c['id']: c['en'] for c in report['cues']}
    assert texts[0] == 'In a kitchen, hands pour water into flour.'
    assert len(fake.role('tighten')) == 1 and fake.role('tighten')[0]['system'] == P.STRIKE
    assert report['director_stats']['ultra_calls'] <= 6 and not any('Establishing gap' in i for i in report['issues'])
    reasons = fake.role('repair')[0]['data']['gaps'][0]['why_rejected']
    assert any('remove or correct only "gloved"' in r and 'keep the place' in r for r in reasons)


def test_strike_that_adds_words_is_rejected(tmp_path, monkeypatch):
    bad = 'In a kitchen, gloved hands pour water into flour.'
    cues = {**GOOD, 0: (bad, ['e1'])}
    repair = lambda data, n: {'cues': [{'gap_id': g['gap_id'], 'text': bad, 'evidence': ['e1']} for g in data['gaps']]}
    d, report, fake = run(tmp_path, monkeypatch, langs=('en',), script=script(cues), repair=repair,
                          tighten={'text': 'In a kitchen, hands pour milk into flour.'}, verify=supported_unless('gloved'))
    assert 0 not in {c['id'] for c in report['cues']}
    assert any('Establishing gap 0 has no verified cue' in i for i in report['issues'])


def test_over_budget_cue_whose_measured_speech_fits_is_kept_after_shortening_fails(tmp_path, monkeypatch):
    long = 'Now she kneads the soft dough firmly on the table into a smooth ball.'    # 14 words, max 12, fallback 16
    cues = {**GOOD, 1: (long, ['e3'])}
    d, report, fake = run(tmp_path, monkeypatch, langs=('en',), script=script(cues), tighten=lambda data, n: {'options': [{'text': long}]},
                          repair=lambda data, n: {'cues': [{'gap_id': g['gap_id'], 'text': long, 'evidence': ['e3']} for g in data['gaps']]})
    g = d.gap(1)
    assert g['director_words_en'] < 14 <= d.fallback_words(g) and 14 > d.hard_words(g)
    assert {c['id']: c['en'] for c in report['cues']}[1] == long
    assert report['director_stats']['length_fallback'] == 1 and report['director_stats']['ultra_calls'] <= 6


def test_far_over_budget_is_still_dropped(tmp_path, monkeypatch):
    far = 'Now she kneads the soft dough firmly with both hands on the wooden table into a smooth round ball today.'   # 20 words
    cues = {**GOOD, 1: (far, ['e3'])}
    d, report, fake = run(tmp_path, monkeypatch, langs=('en',), script=script(cues), tighten=lambda data, n: {'text': far},
                          repair=lambda data, n: {'cues': [{'gap_id': g['gap_id'], 'text': far, 'evidence': ['e3']} for g in data['gaps']]})
    assert 1 not in {c['id'] for c in report['cues']} and 'over budget' in report['dropped_gaps'][1]


def test_tighten_picks_the_best_of_three_options_and_sees_measured_seconds(tmp_path, monkeypatch):
    long = 'Now she kneads the soft dough firmly with both hands on the wooden table into a smooth round ball today.'
    cues = {**GOOD, 1: (long, ['e3'])}
    options = {'options': [{'text': 'The camera pans as she kneads the dough into a smooth ball.'},   # hard: camera direction
                           {'text': 'Now she kneads the dough into a smooth ball.'},
                           {'text': 'She kneads it.'}]}                                                # soft: no concrete detail
    d, report, fake = run(tmp_path, monkeypatch, langs=('en',), script=script(cues), tighten=options)
    assert {c['id']: c['en'] for c in report['cues']}[1] == 'Now she kneads the dough into a smooth ball.'
    sent = fake.role('tighten')[0]['data']['cue']
    assert sent['measured_seconds'] > 0 and sent['allowed_seconds'] > 0 and not fake.role('repair')
    assert 'THREE shorter versions' in P.TIGHTEN and '"options"' in P.TIGHTEN


def test_failed_max_silence_rescue_stays_silent_by_choice(tmp_path, monkeypatch):
    camera = {'cues': [{'gap_id': g, 'text': 'The camera pans over the smooth dough ball.', 'evidence': ['e3']} for g in range(3)]}
    d, report, fake = run(tmp_path, monkeypatch, langs=('en',), director={'max_silent_run_s': 10},
                          script=script(cues={0: GOOD[0]}, skip=(1, 2)), repair=lambda data, n: {'cues': [c for c in camera['cues'] if c['gap_id'] in [g['gap_id'] for g in data['gaps']]]})
    rescued = [g for g, rows in report['cue_history'].items() if any(r['step'] == 'max_silence' for r in rows)]
    assert rescued and report['director_stats']['silence_rescue_failed'] == 1
    silent = report['coverage']['silent'][rescued[0]]
    assert silent['why'] == 'no_new_info' and report['coverage']['dropped'] == 0


def test_script_payload_puts_word_limits_next_to_each_gap_and_uses_low_temperature(tmp_path, monkeypatch):
    d, report, fake = run(tmp_path, monkeypatch, langs=('en',))
    data = fake.role('script')[0]['data']
    assert list(data)[0] == 'WORD_LIMITS' and len(data['WORD_LIMITS']) == 3
    assert data['WORD_LIMITS'][1].startswith('gap 1: ') and f"HARD max {d.gap(1)['director_words_en']}" in data['WORD_LIMITS'][1]
    assert all(g['words'].endswith(f"(HARD max {g['max_words']})") for g in data['gaps'])
    assert data['_temperature'] == .2 and fake.role('verify')[0]['data']['_temperature'] == 0.
    assert 'WORD_LIMITS' in P.SCRIPT and 'WORD_LIMITS' in P.REPAIR
    cfg = load_config()['director']
    assert cfg['temperature'] == .2 and cfg['verify_temperature'] == 0 and cfg['fallback_word_tolerance'] == .35


def test_client_sends_temperature_but_not_in_payload(monkeypatch):
    monkeypatch.setenv('NARRATE_TEST_KEY', 'fake-test-value')
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        return NS(usage=NS(prompt_tokens=20, completion_tokens=8), choices=[NS(message=NS(content='{"cues":[]}'))])
    cfg = load_config()
    cfg['key_env'] = 'NARRATE_TEST_KEY'
    client = Client(cfg, sdk_factory=lambda **kw: NS(chat=NS(completions=NS(create=create))))
    client.call('edit', {'gaps': [], '_temperature': .2})
    client.call('edit', {'gaps': []})
    assert calls[0]['temperature'] == .2 and 'temperature' not in calls[1]
    assert json.loads(calls[0]['messages'][1]['content'][0]['text']) == {'gaps': []}


def test_tts_preflight_aborts_before_any_model_call(tmp_path, monkeypatch):
    fake = Fake(timeline=windows, bible=BIBLE, script=script()).install(monkeypatch)
    d = make(tmp_path, monkeypatch, langs=('en', 'hi'))
    real = d.engine
    class Broken:
        def render(self, text, lang, target):
            if lang == 'hi':
                raise ModuleNotFoundError("No module named 'piper'")
            return real.render(text, lang, target)
    d.engine = Broken()
    with pytest.raises(RuntimeError, match=r'TTS preflight failed for hi .*no paid API call was made'):
        d.run()
    assert fake.calls == []


def test_tts_preflight_passes_with_a_working_voice(tmp_path, monkeypatch):
    Fake().install(monkeypatch)
    d = make(tmp_path, monkeypatch, langs=('en', 'hi'))
    assert d.preflight_tts() is True
    assert all((P.CALIBRATION[l], l) in d.tts_cache for l in ('en', 'hi'))   # calibration reuses the preflight render
