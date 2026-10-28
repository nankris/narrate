"""Offline regressions for the second real-run fixes (fake clients only; no network)."""
import json
import re
from types import SimpleNamespace as NS
import pytest
from narrate.agent import run_agent
from narrate.agent.core import Agent, absolute_times
from narrate.agent.models import Orchestrator, SYSTEM
from narrate.agent.schema import TOOLS
from narrate.config import load_config, resolve_provider
from narrate.llm import Client, SpendGuard, BudgetExceeded
from narrate.media import write_texts


def make_agent(tmp_path,gaps=None,**kw):
    cfg=resolve_provider(load_config(),'mock')
    cfg['tts']['backend']='silent'
    a=Agent('samples/sample_kitchen.mp4',tmp_path,cfg,['en','hi'],SpendGuard(.5),**kw)
    a.gaps=gaps or [{'id':0,'start':5.,'end':8.,'duration':3.,'word_budget_en':5,'word_budget_hi':4,'narratable':True}]
    a.speech=[{'start':0,'end':4}]
    return a


@pytest.fixture
def agent(tmp_path):
    return make_agent(tmp_path)


def two_gaps():
    return [{'id':0,'start':5.,'end':8.,'duration':3.,'word_budget_en':6,'word_budget_hi':4,'narratable':True},
            {'id':1,'start':12.,'end':15.,'duration':3.,'word_budget_en':6,'word_budget_hi':4,'narratable':True}]


def tool_call(name,**args):
    return {'id':name,'type':'function','function':{'name':name,'arguments':json.dumps({'note':'Exercise the tool offline.',**args})}}


class Script:
    """Orchestrator that plays fixed turns then raises."""
    def __init__(self,turns,error=RuntimeError('boom')):
        self.turns,self.error=list(turns),error
    def next(self,messages,a):
        if not self.turns:
            raise self.error
        return {'role':'assistant','content':'','tool_calls':self.turns.pop(0)(a)}


# 1 ---- never-commit
def test_check_fit_records_candidate_and_points_to_commit(agent):
    result=agent.check_fit(0,'Title appears','en')
    assert result['ok'] and result['next']=='call propose_cue/commit_cue to commit'
    assert agent.candidates[0]=='Title appears' and not agent.cues
    assert not agent.check_fit(0,'word '*9,'en')['ok'] and agent.candidates[0]=='Title appears'


def test_fallback_commits_best_candidate_without_any_commit_call(tmp_path):
    cfg=load_config(); cfg['tts']['backend']='silent'
    def explore(a):
        g=[g for g in a.gaps if g['narratable']][:2]
        return [tool_call('check_fit',gap_id=x['id'],text=t,lang='en') for x,t in zip(g,('Onion title appears','Stir and serve'))]
    report=run_agent('samples/sample_kitchen.mp4',tmp_path,'mock',config=cfg,orchestrator=Script([lambda a:[tool_call('detect_speech_gaps')],explore]))
    assert report['fallback_finalize'] and report['cues_committed']==2
    trace=json.loads((tmp_path/'trace.json').read_text())
    fb=[s for s in trace['steps'] if s['role']=='fallback']
    assert any('best fitting candidate' in s['note'] for s in fb) and fb[-1]['tool_name']=='finalize'


def test_fallback_trims_draft_or_drops(tmp_path):
    a=make_agent(tmp_path,two_gaps())
    a.drafts[0]='A person walks into the busy kitchen carrying groceries'
    a.fallback_finish('test stop')
    assert a.cues[0]['en'].endswith('.') and len(a.cues[0]['en'].split())<=6
    assert 1 in a.dropped and 'Fallback' in a.dropped[1]
    roles={s['role'] for s in a.steps}
    assert 'fallback' in roles and a.report['status']=='complete'


def test_prompt_prefers_propose_cue():
    assert 'Prefer propose_cue' in SYSTEM and 'NEVER commit' in SYSTEM
    desc={t['function']['name']:t['function']['description'] for t in TOOLS}
    assert desc['propose_cue'].startswith('PREFERRED') and 'EXPLORATION ONLY' in desc['check_fit'] and 'EXPLORATION ONLY' in desc['measure_tts_duration']


# 2 ---- transient errors
class HTTPError(Exception):
    def __init__(self,status): self.status_code=status


def flaky(errors,ok):
    calls=[]
    def create(**kw):
        calls.append(kw)
        if len(calls)<=len(errors):
            raise errors[len(calls)-1]
        return ok()
    return NS(chat=NS(completions=NS(create=create))),calls


def fit_response():
    return NS(usage=NS(prompt_tokens=10,completion_tokens=10),choices=[NS(message=NS(content='{"text":"x"}'))])


