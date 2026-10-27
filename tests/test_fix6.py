"""Real-run regression (fix5 ToS/NASA): after ~15 turns Ultra omitted `note`, and every later tool call
failed with a bare "ValidationError" until the turn cap. Calls without a note must run; bad args must explain themselves."""
from tests.test_fix5 import kitchen_agent


def test_missing_or_long_note_still_runs(tmp_path, monkeypatch):
    a = kitchen_agent(tmp_path, monkeypatch)
    r = a.execute('drop_gap', {'gap_id': 3, 'reason': 'test'})
    assert r.get('ok') is not False, r
    r = a.execute('drop_gap', {'gap_id': 2, 'reason': 'test', 'note': ' '.join(['word'] * 40)})
    assert r.get('ok') is not False, r


def test_invalid_args_error_is_explained(tmp_path, monkeypatch):
    a = kitchen_agent(tmp_path, monkeypatch)
    r = a.execute('drop_gap', {'gap_id': 'three', 'reason': 'x'})
    assert r['ok'] is False and r['error'].startswith('invalid arguments: ') and 'three' in r['error']


def test_unknown_gap_id_and_no_gap_inspection_explain_themselves(tmp_path, monkeypatch):
    """Real-run regression (fix6 continuous-speech clip): StopIteration on unknown gap ids cost 20 turns / $0.10."""
    a = kitchen_agent(tmp_path, monkeypatch)
    r = a.execute('draft_description', {'gap_id': 9})
    assert r['ok'] is False and 'unknown gap_id 9' in r['error'] and 'valid gap ids' in r['error']
    a.gaps = []
    a.counts['gap_detection'] = 1
    r = a.execute('draft_description', {'gap_id': 1})
    assert 'call finalize' in r['error']
    r = a.execute('inspect_video_segment', {'start': 0, 'end': 10})
    assert r['ok'] is False and r['next'] == 'finalize'
