"""Offline regressions for the fourth real-run fixes (evidence board, re-inspection loop, grounded text)."""
import json
from narrate.agent import run_agent
from narrate.agent.models import SYSTEM, compact_history
from narrate.config import load_config
from tests.test_fix2 import make_agent, tool_call, two_gaps
from tests.test_fix3 import fake_detect


def with_events(a):
    a.events=[{'t_start':5.2,'t_end':7.0,'what':'person in black shirt adjusts plant chamber','importance':3,'confidence':.8},
              {'t_start':12.5,'t_end':14.0,'what':'hands close the lid','importance':2,'confidence':.9}]
    return a


# 1 ---- evidence board
def test_evidence_board_compact_and_complete(tmp_path):
    a=with_events(make_agent(tmp_path,two_gaps()))
    line=a.evidence_line(a.gap(0))
    assert line.startswith('5.2-7.0: person in black shirt') and '[conf 0.8]' in line and len(line)<=160
    a.draft_description(gap_ids=[0]); a.propose_cue(1,'Hands close the lid')
    board=a.board_text()
    assert 'gap 0' in board and 'draft "' in board and 'COMMITTED "Hands close the lid"' in board
    a.events*=1; a.events+= [{'t_start':5.3+i/10,'t_end':6,'what':'w'*80,'importance':3,'confidence':1} for i in range(6)]
    assert len(a.evidence_line(a.gap(0)))<=160 and a.evidence_line(a.gap(0)).count('[conf')<=3


def test_inspect_summary_points_to_board():
    msgs=[{'role':'system','content':'S'},{'role':'user','content':'t'}]
    for i in range(8):
        msgs+=[{'role':'assistant','content':'','tool_calls':[{'id':f'c{i}','type':'function','function':{'name':'inspect_video_segment','arguments':json.dumps({'start':i,'end':i+9,'note':'n'})}}]},
               {'role':'tool','tool_call_id':f'c{i}','content':json.dumps({'events':[{'what':'x'*200}],'evidence_gaps':[i],'ok':True})}]
    out=compact_history(msgs,6)
    assert 'events stored on evidence board for gap 0' in out[3]['content']


# 2 ---- loops
def test_reinspection_refused_without_events_and_counts(tmp_path):
    a=make_agent(tmp_path,two_gaps()); a.speech=[]
    first=a.inspect_video_segment(4,8)
    assert first['events'] and first['evidence_gaps']==[0]
    r=a.inspect_video_segment(4.5,8)
    assert r['ok'] is False and r['error']=='already inspected' and 'events' not in r
    assert r['see']=='evidence board gap 0' and r['next']=='draft_description(gap_ids=[0])'
    assert a.repeat_refusals==1 and a.counts['inspections']==1
    st=a.execute('inspect_video_segment',{'start':4,'end':8,'note':'again'})['state']
    assert 'next_action' in st and 'draft_description(gap_ids=[0])' in st['next_action']


def test_identical_calls_refused_on_third(tmp_path):
    a=make_agent(tmp_path)
    args={'gap_id':0,'text':'Title appears','lang':'en','note':'probe'}
    assert a.execute('check_fit',args)['ok'] and a.execute('check_fit',args)['ok']
    r=a.execute('check_fit',args)
    assert r['ok'] is False and 'repeated' in r['error'] and a.repeat_refusals==1


