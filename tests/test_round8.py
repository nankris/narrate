"""Round 8 extended AD and independent ground truth. Offline only."""
import json
import sys

import pytest

from narrate.config import load_config
from narrate.extended import (build_extended_timeline, map_source_to_output, plan_pauses,
                              write_extended_texts)
from narrate.extended_director import run_extended_director
from narrate.groundtruth import normalise_frame_descriptions, normalise_groundtruth, sample_times
from narrate.media import probe
from scripts.score_extended import aggregate_score, normalise_judge


def test_pause_planner_snaps_from_speech_and_keeps_establishing_spacing_and_cap():
    speech = [{'start': 0, 'end': 4}, {'start': 4.5, 'end': 12}, {'start': 12.5, 'end': 20}]
    pauses = plan_pauses(40, speech, scene_cuts=[2, 12.2, 25],
                         timeline_events=[{'id': 'e1', 't_end': 19, 'importance': 5}],
                         story_beats=[{'id': 'b1', 't': 31, 'beat': 'result'}],
                         min_spacing_s=8, max_pauses_per_minute=6, snap_max_s=4)
    assert pauses and pauses[0]['source'] == 'establishing'
    assert pauses[0]['t'] == pytest.approx(4.15)
    assert all(not any(s['start'] - .15 < p['t'] < s['end'] + .15 for s in speech) for p in pauses)
    assert all(b['t'] - a['t'] + 1e-9 >= 8 for a, b in zip(pauses, pauses[1:]))
    assert len(pauses) <= 4


def test_continuous_speech_like_plan_uses_short_inter_sentence_silences():
    speech = [{'start': 0, 'end': 5}, {'start': 5.4, 'end': 11}, {'start': 11.5, 'end': 18},
              {'start': 18.4, 'end': 24}, {'start': 24.5, 'end': 30}]
    pauses = plan_pauses(30, speech, min_spacing_s=10, max_pauses_per_minute=4)
    assert pauses[0]['t'] == pytest.approx(5.15)
    assert any(p['source'] == 'speech_end' for p in pauses[1:])
    assert all(not any(s['start'] < p['t'] < s['end'] for s in speech) for p in pauses)


def test_extended_timeline_is_contiguous_maps_source_and_adds_exact_freezes():
    timeline = build_extended_timeline(30, [(5, 2), (20, 3)], [{'start': 0, 'end': 4}], .3, .4)
    assert timeline.total_duration == pytest.approx(36.4)
    assert sum(s['out_end'] - s['out_start'] for s in timeline if s['kind'] == 'freeze') == pytest.approx(6.4)
    assert all(a['out_end'] == pytest.approx(b['out_start']) for a, b in zip(timeline, timeline[1:]))
    assert timeline[0]['out_start'] == 0 and timeline[-1]['out_end'] == pytest.approx(36.4)
    assert timeline.source_to_output(5) == 5
    assert map_source_to_output(6, timeline.pauses) == pytest.approx(8.7)
    assert timeline.source_to_output(25) == pytest.approx(31.4)
    assert timeline.cue_times[1] == {'start': 5.3, 'end': 7.3, 'freeze_start': 5.0, 'freeze_end': 7.7}


def test_extended_timeline_rejects_pause_inside_speech():
    with pytest.raises(ValueError, match='inside speech'):
        build_extended_timeline(10, [(4, 1)], [{'start': 3, 'end': 5}])


def test_extended_vtt_uses_output_timeline(tmp_path):
    write_extended_texts(tmp_path, [{'id': 1, 'out_start': 5.3, 'out_end': 7.3, 'text': 'First sentence. Second sentence.'}])
    vtt = (tmp_path / 'ad_extended_en.vtt').read_text()
    assert '00:00:05.300 --> 00:00:07.300' in vtt
    assert 'First sentence. Second sentence.' in vtt
    assert '[00:00:05.300]' in (tmp_path / 'transcript_extended_en.txt').read_text()


