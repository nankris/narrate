"""Round 8b extended-AD coverage, chronology and boundary regressions. Offline only."""
import pytest

from narrate.extended import plan_pauses
from narrate.extended_director import (DEFAULTS, ExtendedDirector, event_in_window,
                                       split_speech_at_silences)
from narrate.media import micro_silences, sensitive_visual_changes


LECTURE = 'samples/failure_continuous_speech.mp4'


def test_real_lecture_micro_silences_and_sensitive_slide_change():
    gaps = micro_silences(LECTURE, 30, noise_db=-30, minimum=.08)
    assert [g['end'] for g in gaps] == pytest.approx([3.1617, 10.6836, 18.1873, 25.7015], abs=.03)
    assert sensitive_visual_changes(LECTURE, threshold=1., fps=2.) == [15.0]

    speech = split_speech_at_silences([{'start': 0, 'end': 30}], gaps)
    pauses = plan_pauses(30, speech, micro_silences=gaps, visual_changes=[15],
                         min_spacing_s=12, max_pauses_per_minute=4)
    assert pauses[0]['t'] == pytest.approx(3.105, abs=.03)
    slide = next(p for p in pauses if p['source'] == 'visual_change')
    assert slide['t'] == pytest.approx(18.13, abs=.03)
    assert slide['snap_reason'] == 'forward_to_micro_silence'
    assert all(not any(s['start'] < p['t'] < s['end'] for s in speech) for p in pauses)


def test_pause_plan_hard_coverage_gap_and_closing_pause():
    pauses = plan_pauses(120, [], min_spacing_s=12, max_pauses_per_minute=4,
                         max_coverage_gap_s=25, final_pause_within_s=3)
    points = [0.] + [p['t'] for p in pauses] + [120.]
    assert max(b - a for a, b in zip(points, points[1:])) <= 25
    assert pauses[-1]['t'] == 120
    assert pauses[-1]['source'] == 'closing'
    assert pauses[-1]['snap_reason'] == 'source_end_closing_freeze'


def test_key_event_snaps_forward_to_natural_boundary_and_records_why():
    pauses = plan_pauses(35, [], scene_cuts=[12.5],
                         timeline_events=[{'id': 'e1', 't_end': 10, 'importance': 5}],
                         min_spacing_s=5, max_pauses_per_minute=20)
    event = next(p for p in pauses if p['source'] == 'timeline_event')
    assert event['t'] == 12.5
    assert event['from_t'] == 10
    assert event['snap_reason'] == 'forward_to_scene_cut'


def _director_for_checks():
    director = object.__new__(ExtendedDirector)
    director.x = {**DEFAULTS, 'min_words': 0, 'max_words': 80, 'redundancy_previous': .48}
    director.pause_rows = [
        {'id': 1, 't': 10, 'reason': 'establishing'},
        {'id': 2, 't': 20, 'reason': 'event'},
    ]
    director.timeline = [
        {'id': 'e1', 't_start': 1, 't_end': 9, 'what': 'A bowl is set down.',
         'subtitle_text': '', 'confidence': 1},
        {'id': 'e2', 't_start': 10, 't_end': 18, 'what': 'Dough is rolled flat.',
         'subtitle_text': '', 'confidence': 1},
        {'id': 'e3', 't_start': 19, 't_end': 24, 'what': 'The dough is flipped.',
         'subtitle_text': '', 'confidence': 1},
    ]
    director.pause_frames = {}
    return director


def test_window_assignment_and_postcheck_flag_future_evidence():
    director = _director_for_checks()
    assert event_in_window(director.timeline[1], 10, 20)
    assert not event_in_window(director.timeline[2], 10, 20)
    payload = director.pause_payload(director.pause_rows[1], 10)
    assert [e['id'] for e in payload['events']] == ['e2']
    assert payload['events'][0]['t_start'] == 10 and payload['events'][0]['t_end'] == 18

    entry = {'text': 'The dough is rolled flat on the mat. It rests there in a thin round.',
             'evidence': ['e2', 'e3']}
    valid, problems = director.cue_problems(2, entry)
    assert valid == ['e2']
    assert any('future event evidence' in p and 'e3' in p for p in problems)


def test_previous_cue_redundancy_is_repaired():
    director = _director_for_checks()
    prior = {'text': 'The cook rolls the dough into a long thin oval. Small dough balls wait nearby.'}
    entry = {'text': 'The cook rolls the dough into a long, thin oval. Several dough balls wait nearby.',
             'evidence': ['e2']}
    _, problems = director.cue_problems(2, entry, {1: prior})
    assert 'repeats or paraphrases the previous extended cue' in problems


def test_two_or_three_sentences_is_a_real_run_hard_check():
    director = _director_for_checks()
    director.mock = False
    entry = {'text': 'The dough is rolled flat on the mat.', 'evidence': ['e2']}
    _, problems = director.cue_problems(2, entry)
    assert 'cue must be 2-3 fluent sentences' in director.hard_problems(problems)


def test_establishing_frame_cannot_make_global_only_visible_claim():
    director = _director_for_checks()
    entry = {'text': 'A cook works at a kitchen table. Only their hands are visible.',
             'evidence': ['e1']}
    _, problems = director.cue_problems(1, entry)
    assert 'unsupported global visibility claim from one establishing frame' in problems


def test_dropped_pause_gets_model_written_rescue_retry():
    director = _director_for_checks()
    director.x = {**director.x, 'rescue_rounds': 1, 'max_repair_rounds': 2}
    director.pause_rows = [director.pause_rows[0]]
    director.timeline = [director.timeline[0]]
    director.pause_frames = {1: {}}
    director.extended_cues = {}
    director.ext_candidates = {}
    director.ext_dropped = {1: 'writer returned no cue'}
    director.ext_history = {}
    model_entry = {'text': 'A bowl sits on the kitchen table. A hand steadies it beside a spoon.',
                   'evidence': ['e1']}
    director.repair = lambda failed, round_no: {1: model_entry}
    director.verify = lambda entries: {1: {'verdict': 'supported', 'wrong': '', 'reason': 'visible'}}

    result = director.st_rescue_extended()
    assert '1 of 1' in result
    assert director.extended_cues[1]['text'] == model_entry['text']
    assert director.extended_cues[1]['rescued'] is True
    assert 1 not in director.ext_dropped
