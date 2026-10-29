import json

from narrate.extended import plan_pauses
from narrate.extended_audit import audit_cached_run, audit_extended_plan


def test_event_candidate_anchors_after_event_end_not_generic_time():
    pauses = plan_pauses(20, [], timeline_events=[
        {'id': 'e1', 't': 4, 't_start': 4, 't_end': 8, 'importance': 5, 'what': 'rolling'}
    ], min_spacing_s=1, max_pauses_per_minute=30)
    event_pause = next(p for p in pauses if p['source'] == 'timeline_event')
    assert event_pause['t'] >= 8


def test_audit_rejects_future_event_and_accepts_small_tolerance():
    bad = {'pauses': [{'cue_id': 1, 't': 5, 'evidence_times': [{'id': 'e1', 't_end': 6}]}]}
    assert audit_extended_plan(bad)[0]['evidence_id'] == 'e1'
    good = {'pauses': [{'cue_id': 1, 't': 5, 'evidence_times': [{'id': 'e1', 't_end': 5.04}]}]}
    assert audit_extended_plan(good) == []


def test_audit_cached_run_requires_timed_evidence(tmp_path):
    (tmp_path / 'pause_plan.json').write_text(json.dumps({'pauses': [{'cue_id': 2, 't': 3}]}))
    assert audit_cached_run(tmp_path)[0]['reason'] == 'missing timed evidence'
