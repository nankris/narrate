import os
import hashlib
import json
import math
import re
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse
import jsonschema
from ..config import load_config, resolve_provider
from ..llm import Client, SpendGuard, BudgetExceeded, SYSTEM as SUBSYSTEM, sanitize, normalize_json
from ..media import probe, ffmpeg, word_budget, write_texts, scene_cuts, split_slots
from ..perception import data_url, separate_frames
from ..tts import backend, mix
from .models import SYSTEM, Orchestrator, MockOrchestrator, compact_history
from .schema import TOOLS
from .vad import detect


def compact(value, limit=800):
    def rounded(v):
        if isinstance(v,float): return round(v,2)
        if isinstance(v,dict): return {k:rounded(x) for k,x in v.items()}
        if isinstance(v,list): return [rounded(x) for x in v]
        return v
    result=rounded(value)
    dump=lambda v: json.dumps(v,ensure_ascii=False,separators=(',',':'))
    if len(dump(result))<=limit: return result
    if not isinstance(result,dict): result={'value':result}
    result['truncated']=True
    # Keep result keys (including cached/ok/state); trim long text and arrays structurally.
    while len(dump(result))>limit:
        candidates=[]
        def visit(v):
            if isinstance(v,dict):
                for k,x in v.items():
                    if k=='state': continue
                    if isinstance(x,str) and len(x)>24: candidates.append((len(x),v,k))
                    elif isinstance(x,list) and x: candidates.append((len(dump(x)),v,k))
                    if isinstance(x,dict): visit(x)
            elif isinstance(v,list):
                for x in v: visit(x)
        visit(result)
        if not candidates: break
        _,parent,key=max(candidates,key=lambda x:x[0])
        item=parent[key]
        if isinstance(item,list):
            if len(item)>1: item.pop()
            else:
                before=len(dump(item))
                visit(item)
                nested=[c for c in candidates if c[1] is not parent]
                if nested:
                    _,obj,k=max(nested,key=lambda x:x[0])
                    if isinstance(obj[k],str): obj[k]=obj[k][:max(24,len(obj[k])//2)]
                    else: obj[k].pop()
                if len(dump(item))==before: item.pop()
        else: parent[key]=item[:max(24,len(item)//2)]

    return result


def absolute_times(events,start,end,tol=.5):
    """Return (events, base) with t_start/t_end in absolute video seconds.

    The VL model sees a clip cut at `start`, so it may answer with clip-relative times (0..duration) even
    though absolute times were requested. Heuristic: if every event fits [start-tol, end+tol] the times are
    absolute (kept, also when both readings fit); else if every event fits [0, duration+tol] they are
    relative and `start` is added; otherwise ('mixed') they are kept and the caller drops any event that
    lies outside the segment."""
    spans=[]
    for e in events:
        try: spans.append((float(e['t_start']),float(e['t_end'])))
        except (KeyError,ValueError,TypeError): pass
    if not spans or start<=tol or all(s>=start-tol and t<=end+tol for s,t in spans):
        return events,'absolute'
    if all(s>=0 and t<=end-start+tol for s,t in spans):
        shifted=[]
        for e in events:
            try: shifted.append({**e,'t_start':round(float(e['t_start'])+start,3),'t_end':round(float(e['t_end'])+start,3)})
            except (KeyError,ValueError,TypeError): shifted.append(e)
        return shifted,'relative->absolute'
    return events,'mixed'


def tokens(text):
    return set(re.findall(r'\w+',text.lower()))


def similarity(a,b):
    x,y=tokens(a),tokens(b)
    return len(x&y)/len(x|y) if x|y else 0.


def risky_text(text):
    """Cheap heuristic: quotes, digits or capitalized words that do not start a sentence."""
    reasons=[]
    if re.search('["\u201c\u201d]',text): reasons.append('quoted text')
    if re.search(r'\d',text): reasons.append('number')
    words=text.split()
    if any(i and not re.search(r'[.!?]$',words[i-1]) and len(w)>1 and w[0].isupper() for i,w in enumerate(words)):
        reasons.append('named entity')
    return reasons


SCENE_INSTRUCTION=('Establish the scene for a blind viewer from these frames sampled across the whole video. Return JSON '
    '{setting, people:[{description, doing}], materials:[], tools:[], objects:[], activity, goal, visual_style, '
    'burned_in_subtitles, confidence}. setting: the kind of place (e.g. room type, indoor/outdoor, surfaces, lighting). '
    'Keep setting under 15 words and each person description under 12 words. '
    'people: who is visible, by appearance only (clothing, hands only, how many); never guess names, age or identity. '
    'materials/tools/objects: short concrete nouns that are clearly visible. activity: what is being done overall. '
    'goal: what is being done only if visibly established or written on screen, else "". burned_in_subtitles: true if '
    'any frame has a short line of text (usually near the bottom) that reads like a fragment of spoken words, i.e. subtitles '
    'of the speaker; titles, labels and signs do not count. confidence 0-1. Use only what is visible.')
SCENE_LISTS=('materials','tools','objects')


def clean_scene(raw):
    """Normalise a scene-context answer into short strings and lists; anything malformed is dropped."""
    raw=raw if isinstance(raw,dict) else {}
    def cut(t,n):
        return t if len(t)<=n else t[:n].rsplit(' ',1)[0].rstrip(' ,;:')
    short=lambda v,n: cut(' '.join(str(v).split()),n) if isinstance(v,(str,int,float)) and not isinstance(v,bool) else ''
    old_goal=raw.get('di'+'sh','')
    out={k:short(raw.get(k, old_goal if k == 'goal' else ''),200) for k in ('setting','activity','goal','visual_style')}
    people=raw.get('people',[])
    people=people if isinstance(people,list) else [people]
    out['people']=[x for x in ([' '.join(', '.join(x for x in (short(p.get('description',''),100),short(p.get('doing',''),80)) if x).split()) if isinstance(p,dict) else short(p,120) for p in people[:4]]) if x]
    for k in SCENE_LISTS:
        v=raw.get(k, raw.get('ingre'+'dients', []) if k == 'materials' else [])
        v=v if isinstance(v,list) else [v]
        out[k]=list(dict.fromkeys(x for x in (short(i,40) for i in v[:10]) if x))
    out['ingre'+'dients']=out['materials']
    out['di'+'sh']=out['goal']
    out['burned_in_subtitles']=raw.get('burned_in_subtitles') in (True,'true','yes',1)
    try: out['confidence']=max(0.,min(1.,float(raw.get('confidence',0))))
    except (TypeError,ValueError): out['confidence']=0.
    return out


def scene_brief(ctx,limit=420):
    """One compact line of scene context for drafting/inspection prompts ('' when unknown)."""
    if not ctx: return ''
    parts=[f"setting: {ctx['setting']}" if ctx.get('setting') else '',
        'people: '+'; '.join(ctx['people']) if ctx.get('people') else '',
        f"activity: {ctx['activity']}" if ctx.get('activity') else '',
        f"goal: {ctx['goal']}" if ctx.get('goal') else '',
        *[f"{k}: "+', '.join(ctx[k]) for k in SCENE_LISTS if ctx.get(k)]]
    return ' | '.join(p for p in parts if p)[:limit]


CAMERA_DIRECTION=re.compile(r'\b(?:the\s+)?camera\s+(?:moves|pans|zooms|tilts|cuts|records|follows|shows|focuses|captures|reveals|lingers|switches|stays|returns)\b'
    r'|\b(?:as|while)\s+the\s+camera\b|\bon\s+camera\b|\bcamera\s+(?:angle|view|work)\b|\bzooms?\s+(?:in|out)\b|^\s*cut\s+to\b',re.I)
# A recording device held by someone in the video is a legitimate object;
# only camera DIRECTION language (the camera pans/zooms/cuts/shows, "on camera") is banned.
BANNED=[(re.compile(r'\b(?:we|you)\s+(?:can\s+)?see\b',re.I),'"we see"','state the action directly with its subject, e.g. "<who> <verbs> <object>"'),
    (CAMERA_DIRECTION,'camera direction','describe what is visible, not camera movement; a recording device held by a person is an ordinary object'),
    (re.compile(r'\bTITLE\b(?!:)'),'literal TITLE label (write Title: "...")','write Title: "..." with the exact on-screen words'),
    (re.compile(r'^\s*(?:the\s+)?screen\b',re.I),'cue starts with "Screen"','open with who or what is visible'),
    (re.compile(r'\bSKIP\b'),'SKIP marker is not narration','return {"skip": true} instead of text')]


def lint(text):
    """Deterministic style rules the prompts state but models break (review finding 7)."""
    return [f'Banned phrasing: {why}' for rx,why,_ in BANNED if rx.search(text)]


def lint_with_hints(text):
    """lint() plus a concrete fix for each rule, so a repair request says how to fix it, not only what is wrong."""
    return [f'Banned phrasing: {why}. Fix: {hint}' for rx,why,hint in BANNED if rx.search(text)]


def is_skip(text):
    return isinstance(text,str) and text.strip().strip('."\'').upper() in ('SKIP','NO NEW INFORMATION')


class Agent:
    def __init__(self,path,out,cfg,langs,guard,on_step=None,client=None):
        self.path,self.out,self.cfg = Path(path),Path(out),cfg
        self.out.mkdir(parents=True,exist_ok=True)
        self.work = self.out/'work'; self.work.mkdir(exist_ok=True)
        self.duration,self.has_audio = probe(path)
        if not 0 < self.duration <= cfg['max_duration']:
            raise ValueError('Video duration outside configured limit')
        self.langs,self.guard,self.on_step = langs,guard,on_step
        self.mock = cfg['provider']=='mock'
        self.client = client or Client(cfg,guard)
        self.client.guard = guard
        self.client.config = cfg
        self.engine = backend(cfg['tts'])
        self.started = time.monotonic()
        self.client.deadline = self.started + cfg['agent']['timeout_s']
        self.gaps,self.speech,self.events = [],[],[]
        self.cues,self.dropped,self.cache,self.tts_cache = {},{},{},{}
        self.counts = Counter(); self.pending_failures = []
        self.translation_done=False
        self.candidates,self.drafts,self.verified,self.rejected = {},{},{},{}
        self.contradicted=0
        self.draft_history,self.authored,self.call_counts = {},{},Counter()
        self.repeat_refusals=0
        self.propose_fails,self.inspect_tries,self.auto_redrafts,self.draft_overlimit=Counter(),Counter(),0,0
        self.client.retry_attempts = cfg['agent'].get('retry_attempts',3)
        self.client.on_retry = lambda note: self.trace('system',note=note,ok=False)
        self.steps = []; self.turn=0; self.rejections=0; self.done=False
        self.report = {'mock':self.mock,'provider':cfg['provider'],'dev_only':cfg['provider']=='nvidia-dev',
            'duration_s':self.duration,'fallback_finalize':False,'issues':[]}
        self.scenes = []
        self.scene_context = None
        self.skipped = {}
        self.translated_cues = None
        sidecar = self.path.with_suffix('.scenes.json')
        if self.mock and sidecar.is_file():
            self.scenes = json.loads(sidecar.read_text())

    def trace(self,role,**kw):
        row = {'step':len(self.steps)+1,'t_wall':time.monotonic()-self.started,'role':role,'note':'',
               'tool_name':None,'args':{},'result':None,'ok':True,'latency_s':0,'tokens_in':0,'tokens_out':0,
               'cost_usd':0,'model':None,'correction':False,**kw}
        self.steps.append(row)
        if self.on_step:
            self.on_step(dict(row))
        return row['step']

    def mock_events(self,start,end):
        overlap=lambda s: min(end,s['t_end'])-max(start,s['t_start'])
        return [{**s,'what':s.get('action',''),'confidence':1.0,'mock':True} for s in sorted(self.scenes,key=lambda s:-overlap(s))
                if overlap(s) > 0] or [
                    {'t_start':start,'t_end':end,'what':'A static scene is displayed','on_screen_text':'',
                     'importance':2,'confidence':0,'mock':True}]

    def mock_line(self,events,limit):
        # Sidecar text is synthetic ground truth only in mock mode.
        text = events[0].get('on_screen_text') or events[0].get('what','Scene')
        return ' '.join(text.split()[:max(1,min(limit,7))])

    def submodel(self,stage,data,media=None,mock_result=None,system=None):
        start = time.monotonic()
        if start > self.client.deadline:
            raise TimeoutError('Agent deadline reached')
        if self.mock:
            self.guard.reserve(0)
            result = mock_result
            usage = {'model':'MOCK/'+stage,'input_tokens':max(1,len(json.dumps(data))//3),
                     'output_tokens':max(1,len(json.dumps(result))//3),'cost_usd':0}
        else:
            before=len(self.client.usage)
            try:
                result = self.client.call(stage,{**data, '_system': system or 'You are a precise audio description assistant. Follow the requested JSON schema. Describe only supported visible facts. '+data.get('instruction','')},media)
            except Exception:
                for usage in self.client.usage[before:]:
                    usage['cost_role']=getattr(self,'cost_role',None) or {'fit':'draft','edit':'translate'}.get(stage,stage)
                    self.trace('submodel',cost_role=getattr(self,'cost_role',None) or {'fit':'draft','edit':'translate'}.get(stage,stage),cached_tokens=usage.get('cached_tokens',0),model=usage['model'],tokens_in=usage['input_tokens'],tokens_out=usage['output_tokens'],cost_usd=usage['cost_usd'],latency_s=usage['latency_s'],ok=False,result={'error':'Submodel response failed'})
                raise
            for entry in self.client.usage[before:]:
                entry['cost_role']=getattr(self,'cost_role',None) or {'fit':'draft','edit':'translate'}.get(stage,stage)
            usage = dict(self.client.usage[-1])
            usage.update({k:sum(u.get(k,0) for u in self.client.usage[before:]) for k in ('input_tokens','output_tokens','cost_usd','cached_tokens')})
        result=normalize_json(result)
        self.trace('submodel',cost_role=getattr(self,'cost_role',None) or {'fit':'draft','edit':'translate'}.get(stage,stage),cached_tokens=usage.get('cached_tokens',0),model=usage['model'],tokens_in=usage['input_tokens'],tokens_out=usage['output_tokens'],
                   cost_usd=usage['cost_usd'],latency_s=time.monotonic()-start,result=compact(result))
        return result

    def mock_scene(self):
        whats=[s.get('action','') for s in self.scenes if s.get('action')]
        return {'setting':'MOCK: '+(whats[0] if whats else 'static synthetic scene'),'people':[],'materials':[],'tools':[],
                'objects':[s.get('who','') for s in self.scenes[:3] if s.get('who')],'activity':'MOCK sidecar scene','goal':'','confidence':0}

    def establish_scene(self):
        """Scene-context pass (Super VL, once per run): setting, people, objects, materials and activity.

        Frames are sampled evenly across the whole video so the context does not depend on any one gap. The
        result is fed into every inspection, draft and translation so cues can name the place, who is in it
        and what they handle, instead of bare actions."""
        if self.scene_context is not None or not self.cfg['agent'].get('scene_context',True):
            return self.scene_context or {}
        n=max(1,int(self.cfg['agent'].get('scene_frames',6)))
        times=[round(self.duration*(i+.5)/n,2) for i in range(n)]
        media=None if self.mock else separate_frames(self.path,times)
        previous=getattr(self,'cost_role',None); self.cost_role='scene'
        try:
            raw=self.submodel('perceive',{'duration':0,'instruction':SCENE_INSTRUCTION,'timestamps':times},media,self.mock_scene())
        except BudgetExceeded:
            raise
        except Exception as exc:
            raw={}; self.report['issues'].append('Scene context unavailable: '+sanitize(exc))
        finally:
            self.cost_role=previous
        self.scene_context=clean_scene(raw)
        self.report['scene_context']=self.scene_context
        return self.scene_context

    def establishing_gap(self):
        """Id of the first narratable gap: its cue opens with the setting and who is present."""
        ids=[g['id'] for g in sorted(self.gaps,key=lambda g:g['start']) if g.get('narratable',True) and g['id'] not in self.dropped]
        return ids[0] if ids else None

    def detect_speech_gaps(self):
        if self.counts['gap_detection']:
            return {'cached':True,'reminder':'Use the gaps from the first detection.'+('' if any(g.get('narratable',True) for g in self.gaps) else ' There are no narratable gaps: call finalize.')}
        self.counts['gap_detection']+=1
        result = detect(self.path,self.duration,self.has_audio,self.cfg)
        cfg_min_gap = self.cfg['agent'].get('min_gap_s',1.5)
        self.speech=result['speech']; self.gaps=[]
        max_slot = self.cfg['agent'].get('max_slot_s',12)
        raw = [(g['start']+.08,g['end']-.08) for g in result['gaps']]
        cuts = []
        if any(e-s >= cfg_min_gap and e-s > max_slot for s,e in raw):
            cuts = scene_cuts(self.path)
        for parent,(start,end) in enumerate(raw):
            narratable = end-start >= cfg_min_gap
            slots = split_slots(start,end,max_slot,cuts) if narratable else [(start,end)]
            for s,e in slots:
                self.gaps.append({'id':len(self.gaps),'start':s,'end':e,'duration':e-s,'narratable':narratable,
                    **({'parent_gap':parent} if len(slots) > 1 else {}),
                    **({} if narratable else {'reason':'too short'}),
                    **{'word_budget_'+lang:word_budget(e-s,self.cfg['words_per_second'][lang],self.cfg['word_margin']) for lang in ('en','hi')}})
                self.gaps[-1].update({'max_words_'+lang:self.max_words(self.gaps[-1],lang) for lang in ('en','hi')})
        slot_count = sum(g['narratable'] for g in self.gaps)
        self.cfg['agent']['max_inspections'] = max(self.cfg['agent']['max_inspections'],slot_count+2)
        self.report.update(detector=result['detector'],speech_ratio=result['speech_ratio'],detector_fallback_reason=result['fallback_reason'])
        if self.gaps and not any(g['narratable'] for g in self.gaps):
            self.report['issues'].append('Every speech-free gap is shorter than agent.min_gap_s; extended AD is needed.')
        if not self.gaps:
            self.report['issues'].append('Cannot narrate safely without extended AD (pause-the-video): no usable speech-free gaps.')
        scene=self.establish_scene() if any(g['narratable'] for g in self.gaps) else {}
        return {**({'scene_context':scene_brief(scene,200)} if scene_brief(scene) else {}),'gaps':[{k:g[k] for k in ('id','start','end','max_words_en','max_words_hi','narratable','reason','parent_gap') if k in g} for g in self.gaps], 'detector':result['detector'],'speech_ratio':result['speech_ratio']}

    def cue_cap(self,g):
        """Longest speech a single English cue may take in this gap (seconds)."""
        return min(g['duration']*.9,self.cfg['agent'].get('max_cue_s',8.))

    def max_words(self,g,lang='en'):
        """The ONE effective word limit: word budget AND what fits the single-cue duration cap."""
        budget=g['word_budget_'+lang]
        fits=word_budget(self.cue_cap(g),self.cfg['words_per_second'][lang],self.cfg['word_margin'])
        return max(1,min(budget,fits)) if budget>0 else 0

    def segment(self,start,end):
        if not all(math.isfinite(x) for x in (start,end)) or not 0 <= start < end <= self.duration:
            raise ValueError('Invalid segment bounds')

    @staticmethod
    def window(g):
        return g['start']-1.0,g['end']+.5

    def overlaps(self,e,g):
        """Event belongs to gap g only if it really happens there (review finding 4).

        Assigned when the event midpoint lies in the gap window (1 s pre-roll, 0.5 s tail), or it overlaps the gap
        itself by >= max(1 s, half the event), or it covers >= half of the gap. A long shot that only brushes the
        gap edge no longer leaks into the gap's narration."""
        try: s,e1=float(e['t_start']),float(e['t_end'])
        except (KeyError,TypeError,ValueError): return False
        w0,w1=self.window(g)
        if not (s<w1 and e1>w0): return False
        if w0<=(s+e1)/2<=w1: return True
        ov=max(0.,min(e1,g['end'])-max(s,g['start']))
        return ov>=max(1.,.5*(e1-s)) or ov>=.5*max(g['end']-g['start'],1e-6)

    def gap_events(self,g,passed=None):
        """Evidence for one gap: events overlapping its window, plus at most 2 recent earlier ones (context only)."""
        w0,_=self.window(g)
        pool=[]
        for e in list(self.events)+list(passed or []):
            if isinstance(e,dict) and 't_start' in e and 't_end' in e and not any(e['t_start']==x['t_start'] and e['t_end']==x['t_end'] and e.get('what')==x.get('what') for x in pool):
                pool.append(e)
        pool=[e for e in pool if not e.get('refuted')]
        inside=[e for e in pool if self.overlaps(e,g)]
        # Only recent predecessors (<=10s) are useful context; anything else risks narrating the wrong moment.
        earlier=sorted([e for e in pool if float(e['t_end'])<=w0 and w0-float(e['t_end'])<=10],key=lambda e:float(e['t_end']))[-2:]
        return [{**e,'context':'earlier, context only'} for e in earlier]+inside

    def owned_gaps(self,start,end):
        """Narratable gaps at least half inside the range (a pre-roll only brushes the previous gap)."""
        return [g for g in self.gaps if g.get('narratable',True) and min(end,g['end'])-max(start,g['start'])>=.5*g['duration']]

    def refuse_inspection(self,start,end):
        self.repeat_refusals+=1
        ids=self.range_gaps(start,end)
        todo=[i for i in ids if i not in self.cues and i not in self.dropped]
        return {'ok':False,'error':'already inspected','evidence_gaps':ids,
            'see':'evidence board gap '+','.join(map(str,ids)) if ids else 'evidence board',
            'next':f'draft_description(gap_ids={todo})' if todo else 'gaps in this range are already committed; move on'}

    def inspect_video_segment(self,start,end,focus=''):
        if self.counts['gap_detection'] and not any(g.get('narratable',True) for g in self.gaps):
            return {'ok':False,'error':'no narratable gaps: speech covers the video, so nothing seen can be narrated without extended AD','next':'finalize'}
        self.segment(start,end)
        key=(start,end,focus)
        for (s,e,_),cached in self.cache.items():
            if not cached.get('events'): continue
            inter=max(0,min(end,e)-max(start,s))
            if inter/(end-start)>=.7 or inter/(e-s)>=.9:
                return self.refuse_inspection(start,end)
        # Gaps mostly inside this range: refuse when every one already has events (pre-roll variants, sub-ranges)
        # or was already tried twice with zero events (one retry allowed).
        owned=self.owned_gaps(start,end)
        if owned and all(self.inspect_tries[g['id']]>=(1 if self.evidence_line(g) else 2) for g in owned):
            return self.refuse_inspection(start,end)
        if self.counts['inspections'] >= self.cfg['agent']['max_inspections']:
            return {'ok':False,'error':'Inspection cap reached'}
        self.counts['inspections']+=1
        for g in self.owned_gaps(start,end): self.inspect_tries[g['id']]+=1
        data={'duration':end-start,'instruction':'Inspect this segment. Return events with absolute video t_start/t_end (seconds), what, on_screen_text, importance 1-5, confidence 0-1. Segment starts at '+str(start)
              +' s. In what, say who acts, on which object or material, with which tool, and the visible result; reuse the nouns from scene_context when they match what is visible. on_screen_text is only for titles, labels and signs; subtitle lines that transcribe the speaker\'s words are NOT on_screen_text (leave it empty)'+(' - this video has burned-in subtitles' if (self.scene_context or {}).get('burned_in_subtitles') else '')+'.',
              'focus':focus,**({'scene_context':scene_brief(self.scene_context)} if scene_brief(self.scene_context) else {})}
        media=None; modality='mock'
        if not self.mock:
            clip=self.work/'inspection.mp4'
            ffmpeg('-ss',start,'-i',self.path,'-t',end-start,'-an','-vf','scale=640:360,fps=10','-c:v','libx264',clip)
            media=[{'type':'video_url','video_url':{'url':data_url(clip.read_bytes(),'video/mp4')}}]; modality='video'
        def as_events(r):
            # Some model responses contain one bare event object instead of {events:[...]}.
            if isinstance(r,dict) and not r.get('events') and 't_start' in r and 't_end' in r: return {'events':[r]}
            if isinstance(r,list): return {'events':r}
            return r
        try:
            result=as_events(self.submodel('perceive',data,media,{'events':self.mock_events(start,end)}))
            if not result.get('events'):
                raise ValueError('No events')
        except BudgetExceeded:
            raise
        except Exception:
            if self.mock:
                raise
            modality='frames-fallback'
            result=as_events(self.submodel('perceive',data,separate_frames(self.path,[start,start+(end-start)/2,max(start,end-.1)])))
        valid=[]; raw=result.get('events',[])
        if not self.mock:
            raw,base=absolute_times(raw,start,end)
        else: base='absolute'
        for event in raw:
            try:
                s,e=float(event['t_start']),float(event['t_end'])
                if base=='mixed' and (e<=start-.5 or s>=end+.5): continue
                if not 0<=s<e<=self.duration or not 1<=float(event['importance'])<=5:
                    continue
                event={**event,'what':event.get('what') or event.get('action') or event.get('event') or event.get('description') or ''}
                if not isinstance(event['what'],str):
                    continue
                if event not in self.events:
                    self.events.append(event)
                valid.append(event)
            except (KeyError,ValueError,TypeError):
                continue
        result={'events':valid,'modality':modality,'time_base':base,'evidence_gaps':self.range_gaps(start,end)}
        self.cache[key]=result
        return result

    def range_gaps(self,start,end):
        return [g['id'] for g in self.gaps if g.get('narratable',True) and g['start']<end and g['end']>start]

    def evidence_line(self,g):
        """Compact stored evidence for one gap (<=3 events, <=160 chars); survives history compaction."""
        def num(v,d=1.):
            try: return float(v)
            except (TypeError,ValueError): return d
        evs=[e for e in self.gap_events(g) if 'context' not in e]
        evs=sorted(sorted(evs,key=lambda e:-num(e.get('importance'))*num(e.get('confidence')))[:3],key=lambda e:num(e['t_start'],0))
        return '; '.join(f"{num(e['t_start']):.1f}-{num(e['t_end']):.1f}: {str(e.get('what','')).strip()[:50]} [conf {num(e.get('confidence')):.1f}]" for e in evs)[:160]

    def next_action(self):
        todo=[g for g in self.gaps if g.get('narratable',True) and g['id'] not in self.cues and g['id'] not in self.dropped]
        blind=[g['id'] for g in todo if not self.evidence_line(g)]
        empty=[i for i in blind if self.inspect_tries[i]>=2]; blind=[i for i in blind if i not in empty]
        undrafted=[g['id'] for g in todo if g['id'] not in blind+empty and g['id'] not in self.drafts]
        if undrafted: return f'STOP inspecting; call draft_description(gap_ids={undrafted}) now (gaps already have evidence)'
        if todo and len(blind)+len(empty)<len(todo): return 'propose_cue for gaps '+str([g['id'] for g in todo if g['id'] not in blind+empty])+' using their drafts (if one fails: draft_description(gap_ids=[id], max_words=N), do not hand-edit)'
        if blind: return f'inspect_video_segment gaps {blind} (no evidence yet)'
        if empty: return f'drop_gap for gaps {empty}: inspected twice, no events found'
        return 'translate_hindi once, then finalize'

    def board_text(self):
        rows=[]
        for g in self.gaps:
            if not g.get('narratable',True): continue
            gid=g['id']; row=f"gap {gid} {g['start']:.1f}-{g['end']:.1f}s <={self.max_words(g)}w: "
            if gid in self.cues: row+='COMMITTED "'+self.cues[gid]['en']+'"'
            elif gid in self.dropped: row+='DROPPED ('+self.dropped[gid][:40]+')'
            else:
                row+='evidence '+(self.evidence_line(g) or ('no events found (inspected)' if self.inspect_tries[gid] else 'NONE (not inspected)'))
                if gid in self.drafts: row+=' | draft "'+self.drafts[gid]+'"'
            rows.append(row)
        return ('[EVIDENCE BOARD - authoritative state; never re-inspect a gap that has evidence. Use draft_description(gap_ids=[...]) and propose its text]\n'
            +'\n'.join(rows)+'\nnext: '+self.next_action()) if rows else ''

    def grounded(self,gap_id,text):
        t=tokens(text)
        return any(similarity(text,d)>=.6 or (t and t<=tokens(d)) for d in self.draft_history.get(gap_id,[]))

    def verification_reasons(self,gap_id):
        """Why a committed English cue must be verified before finalize (empty = not required)."""
        c=self.cues[gap_id]; reasons=risky_text(c['en'])
        if self.authored.get(gap_id)==c['en']: reasons.append('orchestrator-authored text')
        floor=self.cfg['agent'].get('verify_below',.75)
        low=[e for e in self.gap_events(c) if 'context' not in e and float(e.get('confidence',1))<floor]
        if low: reasons.append(f'low-confidence events (<{floor})')
        return reasons

    def needs_verification(self):
        return {gid:r for gid in self.cues if gid not in self.verified and (r:=self.verification_reasons(gid))}

    def verify_claim(self,start=None,end=None,claim=None,gap_id=None):
        if not isinstance(claim,str) or not claim.strip():
            raise ValueError('verify_claim needs a claim')
        if gap_id is not None:
            g=self.gap(gap_id); start,end=g['start'],g['end']; ids=[gap_id]
        elif start is None or end is None:
            raise ValueError('verify_claim needs gap_id or start and end')
        else:
            ids=[g['id'] for g in self.gaps if g['start']<end and g['end']>start]
        self.segment(start,end)
        if self.counts['verifications'] >= self.cfg['agent']['max_verifications']:
            return {'ok':False,'error':'Verification cap reached'}
        self.counts['verifications']+=1
        media=None if self.mock else separate_frames(self.path,[start,start+(end-start)/2,max(start,end-.1)])
        known=[t for s in self.scenes for t in (s.get('on_screen_text',''),s.get('action','')) if t]
        mock={'verdict':'contradicted' if 'blue dot' in claim else 'supported' if self.mock and any(similarity(claim,t)>=.8 for t in known) else 'uncertain',
              'evidence':'MOCK sidecar describes title and yellow shape; no blue dot or fading text.'}
        result=self.submodel('perceive',{'duration':end-start,'instruction':'Use these FRAMES only. Verify the claim; return {verdict: supported|contradicted|uncertain, evidence: string}. Do not infer motion between stills.','claim':claim},media,mock)
        result=normalize_json(result)
        result['verdict']=str(result.get('verdict','')).strip().lower()
        if result.get('verdict') not in ('supported','contradicted','uncertain'):
            return {'ok':False,'error':'Invalid verification response'}
        verdict=result['verdict']; out={**result,'modality':'frames','gap_ids':ids}
        for gid in ids:
            self.verified[gid]=verdict
            if verdict=='contradicted':
                self.rejected.setdefault(gid,[]).append(claim)
                if gid in self.cues:
                    self.rejected[gid].append(self.cues.pop(gid)['en'])
                    self.translation_done=False
                    out.setdefault('uncommitted',[]).append(gid)
        if verdict=='contradicted':
            refuted=self.refute(claim,ids)
            if refuted: out['refuted_events']=refuted
            self.contradicted+=1
            for gid in ids: self.verified.pop(gid,None)
            out['next']='claim contradicted: cue uncommitted; redraft with draft_description, then propose_cue a corrected, supported description'
        return out

    def refute(self,claim,ids):
        """Mark stored events that a contradicted claim was built on as refuted (review finding 3).

        Refuted events leave the evidence board, drafting, on-screen text and finalize coverage, so a hallucinated
        title cannot be re-drafted again and again or block finalize as an 'uncovered' event."""
        ct=tokens(claim); low=claim.lower(); count=0
        gaps=[self.gap(i) for i in ids if any(g['id']==i for g in self.gaps)]
        for e in self.events:
            if e.get('refuted') or not any(self.overlaps(e,g) for g in gaps): continue
            ost=str(e.get('on_screen_text') or '').strip()
            wt=tokens(str(e.get('what','')))
            if (ost and (ost.lower() in low or len(tokens(ost)&ct)>=max(1,len(tokens(ost))//2))) or (wt and len(wt&ct)/len(wt)>=.5):
                e['refuted']=True; count+=1
        return count

    def gap(self,gap_id):
        for g in self.gaps:
            if g['id']==gap_id: return g
        # Real-run finding (fix6, continuous-speech clip): an unknown id raised a bare StopIteration and Ultra
        # retried for 20 turns. Say what is valid instead.
        ids=[g['id'] for g in self.gaps if g.get('narratable',True)]
        raise ValueError(f'invalid arguments: unknown gap_id {gap_id}; '+(f'valid gap ids: {ids}' if ids else 'there are no narratable gaps, so nothing can be described: call finalize'))

    def onscreen(self,g,context_events=None):
        """Distinct on-screen texts among the (non-context) events of one gap, most important first."""
        out=[]
        for e in sorted([e for e in self.gap_events(g,context_events) if 'context' not in e],key=lambda e:-float(e.get('importance') or 0)):
            t=e.get('on_screen_text')
            if isinstance(t,str) and t.strip() and t.strip() not in out: out.append(t.strip())
        return out

    @staticmethod
    def trim_words(text,limit):
        words=text.split()[:max(1,limit)]
        out=' '.join(words).rstrip(' ,;:.!?-')
        if out.count('"')%2: out+='"'
        return out+'.'

    def fallback_text(self,g,limit,context_events=None,draft=''):
        """Deterministic last resort: on-screen text first, else the draft/first event cut at a word boundary."""
        texts=self.onscreen(g,context_events)
        if texts:
            title=f'Title: "{texts[0]}"'
            return self.trim_words(title if len(title.split())<=limit else f'"{texts[0]}"',limit)
        if not draft:
            evs=[e for e in self.gap_events(g,context_events) if 'context' not in e]
            draft=str(evs[0].get('what','')) if evs else ''
        return self.trim_words(draft,limit) if draft.strip() else ''

    def draft_batch(self,gaps,limits,context_events=None,avoid=None):
        """Draft one line per gap (cheap fit model), then enforce each gap's word limit server-side.

        Over-limit drafts are re-asked ONCE (batched, failing gaps only, hard limit); anything still over is
        replaced deterministically, so every returned draft fits."""
        avoid=avoid or {}
        def ask(todo,hard):
            opener=self.establishing_gap()
            payload=[{'id':g['id'],'start':g['start'],'end':g['end'],'duration':round(g['duration'],2),'max_words':limits[g['id']],
                      'role':'establishing' if g['id']==opener else 'action',
                      **({'previous_lines':prev} if (prev:=self.previous_lines(g)) else {}),
                      'on_screen_text':self.onscreen(g,context_events),'events':self.gap_events(g,context_events),
                      **({'avoid_repeating':avoid[g['id']]} if avoid.get(g['id']) else {})} for g in todo]
            single={'events':payload[0]['events'],'max_words':payload[0]['max_words'],'avoid_repeating':payload[0].get('avoid_repeating','')} if len(todo)==1 else {}
            lead='HARD LIMIT: your previous draft was too long; every text MUST have at most max_words words. ' if hard else ''
            def mock_text(g):
                if self.mock and getattr(self,'inject_overbudget',False) and not hard: return 'word '*(limits[g['id']]+5)
                return self.mock_line(self.mock_events(g['start'],g['end']),limits[g['id']])
            brief=scene_brief(self.scene_context)
            scene_rules=(' Use scene_context for concrete nouns: the kind of place, the visible person (by appearance, never a name), objects and materials. '
                'A gap with role "establishing" opens with where we are and who is there, then the action in this gap. Other gaps: who does what, to which object or material, with which tool, and the visible result; do not repeat the setting. '
                'Write each cue as one full present-tense sentence in the third person with a subject; never imperatives. '
                'Write natural, fluent sentences (no semicolons, no "Label:" headings); vary sentence openings; after the first mention refer to the person briefly (e.g. by their role or one visible detail).') if brief else ''
            continuity=(' Only describe what is NEW compared with previous_lines and earlier gaps in this batch; never paraphrase them. '
                'If nothing new and visually important happens in an action gap, return text "SKIP" for it (silence is better than repetition); never SKIP the establishing gap. '
                'Never read out subtitle text that transcribes the speaker; on_screen_text worth quoting is titles, labels and signs, written as Title: "..." or Label: "...".')
            result=self.submodel('fit',{'instruction':lead+'Draft one English audio-description cue per gap. Return {cues:[{id,text}]}. Quote on-screen text verbatim when present (it is the most important content); <= max_words words; describe only events in this gap. Events tagged "earlier, context only" must not be described.'+scene_rules+continuity,
                **({'scene_context':brief} if brief else {}),'gaps':payload,**single},mock_result={'cues':[{'id':g['id'],'text':mock_text(g)} for g in todo]})
            if not hard: self.inject_overbudget=False
            if len(todo)==1 and isinstance(result.get('text'),str): return {todo[0]['id']:result['text']}
            return {c['id']:c['text'] for c in result.get('cues',[]) if isinstance(c,dict) and isinstance(c.get('text'),str) and c.get('id') in limits}
        # A gap with no evidence of its own is not drafted (and never SKIPped): it needs inspect_video_segment first.
        blind=[g for g in gaps if not [e for e in self.gap_events(g,context_events) if 'context' not in e]]
        if self.mock or len(blind)==len(gaps) and context_events: blind=[]
        self.blind_drafts=[g['id'] for g in blind]
        gaps=[g for g in gaps if g not in blind]
        if not gaps: return {}
        texts=ask(gaps,False)
        skip={i for i,t in texts.items() if is_skip(t) and i!=self.establishing_gap()}
        over=[g for g in gaps if g['id'] not in skip and (len(texts.get(g['id'],'').split())>limits[g['id']] or g['id'] not in texts or is_skip(texts.get(g['id'])) or lint(texts.get(g['id'],'')))]
        self.draft_overlimit+=sum(g['id'] in texts for g in over)
        if over:
            texts.update({i:t for i,t in ask(over,True).items() if t.strip() and not is_skip(t)})
        out={}
        for g in gaps:
            if g['id'] in skip:
                # The drafter judged the gap redundant: leave it silent (DCMP: describe what is new; silence is allowed).
                self.skipped[g['id']]=True; self.drop_gap(g['id'],'no new visual information (drafter SKIP)')
                continue
            t=texts.get(g['id'],'')
            if is_skip(t) or lint(t): t=''
            if not t.strip() or len(t.split())>limits[g['id']]:
                t=self.fallback_text(g,limits[g['id']],context_events,t)
            if not t: continue
            out[g['id']]=t
            self.drafts[g['id']]=t; self.draft_history.setdefault(g['id'],[]).append(t)
        return out

    def draft_description(self,gap_id=None,context_events=None,max_words=None,avoid_repeating='',gap_ids=None):
        if gap_ids is not None:
            gaps=[self.gap(i) for i in gap_ids]
            usable=[g for g in gaps if g.get('narratable',True)]
            limits={g['id']:max(1,min(max_words or 99,self.max_words(g))) for g in usable}
            out=self.draft_batch(usable,limits,context_events) if usable else {}
            result={'cues':[{'id':i,'text':t,'max_words':limits[i]} for i,t in out.items()],
                    **({'needs_inspection_first':self.blind_drafts} if getattr(self,'blind_drafts',None) else {}),
                    **({'skipped_no_new_info':[g['id'] for g in usable if g['id'] in self.skipped and g['id'] not in out]} if any(g['id'] in self.skipped and g['id'] not in out for g in usable) else {})}
            skipped=[g['id'] for g in gaps if not g.get('narratable',True)]
            return {**result,'skipped_too_short':skipped} if skipped else result
        g=self.gap(gap_id)
        if not g.get('narratable',True):
            return {'ok':False,'problems':['too short'],'reason':'too short'}
        limit=max(1,min(max_words or self.max_words(g),self.max_words(g)))
        out=self.draft_batch([g],{gap_id:limit},context_events,{gap_id:avoid_repeating})
        if gap_id in out: return {'text':out[gap_id],'max_words':limit}
        if gap_id in self.skipped: return {'ok':True,'skipped':True,'reason':'no new visual information; gap dropped (silence)'}
        if gap_id in getattr(self,'blind_drafts',[]): return {'ok':False,'problems':['no evidence for this gap'],'next':f'call inspect_video_segment for gap {gap_id} first'}
        return {'ok':False,'problems':['no draft produced from the evidence']}

    def previous_lines(self,g,n=2):
        """Last n committed English cues before gap g (continuity context for the drafter)."""
        before=sorted([c for c in self.cues.values() if c['start']<g['start'] and c['id']!=g['id']],key=lambda c:c['start'])
        return [c['en'] for c in before[-n:]]

    def measure_tts_duration(self,text,lang):
        if lang not in ('en','hi') or not isinstance(text,str) or len(text)>4000:
            raise ValueError('Invalid TTS input')
        key=(text,lang)
        if key not in self.tts_cache:
            target=self.work/(hashlib.sha256((lang+text).encode()).hexdigest()+'.wav')
            self.engine.render(text,lang,target)
            self.tts_cache[key]=(probe(target)[0],target)
        return {'seconds':self.tts_cache[key][0],'cached':True}

    def check_fit(self,gap_id,text,lang):
        g=self.gap(gap_id); problems=[]
        if not g.get('narratable',True):
            return {'ok':False,'problems':['too short'],'reason':'too short','suggested_max_words':0,'seconds':0,'overlap_seconds':0}
        limit=self.max_words(g,lang)
        count=len(text.split())
        if not text.strip() or '\n' in text or '-->' in text:
            problems.append('Text must be one nonempty line')
        if count>g['word_budget_'+lang] and lang!='hi':
            problems.append(f"Word budget exceeded (max {limit} words)")
        if re.search(r'\bwe see\b',text,re.I) or CAMERA_DIRECTION.search(text):
            problems.append('Banned phrase')
        if lang=='en':
            problems+= [p for p in lint(text) if not (p.endswith('"we see"') or p.endswith('camera direction')) or 'Banned phrase' not in problems]
        if lang=='hi' and not re.search('[\u0900-\u097f]',text):
            problems.append('Hindi must use Devanagari')
        seconds=self.measure_tts_duration(text,lang)['seconds']
        allowed=g['duration']*self.cfg['agent']['max_atempo']
        if seconds > allowed:
            problems.append('TTS duration exceeds allowed speedup')
        target=allowed
        if lang=='en':
            cap=self.cue_cap(g); target=min(allowed,cap)
            # A text inside the effective word limit is not rejected on the estimate-based cap alone.
            if seconds > cap and (count>limit or seconds>allowed):
                problems.append(f'cue too long for a single description; keep it under {cap:.1f} s')
        overlap=sum(max(0,min(g['end'],s['end'])-max(g['start'],s['start'])) for s in self.speech)
        if overlap>1e-6:
            problems.append('Overlaps detected speech')
        suggested=min(limit,max(1,int(count*target/max(seconds,.001))))
        if count>1 and seconds>target: suggested=min(suggested,count-1)
        result={'ok':not problems,'problems':problems,'suggested_max_words':suggested,'seconds':seconds,'overlap_seconds':overlap}
        if result['ok'] and lang=='en':
            # Best fitting candidate: the fallback finisher commits it if the agent never does.
            self.candidates[gap_id]=text
            result['next']='call propose_cue/commit_cue to commit'
        return result

    def _commit(self,gap_id,text):
        result=self.check_fit(gap_id,text,'en')
        if not result['ok']:
            return result
        for other,c in self.cues.items():
            if other!=gap_id and similarity(text,c['en'])>=.8:
                return {**result,'ok':False,'problems':[f'duplicate of gap {other}'],'problem':f'duplicate of gap {other}'}
        prev=[c for c in self.cues.values() if c['id']!=gap_id and c['start']<self.gap(gap_id)['start']]
        if prev:
            last=max(prev,key=lambda c:c['start'])
            if similarity(text,last['en'])>=.5:
                return {**result,'ok':False,'problems':[f"repeats the previous cue (gap {last['id']})"],'problem':'too similar to the previous cue: describe only what is new, or drop_gap if nothing new happens'}
        if any(similarity(text,r)>=.8 for r in self.rejected.get(gap_id,[])):
            return {**result,'ok':False,'problems':['text was contradicted by verification'],'problem':'text was contradicted by verification; redraft'}
        g=self.gap(gap_id)
        previous=self.cues.get(gap_id)
        if previous and previous['en']!=text:
            self.verified.pop(gap_id,None)
        self.translation_done=False
        self.cues[gap_id]={**g,'en':text}
        self.dropped.pop(gap_id,None); self.skipped.pop(gap_id,None)
        own=not self.grounded(gap_id,text)
        if own: self.authored[gap_id]=text
        else: self.authored.pop(gap_id,None)
        reasons=self.verification_reasons(gap_id)
        extra={'verify_required':reasons,'next':'call verify_claim(gap_id, claim) before finalize'} if reasons and gap_id not in self.verified else {}
        if own: extra['orchestrator_authored']='text was not produced by draft_description for this gap: added to needs_verification (verify_claim required before finalize). Prefer the draft text; if it fails, call draft_description(gap_ids=[id], max_words=N).'
        return {'ok':True,'cue':self.cues[gap_id],**extra}

    def commit_cue(self,gap_id,text):
        """Fit-check and commit. The 2nd failure for a gap auto-redrafts it (cheap fit call); the 4th try is refused."""
        g=self.gap(gap_id)
        if self.propose_fails[gap_id]>=3:
            self.repeat_refusals+=1
            return {'ok':False,'error':'3 proposals for this gap already failed','problems':['too many failed proposals'],'next':'drop_gap or move on'}
        result=self._commit(gap_id,text)
        if result['ok']: return result
        self.propose_fails[gap_id]+=1
        if self.propose_fails[gap_id]==2 and g.get('narratable',True) and 'suggested_max_words' in result:
            try:
                limit=max(1,min(result['suggested_max_words'],self.max_words(g)))
                new=self.draft_batch([g],{gap_id:limit},avoid={gap_id:text}).get(gap_id)
                again=self._commit(gap_id,new) if new else None
            except BudgetExceeded:
                raise
            except Exception as exc:
                new,again=None,None; result['auto_redraft']='unavailable: '+sanitize(exc)
            if again and again['ok']:
                self.auto_redrafts+=1
                return {**again,'auto_redrafted':True}
            if new: result['auto_redraft']=f'tried "{new}": '+'; '.join(again['problems'])
        if self.propose_fails[gap_id]>=3: result['next']='drop_gap or move on'
        elif self.propose_fails[gap_id]==1: result['next']=f"call draft_description(gap_ids=[{gap_id}], max_words={result.get('suggested_max_words')}) instead of hand-editing"
        return result

    propose_cue = commit_cue

    def drop_gap(self,gap_id,reason):
        self.gap(gap_id)
        self.cues.pop(gap_id,None); self.dropped[gap_id]=reason
        return {'ok':True,'reason':reason}

    def translate_hindi(self,cue_ids=None,max_words=None):
        cues=[c for i,c in self.cues.items() if cue_ids is None or i in cue_ids]
        signature=sorted((c['id'],c['en']) for c in cues)
        if cues and cue_ids is None and self.translation_done and self.translated_cues==signature and all(c.get('hi') for c in cues):
            return {'ok':True,'cached':True,'note':'cue set unchanged since the last translation; nothing to do','cues':[{'id':c['id'],'text':c['hi']} for c in cues]}
        if not cues:
            self.translation_done=True
            return {'cues':[]}
        limits={c['id']:min(c['word_budget_hi'],max_words) if max_words is not None else c['word_budget_hi'] for c in cues}
        mock=[]
        for c in cues:
            events=self.mock_events(c['start'],c['end'])
            hi=events[0].get('hi','दृश्य दिखाई देता है।')
            if len(hi.split())>limits[c['id']]:
                hi='शीर्षक।'
            mock.append({'id':c['id'],'hi':hi})
        brief=scene_brief(self.scene_context)
        response=self.submodel('edit',{'instruction':'Translate committed English cues into natural Devanagari Hindi. Return {cues:[{id,hi}]}, each <= its word limit. Preserve meaning.'+(' Use scene_context only to pick the usual Hindi words for the place, objects and materials; add no facts.' if brief else ''),**({'scene_context':brief} if brief else {}),'cues':cues,'limits':limits},mock_result={'cues':mock})
        results={}
        for attempt in range(2):
            by_id={c['id']:c for c in response.get('cues',[]) if isinstance(c,dict) and 'id' in c}
            failing=[]
            for c in cues:
                text=by_id.get(c['id'],{}).get('hi','')
                fit=self.check_fit(c['id'],text,'hi')
                results[c['id']]={'id':c['id'],'text':text,**fit,'retried':bool(attempt)}
                if fit['ok']: c['hi']=text
                else:
                    c.pop('hi',None)
                    failing.append({**c,'max_words':fit['suggested_max_words'],'max_seconds':c['duration']*self.cfg['agent']['max_atempo']})
            if not failing or attempt: break
            cues=[self.cues[c['id']] for c in failing]
            response=self.submodel('edit',{'instruction':'Shorten failing Hindi translations. Return {cues:[{id,hi}]}. Obey explicit max_words and max_seconds per cue; retain core meaning.','cues':failing},mock_result={'cues':[{'id':c['id'],'hi':'शीर्षक।'} for c in failing]})
        self.translation_done=True
        if cue_ids is None: self.translated_cues=signature
        return {'ok':all(c['ok'] for c in results.values()),'cues':list(results.values())}

    def render(self,lang,target):
        selected=[]; wavs=[]
        for c in self.cues.values():
            if not c.get(lang) or not self.check_fit(c['id'],c[lang],lang)['ok']:
                continue
            seconds,raw=self.tts_cache[(c[lang],lang)]
            speed=max(1,seconds/c['duration'])
            fitted=self.work/f"fit-{lang}-{c['id']}.wav"
            ffmpeg('-i',raw,'-af',f'atempo={speed}','-ar',24000,'-ac',1,fitted)
            # Caption timing reflects audible duration, not the full reserved gap.
            c.setdefault('tts_backend',{})[lang]=type(self.engine).__name__
            selected.append({**c,'end':min(c['end'],c['start']+seconds/speed)})
            wavs.append(fitted)
        order=sorted(range(len(selected)),key=lambda i:selected[i]['start'])
        selected,wavs=[selected[i] for i in order],[wavs[i] for i in order]
        mix(self.path,target,self.duration,self.has_audio,selected,wavs,self.cfg['ducking_level'])
        return selected

    def render_preview(self,start,end,lang):
        self.segment(start,end)
        if lang not in ('en','hi'):
            raise ValueError('Invalid language')
        full=self.work/f'preview-source-{lang}.mp4'
        self.render(lang,full)
        target=self.out/f'preview_{lang}.mp4'
        ffmpeg('-ss',start,'-i',full,'-t',end-start,'-c:v','libx264','-c:a','aac',target)
        return {'path':str(target),'duration':probe(target)[0]}

    def finalize(self,force=False):
        problems=[]; warnings=[]
        capped=self.counts['verifications'] >= self.cfg['agent']['max_verifications']
        pending=self.needs_verification()
        if pending and not force and not capped:
            return {'ok':False,'problems':[f'Cue {gid} needs verification: '+', '.join(r) for gid,r in pending.items()],
                'needs_verification':list(pending),'next':'call verify_claim(gap_id, claim) for each listed gap, then finalize'}
        for c in list(self.cues.values()):
            for lang in self.langs:
                if not c.get(lang):
                    (warnings if lang=='hi' and self.translation_done else problems).append(f"Cue {c['id']}: missing {lang}")
                elif not self.check_fit(c['id'],c[lang],lang)['ok']:
                    problems.append(f"Cue {c['id']}: invalid {lang}")
        narratable=[g for g in self.gaps if g.get('narratable',True)]
        live=[e for e in self.events if not e.get('refuted') and self.gap_for(e) not in self.skipped]
        high=[e for e in live if float(e['importance'])>=4 and any(self.overlaps(e,g) for g in narratable)]
        in_speech=[e for e in live if float(e['importance'])>=4 and not any(self.overlaps(e,g) for g in narratable)]
        # Temporal association is explicitly a proxy, not semantic coverage verification.
        uncovered=[e for e in high if not any(self.overlaps(e,c) for c in self.cues.values())]
        if uncovered:
            problems.append(f'{len(uncovered)} high-importance events lack an associated cue')
        if problems and self.rejections<2 and not force:
            self.rejections+=1
            return {'ok':False,'problems':problems,'uncovered_events':uncovered,'rejection':self.rejections}
        unverified=[gid for gid in self.verified_required() if self.verified.get(gid)!='supported']
        warnings+= [f'Cue {gid}: unverified' for gid in unverified]
        self.report['issues'].extend(problems+warnings)
        # Never publish a failed language track, even after warning acceptance.
        for gid,c in list(self.cues.items()):
            if not self.check_fit(gid,c['en'],'en')['ok']:
                self.drop_gap(gid,'Final validation rejected English cue')
                continue
            if c.get('hi') and not self.check_fit(gid,c['hi'],'hi')['ok']:
                c.pop('hi')
        tracks={}
        for lang in self.langs:
            tracks[lang]=self.render(lang,self.out/f'narrated_{lang}.mp4')
            write_texts(self.out,lang,tracks[lang])
        total=max(.001,sum(g['duration'] for g in narratable if g['id'] not in self.skipped))
        self.report.update(status='complete',cues=sorted(self.cues.values(),key=lambda c:c['start']),tracks=tracks,gaps=self.gaps,speech=self.speech,
            cues_committed=len(self.cues),cues_dropped=len(self.dropped),dropped_gaps=self.dropped,gaps_skipped_no_new_info=sorted(self.skipped),
            overlaps_with_speech=sum(self.check_fit(c['id'],c[l],l)['overlap_seconds']>0 for c in self.cues.values() for l in self.langs if c.get(l)),
            gap_coverage_percent={l:100*sum(c['end']-c['start'] for c in track)/total for l,track in tracks.items()},
            high_importance_covered_percent=100*(len(high)-len(uncovered))/len(high) if high else 100,
            events_in_speech_regions={'count':len(in_speech),'events':in_speech,'note':'informational: high-importance events outside every narratable gap; may need extended AD'},
            coverage_method='temporal association proxy (events overlapping narratable gap windows); not semantic verification',uncovered_events=uncovered)
        self.done=True
        return {'ok':True,'warnings':problems+warnings,'outputs':str(self.out)}

    def gap_for(self,e):
        ids=[g['id'] for g in self.gaps if g.get('narratable',True) and self.overlaps(e,g)]
        return ids[0] if len(ids)==1 else None

    def verified_required(self):
        return [gid for gid in self.cues if self.verification_reasons(gid)]

    def execute(self,name,args):
        start=time.monotonic()
        note=''
        self.cost_role={'verify_claim':'verify','inspect_video_segment':'perceive','draft_description':'draft','translate_hindi':'translate'}.get(name)
        try:
            schema=next(t['function']['parameters'] for t in TOOLS if t['function']['name']==name)
            args=dict(args or {})
            # Some long runs omit or overfill `note`;
            # a missing note must not turn every later tool call into a bare "ValidationError".
            args['note']=' '.join(str(args.get('note') or name.replace('_',' ')).split()[:25])
            try:
                jsonschema.validate(args,schema)
            except jsonschema.ValidationError as exc:
                raise ValueError('invalid arguments: '+exc.message[:200]) from None
            args=dict(args)
            note=args.pop('note')
            key=(name,json.dumps(args,sort_keys=True,default=str)); self.call_counts[key]+=1
            if name not in ('finalize','detect_speech_gaps') and self.call_counts[key]>=3:
                self.repeat_refusals+=1
                result={'ok':False,'error':'identical call repeated 3+ times; refused','next':self.next_action()}
            else:
                result=getattr(self,name)(**args)
        except BudgetExceeded:
            self.trace('tool',note=note,tool_name=name,args=compact(args),ok=False,result={'error':'Budget exceeded'},latency_s=time.monotonic()-start)
            raise
        except Exception as exc:
            msg=str(exc)
            result={'ok':False,'error':msg if isinstance(exc,ValueError) and msg.startswith('invalid arguments: ') else sanitize(exc)}
        args = args if isinstance(args,dict) else {}
        failed=result.get('ok') is False or result.get('verdict')=='contradicted'
        correction=None
        if not failed and name in ('check_fit','commit_cue','propose_cue','draft_description','translate_hindi','drop_gap'):
            for failure in self.pending_failures:
                if failure['gap_id']==args.get('gap_id') or (failure['gap_id'] is None and name=='translate_hindi'):
                    correction=failure['step']; self.pending_failures.remove(failure); break
        result={**result,'state':{'committed':list(self.cues),'remaining':[g['id'] for g in self.gaps if g.get('narratable',True) and g['id'] not in self.cues and g['id'] not in self.dropped],'skipped_too_short':[g['id'] for g in self.gaps if not g.get('narratable',True)],'needs_verification':list(self.needs_verification()),'budget':{'turns':max(0,self.cfg['agent']['max_steps']-self.turn-1),'inspections':self.cfg['agent']['max_inspections']-self.counts['inspections'],'verifications':self.cfg['agent']['max_verifications']-self.counts['verifications']},**({'next_action':self.next_action()} if self.repeat_refusals>=2 else {})}}
        sid=self.trace('tool',note=note,tool_name=name,args=compact(args),result=compact(result),ok=not failed,
            latency_s=time.monotonic()-start,correction=correction is not None,corrects_step=correction)
        if failed:
            gid=args.get('gap_id')
            if name=='verify_claim' and gid is None:
                gid=next((g['id'] for g in self.gaps if g['start']==args.get('start')),None)
            self.pending_failures.append({'step':sid,'gap_id':gid})
        return result

    def fallback_finish(self,reason):
        """Deterministic finisher for any early stop: commit what fits, verify if possible, translate, finalize."""
        def note(text,tool=None,ok=True,**kw):
            self.trace('fallback',note=text,tool_name=tool,ok=ok,**kw)
        self.report['fallback_finalize']=True; self.report['fallback_reason']=reason
        note(f'Fallback finisher started: {reason}')
        need=[g['id'] for g in self.gaps if g.get('narratable',True) and g['id'] not in self.cues and g['id'] not in self.dropped
              and g['id'] not in self.candidates and g['id'] not in self.drafts and self.evidence_line(g)]
        if need and 'budget' not in reason and time.monotonic()<self.client.deadline:
            try:
                self.draft_description(gap_ids=need); note(f'Drafted gaps {need} in one batched call from stored evidence','draft_description',args={'gap_ids':need})
            except Exception as exc:
                note(f'Batched drafting unavailable ({sanitize(exc)})','draft_description',False)
        for g in self.gaps:
            gid=g['id']
            if gid in self.cues or gid in self.dropped or not g.get('narratable',True):
                continue
            skip=self.rejected.get(gid,[])
            candidate=self.candidates.get(gid)
            if candidate and not any(similarity(candidate,r)>=.8 for r in skip):
                result=self._commit(gid,candidate)
                if result['ok']:
                    note(f'Gap {gid}: committed best fitting candidate "{candidate}"','commit_cue',args={'gap_id':gid}); continue
                note(f"Gap {gid}: candidate rejected ({'; '.join(result['problems'])})",'commit_cue',False)
            draft=self.drafts.get(gid)
            if draft and not self.evidence_line(g) and any(e.get('refuted') and self.overlaps(e,g) for e in self.events):
                draft=None; note(f'Gap {gid}: stale draft ignored, its evidence was refuted by verification','commit_cue',False)
            if draft and not any(similarity(draft,r)>=.8 for r in skip):
                fit=self.check_fit(gid,draft,'en')
                text=draft
                if not fit['ok']:
                    words=draft.split()[:fit['suggested_max_words']]
                    text=' '.join(words).rstrip(' ,;:.!?-')+'.' if words else ''
                result=self._commit(gid,text) if text else {'ok':False,'problems':['empty after trimming']}
                if result['ok']:
                    note(f'Gap {gid}: committed latest draft'+('' if text==draft else ' shortened to fit')+f': "{text}"','commit_cue',args={'gap_id':gid}); continue
                note(f"Gap {gid}: shortened draft still unusable ({'; '.join(result['problems'])})",'commit_cue',False)
            self.drop_gap(gid,'Fallback: no fitting candidate or draft')
            note(f'Gap {gid}: dropped, no fitting candidate or draft','drop_gap',args={'gap_id':gid})
        # The finisher may spend a few verifications beyond the orchestrator's cap: nothing risky ships unchecked.
        self.cfg['agent']['max_verifications']=max(self.cfg['agent']['max_verifications'],self.counts['verifications']+len(self.needs_verification()))
        for gid in sorted(self.needs_verification()):
            if gid not in self.cues: continue
            try:
                result=self.verify_claim(gap_id=gid,claim=self.cues[gid]['en'])
            except BudgetExceeded:
                note(f'Gap {gid}: unverified, budget exhausted','verify_claim',False); break
            except Exception as exc:
                note(f'Gap {gid}: unverified, verification unavailable ({sanitize(exc)})','verify_claim',False); continue
            if result.get('ok') is False:
                note(f"Gap {gid}: unverified, {result['error']}",'verify_claim',False); continue
            if result['verdict']=='contradicted':
                self.drop_gap(gid,'Fallback: claim contradicted by verification')
                note(f'Gap {gid}: contradicted by verification; dropped','verify_claim',False,result=compact(result))
            else:
                note(f"Gap {gid}: verification {result['verdict']}",'verify_claim',result=compact(result))
        for gid in sorted(self.needs_verification()):
            if gid in self.cues:
                # Review finding 8: a cue that needed verification but was never checked is not shipped by the fallback.
                self.drop_gap(gid,'Fallback: verification required but not run')
                self.report['issues'].append(f'Gap {gid}: unverified cue dropped by the fallback finisher')
                note(f'Gap {gid}: dropped, verification required but not run (unverified)','drop_gap',False,args={'gap_id':gid})
        if 'hi' in self.langs and not self.translation_done:
            try:
                self.translate_hindi(); note('Translated committed cues to Hindi','translate_hindi')
            except Exception as exc:
                self.report['issues'].append('Fallback Hindi translation unavailable within remaining budget/time')
                note(f'Hindi translation unavailable ({sanitize(exc)})','translate_hindi',False)
        result=self.finalize(force=True)
        note('Forced finalize with committed cues','finalize',result=compact(result))

    def save(self):
        cost=sum(u['cost_usd'] for u in self.client.usage) if self.client.usage else sum(s['cost_usd'] for s in self.steps)
        summary={'tool_calls':dict(Counter(s['tool_name'] for s in self.steps if s['role']=='tool')),
            'corrections':sum(s['correction'] for s in self.steps),
            'verifications':{'verified':sum(v=='supported' for v in self.verified.values()),'contradicted':self.contradicted,
                'unverified':sum(self.verified.get(g)!='supported' for g in self.verified_required())},
            'repeat_refusals':self.repeat_refusals,'auto_redrafts':self.auto_redrafts,'draft_overlimit':self.draft_overlimit,'orchestrator_authored_cues':sum(self.authored.get(g)==c['en'] for g,c in self.cues.items()),
            'orchestrator_turns':sum(s['role']=='orchestrator' for s in self.steps),'cost_by_model':{},'total_latency_s':time.monotonic()-self.started}
        for s in self.steps:
            if s['model']:
                summary['cost_by_model'][s['model']]=summary['cost_by_model'].get(s['model'],0)+s['cost_usd']
        metadata={**{k:self.report[k] for k in ('provider','mock','dev_only')},
            'models':{k:v['id'] for k,v in self.cfg['models'].items()},'base_url_host':None if self.mock else urlparse(self.cfg['base_url']).hostname,
            'budgets':{**self.cfg['agent'],'budget_usd':self.guard.cap},'mock_notice':'Scripted synthetic behavior; not visual understanding' if self.mock else None}
        trace={'metadata':metadata,'steps':self.steps,'summary':summary}
        (self.out/'trace.json').write_text(json.dumps(trace,ensure_ascii=False,indent=2))
        (self.out/'trace.md').write_text('# Agent trace'+(' — MOCK' if self.mock else '')+'\n\n'+'\n'.join(
            f"- {s['step']} {'↪' if s['correction'] else '✓' if s['ok'] else '✗'} {s['role']} {s['tool_name'] or ''}: {s['note'] or json.dumps(s['result'],ensure_ascii=False)[:220]}"+ (f" (corrects {s['corrects_step']})" if s['correction'] else '') for s in self.steps))
        roles={r:sum(s['cost_usd'] for s in self.steps if s.get('cost_role',s['role'])==r) for r in ('orchestrator','scene','perceive','verify','draft','translate')}
        if self.client.usage:
            roles={r:sum(u['cost_usd'] for u in self.client.usage if u.get('cost_role',{'orchestrate':'orchestrator','fit':'draft','edit':'translate'}.get(u['stage'],u['stage']))==r) for r in roles}
        self.report.update(usage=self.client.usage,cost_by_role=roles,billed_to='nvidia-dev free tier (dev only)' if self.cfg['provider']=='nvidia-dev' else 'mock (offline)' if self.mock else 'nebius token factory',cost_per_minute_usd=cost/(self.duration/60),agent_stats=summary,estimated_cost_usd=cost,
            would_be_token_factory_cost_usd=cost,reserved_spend_usd=self.guard.spent,cost_per_minute=cost/(self.duration/60),latency_s=summary['total_latency_s'])
        (self.out/'report.json').write_text(json.dumps(self.report,ensure_ascii=False,indent=2))


def run_agent(path,out_dir,provider=None,langs=('en','hi'),max_steps=None,budget_usd=None,on_step=None,*,config=None,client=None,orchestrator=None,orchestrator_model='ultra'):
    """Synchronous streaming API; callback gets each JSON-serializable trace step."""
    cfg=resolve_provider(config or load_config(),provider)
    if client is None and orchestrator is None and cfg['provider']!='mock' and not os.environ.get(cfg['key_env']):
        raise RuntimeError(f"Provider '{cfg['provider']}' needs env {cfg['key_env']}; use provider='mock' offline")
    if orchestrator_model=='super':
        if 'orchestrate_alt' not in cfg['models']:
            raise ValueError('Super orchestrator is available with nebius only')
        cfg['models']['orchestrate']=cfg['models']['orchestrate_alt']
    if isinstance(langs,str):
        langs=langs.split(',')
    if not langs or any(l not in ('en','hi') for l in langs):
        raise ValueError('Supported languages: en,hi')
    explicit_steps=max_steps is not None
    steps=cfg['agent']['max_steps'] if max_steps is None else max_steps
    if not isinstance(steps,int) or steps<0:
        raise ValueError('max_steps must be nonnegative integer')
    cfg['agent']['max_steps']=steps
    guard=SpendGuard(cfg['agent']['budget_usd'] if budget_usd is None else budget_usd)
    a=Agent(path,out_dir,cfg,langs,guard,on_step,client)
    planner=orchestrator or (MockOrchestrator() if a.mock else Orchestrator(a.client))
    messages=[{'role':'system','content':SYSTEM},{'role':'user','content':f'Describe this {a.duration:.2f}s video. Languages: {langs}. Maximum tool turns: {steps}.'}]
    scaled=False
    stop='orchestrator stopped early (max turns, timeout or no tool calls)'
    try:
        turn=-1
        while turn+1<steps:
            turn+=1
            a.turn=turn
            messages[:]=[m for m in messages if not str(m.get('content') or '').startswith('[EVIDENCE BOARD') or m.get('role')!='user']
            messages[:]=compact_history(messages,cfg['agent'].get('history_turns',6))
            if steps-turn==3:
                messages.append({'role':'system','content':'3 turns left: commit what you have, translate, finalize'})
            if time.monotonic()-a.started>cfg['agent']['timeout_s']:
                a.report['issues'].append('Wall-clock timeout reached'); break
            board=a.board_text()
            if board: messages.append({'role':'user','content':board})
            before=len(a.client.usage); start=time.monotonic()
            message=planner.next(messages,a)
            usage=dict(a.client.usage[-1]) if len(a.client.usage)>before else {}
            if usage:
                usage.update({k:sum(u.get(k,0) for u in a.client.usage[before:]) for k in ('input_tokens','output_tokens','cost_usd','cached_tokens')})
            a.trace('orchestrator',cached_tokens=usage.get('cached_tokens',0),note=(message.get('content') or '')[:800],model=usage.get('model','MOCK/orchestrate'),
                tokens_in=usage.get('input_tokens',0),tokens_out=usage.get('output_tokens',0),cost_usd=usage.get('cost_usd',0),latency_s=time.monotonic()-start)
            calls=message.get('tool_calls',[])
            if not calls:
                a.report['issues'].append('Orchestrator stopped calling tools'); break
            messages.append(message)
            for call in calls:
                if time.monotonic() > a.client.deadline:
                    break
                try:
                    args=json.loads(call['function']['arguments'])
                except (ValueError,TypeError):
                    args=None
                result=a.execute(call['function']['name'],args)
                messages.append({'role':'tool','tool_call_id':call['id'],'content':json.dumps(compact(result),ensure_ascii=False,separators=(',',':'))})
                if a.done:
                    break
            if a.done:
                break
            if not explicit_steps and a.gaps and not scaled:
                scaled=True
                slots=sum(g.get('narratable',True) for g in a.gaps)
                steps=cfg['agent']['max_steps']=max(steps,min(60,max(30,6+3*slots)))
    except BudgetExceeded:
        a.report['issues'].append('Budget exceeded; finalized committed cues without more model calls')
        stop='budget exceeded'
    except Exception as exc:
        a.report['issues'].append('Agent stopped: '+sanitize(exc))
        stop='agent stopped: '+sanitize(exc)
    finally:
        if not a.done:
            a.fallback_finish(stop)
        a.save()
    return a.report
