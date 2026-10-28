"""Offline tests for the scene-context pass (Super VL establishes setting, people, ingredients, tools once)."""
import json
from narrate.agent import run_agent
from narrate.agent.core import Agent, clean_scene, scene_brief
from narrate.config import load_config
from tests.test_fix2 import make_agent
from tests.test_fix3 import fake_detect

SCENE = {'setting': 'bright home kitchen counter', 'people': [{'description': 'cook in a striped shirt', 'doing': 'kneading dough'}],
         'ingredients': ['flour', 'oil', 'flour'], 'tools': ['rolling pin', 'wooden bowl'], 'objects': [], 'activity': 'making flatbread',
         'dish': '', 'burned_in_subtitles': True, 'confidence': 0.9}


def recorder(monkeypatch, scene=SCENE, fail=False):
    calls = []
    def submodel(self, stage, data, media=None, mock_result=None):
        calls.append((stage, data, getattr(self, 'cost_role', None)))
        if 'Establish the scene' in data.get('instruction', ''):
            if fail:
                raise RuntimeError('provider down')
            return scene
        if stage == 'perceive':
            return {'events': [{'t_start': 5.1, 't_end': 7.9, 'what': 'Hands knead dough in a bowl', 'on_screen_text': '', 'importance': 4, 'confidence': .9}]}
        if stage == 'fit':
            return {'cues': [{'id': g['id'], 'text': 'Hands knead dough'} for g in data['gaps']]}
        return mock_result
    monkeypatch.setattr(Agent, 'submodel', submodel)
    return calls


def test_clean_scene_normalises_and_dedupes():
    out = clean_scene({**SCENE, 'tools': 'rolling pin', 'people': ['cook'], 'confidence': '7', 'setting': 5, 'dish': None})
    assert out['ingredients'] == ['flour', 'oil'] and out['tools'] == ['rolling pin'] and out['people'] == ['cook']
    assert out['confidence'] == 1.0 and out['setting'] == '5' and out['dish'] == '' and out['burned_in_subtitles']
    assert clean_scene('garbage')['people'] == [] and scene_brief({}) == '' and scene_brief(None) == ''
    brief = scene_brief(clean_scene(SCENE))
    assert 'setting: bright home kitchen' in brief and 'tools: rolling pin, wooden bowl' in brief and len(brief) <= 420


def test_detect_runs_scene_pass_once(tmp_path, monkeypatch):
    calls = recorder(monkeypatch)
    a = make_agent(tmp_path)
    monkeypatch.setattr('narrate.agent.core.detect', fake_detect([(4.0, 9.0), (12.0, 18.0)]))
    out = a.detect_speech_gaps()
    scene = [c for c in calls if 'Establish the scene' in c[1]['instruction']]
    assert len(scene) == 1 and scene[0][0] == 'perceive' and scene[0][2] == 'scene'
    times = scene[0][1]['timestamps']
    assert len(times) == 6 and times[0] > 0 and times[-1] < a.duration and times == sorted(times)
    assert 'bright home kitchen' in out['scene_context'] and a.report['scene_context']['tools'] == ['rolling pin', 'wooden bowl']
    a.detect_speech_gaps(); a.establish_scene()
    assert len([c for c in calls if 'Establish the scene' in c[1]['instruction']]) == 1


def test_scene_context_feeds_inspection_drafts_and_translation(tmp_path, monkeypatch):
    calls = recorder(monkeypatch)
    a = make_agent(tmp_path)
    monkeypatch.setattr('narrate.agent.core.detect', fake_detect([(4.0, 9.0), (12.0, 18.0)]))
    a.detect_speech_gaps(); a.speech = []
    ids = [g['id'] for g in a.gaps if g['narratable']]
    a.inspect_video_segment(3.0, 9.0)
    inspect = [c[1] for c in calls if c[0] == 'perceive' and 'Inspect this segment' in c[1]['instruction']][0]
    assert 'rolling pin' in inspect['scene_context'] and 'burned-in subtitles' in inspect['instruction']
    a.draft_description(gap_ids=ids)
    fit = [c[1] for c in calls if c[0] == 'fit'][0]
    assert 'flour' in fit['scene_context'] and 'establishing' in fit['instruction']
    roles = {g['id']: g['role'] for g in fit['gaps']}
    assert roles[min(ids, key=lambda i: a.gap(i)['start'])] == 'establishing' and list(roles.values()).count('establishing') == 1
    a.cues[ids[0]] = {**a.gap(ids[0]), 'en': 'Hands knead dough'}
    a.translate_hindi()
    edit = [c[1] for c in calls if c[0] == 'edit'][0]
    assert 'scene_context' in edit and 'add no facts' in edit['instruction']


def test_scene_failure_is_reported_not_fatal(tmp_path, monkeypatch):
    recorder(monkeypatch, fail=True)
    a = make_agent(tmp_path)
    monkeypatch.setattr('narrate.agent.core.detect', fake_detect([(4.0, 9.0)]))
    out = a.detect_speech_gaps()
    assert out['gaps'] and 'scene_context' not in out
    assert any('Scene context unavailable' in i for i in a.report['issues'])
    a.speech = []
    a.draft_description(gap_ids=[0])                      # drafting works without context
    assert a.drafts[0] == 'Hands knead dough'


def test_scene_pass_can_be_disabled(tmp_path, monkeypatch):
    calls = recorder(monkeypatch)
    a = make_agent(tmp_path)
    a.cfg['agent']['scene_context'] = False
    monkeypatch.setattr('narrate.agent.core.detect', fake_detect([(4.0, 9.0)]))
    out = a.detect_speech_gaps()
    assert 'scene_context' not in out and not any('Establish the scene' in c[1]['instruction'] for c in calls)


def test_mock_run_records_scene_cost_role_and_context(tmp_path):
    cfg = load_config(); cfg['tts']['backend'] = 'silent'
    report = run_agent('samples/sample_kitchen.mp4', tmp_path, 'mock', config=cfg)
    assert report['scene_context']['setting'].startswith('MOCK') and 'scene' in report['cost_by_role']
    trace = json.loads((tmp_path / 'trace.json').read_text())
    assert any(s.get('cost_role') == 'scene' for s in trace['steps'])
