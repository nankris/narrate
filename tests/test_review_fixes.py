"""Offline tests for the Opus review fixes (a)-(e): refuted evidence, gap assignment, continuity/SKIP,
banned phrasing, and a fallback that never ships unchecked text. Fake clients only; no network."""
from narrate.agent.core import lint, is_skip
from test_fix2 import make_agent, two_gaps


def fake(a, monkeypatch, verdict='supported', fit=None, calls=None):
    real = a.submodel
    def sub(stage, data, media=None, mock_result=None):
        if calls is not None: calls.append((stage, data))
        if stage == 'perceive' and 'claim' in data: return {'verdict': verdict, 'evidence': 'fake'}
        if stage == 'fit' and fit is not None: return fit(data)
        return real(stage, data, media, mock_result)
    monkeypatch.setattr(a, 'submodel', sub)


# (a) contradicted claims leave the evidence board
def test_contradicted_claim_refutes_its_event(tmp_path, monkeypatch):
    a = make_agent(tmp_path)
    a.events = [{'t_start': 5., 't_end': 7., 'what': 'Title card appears', 'on_screen_text': '40 YEARS LATER'},
                {'t_start': 5.5, 't_end': 7.5, 'what': 'A woman walks along a bridge'}]
    g = a.gap(0)
    assert a.onscreen(g) == ['40 YEARS LATER']
    fake(a, monkeypatch, verdict='contradicted')
    out = a.verify_claim(gap_id=0, claim='Title: "40 YEARS LATER".')
    assert out['refuted_events'] == 1 and a.events[0]['refuted'] and not a.events[1].get('refuted')
    assert a.onscreen(g) == [] and all('40 YEARS' not in str(e) for e in a.gap_events(g))


# (b) an event that only brushes a gap is not assigned to it
def test_event_barely_overlapping_gap_is_not_assigned(tmp_path):
    a = make_agent(tmp_path)  # gap 5-8, window 4-8.5
    g = a.gap(0)
    assert not a.overlaps({'t_start': 7.6, 't_end': 14.}, g)      # 0.4 s overlap, later shot
    assert not a.overlaps({'t_start': 0., 't_end': 4.4}, g)       # ends in pre-roll only
    assert a.overlaps({'t_start': 4.5, 't_end': 7.5}, g)          # midpoint inside
    assert a.overlaps({'t_start': 0., 't_end': 20.}, g)           # covers the whole gap
    assert a.overlaps({'t_start': 6., 't_end': 9.5}, g)           # 2 s overlap


# (c) drafter sees previous lines and may skip redundant action gaps
def test_drafter_sees_previous_lines_and_can_skip(tmp_path, monkeypatch):
    a = make_agent(tmp_path, two_gaps()); a.langs = ['en']
    a.cues[0] = {'id': 0, 'start': 5., 'end': 8., 'en': 'A man tends plants in a greenhouse.'}
    calls = []
    fake(a, monkeypatch, fit=lambda d: {'cues': [{'id': 1, 'text': 'SKIP'}]}, calls=calls)
    out = a.draft_description(gap_ids=[1])
    payload = [d for s, d in calls if s == 'fit'][0]['gaps'][0]
    assert payload['previous_lines'] == ['A man tends plants in a greenhouse.']
    assert out['cues'] == [] and out['skipped_no_new_info'] == [1] and 1 in a.dropped and 1 in a.skipped


def test_establishing_gap_is_never_skipped(tmp_path, monkeypatch):
    a = make_agent(tmp_path, two_gaps())
    a.events = [{'t_start': 5., 't_end': 7.5, 'what': 'A man waters plants'}]
    fake(a, monkeypatch, fit=lambda d: {'cues': [{'id': g['id'], 'text': 'SKIP'} for g in d['gaps']]})
    out = a.draft_description(gap_ids=[0])
    assert 0 not in a.skipped and out['cues'] and not is_skip(out['cues'][0]['text'])


def test_commit_rejects_near_repeat_of_previous_cue(tmp_path):
    a = make_agent(tmp_path, two_gaps()); a.langs = ['en']
    assert a.propose_cue(0, 'A man tends the plants.')['ok']
    r = a.propose_cue(1, 'A man tends the plants.')
    assert not r['ok'] and ('repeats the previous cue' in str(r) or 'duplicate of gap 0' in str(r))
    r = a._commit(1, 'A man tends plants again.')
    assert not r['ok'] and 'repeats the previous cue' in str(r)


