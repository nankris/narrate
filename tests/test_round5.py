"""Round 5 (DESIGN_v2.md): story arc + object identity in the bible, focused re-look, opening variety, concrete-detail /
sound / camera-subject lint, Hindi active voice and the Hindi refit fix. Offline: scripted fake models only, no network."""
from narrate import director_prompts as P
from narrate.director import clean_bible, hi_passives, opening
from tests.test_director import BIBLE, EVENTS, GOOD, postcheck_director, run, script


def first_cue(d):
    d.pending[0] = {'text': GOOD[0][0], 'evidence': ['e1']}


def test_camera_subject_with_any_verb_is_banned_but_camera_object_allowed(tmp_path, monkeypatch):
    d = postcheck_director(tmp_path, monkeypatch)
    first_cue(d)
    for bad in ('The camera lowers from the bowl and the cook kneads the dough.', 'She kneads the dough as the camera rises.',
                'The dough rests, and the camera is lowered toward the bowl.'):
        assert any('camera as the subject' in p and 'Fix:' in p for p in d.check_cue(1, bad, ['e3'])[1]), bad
    for ok in ('She lowers the camera and kneads the dough into a ball.', 'The cook holds the camera high over the smooth dough.'):
        assert not any('camera' in p for p in d.check_cue(1, ok, ['e3'])[1]), ok


def test_sound_descriptions_are_banned(tmp_path, monkeypatch):
    d = postcheck_director(tmp_path, monkeypatch)
    first_cue(d)
    for bad in ('Applause sounds as she kneads the dough.', 'She kneads the dough ball with laughter.', 'Music plays while she kneads the dough.'):
        assert any('sound the listener already hears' in p for p in d.check_cue(1, bad, ['e3'])[1]), bad
    assert d.check_cue(1, 'She claps and laughs over the smooth dough ball.', ['e3'])[1] == []


def test_bare_subject_and_verb_needs_a_concrete_detail(tmp_path, monkeypatch):
    d = postcheck_director(tmp_path, monkeypatch)
    first_cue(d)
    for bare in ('The cook rolls.', 'She kneads it.', 'They knead it again.'):
        assert any('no concrete detail' in p for p in d.check_cue(1, bare, ['e3'])[1]), bare
    assert d.check_cue(1, 'The cook kneads the dough smooth.', ['e3'])[1] == []


def test_clean_bible_story_arc_names_and_look_for():
    raw = {'beats': [{'t': 80, 'beat': 'the strip is coiled', 'why': 'the coil makes the layers', 'events': ['e25', 3, None]},
                     {'t': 5, 'beat': 'water into flour'}, {'t': 9, 'beat': ''}],
           'names': [{'name': 'the harvested pepper', 'aliases': ['Small plant', 'plant', 'the harvested pepper'], 'from_t': 77},
                     {'name': 'ghost', 'aliases': 'plant'}, {'name': 'only itself', 'aliases': ['only itself']}],
           'look_for': [{'t_start': 90, 't_end': 100, 'what': 'the crew tastes the pepper'}, {'t_start': 5, 't_end': 2, 'what': 'bad window'},
                        {'t_start': 1, 't_end': 3, 'what': ''}]}
    b = clean_bible(raw, {})
    assert b['beats'][0] == {'t': 80., 'beat': 'the strip is coiled', 'why': 'the coil makes the layers', 'events': ['e25', '3']}
    assert b['beats'][1] == {'t': 5., 'beat': 'water into flour'} and len(b['beats']) == 2
    assert b['names'] == [{'name': 'the harvested pepper', 'aliases': ['small plant', 'plant'], 'from_t': 77.}]
    assert b['look_for'] == [{'t_start': 90., 't_end': 100., 'what': 'the crew tastes the pepper'}]
    assert clean_bible({}, {})['names'] == [] and clean_bible({}, {})['look_for'] == []


