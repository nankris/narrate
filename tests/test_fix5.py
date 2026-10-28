"""Offline regressions for the fourth real-run propose loop (one limit, enforced drafts, auto-redraft, inspect dedup)."""
import json
import re
from narrate.agent import run_agent
from narrate.agent.core import Agent
from narrate.config import load_config
from tests.test_fix2 import make_agent, tool_call
from tests.test_fix3 import fake_detect

KITCHEN_GAPS=[(4.67,8.71),(11.87,16.61),(19.93,24.71),(25.5,29.5)]
TEXTS=['A person enters a kitchen','STEP 1 - chop onions','Add salt and pepper','Stir and serve']
COLORS=['teal','maroon','green','orange']


def kitchen_gap(i=0,start=4.67,end=8.71):
    d=end-start
    return {'id':i,'start':start,'end':end,'duration':d,'word_budget_en':8,'word_budget_hi':9,'narratable':True}


def fake_models(monkeypatch,fit_calls=None):
    """Fake VL (events with on-screen text) and a stubborn drafter: 14 words, never the on-screen text."""
    def submodel(self,stage,data,media=None,mock_result=None):
        if stage=='perceive':
            start=float(re.search(r'starts at ([\d.]+)',data['instruction']).group(1)); end=start+data['duration']
            i=min(range(4),key=lambda k:abs(sum(KITCHEN_GAPS[k])/2-(start+end)/2))
            return {'events':[{'t_start':start+.1,'t_end':end-.1,'what':f'{COLORS[i]} screen with a yellow outline','on_screen_text':TEXTS[i],'importance':5,'confidence':1.0}]}
        if stage=='fit':
            if fit_calls is not None: fit_calls.append(data)
            return {'cues':[{'id':g['id'],'text':f'A {COLORS[g["id"]%4]} screen shows a small yellow rectangular outline moving slowly across the center'} for g in data['gaps']]}
        return mock_result
    monkeypatch.setattr(Agent,'submodel',submodel)


def kitchen_agent(tmp_path,monkeypatch,n=4,fit_calls=None):
    fake_models(monkeypatch,fit_calls)
    a=make_agent(tmp_path,[kitchen_gap(i,*KITCHEN_GAPS[i]) for i in range(n)])
    for g in a.gaps: g.update(max_words_en=a.max_words(g),max_words_hi=a.max_words(g,'hi'))
    a.speech=[]
    return a


# 1 ---- one effective limit
def test_single_effective_limit_in_detect_and_board(tmp_path,monkeypatch):
    a=make_agent(tmp_path)
    monkeypatch.setattr('narrate.agent.core.detect',fake_detect([(4.59,8.79)]))
    out=a.detect_speech_gaps()['gaps'][0]
    g=a.gaps[0]
    assert g['duration']>4 and g['word_budget_en']==8 and out['max_words_en']==7 and out['max_words_hi']<=g['word_budget_hi']
    assert '<=7w' in a.board_text() and 'word_budget' not in json.dumps(out)


def test_seven_words_not_rejected_on_estimate_margin(tmp_path):
    a=make_agent(tmp_path,[kitchen_gap()]); a.speech=[]
    # silent TTS 2.5 w/s: 7 words = 2.8 s <= cap 3.6; force a measured value just over the cap but under gap*atempo
    a.tts_cache[('one two three four five six seven','en')]=(3.74,None)
    r=a.check_fit(0,'one two three four five six seven','en')
    assert r['ok'] and r['suggested_max_words']<=7
    a.tts_cache[('one two three four five six seven','en')]=(5.2,None)        # > 4.04*1.25 -> really too long
    r=a.check_fit(0,'one two three four five six seven','en')
    assert not r['ok'] and r['suggested_max_words']<7


# 2 ---- drafter enforcement
def test_batched_draft_enforced_with_onscreen_text(tmp_path,monkeypatch):
    calls=[]; a=kitchen_agent(tmp_path,monkeypatch,fit_calls=calls)
    for g in a.gaps: a.inspect_video_segment(g['start']-1,g['end'])
    out=a.draft_description(gap_ids=[0,1,2,3])['cues']
    assert len(out)==4 and len(calls)==2 and [c['id'] for c in calls[1]['gaps']]==[0,1,2,3]       # one re-ask, still over
    assert 'HARD LIMIT' in calls[1]['instruction'] and 'verbatim' in calls[0]['instruction']
    assert calls[0]['gaps'][0]['on_screen_text']==[TEXTS[0]] and calls[0]['gaps'][0]['max_words']==7
    for c in out:
        assert len(c['text'].split())<=c['max_words']
    assert out[0]['text']=='Title: "A person enters a kitchen".' and out[1]['text']=='Title: "STEP 1 - chop onions".'
    assert a.draft_overlimit==4


def test_reask_only_failing_gaps_and_single_draft_enforced(tmp_path,monkeypatch):
    a=kitchen_agent(tmp_path,monkeypatch)
    asked=[]
    def submodel(stage,data,*x,**k):
        asked.append([g['id'] for g in data['gaps']])
        return {'cues':[{'id':g['id'],'text':'ok short' if g['id']==0 else 'w '*14} for g in data['gaps']] if len(asked)==1 else [{'id':g['id'],'text':'fixed it now'} for g in data['gaps']]}
    monkeypatch.setattr(a,'submodel',submodel)
    out=a.draft_description(gap_ids=[0,1])['cues']
    assert asked==[[0,1],[1]] and [c['text'] for c in out]==['ok short','fixed it now'] and a.draft_overlimit==1
    one=a.draft_description(2,max_words=3)
    assert len(one['text'].split())<=3 and one['max_words']==3


