"""Round 8b time-aware scoring and visual-ground-truth regressions. Offline only."""
import json

import pytest

from narrate.config import load_config
from narrate.groundtruth import (GROUNDTRUTH_VISUAL_CONSOLIDATE, frame_text_change_times,
                                 parse_micro_silences, snap_pause_forward)
from scripts.score_extended import (aggregate_score, attach_window_groundtruth, build_cue_windows,
                                    normalise_judge, score_extended, target_in_window)


def test_cue_windows_use_preceding_source_and_closing_cue_reaches_clip_end():
    windows = build_cue_windows([
        {'cue_id': 1, 't': 10, 'cue_text': 'first'},
        {'cue_id': 2, 't': 20, 'cue_text': 'second'},
        {'cue_id': 3, 't': 105, 'cue_text': 'closing'},
    ], 100)
    assert [(w['source_start'], w['source_end']) for w in windows] == [(0., 10.), (10., 20.), (20., 100.)]
    assert windows[0]['start_inclusive'] and not windows[1]['start_inclusive']
    assert target_in_window({'t': 12}, windows[0])  # two-second timestamp tolerance
    assert not target_in_window({'t': 12.001}, windows[0])
    assert not target_in_window({'t': 10}, windows[1], tolerance_s=0)


def _groundtruth():
    return {
        'duration': 100,
        'setting': 'workbench',
        'cast': [],
        'objects': ['bowl', 'dough'],
        'speech_intervals': [],
        'scene_cuts': [30],
        'segments': [
            {'id': 's1', 't_start': 0, 't_end': 10,
             'action_steps': ['Pours water into the bowl (5s).']},
            {'id': 's2', 't_start': 10, 't_end': 30,
             'action_steps': ['Cuts the dough with a knife (25s).']},
            {'id': 's3', 't_start': 80, 't_end': 95,
             'action_steps': ['Pours oil over dough balls in the bowl (90s).']},
        ],
        'key_events': [
            {'id': 'k1', 't': 5, 'what': 'Pours water into the bowl', 'scoring_target': True},
            {'id': 'k2', 't': 25, 'what': 'Cuts dough with a knife', 'scoring_target': True},
            {'id': 'k3', 't': 90, 'what': 'Pours oil over dough balls', 'scoring_target': True},
        ],
        'confusing_parts': [
            {'id': 'c1', 't': 25, 'what': 'Dough is suddenly divided',
             'what_to_explain': 'A knife divides the dough', 'scoring_target': True},
        ],
    }


def test_window_membership_and_normalisation_reject_cross_window_coverage():
    gt = _groundtruth()
    windows = build_cue_windows([{'cue_id': 1, 't': 10}, {'cue_id': 2, 't': 30}], 100)
    windows, events, actions, confusing = attach_window_groundtruth(windows, gt)
    assert [x['id'] for x in windows[0]['key_events']] == ['k1']
    assert [x['id'] for x in windows[1]['key_events']] == ['k2']
    assert all('k3' not in [x['id'] for x in window['key_events']] for window in windows)

    raw = {'cues': [
        {'cue_id': 1,
         'key_events': [{'id': 'k1', 'coverage': 'yes'}, {'id': 'k2', 'coverage': 'yes'}],
         'action_steps': [{'id': 's1.a1', 'coverage': 'yes'}],
         'unsupported_claims': ['"cuts the dough"'],
         'chronology_errors': [{'claim': '"cuts the dough"', 'reason': 'belongs to cue 2'}],
         'confusing_parts': [], 'fluency': {'score': 5}},
        {'cue_id': 2,
         'key_events': [{'id': 'k2', 'coverage': 'partial'}, {'id': 'k3', 'coverage': 'yes'}],
         'action_steps': [{'id': 's2.a1', 'coverage': 'partial'}],
         'unsupported_claims': [], 'chronology_errors': [],
         'confusing_parts': [{'id': 'c1', 'explained': 'partial'}], 'fluency': {'score': 3}},
    ]}
    judge = normalise_judge(raw, [e['id'] for e in events], [1, 2], [c['id'] for c in confusing],
                            [a['id'] for a in actions], windows)
    by_event = {(x['id'], x['cue_id']): x['coverage'] for x in judge['key_events']}
    assert ('k2', 1) not in by_event and ('k3', 2) not in by_event
    assert by_event[('k1', 1)] == 'yes' and by_event[('k2', 2)] == 'partial'
    assert next(x for x in judge['key_events'] if x['id'] == 'k3')['coverage'] == 'no'
    score = aggregate_score({'pauses_inside_speech': 0}, judge)
    assert score['key_event_coverage_percent'] == 50
    assert score['action_step_coverage_percent'] == 50
    assert score['confusing_explained_percent'] == 50
    assert score['hallucinated_claims'] == 1 and score['chronology_errors'] == 1