def test_object_identity_from_the_bible_is_enforced_and_given_to_the_verifier(tmp_path, monkeypatch):
    d = postcheck_director(tmp_path, monkeypatch)
    first_cue(d)
    d.bible = {**BIBLE, 'names': [{'name': 'the dough ball', 'aliases': ['lump', 'small lump'], 'from_t': 12}]}
    problems = d.check_cue(1, 'She kneads the small lump smooth.', ['e3'])[1]
    assert any('object identity ("lump" is "the dough ball"' in p and 'Fix: call it "the dough ball"' in p for p in problems)
    assert d.check_cue(1, 'She kneads the lump into a smooth dough ball.', ['e3'])[1] == []   # canonical name present
    d.bible['names'][0]['from_t'] = 30                                                       # alias not yet that object
    assert not d.identity_problems(d.gap(1), 'She kneads the lump smooth.')
    bible = {**BIBLE, 'names': [{'name': 'the dough ball', 'aliases': ['lump'], 'from_t': 0}]}
    d2, report, fake = run(tmp_path / 'run', monkeypatch, langs=('en',), bible=bible)
    assert fake.role('verify')[0]['data']['object_names'] == bible['names']
    assert fake.role('script')[0]['data']['bible']['names'] == bible['names']


def test_beats_key_event_and_routine_reach_the_script(tmp_path, monkeypatch):
    events = EVENTS + [{'t_start': 22.0, 't_end': 25.5, 'what': 'The cook laughs and holds up the flat round', 'importance': 5, 'confidence': .9}]
    windows = lambda data, n: {'events': [ev for ev in events if data['window'][0] <= (ev['t_start'] + ev['t_end']) / 2 < data['window'][1]]}
    bible = {**BIBLE, 'beats': [{'t': 13, 'beat': 'the dough becomes smooth', 'why': 'so it rolls thin', 'events': ['e3']},
                                {'t': 21, 'beat': 'the first round is rolled'}]}
    d, report, fake = run(tmp_path, monkeypatch, langs=('en',), timeline=windows, bible=bible)
    gaps = {g['gap_id']: g for g in fake.role('script')[0]['data']['gaps']}
    assert gaps[1]['beat'] == 'the dough becomes smooth (so it rolls thin)'   # mapped by its cited event
    assert gaps[2]['beat'] == 'the first round is rolled'                     # mapped by time
    assert 'beat' not in gaps[0] and gaps[2]['key_event'] == 'e5'              # importance 5 + a visible reaction
    for needle in ('Tell the story arc', 'Lead with key_event', 'bare subject and verb', 'Vary the openings', 'Never describe sounds', 'routine'):
        assert needle in P.SCRIPT
    assert '**Beats per gap:** gap 1: the dough becomes smooth' in (tmp_path / 'trace.md').read_text()


def test_routine_flag_marks_a_gap_that_repeats_the_previous_activity(tmp_path, monkeypatch):
    events = [{'t_start': 5.0, 't_end': 8.0, 'what': 'The cook kneads the dough in the bowl with both hands', 'importance': 3, 'confidence': .9},
              {'t_start': 13.0, 't_end': 17.0, 'what': 'The cook kneads the dough in the bowl with both hands', 'importance': 3, 'confidence': .9},
              {'t_start': 21.0, 't_end': 26.0, 'what': 'The cook rolls a dough ball flat with a rolling pin', 'importance': 5, 'confidence': .9}]
    windows = lambda data, n: {'events': [ev for ev in events if data['window'][0] <= (ev['t_start'] + ev['t_end']) / 2 < data['window'][1]]}
    cues = {0: ('In a kitchen, the cook kneads dough.', ['e1']), 2: ('She rolls a dough ball flat with a rolling pin.', ['e3'])}
    d, report, fake = run(tmp_path, monkeypatch, langs=('en',), timeline=windows, bible={**BIBLE, 'beats': []}, script=script(cues, skip=(1,)))
    gaps = {g['gap_id']: g for g in fake.role('script')[0]['data']['gaps']}
    assert gaps[1].get('routine') is True and 'routine' not in gaps[0] and 'routine' not in gaps[2]
    assert report['gaps_skipped_no_new_info'] == [1]


