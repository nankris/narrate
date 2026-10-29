"""Offline full-pipeline smoke tests over unrelated visual structures."""
import json, subprocess
from pathlib import Path
import pytest
from narrate.config import load_config
from narrate.director import run_director
from narrate.extended_audit import audit_cached_run
from narrate.extended_director import run_extended_director, unsupported_terms

@pytest.fixture(scope='module')
def generic_clips(tmp_path_factory):
    root = tmp_path_factory.mktemp('generic-media')
    short = root/'field.mp4'
    silent = root/'silent.mp4'
    subprocess.run(['ffmpeg','-y','-loglevel','error','-ss','0','-i','samples/nasa_chile_harvest_0000-0150.mp4','-t','10','-c:v','libx264','-an',str(short)], check=True)
    subprocess.run(['ffmpeg','-y','-loglevel','error','-f','lavfi','-i','testsrc=size=320x180:rate=10','-t','10','-c:v','libx264','-pix_fmt','yuv420p','-an',str(silent)], check=True)
    return [Path('samples/failure_continuous_speech.mp4'), short, silent]

def _assert_generic_outputs(out, extended):
    report = json.loads((out/'report.json').read_text())
    assert report['status'] == 'complete'
    assert (out/('ad_extended_en.vtt' if extended else 'ad_en.vtt')).is_file()
    timeline = report.get('timeline', [])
    bible = report.get('bible', {})
    plan_evidence = {}
    if extended:
        plan_evidence = {p['cue_id']: p.get('evidence', []) for p in json.loads((out/'pause_plan.json').read_text())['pauses']}
    for cue in report.get('cues', []):
        text = cue.get('text', cue.get('en', ''))
        evidence = set(cue.get('evidence', plan_evidence.get(cue.get('id'), [])))
        events = [e for e in timeline if e.get('id') in evidence]
        if events:
            assert not unsupported_terms(text, events, bible, {})
        else:
            history = report.get('cue_history', {}).get(str(cue.get('id')), [])
            assert not any('unsupported term:' in problem for row in history for problem in row.get('problems', []))
        assert not any(word in text.lower() for word in (' roti ',' dough ',' flour ',' kitchen '))
    if extended:
        assert (out/'pause_plan.json').is_file() and (out/'timing_check.txt').is_file()
        assert not audit_cached_run(out)

def test_full_pipeline_is_generic_in_gap_and_extended(generic_clips, tmp_path):
    cfg = load_config(); cfg['tts']['backend'] = 'silent'
    cfg['extended'].update(min_pause_spacing_s=8, max_pauses_per_minute=4)
    for index, clip in enumerate(generic_clips):
        ingap = tmp_path/f'in-{index}'
        extended = tmp_path/f'ext-{index}'
        run_director(clip, ingap, provider='mock', langs=('en',), config=cfg)
        run_extended_director(clip, extended, provider='mock', config=cfg)
        _assert_generic_outputs(ingap, False)
        _assert_generic_outputs(extended, True)
