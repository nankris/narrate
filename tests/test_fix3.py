"""Offline regressions for the third real-run fixes (long gaps, cue length, history growth, turn budget)."""
import json
import subprocess
import pytest
from narrate.agent import run_agent
from narrate.agent.models import compact_history
from narrate.config import load_config
from narrate.media import scene_cuts, split_slots
from tests.test_fix2 import make_agent, tool_call, Script


def fake_detect(gaps):
    return lambda *a: {'gaps':[{'start':s,'end':e} for s,e in gaps],'speech':[],'detector':'x','speech_ratio':0,'fallback_reason':None}


# 1 ---- slots
def test_split_slots_equal_and_bounded():
    assert split_slots(0,10) == [(0,10)]
    slots = split_slots(.18,79.09)
    assert len(slots) == 7 and all(6 <= e-s <= 12 for s,e in slots)
    assert slots[0][0] == .18 and slots[-1][1] == 79.09
    assert all(a[1] == b[0] for a,b in zip(slots,slots[1:]))
    assert len(split_slots(0,13)) == 2 and len(split_slots(0,25.8)) == 3


def test_split_slots_snaps_to_cuts_within_two_seconds():
    assert split_slots(0,20)[0][1] == 10
    assert split_slots(0,20,cuts=[8.5,19])[0][1] == 8.5
    assert split_slots(0,20,cuts=[11.5,8.2])[0][1] == 11.5       # nearest to the ideal boundary
    assert split_slots(0,20,cuts=[7.5])[0][1] == 10              # farther than 2 s
    assert split_slots(0,24,cuts=[10.5,13.9])[0][1] == 12        # would leave a slot above max_slot
    for cuts in ([8.5],[11.9],[9.0,11.0]):
        assert all(4 <= e-s <= 12 for s,e in split_slots(0,20,cuts=cuts))
    three = split_slots(0,30,cuts=[9.1,20.9])
    assert [round(e,1) for s,e in three[:-1]] == [9.1,20.9]


def test_scene_cuts_falls_back_on_timeout_and_error(monkeypatch):
    def boom(*a,**k): raise subprocess.TimeoutExpired('ffmpeg',1)
    monkeypatch.setattr('narrate.media.subprocess.run',boom)
    assert scene_cuts('x.mp4') == []
    monkeypatch.setattr('narrate.media.subprocess.run',lambda *a,**k:subprocess.CompletedProcess(a,0,b'',b'[Parsed_showinfo_3] n:0 pts_time:4.2 x\n pts_time:1.5 y'))
    assert scene_cuts('x.mp4') == [1.5,4.2]


def test_detect_splits_long_gaps_into_slots(tmp_path,monkeypatch):
    a = make_agent(tmp_path)
    monkeypatch.setattr('narrate.agent.core.detect',fake_detect([(0,79.25),(84,110),(115,116)]))
    monkeypatch.setattr('narrate.agent.core.scene_cuts',lambda p:[])
    found = a.detect_speech_gaps()
    gaps = found['gaps']
    assert [g['parent_gap'] for g in gaps if 'parent_gap' in g] == [0]*7+[1]*3
    assert len(gaps) == 11 and [g['id'] for g in gaps] == list(range(11))
    narratable = [g for g in gaps if g['narratable']]
    assert len(narratable) == 10 and all(6 <= g['end']-g['start'] <= 12 for g in narratable)
    assert gaps[-1]['narratable'] is False and 'parent_gap' not in gaps[-1]
    # budgets follow each slot's own duration; inspection cap scales with slots
    assert all(a.gap(g['id'])['word_budget_en'] == int(a.gap(g['id'])['duration']*2.3-1) for g in narratable)
    assert a.cfg['agent']['max_inspections'] >= 12


def test_detect_skips_scene_pass_when_nothing_to_split(tmp_path,monkeypatch):
    a = make_agent(tmp_path)
    monkeypatch.setattr('narrate.agent.core.detect',fake_detect([(0,9)]))
    monkeypatch.setattr('narrate.agent.core.scene_cuts',lambda p:pytest.fail('no scene pass needed'))
    assert len(a.detect_speech_gaps()['gaps']) == 1


# 2 ---- overlong cues
def test_overlong_cue_rejected(tmp_path):
    gaps = [{'id':0,'start':0.,'end':12.,'duration':12.,'word_budget_en':26,'word_budget_hi':30,'narratable':True}]
    a = make_agent(tmp_path,gaps); a.speech = []
    long = ' '.join(f'w{i}' for i in range(24))        # silent TTS: 2.5 words/s -> 9.6 s
    r = a.propose_cue(0,long)
    assert not r['ok'] and any(p.startswith('cue too long for a single description; keep it under 8.0 s') for p in r['problems'])
    assert 0 not in a.cues and r['suggested_max_words'] <= 20
    assert a.propose_cue(0,' '.join(f'w{i}' for i in range(19)))['ok']
    a.cfg['agent']['max_cue_s'] = 4
    assert not a.check_fit(0,' '.join(f'w{i}' for i in range(19)),'en')['ok']