@pytest.mark.parametrize('error',[HTTPError(500),HTTPError(429),TimeoutError('slow'),ConnectionError('reset')])
def test_submodel_retries_transient(monkeypatch,error):
    monkeypatch.setenv('NEBIUS_API_KEY','fake-test-credential')
    sdk,calls=flaky([error,error],fit_response)
    sleeps,notes=[],[]
    c=Client(load_config(),sdk_factory=lambda **kw:sdk); c.sleep=sleeps.append; c.on_retry=notes.append
    assert c.call('fit',{})=={'text':'x'}
    assert len(calls)==3 and sleeps==[1,2] and len(notes)==2


def test_submodel_gives_up_after_three_and_skips_4xx(monkeypatch):
    monkeypatch.setenv('NEBIUS_API_KEY','fake-test-credential')
    for errors,expected in (([HTTPError(503)]*5,3),([HTTPError(401)]*5,1),([HTTPError(404)]*5,1)):
        sdk,calls=flaky(errors,fit_response)
        c=Client(load_config(),sdk_factory=lambda **kw:sdk); c.sleep=lambda s:None
        with pytest.raises(HTTPError): c.call('fit',{})
        assert len(calls)==expected


def test_orchestrator_500_retried_then_fallback(monkeypatch,tmp_path):
    monkeypatch.setenv('NEBIUS_API_KEY','fake-test-credential')
    msg=NS(content='go',tool_calls=[1],model_dump=lambda **kw:{'role':'assistant','content':'go','tool_calls':[tool_call('detect_speech_gaps')]})
    ok=lambda:NS(usage=NS(prompt_tokens=10,completion_tokens=10),choices=[NS(message=msg)])
    cfg=load_config(); cfg['tts']['backend']='silent'
    # one 500 then success: the run continues (retry traced as system step)
    sdk,calls=flaky([HTTPError(500)],ok)
    client=Client(resolve_provider(cfg,'mock'),sdk_factory=lambda **kw:sdk); client.sleep=lambda s:None
    report=run_agent('samples/sample_kitchen.mp4',tmp_path/'a',config=cfg,provider='mock',client=client,orchestrator=Orchestrator(client),max_steps=1)
    steps=json.loads((tmp_path/'a'/'trace.json').read_text())['steps']
    assert [s['note'] for s in steps if s['role']=='system'][0].startswith('retry after HTTP 500')
    # permanent 500: three attempts, then the fallback finisher runs
    sdk,calls=flaky([HTTPError(500)]*9,ok); sleeps=[]
    client=Client(resolve_provider(cfg,'mock'),sdk_factory=lambda **kw:sdk); client.sleep=sleeps.append
    report=run_agent('samples/sample_kitchen.mp4',tmp_path/'b',config=cfg,provider='mock',client=client,orchestrator=Orchestrator(client))
    assert len(calls)==3 and sleeps==[1,2] and report['fallback_finalize']
    assert any('HTTP 500' in i for i in report['issues'])


# 3 ---- wrong-event drafts / timestamps
def test_draft_context_limited_to_gap_window(tmp_path,monkeypatch):
    a=make_agent(tmp_path,[{'id':0,'start':30.5,'end':33.5,'duration':3.,'word_budget_en':4,'word_budget_hi':3,'narratable':True}])
    rocket={'t_start':0,'t_end':9,'what':'rocket ignition','importance':5}
    near={'t_start':30.0,'t_end':31.0,'what':'man looks up','importance':3}
    before=[{'t_start':20,'t_end':22,'what':f'old {i}','importance':3} for i in range(3)]
    after={'t_start':40,'t_end':42,'what':'future event','importance':3}
    a.events=[rocket,near,after]
    seen=[]
    monkeypatch.setattr(a,'submodel',lambda stage,data,*x,**k:seen.append(data) or {'text':'Man looks up'})
    a.draft_description(0,context_events=[rocket]+before+[after])
    whats=[e['what'] for e in seen[0]['events']]
    assert 'man looks up' in whats and 'rocket ignition' not in whats and 'future event' not in whats
    earlier=[e for e in seen[0]['events'] if e.get('context')=='earlier, context only']
    assert len(earlier)<=2 and all(e['t_end']<=29.5 for e in earlier)
    assert a.drafts[0]=='Man looks up'
    a.draft_description(gap_ids=[0])
    assert 'rocket ignition' not in json.dumps(seen[1])


def test_absolute_times_heuristic():
    seg=(24.52,31.65)
    rel=[{'t_start':0.0,'t_end':1.5},{'t_start':5.0,'t_end':7.0}]
    fixed,base=absolute_times(rel,*seg)
    assert base=='relative->absolute' and fixed[0]['t_start']==24.52 and fixed[1]['t_end']==31.52
    ab=[{'t_start':24.52,'t_end':26.04},{'t_start':30.6,'t_end':31.6}]
    assert absolute_times(ab,*seg)==(ab,'absolute')
    assert absolute_times(rel,0,7)[1]=='absolute'
    assert absolute_times([{'t_start':3,'t_end':4},{'t_start':80,'t_end':81}],*seg)[1]=='mixed'


