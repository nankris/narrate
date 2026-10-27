import json
from pathlib import Path
import numpy as np
import pytest
import jsonschema
from narrate.agent import run_agent
from narrate.agent.core import Agent
from narrate.agent.schema import TOOLS
from narrate.agent.models import Orchestrator
from narrate.agent.vad import silero_intervals
from narrate.config import load_config, resolve_provider
from narrate.llm import SpendGuard, BudgetExceeded, Client
from narrate.media import ffmpeg, energy_gaps, command
from scripts.eval_against_subs import intervals, evaluate


@pytest.fixture
def agent(tmp_path):
    cfg=resolve_provider(load_config(),'mock')
    cfg['tts']['backend']='silent'
    a=Agent('samples/sample_kitchen.mp4',tmp_path,cfg,['en','hi'],SpendGuard(.5))
    a.gaps=[{'id':0,'start':5.,'end':8.,'duration':3.,'word_budget_en':5,'word_budget_hi':4}]
    a.speech=[{'start':0,'end':4}]
    return a


def test_schemas():
    assert len(TOOLS)==11
    for tool in TOOLS:
        jsonschema.Draft202012Validator.check_schema(tool['function']['parameters'])


@pytest.mark.parametrize('text,ok',[('Title appears',True),('we see a title',False),('the camera pans',False),('word '*10,False),('',False),('line\nbreak',False)])
def test_fit(agent,text,ok):
    assert agent.check_fit(0,text,'en')['ok'] is ok


def test_duration_overlap_and_commit(agent):
    agent.tts_cache[('Title','en')]=(4,Path('unused'))
    assert not agent.check_fit(0,'Title','en')['ok']
    assert not agent.commit_cue(0,'word '*12)['ok']
    assert not agent.cues
    agent.speech.append({'start':7,'end':9})
    assert agent.check_fit(0,'Short','en')['overlap_seconds']==1


def test_tools_and_caps(agent):
    found=agent.detect_speech_gaps()
    assert found['detector'] and 0<=found['speech_ratio']<=1
    g=agent.gaps[0]
    args={'start':g['start'],'end':g['end']}
    result=agent.inspect_video_segment(**args)
    assert result==agent.inspect_video_segment(**args)
    assert agent.counts['inspections']==1
    agent.cfg['agent']['max_inspections']=1
    assert not agent.inspect_video_segment(0,1)['ok']
    assert agent.verify_claim(**args,claim='blue dot')['verdict']=='contradicted'
    agent.cfg['agent']['max_verifications']=1
    assert not agent.verify_claim(**args,claim='anything')['ok']
    draft=agent.draft_description(g['id'],result['events'],2)
    assert len(draft['text'].split())<=2
    assert agent.measure_tts_duration('Title','en')==agent.measure_tts_duration('Title','en')
    assert agent.commit_cue(g['id'],'Title')['ok']
    assert agent.translate_hindi()['cues']
    assert agent.drop_gap(g['id'],'not essential')['ok']
    assert not agent.cues
    assert not agent.execute('commit_cue',{'gap_id':0,'text':'Title','extra':1})['ok']


def test_finalize_reject_then_accept(agent):
    agent.events=[{'importance':5,'t_start':10,'t_end':12}]
    assert not agent.finalize()['ok']
    assert not agent.finalize()['ok']
    assert agent.finalize()['ok'] and agent.report['issues']


@pytest.mark.parametrize('mode',['steps','budget','stopped'])
def test_fallback(tmp_path,mode):
    class Stop:
        def next(self,*args):
            if mode=='budget':
                raise BudgetExceeded('fake cap')
            return {'role':'assistant','content':'Done'}
    cfg=load_config(); cfg['tts']['backend']='silent'
    report=run_agent('samples/sample_kitchen.mp4',tmp_path,provider='mock',config=cfg,
        max_steps=0 if mode=='steps' else 2,orchestrator=Stop())
    assert report['fallback_finalize'] and report['status']=='complete'
    assert (tmp_path/'trace.json').is_file()