def test_groundtruth_sampling_normalisation_and_pause_snap():
    assert sample_times(3.2, 1, [1.4]) == [0., 1., 1.45, 2., 3.]
    frames = normalise_frame_descriptions({'descriptions': [
        {'timestamp': '1', 'visible': 'a cook', 'description': 'They stir flour',
         'text_on_screen': 'STEP 1', 'subtitles': 'mix it'}]}, [1])
    assert frames[0]['present'] == ['a cook'] and frames[0]['action'] == 'They stir flour'
    raw = {'clip': 'x', 'duration': 10, 'setting': 'a kitchen', 'cast': [], 'objects': ['bowl'],
           'segments': [], 'key_events': [{'id': 'k1', 't': 4, 'what': 'The bowl tips', 'importance': 5}],
           'confusing_parts': [{'id': 'c1', 't': 7, 'what': 'A hidden hand moves it', 'why': 'occluded',
                                'what_to_explain': 'whose hand'}],
           'pause_points': [{'t': 4, 'why': 'explain the tip'}]}
    gt = normalise_groundtruth(raw, 'x.mp4', 10, [{'start': 3, 'end': 5}], [2, 6])
    assert gt['pause_points'][0]['t'] == 5
    assert gt['pause_points'][0]['snapped'] and gt['pause_points'][0]['snap_reason'] == 'forward_speech_end'
    assert gt['key_events'][0]['what'] == 'The bowl tips' and gt['confusing_parts'][0]['why'] == 'occluded'


def test_scorer_normalises_canned_judge_and_aggregates():
    raw = {'key_events': [{'id': 'k1', 'coverage': 'yes'}, {'id': 'k2', 'coverage': 'partial'}],
           'cue_claims': [{'cue_id': 1, 'unsupported_claims': ['"a red bowl"']}],
           'confusing_parts': [{'id': 'c1', 'explained': 'yes'}],
           'fluency': [{'cue_id': 1, 'score': 5, 'reason': 'native'}, {'cue_id': 2, 'score': 3, 'reason': 'stiff'}]}
    judge = normalise_judge(raw, ['k1', 'k2'], [1, 2], ['c1'])
    score = aggregate_score({'pauses_inside_speech': 0}, judge)
    assert score['key_event_coverage_percent'] == 75
    assert score['hallucinated_claims'] == 1 and score['confusing_explained_percent'] == 100
    assert score['fluency_mean'] == 4


def test_extended_mode_cli_routes_and_drops_hindi(monkeypatch, tmp_path, capsys):
    import narrate.__main__ as main
    import narrate.extended_director as extended_director
    seen = {}
    monkeypatch.setattr(extended_director, 'run_extended_director',
                        lambda *a, **kw: seen.update(kw) or {'estimated_cost_usd': 0})
    monkeypatch.setattr(sys, 'argv', ['narrate', 'agent', 'samples/sample_kitchen.mp4', '--out', str(tmp_path),
                                     '--mock', '--ad-mode', 'extended', '--lang', 'en,hi'])
    main.main()
    assert seen['langs'] == 'en' and 'English-only' in capsys.readouterr().out


def test_extended_mock_end_to_end_duration_is_source_plus_freezes(tmp_path):
    cfg = load_config()
    cfg['tts']['backend'] = 'silent'
    cfg['extended'].update(min_pause_spacing_s=8, max_pauses_per_minute=4)
    report = run_extended_director('samples/sample_kitchen.mp4', tmp_path, provider='mock', config=cfg)
    plan = json.loads((tmp_path / 'pause_plan.json').read_text())
    source_s = probe('samples/sample_kitchen.mp4')[0]
    expected = source_s + sum(p['freeze_seconds'] for p in plan['pauses'])
    assert report['status'] == 'complete' and report['ad_mode'] == 'extended'
    assert report['overlaps_with_speech'] == 0 and plan['pauses']
    for name in ('extended_en.mp4', 'extended_en.m4a', 'ad_extended_en.vtt',
                 'transcript_extended_en.txt', 'pause_plan.json', 'report.json'):
        assert (tmp_path / name).is_file(), name
    assert probe(tmp_path / 'extended_en.mp4')[0] == pytest.approx(expected, abs=.1)
    assert probe(tmp_path / 'extended_en.m4a')[0] == pytest.approx(expected, abs=.1)