@pytest.mark.parametrize('returned,expected_start',[([{'t_start':0.0,'t_end':1.5,'what':'ignition','importance':4,'confidence':.9}],24.52),
                                                    ([{'t_start':24.52,'t_end':26.04,'what':'ignition','importance':4,'confidence':.9}],24.52)])
def test_inspect_converts_relative_vl_times(tmp_path,monkeypatch,returned,expected_start):
    """Fake VL client answering with clip-relative (0..dur) or already-absolute seconds."""
    class VL:
        usage=[]
        def call(self,stage,data,media=None):
            self.usage.append({'stage':stage,'model':'fake-vl','input_tokens':1,'output_tokens':1,'cost_usd':0,'latency_s':0})
            return {'events':returned}
    cfg=resolve_provider(load_config(),'mock'); cfg['tts']['backend']='silent'
    a=Agent('samples/sample_kitchen.mp4',tmp_path,cfg,['en'],SpendGuard(.5),client=VL())
    a.mock=False
    monkeypatch.setattr('narrate.agent.core.ffmpeg',lambda *args:open(args[-1],'wb').write(b'fake clip'))
    result=a.inspect_video_segment(24.52,29.5)
    assert result['events'][0]['t_start']==pytest.approx(expected_start)
    assert result['time_base']==('relative->absolute' if returned[0]['t_start']==0 else 'absolute')


# 4 ---- sorted VTT
def test_vtt_and_transcript_sorted(tmp_path):
    cues=[{'start':s,'end':s+1,'en':f'cue {s}','hi':f'दृश्य {s}'} for s in (19.9,11.8,4.6,27.3)]
    for lang in ('en','hi'):
        write_texts(tmp_path,lang,cues)
        vtt=(tmp_path/f'ad_{lang}.vtt').read_text()
        starts=re.findall(r'^(\d\d:\d\d:\d\d\.\d+) -->',vtt,re.M)
        assert starts==sorted(starts) and starts[0]=='00:00:04.600'
        assert re.findall(r'^(\d+)$',vtt,re.M)==['1','2','3','4']
        lines=(tmp_path/f'transcript_{lang}.txt').read_text().splitlines()
        assert lines==sorted(lines) and '00:00:04.600' in lines[0]


# 5 ---- tiny gaps
def test_tiny_gaps_not_narratable(agent,monkeypatch):
    monkeypatch.setattr('narrate.agent.core.detect',lambda *a:{'gaps':[{'start':1,'end':2.4},{'start':10,'end':14}],'speech':[],'detector':'x','speech_ratio':0,'fallback_reason':None})
    found=agent.detect_speech_gaps()
    assert found['gaps'][0]['narratable'] is False and found['gaps'][0]['reason']=='too short'
    assert found['gaps'][1]['narratable'] is True
    monkeypatch.setattr(agent,'measure_tts_duration',lambda *a:pytest.fail('must fail before TTS'))
    for call in (lambda:agent.check_fit(0,'Hi','en'),lambda:agent.propose_cue(0,'Hi'),lambda:agent.draft_description(0)):
        r=call(); assert r['ok'] is False and 'too short' in r['problems']
    result=agent.execute('check_fit',{'gap_id':0,'text':'Hi','lang':'en','note':'Try the tiny gap.'})
    assert result['state']['skipped_too_short']==[0] and 0 not in result['state']['remaining']


# 6 ---- enforced verification
def test_finalize_requires_verification_for_text_and_numbers(agent,monkeypatch):
    agent.langs=['en']
    monkeypatch.setattr(agent,'render',lambda *a:[])
    committed=agent.propose_cue(0,'Sign reads OPEN at 9')
    assert committed['ok'] and committed['verify_required']
    refused=agent.finalize()
    assert refused['ok'] is False and refused['needs_verification']==[0]
    monkeypatch.setattr(agent,'submodel',lambda *a,**k:{'verdict':'Supported','evidence':'visible'})
    assert agent.verify_claim(gap_id=0,claim='Sign reads OPEN at 9')['verdict']=='supported'
    assert agent.finalize()['ok']
    agent.save()
    assert agent.report['agent_stats']['verifications']=={'verified':1,'contradicted':0,'unverified':0}


def test_low_confidence_triggers_and_plain_text_does_not(agent):
    agent.events=[{'t_start':5,'t_end':7,'what':'x','importance':3,'confidence':.5}]
    agent.draft_history[0]=['the figure walks left']
    agent.propose_cue(0,'the figure walks left')
    assert 'low-confidence' in agent.needs_verification()[0][0]
    agent.events[0]['confidence']=.9
    assert not agent.needs_verification()