class _FakeJudge:
    def __init__(self):
        self.calls = []
        self.usage = []

    def call(self, stage, data, media=None):
        self.calls.append((stage, data, media))
        self.usage.append({'input_tokens': 100, 'output_tokens': 50, 'cost_usd': .001})
        cues = []
        for window in data['cue_windows']:
            cues.append({
                'cue_id': window['cue_id'],
                'key_events': [{'id': x['id'], 'coverage': 'yes', 'reason': 'same action and object'}
                               for x in window['key_events']],
                'action_steps': [{'id': x['id'], 'coverage': 'yes', 'reason': 'same action and object'}
                                 for x in window['action_steps']],
                'unsupported_claims': ['"future oil pour"'] if window['cue_id'] == 1 else [],
                'chronology_errors': ([{'claim': '"future oil pour"', 'reason': 'happens at 90 s'}]
                                      if window['cue_id'] == 1 else []),
                'confusing_parts': [{'id': x['id'], 'explained': 'yes', 'reason': 'clear'}
                                    for x in window['confusing_parts']],
                'fluency': {'score': 4, 'reason': 'natural'},
            })
        return {'cues': cues}


def test_score_extended_uses_one_strict_time_aware_call_per_cue_and_writes_audit(tmp_path):
    run = tmp_path / 'run'
    run.mkdir()
    (run / 'pause_plan.json').write_text(json.dumps({
        'source_duration': 100,
        'pauses': [
            {'cue_id': 1, 't': 10, 'cue_text': 'A future oil pour happens.', 'freeze_seconds': 2},
            {'cue_id': 2, 't': 30, 'cue_text': 'They cut the dough.', 'freeze_seconds': 3},
        ],
        'speech_intervals': [],
    }))
    gt_path = tmp_path / 'gt.json'
    gt_path.write_text(json.dumps(_groundtruth()))
    fake = _FakeJudge()
    result = score_extended(run, gt_path, provider='mock', config=load_config(), client=fake, budget_usd=1)
    # Round 8c: one call per cue window so long clips cannot truncate the judge JSON.
    assert len(fake.calls) == 2 and all(c[0] == 'orchestrate' for c in fake.calls)
    payload = fake.calls[0][1]
    assert payload['_temperature'] == 0 and 'Return exactly one strict JSON object' in payload['_system']
    assert [len(c[1]['cue_windows']) for c in fake.calls] == [1, 1]
    assert [x['id'] for x in fake.calls[0][1]['cue_windows'][0]['key_events']] == ['k1']
    assert [x['id'] for x in fake.calls[1][1]['cue_windows'][0]['key_events']] == ['k2']
    assert result['usage']['budget_usd'] == .05
    assert result['aggregate']['max_undescribed_gap_s'] == 70
    assert result['aggregate']['hallucinated_claims'] == 1
    assert result['aggregate']['chronology_errors'] == 1
    markdown = (run / 'score.md').read_text()
    assert '### Cue 1: [0.000, 10.000] s' in markdown
    assert 'Matched GT steps:' in markdown and 'Unsupported claims: "future oil pour"' in markdown


def test_forward_snap_micro_silence_parse_and_frame_text_change_detection():
    log = '''
[silencedetect] silence_start: 3.048
[silencedetect] silence_end: 3.162 | silence_duration: 0.114
[silencedetect] silence_start: 18.074
[silencedetect] silence_end: 18.187 | silence_duration: 0.113
'''
    gaps = parse_micro_silences(log, 30)
    assert gaps == [
        {'start': 3.048, 'end': 3.162, 'duration': 0.114},
        {'start': 18.074, 'end': 18.187, 'duration': 0.113},
    ]
    snapped = snap_pause_forward(15, [{'start': 0, 'end': 30}], 30, gaps)
    assert snapped['t'] == pytest.approx(18.187)
    assert snapped['snap_seconds'] > 0 and snapped['snap_reason'] == 'next_energy_micro_silence_end'
    assert frame_text_change_times([
        {'t': 0, 'on_screen_text': ['SLIDE 1']},
        {'t': 14, 'on_screen_text': ['SLIDE 1']},
        {'t': 15, 'on_screen_text': ['SLIDE 2']},
    ]) == [15.]
    prompt = GROUNDTRUTH_VISUAL_CONSOLIDATE.lower()
    assert 'visual ambiguity' in prompt and 'never summarize' in prompt


def test_round8c_judge_claims_must_quote_the_cue_not_echo_ground_truth():
    from scripts.score_extended import normalise_judge
    windows = [{'cue_id': 1, 'text': 'The cook pours oil over the dough balls.', 'key_events': [], 'action_steps': [],
                'confusing_parts': []}]
    raw = {'cues': [{'cue_id': 1, 'unsupported_claims': ['pours oil over the dough balls',
                                                         'Person mixes flour in wooden bowl with right hand (0-1s)'],
                     'chronology_errors': [{'claim': 'Person holds glass pitcher (2s)', 'reason': 'x'}],
                     'fluency': {'score': 5}}]}
    judge = normalise_judge(raw, [], [1], [], [], windows)
    claims = judge['cue_claims'][0]
    assert claims['unsupported_claims'] == ['pours oil over the dough balls']
    assert claims['chronology_errors'] == []