def test_mock_e2e(tmp_path):
    cfg=load_config(); cfg['tts']['backend']='silent'
    stream=[]
    report=run_agent('samples/sample_kitchen.mp4',tmp_path,'mock',config=cfg,on_step=stream.append)
    assert report['overlaps_with_speech']==0
    assert report['agent_stats']['corrections']>=1
    assert not report['fallback_finalize']
    for name in ('narrated_en.mp4','narrated_hi.mp4','ad_en.vtt','ad_hi.vtt','transcript_en.txt','transcript_hi.txt','report.json','trace.json','trace.md','preview_en.mp4'):
        assert (tmp_path/name).is_file()
    trace=json.loads((tmp_path/'trace.json').read_text())
    assert len(stream)==len(trace['steps'])
    required={'step','t_wall','role','note','tool_name','args','result','ok','latency_s','tokens_in','tokens_out','cost_usd','model','correction'}
    for step in trace['steps']:
        assert required<=step.keys()
        if step['correction']:
            assert step['corrects_step']<step['step']
            assert not trace['steps'][step['corrects_step']-1]['ok']


def test_subtitle_eval():
    srt='1\n00:00:01,000 --> 00:00:03,000\nHello\n\n2\n00:00:05,000 --> 00:00:06,000\nWorld'
    speech=intervals(srt)
    result=evaluate(speech,[(2,4),(7,9)],10)
    assert result['overlap_seconds']==1
    assert result['dialogue_free_narrated_percent']==pytest.approx(300/7)
    assert intervals(srt,-1)[0]==(0,2)


def test_vad_music(tmp_path):
    speech=tmp_path/'speech.wav'
    command(['espeak-ng','-w',str(speech),'--','This is spoken dialogue for the speech detector.'])
    raw=ffmpeg('-i',speech,'-ar',16000,'-ac',1,'-f','f32le','-').stdout
    voice=np.frombuffer(raw,dtype='<f4')
    audio=np.concatenate([voice,np.zeros(16000*3),voice]).astype(np.float32)
    audio+=.025*np.sin(np.arange(len(audio))*2*np.pi*220/16000).astype(np.float32)
    try:
        found=silero_intervals(audio)
    except (ImportError,OSError,RuntimeError) as exc:
        pytest.skip('Silero ONNX unavailable: '+type(exc).__name__)
    assert found
    assert not energy_gaps(audio,noise_db=-40,minimum=1.2)
    assert any(b['start']-a['end']>1.2 for a,b in zip(found,found[1:]))


def test_orchestrator_request(monkeypatch):
    from types import SimpleNamespace as NS
    monkeypatch.setenv('NEBIUS_API_KEY','fake-test-credential')
    calls=[]
    class Message:
        content='I will detect speech.'
        tool_calls=[1]
        def model_dump(self,**kw):
            return {'role':'assistant','content':self.content,'tool_calls':[]}
    def create(**kwargs):
        calls.append(kwargs)
        return NS(usage=NS(prompt_tokens=10,completion_tokens=10),choices=[NS(message=Message())])
    c=Client(load_config(),sdk_factory=lambda **kw:NS(chat=NS(completions=NS(create=create))))
    Orchestrator(c).next([{'role':'user','content':'test'}],None)
    assert calls[0]['tools']==TOOLS and calls[0]['tool_choice']=='auto'
    assert calls[0]['extra_body']['chat_template_kwargs']['enable_thinking'] is False
    assert c.guard.spent>0


def test_empty_reasoning_is_retryable(monkeypatch):
    from types import SimpleNamespace as NS
    monkeypatch.setenv('NEBIUS_API_KEY','fake-test-credential')
    calls=[]
    def create(**kw):
        calls.append(kw)
        return NS(usage=NS(prompt_tokens=10,completion_tokens=10), choices=[NS(message=NS(content='',reasoning_content='{"cues":[]}'))])
    client=Client(load_config(),sdk_factory=lambda **kw:NS(chat=NS(completions=NS(create=create))))
    with pytest.raises(RuntimeError,match='raise max_tokens or disable thinking'):
        client.call('fit',{})
    assert len(calls)==3 and len(client.usage)==3


def test_actual_spend_guard_blocks_before_call(monkeypatch):
    from types import SimpleNamespace as NS
    monkeypatch.setenv('NEBIUS_API_KEY','fake-test-credential')
    def create(**kw):
        pytest.fail('Provider must not be called when reservation fails')
    client=Client(load_config(),guard=SpendGuard(0),sdk_factory=lambda **kw:NS(chat=NS(completions=NS(create=create))))
    with pytest.raises(BudgetExceeded):
        Orchestrator(client).next([{'role':'user','content':'test'}],None)


def test_continuous_speech_failure(tmp_path):
    cfg=load_config(); cfg['tts']['backend']='silent'
    result=run_agent('samples/failure_continuous_speech.mp4',tmp_path,'mock',config=cfg)
    assert not result['cues']
    assert any('extended AD' in issue for issue in result['issues'])