def test_focused_relook_adds_an_unseen_beat_as_evidence(tmp_path, monkeypatch):
    bible = {**BIBLE, 'look_for': [{'t_start': 21, 't_end': 25, 'what': 'the cook tastes a piece of the dough'}]}
    def timeline(data, n):
        if data.get('look_for'):
            return {'events': [{'t_start': 22.0, 't_end': 24.0, 'what': 'The cook bites a corner of the flat dough round', 'importance': 3},
                               {'t_start': 21.0, 't_end': 26.0, 'what': 'The cook rolls a dough ball flat with a rolling pin', 'importance': 5}]}
        s, e = data['window']
        return {'events': [ev for ev in EVENTS if s <= (ev['t_start'] + ev['t_end']) / 2 < e]}
    d, report, fake = run(tmp_path, monkeypatch, langs=('en',), timeline=timeline, bible=bible)
    calls = fake.role('timeline')
    assert len(calls) == 4 and calls[-1]['data']['look_for'] == 'the cook tastes a piece of the dough'
    assert 'FOCUS' in calls[-1]['system'] and 'never invent it' in calls[-1]['system']
    added = [e for e in report['timeline'] if e.get('relook')]
    assert [(e['id'], e['importance']) for e in added] == [('e5', 4)]            # the duplicate rolling event is skipped
    assert 'e5' in next(g for g in fake.role('script')[0]['data']['gaps'] if g['gap_id'] == 2)['evidence']
    assert next(s for s in report['stages'] if s['stage'] == 'relook')['calls'] == 1
    assert report['director_stats']['ultra_calls'] == 2 and report['director_stats']['relook_events'] == 1
    for needle in ('look_for', 'names', 'why', 'events'):
        assert needle in P.BIBLE


def test_no_relook_without_look_for(tmp_path, monkeypatch):
    d, report, fake = run(tmp_path, monkeypatch, langs=('en',))
    assert len(fake.role('timeline')) == 3 and not any(s['stage'] == 'relook' for s in report['stages'])


def test_monotone_openings_are_restyled_in_the_batched_repair_and_kept_if_the_rewrite_fails(tmp_path, monkeypatch):
    same = {0: ('The cook pours water into flour in the home kitchen.', ['e1']), 1: ('The cook kneads the flour into a smooth ball.', ['e3']),
            2: ('The cook rolls a dough ball flat with a pin.', ['e4'])}
    def repair(data, n):
        out = []
        for g in data['gaps']:
            if n == 1:
                assert any(r.startswith('Style: 3 of 3 cues open with "the cook"') for r in g['why_rejected'])
                assert g['other_openings'] and 'the cook' in g['other_openings']
            text = 'Now she kneads the flour into a smooth ball.' if g['gap_id'] == 1 else 'The cook flattens the dough ball with a pin.'
            out.append({'gap_id': g['gap_id'], 'text': text, 'evidence': ['e3'] if g['gap_id'] == 1 else ['e4']})
        return {'cues': out}
    d, report, fake = run(tmp_path, monkeypatch, langs=('en',), script=script(same), repair=repair)
    texts = {c['id']: c['en'] for c in report['cues']}
    assert texts == {0: same[0][0], 1: 'Now she kneads the flour into a smooth ball.', 2: same[2][0]}   # gap 2: verified original kept
    assert [g['gap_id'] for g in fake.role('repair')[0]['data']['gaps']] == [1, 2]
    assert 'still opens with "the cook"' in ' '.join(fake.role('repair')[1]['data']['gaps'][0]['why_rejected'])
    assert report['director_stats']['restyled'] == 2 and report['director_stats']['restyle_kept'] == 1
    assert [h['step'] for h in report['cue_history']['2']][-2:] == ['repair_2', 'restyle_kept']
    assert report['director_stats']['ultra_calls'] == 4 and not report['dropped_gaps'].get(2)