def test_contradicted_uncommits_and_blocks_same_text(agent,monkeypatch):
    agent.propose_cue(0,'Sign reads OPEN')
    monkeypatch.setattr(agent,'submodel',lambda *a,**k:{'verdict':'contradicted','evidence':'closed'})
    r=agent.execute('verify_claim',{'gap_id':0,'claim':'Sign reads OPEN','note':'Check the sign text.'})
    assert r['uncommitted']==[0] and 'redraft' in r['next'] and not agent.cues and r['verdict']=='contradicted'
    assert not agent.propose_cue(0,'Sign reads OPEN')['ok']
    assert agent.propose_cue(0,'Sign reads CLOSED')['ok']
    agent.save()
    assert agent.report['agent_stats']['verifications']['contradicted']==1


def test_verification_cap_does_not_deadlock_and_fallback_marks_unverified(tmp_path,monkeypatch):
    a=make_agent(tmp_path)
    a.cfg['agent']['max_verifications']=0; a.langs=['en']
    a.propose_cue(0,'Sign reads OPEN')
    monkeypatch.setattr(a,'render',lambda *a:[])
    assert a.finalize()['ok'] and any('unverified' in i for i in a.report['issues'])
    b=make_agent(tmp_path/'b')
    b.propose_cue(0,'Sign reads OPEN')
    def broke(*x,**k): raise BudgetExceeded('cap')
    monkeypatch.setattr(b,'submodel',broke)
    b.fallback_finish('budget')
    assert not b.cues and any("unverified" in i for i in b.report["issues"])  # (e) fallback never ships unchecked risky text
    assert any(s['role']=='fallback' and 'unverified' in s['note'] for s in b.steps)


def test_fallback_runs_verification_and_drops_contradicted(tmp_path,monkeypatch):
    a=make_agent(tmp_path)
    a.propose_cue(0,'Sign reads OPEN')
    monkeypatch.setattr(a,'submodel',lambda *x,**k:{'verdict':'contradicted','evidence':'closed'})
    a.fallback_finish('stop')
    assert 0 not in a.cues and 0 in a.dropped


# 7 ---- duplicates
def test_duplicate_cue_rejected(tmp_path):
    a=make_agent(tmp_path,two_gaps())
    assert a.propose_cue(0,'Frame moves right and down.')['ok']
    r=a.propose_cue(1,'frame moves right and down')
    assert r['ok'] is False and r['problems']==['duplicate of gap 0']
    assert a.propose_cue(1,'Yellow shape fades out')['ok']
    assert a.propose_cue(0,'Frame moves right and down.')['ok']  # re-commit own gap is fine


# 8 ---- coverage
def test_coverage_ignores_speech_region_events(tmp_path,monkeypatch):
    a=make_agent(tmp_path); a.langs=['en']
    a.events=[{'importance':5,'t_start':1,'t_end':3,'what':'dialogue scene'},{'importance':5,'t_start':5.5,'t_end':7,'what':'in gap'}]
    a.draft_history[0]=['Title appears']
    a.propose_cue(0,'Title appears')
    monkeypatch.setattr(a,'render',lambda *x:[])
    assert a.finalize()['ok']
    assert a.report['high_importance_covered_percent']==100
    assert a.report['events_in_speech_regions']['count']==1
    b=make_agent(tmp_path/'b'); b.langs=['en']; b.events=[{'importance':5,'t_start':1,'t_end':3,'what':'dialogue scene'}]
    monkeypatch.setattr(b,'render',lambda *x:[])
    assert b.finalize()['ok'] and not b.report['uncovered_events']


# 9 ---- pricing
def test_fit_alt_price_and_new_defaults():
    cfg=load_config()
    assert cfg['prices']['fit_alt']=={'input_price':.06,'output_price':.24,'cached_input_price':.03}
    assert cfg['agent']['min_gap_s']==1.5 and cfg['agent']['verify_below']==.75 and cfg['agent']['max_verifications']==8


# mock end to end
def test_mock_kitchen_demonstrates_fixes(tmp_path):
    cfg=load_config(); cfg['tts']['backend']='silent'
    report=run_agent('samples/sample_kitchen.mp4',tmp_path,'mock',config=cfg)
    assert report['cues_committed']>=3 and not report['fallback_finalize']
    starts=re.findall(r'^(\d\d:\d\d:\d\d\.\d+) -->',(tmp_path/'ad_en.vtt').read_text(),re.M)
    assert starts==sorted(starts)
    stats=report['agent_stats']
    assert stats['verifications']['contradicted']>=1 and stats['verifications']['verified']>=1 and stats['corrections']>=2
    steps=json.loads((tmp_path/'trace.json').read_text())['steps']
    assert any(s['tool_name']=='verify_claim' for s in steps) and any(s['tool_name']=='propose_cue' for s in steps)