def test_orchestrator_loop_reproduction_is_cut_short(tmp_path,monkeypatch):
    """Fake ultra: inspects every slot, then (history compacted) inspects them all again, twice, never drafts."""
    monkeypatch.setattr('narrate.agent.core.detect',fake_detect([(0,79.25)]))
    monkeypatch.setattr('narrate.agent.core.scene_cuts',lambda p:[])
    boards=[]
    class Looper:
        n=0
        def next(self,messages,a):
            self.n+=1
            boards.append([m['content'] for m in messages if str(m.get('content')).startswith('[EVIDENCE BOARD')])
            if self.n==1: return {'role':'assistant','content':'','tool_calls':[tool_call('detect_speech_gaps')]}
            if self.n<=12:
                gs=[g for g in a.gaps if g['narratable']]
                g=gs[(self.n-2)%len(gs)]
                return {'role':'assistant','content':'','tool_calls':[{**tool_call('inspect_video_segment',start=max(0,g['start']-2),end=g['end']),'id':f'c{self.n}'}]}
            raise RuntimeError('stop')
    cfg=load_config(); cfg['tts']['backend']='silent'
    report=run_agent('samples/nasa_chile_harvest_0000-0150.mp4',tmp_path,'mock',config=cfg,orchestrator=Looper())
    stats=report['agent_stats']
    assert stats['repeat_refusals']>=1 and stats['tool_calls']['inspect_video_segment']>=7
    assert all(len(b)<=1 for b in boards) and boards[-1] and 'evidence' in boards[-1][0]
    # fallback drafted every inspected slot in one batched call instead of dropping them
    assert report['cues_committed']>=5
    trace=json.loads((tmp_path/'trace.json').read_text())
    assert any(s['role']=='fallback' and s['tool_name']=='draft_description' for s in trace['steps'])


# 3 ---- grounded text
def test_orchestrator_authored_text_needs_verification(tmp_path):
    a=with_events(make_agent(tmp_path,two_gaps()))
    a.draft_history[0]=['Person adjusts plant chamber carefully']
    ok=a.propose_cue(0,'Person adjusts plant chamber')            # deletion only -> grounded
    assert ok['ok'] and 'orchestrator_authored' not in ok and not a.needs_verification()
    r=a.propose_cue(1,'Astronaut types on a laptop')               # invented
    assert r['ok'] and 'orchestrator_authored' in r and 'orchestrator-authored text' in r['verify_required']
    assert 1 in a.needs_verification()
    assert not a.finalize()['ok'] and 1 in a.finalize()['needs_verification']
    a.draft_history[1]=['Astronaut types on a laptop screen']
    a.propose_cue(1,'Astronaut types on a laptop')
    assert not a.needs_verification()


def test_prompt_and_tools_forbid_self_authored_text():
    from narrate.agent.schema import TOOLS
    assert 'instead of hand-editing' in SYSTEM and 'deleting words' not in SYSTEM and 'inspect up to 4 gaps per turn' in SYSTEM
    desc={t['function']['name']:t['function']['description'] for t in TOOLS}
    assert 'hand-editing' in desc['draft_description'] and 'deleting words' not in desc['propose_cue'] and 'auto-redrafts' in desc['propose_cue']


# 4 ---- fallback drafts
def test_fallback_batches_drafts_for_evidence_gaps(tmp_path):
    a=with_events(make_agent(tmp_path,two_gaps()))
    calls=[]; orig=a.draft_description
    a.draft_description=lambda **k:(calls.append(k),orig(**k))[1]
    a.fallback_finish('test stop')
    assert calls==[{'gap_ids':[0,1]}] and set(a.cues)=={0,1} and not a.dropped


def test_fallback_skips_drafting_without_evidence_or_budget(tmp_path):
    a=make_agent(tmp_path,two_gaps()); a.fallback_finish('test stop')
    assert set(a.dropped)=={0,1}
    b=with_events(make_agent(tmp_path/'b',two_gaps())); b.fallback_finish('budget exceeded')
    assert set(b.dropped)=={0,1}


# 5 ---- efficiency
def test_mock_ten_slot_clip_finishes_in_twelve_turns(tmp_path):
    cfg=load_config(); cfg['tts']['backend']='silent'
    report=run_agent('samples/nasa_chile_harvest_0000-0150.mp4',tmp_path,'mock',config=cfg)
    st=report['agent_stats']
    assert st['orchestrator_turns']<=12 and not report['fallback_finalize'] and report['cues_committed']>=5
    assert st['repeat_refusals']==0 and st['orchestrator_authored_cues']==0