def test_cue_ninety_percent_rule(tmp_path):
    a = make_agent(tmp_path)         # 3 s slot: limit 2.7 s -> 6 words (2.4 s) ok, 7 words (2.8 s) not
    a.cfg['agent']['max_atempo'] = 1.25
    a.gaps[0]['word_budget_en'] = 10
    assert a.check_fit(0,'one two three four five six','en')['ok']
    r = a.check_fit(0,'one two three four five six seven','en')
    assert not r['ok'] and 'keep it under 2.7 s' in ' '.join(r['problems'])


# 3 ---- history growth
def valid_pairing(messages):
    asked = {c['id'] for m in messages if m['role'] == 'assistant' for c in m.get('tool_calls',[])}
    answered = [m['tool_call_id'] for m in messages if m['role'] == 'tool']
    assert sorted(answered) == sorted(asked) and len(set(answered)) == len(answered)
    seen = set()
    for m in messages:                 # every tool message follows the assistant message that issued it
        if m['role'] == 'assistant':
            seen |= {c['id'] for c in m.get('tool_calls',[])}
        if m['role'] == 'tool':
            assert m['tool_call_id'] in seen


def synthetic_history(turns):
    messages = [{'role':'system','content':'SYS'},{'role':'user','content':'task'}]
    for t in range(turns):
        cid = f'c{t}'
        messages.append({'role':'assistant','content':'x'*200,'tool_calls':[{'id':cid,'type':'function','function':{'name':'inspect_video_segment','arguments':json.dumps({'start':t,'end':t+9,'note':'n'*120})}}]})
        messages.append({'role':'tool','tool_call_id':cid,'content':json.dumps({'events':[{'what':'y'*300}]*3,'ok':True,'state':{'committed':[1,2]}})})
    return messages


def test_compact_history_keeps_last_six_full_and_pairing():
    messages = synthetic_history(25)
    out = compact_history(messages,6)
    valid_pairing(out)
    assert out[:2] == messages[:2] and out[-12:] == messages[-12:]
    assert len(json.dumps(out)) < len(json.dumps(messages))/2
    assert out[3]['content'].startswith('[summary] inspect_video_segment ok=true')
    assert compact_history(out,6) == out                      # idempotent
    assert compact_history(messages[:8],6) == messages[:8]


def test_orchestrator_input_bounded_over_25_mock_turns(tmp_path):
    sizes,pairs = [],[]
    class Wide:
        def __init__(self): self.n = 0
        def next(self,messages,a):
            sizes.append(len(json.dumps(messages))); pairs.append(list(messages))
            self.n += 1
            if self.n == 1: return {'role':'assistant','content':'','tool_calls':[tool_call('detect_speech_gaps')]}
            return {'role':'assistant','content':'','tool_calls':[{**tool_call('check_fit',gap_id=0,text='Title appears '+str(self.n),lang='en'),'id':f'call-{self.n}'}]}
    cfg = load_config(); cfg['tts']['backend'] = 'silent'
    run_agent('samples/sample_kitchen.mp4',tmp_path,'mock',config=cfg,max_steps=25,orchestrator=Wide())
    assert len(sizes) >= 25
    assert max(sizes) < 12000, sizes
    assert (sizes[-1]-sizes[10])/(len(sizes)-11) < 400     # old turns cost ~one summary line each (was ~600+/turn full)
    valid_pairing(pairs[-1])


# 4 ---- turn budget
def test_turn_budget_scales_with_slots_unless_explicit(tmp_path):
    def many(a):
        return [tool_call('detect_speech_gaps')]
    seen = {}
    class Probe(Script):
        def next(self,messages,a):
            seen.setdefault('steps',[]).append(a.cfg['agent']['max_steps'])
            return super().next(messages,a)
    cfg = load_config(); cfg['tts']['backend'] = 'silent'
    run_agent('samples/nasa_chile_harvest_0000-0150.mp4',tmp_path/'auto',config=cfg,provider='mock',orchestrator=Probe([many]*5))
    assert seen['steps'][0] == 30 and seen['steps'][-1] == 36        # 10 slots -> 6+3*10
    seen.clear()
    run_agent('samples/nasa_chile_harvest_0000-0150.mp4',tmp_path/'fixed',config=cfg,provider='mock',max_steps=4,orchestrator=Probe([many]*5))
    assert set(seen['steps']) == {4}


# 5 ---- mock demo
def test_mock_nasa_yields_many_slot_cues(tmp_path):
    cfg = load_config(); cfg['tts']['backend'] = 'silent'
    report = run_agent('samples/nasa_chile_harvest_0000-0150.mp4',tmp_path,'mock',config=cfg)
    assert report['cues_committed'] >= 5 and not report['fallback_finalize']
    assert max(c['end']-c['start'] for c in report['tracks']['en']) <= 8.0