def test_fallback_text_without_onscreen_truncates_at_word_boundary(tmp_path):
    a=make_agent(tmp_path,[kitchen_gap()])
    assert a.fallback_text(a.gap(0),4,draft='A person walks into the busy kitchen')=='A person walks into.'
    assert a.trim_words('Say "hello there my friend',3)=='Say "hello there".'


# 3 ---- auto redraft
def test_second_failed_propose_auto_redrafts(tmp_path,monkeypatch):
    a=kitchen_agent(tmp_path,monkeypatch,n=1)
    a.inspect_video_segment(3.67,8.71)
    long='White text appears top left and a yellow outline moves across the center now'
    r1=a.propose_cue(0,long)
    assert not r1['ok'] and 'draft_description(gap_ids=[0]' in r1['next']
    r2=a.propose_cue(0,long+' again')
    assert r2['ok'] and r2['auto_redrafted'] is True and len(r2['cue']['en'].split())<=7
    assert a.auto_redrafts==1 and 0 in a.cues and not a.authored


def test_third_failure_then_refused(tmp_path,monkeypatch):
    a=kitchen_agent(tmp_path,monkeypatch,n=1)
    monkeypatch.setattr(a,'draft_batch',lambda *x,**k:(_ for _ in ()).throw(RuntimeError('fit down')))
    long='w '*14
    r=[a.propose_cue(0,long+str(i)) for i in range(3)]
    assert all(not x['ok'] for x in r) and r[1]['auto_redraft'].startswith('unavailable') and r[2]['next']=='drop_gap or move on'
    r4=a.propose_cue(0,'one two')
    assert not r4['ok'] and r4['next']=='drop_gap or move on' and a.repeat_refusals==1 and 0 not in a.cues


# 4 ---- inspect efficiency
def test_preroll_and_subrange_reinspection_refused(tmp_path,monkeypatch):
    a=kitchen_agent(tmp_path,monkeypatch)
    assert a.inspect_video_segment(3.67,8.71)['events']
    for rng in [(2.67,8.71),(5.5,8.0),(4.67,8.71)]:
        r=a.inspect_video_segment(*rng)
        assert r['ok'] is False and r['error']=='already inspected', rng
    assert a.repeat_refusals==3 and a.counts['inspections']==1
    assert a.inspect_video_segment(10.87,16.61)['events']          # a different gap is still allowed


def test_empty_inspection_counts_one_retry_then_refused(tmp_path,monkeypatch):
    a=make_agent(tmp_path,[kitchen_gap()]); a.speech=[]; a.mock=False
    monkeypatch.setattr('narrate.agent.core.ffmpeg',lambda *x:None)
    monkeypatch.setattr('narrate.agent.core.separate_frames',lambda *x:None)
    (a.work/'inspection.mp4').write_bytes(b'x')
    monkeypatch.setattr(a,'submodel',lambda *x,**k:{'events':[]})
    r1=a.inspect_video_segment(3.67,8.71)
    assert r1['events']==[] and r1['modality']=='frames-fallback' and a.inspect_tries[0]==1
    assert 'no events found' in a.board_text() and 'inspect_video_segment' in a.next_action()
    assert a.inspect_video_segment(3.67,8.71)['events']==[]             # the single retry
    r3=a.inspect_video_segment(4.0,8.71)
    assert r3['ok'] is False and r3['error']=='already inspected' and a.counts['inspections']==2
    assert 'drop_gap' in a.next_action()


# 5 ---- kitchen-like end to end
def test_kitchen_like_run_four_cues_in_few_turns(tmp_path,monkeypatch):
    fake_models(monkeypatch)
    monkeypatch.setattr('narrate.agent.core.detect',fake_detect(KITCHEN_GAPS))
    class Plan:
        n=0
        def next(self,messages,a):
            self.n+=1; ids=[g['id'] for g in a.gaps if g['narratable']]
            if self.n==1: calls=[tool_call('detect_speech_gaps')]
            elif self.n==2: calls=[tool_call('inspect_video_segment',start=max(0,a.gap(i)['start']-1),end=a.gap(i)['end']) for i in ids]
            elif self.n==3: calls=[tool_call('draft_description',gap_ids=ids)]
            elif self.n==4: calls=[tool_call('propose_cue',gap_id=i,text=a.drafts[i]) for i in ids]
            else:
                calls=[tool_call('verify_claim',gap_id=i,claim=a.cues[i]['en']) for i in sorted(a.needs_verification())]+[tool_call('translate_hindi'),tool_call('finalize')]
            return {'role':'assistant','content':'','tool_calls':[{**c,'id':f'c{self.n}-{k}'} for k,c in enumerate(calls)]}
    cfg=load_config(); cfg['tts']['backend']='silent'
    report=run_agent('samples/sample_kitchen.mp4',tmp_path,'mock',config=cfg,orchestrator=Plan())
    st=report['agent_stats']
    assert report['cues_committed']==4 and not report['fallback_finalize']
    assert st['orchestrator_turns']<=8 and st['tool_calls']['propose_cue']<=6 and st['repeat_refusals']==0
    assert st['draft_overlimit']==4 and st['auto_redrafts']==0
    for c,t in zip(sorted(report['cues'],key=lambda c:c['id']),TEXTS):
        assert t in c['en'] or len(c['en'].split())<=7
        assert len(c['en'].split())<=7