# (d) banned phrasing is enforced in code
def test_lint_bans_camera_and_literal_title():
    assert lint('Camera moves to the stove.') and lint('As camera pans, oil heats.') and lint('We see a pan.')
    assert lint('TITLE 40 YEARS LATER.') and lint('SKIP')
    assert not lint('Title: "40 YEARS LATER".') and not lint('She stirs the onions with a wooden spoon.')


def test_check_fit_and_drafts_reject_banned_phrasing(tmp_path, monkeypatch):
    a = make_agent(tmp_path, two_gaps())
    assert not a.check_fit(0, 'Camera moves left.', 'en')['ok']
    a.events = [{'t_start': 5., 't_end': 7.5, 'what': 'A cook stirs a pot'}]
    seen = []
    def fit(d):
        seen.append(d['instruction'].startswith('HARD LIMIT'))
        return {'cues': [{'id': 0, 'text': 'The camera pans to a pot.' if len(seen) == 1 else 'A cook stirs a pot.'}]}
    fake(a, monkeypatch, fit=fit)
    out = a.draft_description(gap_ids=[0])
    assert seen == [False, True] and out['cues'][0]['text'] == 'A cook stirs a pot.'


# (e) the fallback never ships unchecked text
def test_fallback_drops_cue_that_fails_verification(tmp_path, monkeypatch):
    for verdict, kept in (('broken', False), ('supported', True)):   # 'broken' = invalid VL reply: never checked
        a = make_agent(tmp_path / verdict); a.langs = ['en']
        a.cfg['agent']['max_verifications'] = 0   # orchestrator cap already used up
        a.propose_cue(0, 'Sign reads OPEN')
        assert a.needs_verification()
        fake(a, monkeypatch, verdict=verdict)
        monkeypatch.setattr(a, 'render', lambda *x: [])
        a.fallback_finish('turn limit')
        assert (0 in a.cues) is kept


def test_fallback_ignores_draft_built_on_refuted_evidence(tmp_path, monkeypatch):
    a = make_agent(tmp_path); a.langs = ['en']
    a.events = [{'t_start': 5., 't_end': 7., 'what': 'Title card', 'on_screen_text': '40 YEARS LATER', 'refuted': True}]
    a.drafts[0] = 'Title: "40 YEARS LATER".'
    monkeypatch.setattr(a, 'render', lambda *x: [])
    a.fallback_finish('turn limit')
    assert 0 not in a.cues and any('stale draft' in str(r['note']) for r in a.steps)


def test_translate_hindi_is_idempotent(tmp_path, monkeypatch):
    a = make_agent(tmp_path, two_gaps())
    a.propose_cue(0, 'A cook stirs a pot.')
    calls = []
    fake(a, monkeypatch, calls=calls)
    a.translate_hindi(); n = sum(s == 'edit' for s, _ in calls)
    a.translate_hindi()
    assert n >= 1 and sum(s == 'edit' for s, _ in calls) == n and a.cues[0].get('hi')


def test_bare_event_object_from_vl_is_accepted(tmp_path, monkeypatch):
    a = make_agent(tmp_path); a.mock = False
    import narrate.agent.core as core
    monkeypatch.setattr(core, 'ffmpeg', lambda *x: None)
    monkeypatch.setattr(core, 'data_url', lambda *x: 'data:')
    (a.work / 'inspection.mp4').write_bytes(b'x')
    monkeypatch.setattr(a, 'submodel', lambda *x, **k: {'t_start': 5.2, 't_end': 7.0, 'what': 'The cook rolls dough', 'importance': 4, 'confidence': .9})
    out = a.inspect_video_segment(5., 8.)
    assert out['modality'] == 'video' and out['events'][0]['what'] == 'The cook rolls dough'


def test_gap_without_own_evidence_is_not_drafted_or_skipped(tmp_path, monkeypatch):
    a = make_agent(tmp_path, two_gaps()); a.mock = False
    a.events = [{'t_start': 5., 't_end': 7.5, 'what': 'A cook kneads dough'}]
    fake(a, monkeypatch, fit=lambda d: {'cues': [{'id': g['id'], 'text': 'SKIP' if g['id'] else 'A cook kneads dough.'} for g in d['gaps']]})
    out = a.draft_description(gap_ids=[0, 1])
    assert [c['id'] for c in out['cues']] == [0] and out['needs_inspection_first'] == [1] and 1 not in a.dropped
    assert a.draft_description(gap_id=1)['next'].startswith('call inspect_video_segment')