def test_restyle_needs_spare_ultra_calls_and_a_monotone_track(tmp_path, monkeypatch):
    same = {0: ('The cook pours water into flour in the home kitchen.', ['e1']), 1: ('The cook kneads the flour into a smooth ball.', ['e3']),
            2: ('The cook rolls a dough ball flat with a pin.', ['e4'])}
    d, report, fake = run(tmp_path, monkeypatch, langs=('en', 'hi'), director={'max_ultra_calls': 3}, script=script(same))
    assert not fake.role('repair') and len(report['cues']) == 3 and not report['director_stats'].get('restyled')
    assert opening('The cook rolls.') == 'the cook' and opening('"Now," she said') == 'now she'


def test_hindi_passive_counter():
    assert hi_passives('आटे की लोई कसकर लपेटी जाती है, फिर उस पर तेल डाला जाता है।') == 2
    assert hi_passives('आटा गूँधा जा रहा है।') == 1
    assert hi_passives('हाथ आटे को गूँधते हैं।') == 0 and hi_passives('लोई बनती है।') == 0
    assert hi_passives('वह कटोरा ले जाता है।') == 0                                      # compound verb, not a passive


def test_hindi_latin_label_gets_a_targeted_refit(tmp_path, monkeypatch):
    def hindi(data, n):
        if n == 1:
            return {'cues': [{'gap_id': c['gap_id'], 'hi': 'हाथ HATCH CHILE नोट के पास आटा रखते हैं।' if c['gap_id'] == 1 else 'हाथ आटे में पानी डालते हैं।'}
                             for c in data['cues']]}
        assert [c['gap_id'] for c in data['cues']] == [1]
        assert 'Latin letters ("HATCH CHILE")' in data['cues'][0]['problem'][0] and 'Devanagari' in data['cues'][0]['problem'][0]
        return {'cues': [{'gap_id': 1, 'hi': 'हाथ हैच चिली नोट के पास आटा रखते हैं।'}]}
    d, report, fake = run(tmp_path, monkeypatch, hindi=hindi)
    assert {c['id']: c.get('hi') for c in report['cues']}[1] == 'हाथ हैच चिली नोट के पास आटा रखते हैं।'
    out = next(s for s in report['stages'] if s['stage'] == 'hindi')['output']
    assert '1 failed checks (latin 1) -> 1 refit; 0 without Hindi' in out
    assert 'Devanagari letters' in P.HINDI_REFIT and '"problem"' in P.HINDI_REFIT


def test_hindi_passive_chains_are_refit_softly(tmp_path, monkeypatch):
    lines = {0: 'आटे में पानी डाला जाता है और आटा गूँधा जाता है।', 1: 'आटा चिकना गूँधा जाता है।', 2: 'लोई बेलन से बेली जाती है।'}
    def hindi(data, n):
        if n == 1:
            return {'cues': [{'gap_id': c['gap_id'], 'hi': lines[c['gap_id']]} for c in data['cues']]}
        sent = {c['gap_id']: c for c in data['cues']}
        assert set(sent) == {0, 2} and 'passive chain (2 passives)' in sent[0]['problem'][0] and 'too many passive lines' in sent[2]['problem'][0]
        assert all('हाथ' in c['problem'][0] and 'soft' not in c for c in data['cues'])
        return {'cues': [{'gap_id': 0, 'hi': 'हाथ आटे में पानी डालकर उसे गूँधते हैं।'}, {'gap_id': 2, 'hi': 'लोई बेली जाती है और फिर बेली जाती है।'}]}
    d, report, fake = run(tmp_path, monkeypatch, hindi=hindi)
    hi = {c['id']: c.get('hi') for c in report['cues']}
    assert hi == {0: 'हाथ आटे में पानी डालकर उसे गूँधते हैं।', 1: lines[1], 2: lines[2]}   # worse rewrite rejected, original kept
    assert len(fake.role('hindi')) == 2 and 'passive 2' in next(s for s in report['stages'] if s['stage'] == 'hindi')['output']
    assert 'At most ONE' in P.HINDI and 'हाथ' in P.HINDI and 'Latin letters' in P.HINDI
