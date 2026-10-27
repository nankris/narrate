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
from ..media import probe, ffmpeg, word_budget, write_texts
from ..perception import data_url, separate_frames
from ..tts import backend, mix
from .models import SYSTEM, Orchestrator, MockOrchestrator
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
        self.client.retry_attempts = cfg['agent'].get('retry_attempts',3)
        self.client.on_retry = lambda note: self.trace('system',note=note,ok=False)
        self.steps = []; self.turn=0; self.rejections=0; self.done=False
        self.report = {'mock':self.mock,'provider':cfg['provider'],'dev_only':cfg['provider']=='nvidia-dev',
            'duration_s':self.duration,'fallback_finalize':False,'issues':[]}
        self.scenes = []
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

    def submodel(self,stage,data,media=None,mock_result=None):
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
                result = self.client.call(stage,{**data, '_system': 'You are a precise audio description assistant. Follow the requested JSON schema. Describe only supported visible facts. '+data.get('instruction','')},media)
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

    def detect_speech_gaps(self):
        if self.counts['gap_detection']:
            return {'cached':True,'reminder':'Use the gaps from the first detection.'}
        self.counts['gap_detection']+=1
        result = detect(self.path,self.duration,self.has_audio,self.cfg)
        cfg_min_gap = self.cfg['agent'].get('min_gap_s',1.5)
        self.speech=result['speech']; self.gaps=[]
        for i,g in enumerate(result['gaps']):
            start,end = g['start']+.08,g['end']-.08
            narratable = end-start >= cfg_min_gap
            self.gaps.append({'id':i,'start':start,'end':end,'duration':end-start,'narratable':narratable,
                **({} if narratable else {'reason':'too short'}),
                **{'word_budget_'+lang:word_budget(end-start,self.cfg['words_per_second'][lang],self.cfg['word_margin']) for lang in ('en','hi')}})
        self.report.update(detector=result['detector'],speech_ratio=result['speech_ratio'],detector_fallback_reason=result['fallback_reason'])
        if self.gaps and not any(g['narratable'] for g in self.gaps):
            self.report['issues'].append('Every speech-free gap is shorter than agent.min_gap_s; extended AD is needed.')
        if not self.gaps:
            self.report['issues'].append('Cannot narrate safely without extended AD (pause-the-video): no usable speech-free gaps.')
        return {'gaps':[{k:g[k] for k in ('id','start','end','word_budget_en','word_budget_hi','narratable','reason') if k in g} for g in self.gaps], 'detector':result['detector'],'speech_ratio':result['speech_ratio']}

    def segment(self,start,end):
        if not all(math.isfinite(x) for x in (start,end)) or not 0 <= start < end <= self.duration:
            raise ValueError('Invalid segment bounds')

    @staticmethod
    def window(g):
        return g['start']-1.0,g['end']+.5

    def overlaps(self,e,g):
        w0,w1=self.window(g)
        return float(e['t_start'])<w1 and float(e['t_end'])>w0

    def gap_events(self,g,passed=None):
        """Evidence for one gap: events overlapping its window, plus at most 2 recent earlier ones (context only)."""
        w0,_=self.window(g)
        pool=[]
        for e in list(self.events)+list(passed or []):
            if isinstance(e,dict) and 't_start' in e and 't_end' in e and not any(e['t_start']==x['t_start'] and e['t_end']==x['t_end'] and e.get('what')==x.get('what') for x in pool):
                pool.append(e)
        inside=[e for e in pool if self.overlaps(e,g)]
        # Only recent predecessors (<=10s) are useful context; anything else risks narrating the wrong moment.
        earlier=sorted([e for e in pool if float(e['t_end'])<=w0 and w0-float(e['t_end'])<=10],key=lambda e:float(e['t_end']))[-2:]
        return [{**e,'context':'earlier, context only'} for e in earlier]+inside

    def inspect_video_segment(self,start,end,focus=''):
        self.segment(start,end)
        key=(start,end,focus)
        for (s,e,_),cached in self.cache.items():
            if max(0,min(end,e)-max(start,s))/(end-start)>=.7:
                return {**cached,'cached':True,'reminder':'Already inspected >=70% of this range; use cached evidence.'}
        if self.counts['inspections'] >= self.cfg['agent']['max_inspections']:
            return {'ok':False,'error':'Inspection cap reached'}
        self.counts['inspections']+=1
        data={'duration':end-start,'instruction':'Inspect this segment. Return events with absolute video t_start/t_end (seconds), what, on_screen_text, importance 1-5, confidence 0-1. Segment starts at '+str(start),'focus':focus}
        media=None; modality='mock'
        if not self.mock:
            clip=self.work/'inspection.mp4'
            ffmpeg('-ss',start,'-i',self.path,'-t',end-start,'-an','-vf','scale=640:360,fps=10','-c:v','libx264',clip)
            media=[{'type':'video_url','video_url':{'url':data_url(clip.read_bytes(),'video/mp4')}}]; modality='video'
        try:
            result=self.submodel('perceive',data,media,{'events':self.mock_events(start,end)})
            if not result.get('events'):
                raise ValueError('No events')
        except BudgetExceeded:
            raise
        except Exception:
            if self.mock:
                raise
            modality='frames-fallback'
            result=self.submodel('perceive',data,separate_frames(self.path,[start,start+(end-start)/2,max(start,end-.1)]))
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
                event={**event,'what':event.get('what',event.get('action',''))}
                if not isinstance(event['what'],str):
                    continue
                if event not in self.events:
                    self.events.append(event)
                valid.append(event)
            except (KeyError,ValueError,TypeError):
                continue
        result={'events':valid,'modality':modality,'time_base':base}
        self.cache[key]=result
        return result

    def verification_reasons(self,gap_id):
        """Why a committed English cue must be verified before finalize (empty = not required)."""
        c=self.cues[gap_id]; reasons=risky_text(c['en'])
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
            self.contradicted+=1
            for gid in ids: self.verified.pop(gid,None)
            out['next']='claim contradicted: cue uncommitted; redraft with draft_description, then propose_cue a corrected, supported description'
        return out

    def gap(self,gap_id):
        return next(g for g in self.gaps if g['id']==gap_id)

    def draft_description(self,gap_id=None,context_events=None,max_words=None,avoid_repeating='',gap_ids=None):
        if gap_ids is not None:
            gaps=[self.gap(i) for i in gap_ids]
            usable=[g for g in gaps if g.get('narratable',True)]
            result=self.submodel('fit',{'instruction':'Draft one English cue per gap, obey word_budget_en. Return {cues:[{id,text}]}. Use only the events listed under each gap; events tagged "earlier, context only" must not be described.', 'gaps':[{**g,'events':self.gap_events(g,context_events)} for g in usable]},mock_result={'cues':[{'id':g['id'],'text':self.mock_line(self.mock_events(g['start'],g['end']),g['word_budget_en'])} for g in usable]})
            for c in result.get('cues',[]):
                if isinstance(c,dict) and isinstance(c.get('text'),str) and c.get('id') in {g['id'] for g in usable}:
                    self.drafts[c['id']]=c['text']
            skipped=[g['id'] for g in gaps if not g.get('narratable',True)]
            return {**result,'skipped_too_short':skipped} if skipped else result
        g=self.gap(gap_id)
        if not g.get('narratable',True):
            return {'ok':False,'problems':['too short'],'reason':'too short'}
        limit=max(1,min(max_words or g['word_budget_en'],g['word_budget_en']))
        events=self.gap_events(g,context_events)
        mock_text=self.mock_line(self.mock_events(g['start'],g['end']),limit)
        if self.mock and getattr(self,'inject_overbudget',False):
            mock_text='word '*(g['word_budget_en']+5)
            self.inject_overbudget=False
        result=self.submodel('fit',{'instruction':'Write ONE English line of audio description <= max_words. Return {text: string}. Use supplied facts only; events tagged "earlier, context only" must not be described.','gap':g,'events':events,'max_words':limit,'avoid_repeating':avoid_repeating},mock_result={'text':mock_text})
        if isinstance(result.get('text'),str):
            self.drafts[gap_id]=result['text']
        return result

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
        budget=g['word_budget_'+lang]
        count=len(text.split())
        if not text.strip() or '\n' in text or '-->' in text:
            problems.append('Text must be one nonempty line')
        if count>budget and lang!='hi':
            problems.append('Word budget exceeded')
        if re.search(r'\b(we see|the camera)\b',text,re.I):
            problems.append('Banned phrase')
        if lang=='hi' and not re.search('[\u0900-\u097f]',text):
            problems.append('Hindi must use Devanagari')
        seconds=self.measure_tts_duration(text,lang)['seconds']
        if seconds > g['duration']*self.cfg['agent']['max_atempo']:
            problems.append('TTS duration exceeds allowed speedup')
        overlap=sum(max(0,min(g['end'],s['end'])-max(g['start'],s['start'])) for s in self.speech)
        if overlap>1e-6:
            problems.append('Overlaps detected speech')
        suggested=min(budget,max(1,int(count*g['duration']*self.cfg['agent']['max_atempo']/max(seconds,.001)) ))
        result={'ok':not problems,'problems':problems,'suggested_max_words':suggested,'seconds':seconds,'overlap_seconds':overlap}
        if result['ok'] and lang=='en':
            # Best fitting candidate: the fallback finisher commits it if the agent never does.
            self.candidates[gap_id]=text
            result['next']='call propose_cue/commit_cue to commit'
        return result

    def commit_cue(self,gap_id,text):
        result=self.check_fit(gap_id,text,'en')
        if not result['ok']:
            return result
        for other,c in self.cues.items():
            if other!=gap_id and similarity(text,c['en'])>=.8:
                return {**result,'ok':False,'problems':[f'duplicate of gap {other}'],'problem':f'duplicate of gap {other}'}
        if any(similarity(text,r)>=.8 for r in self.rejected.get(gap_id,[])):
            return {**result,'ok':False,'problems':['text was contradicted by verification'],'problem':'text was contradicted by verification; redraft'}
        g=self.gap(gap_id)
        previous=self.cues.get(gap_id)
        if previous and previous['en']!=text:
            self.verified.pop(gap_id,None)
        self.translation_done=False
        self.cues[gap_id]={**g,'en':text}
        self.dropped.pop(gap_id,None)
        reasons=self.verification_reasons(gap_id)
        extra={'verify_required':reasons,'next':'call verify_claim(gap_id, claim) before finalize'} if reasons and gap_id not in self.verified else {}
        return {'ok':True,'cue':self.cues[gap_id],**extra}

    propose_cue = commit_cue

    def drop_gap(self,gap_id,reason):
        self.gap(gap_id)
        self.cues.pop(gap_id,None); self.dropped[gap_id]=reason
        return {'ok':True,'reason':reason}

    def translate_hindi(self,cue_ids=None,max_words=None):
        cues=[c for i,c in self.cues.items() if cue_ids is None or i in cue_ids]
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
        response=self.submodel('edit',{'instruction':'Translate committed English cues into natural Devanagari Hindi. Return {cues:[{id,hi}]}, each <= its word limit. Preserve meaning.','cues':cues,'limits':limits},mock_result={'cues':mock})
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
        high=[e for e in self.events if e['importance']>=4 and any(self.overlaps(e,g) for g in narratable)]
        in_speech=[e for e in self.events if e['importance']>=4 and not any(self.overlaps(e,g) for g in narratable)]
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
        total=max(.001,sum(g['duration'] for g in narratable))
        self.report.update(status='complete',cues=sorted(self.cues.values(),key=lambda c:c['start']),tracks=tracks,gaps=self.gaps,speech=self.speech,
            cues_committed=len(self.cues),cues_dropped=len(self.dropped),dropped_gaps=self.dropped,
            overlaps_with_speech=sum(self.check_fit(c['id'],c[l],l)['overlap_seconds']>0 for c in self.cues.values() for l in self.langs if c.get(l)),
            gap_coverage_percent={l:100*sum(c['end']-c['start'] for c in track)/total for l,track in tracks.items()},
            high_importance_covered_percent=100*(len(high)-len(uncovered))/len(high) if high else 100,
            events_in_speech_regions={'count':len(in_speech),'events':in_speech,'note':'informational: high-importance events outside every narratable gap; may need extended AD'},
            coverage_method='temporal association proxy (events overlapping narratable gap windows); not semantic verification',uncovered_events=uncovered)
        self.done=True
        return {'ok':True,'warnings':problems+warnings,'outputs':str(self.out)}

    def verified_required(self):
        return [gid for gid in self.cues if self.verification_reasons(gid)]

    def execute(self,name,args):
        start=time.monotonic()
        note=''
        self.cost_role={'verify_claim':'verify','inspect_video_segment':'perceive','draft_description':'draft','translate_hindi':'translate'}.get(name)
        try:
            schema=next(t['function']['parameters'] for t in TOOLS if t['function']['name']==name)
            jsonschema.validate(args,schema)
            args=dict(args)
            note=args.pop('note')
            result=getattr(self,name)(**args)
        except BudgetExceeded:
            self.trace('tool',note=note,tool_name=name,args=compact(args),ok=False,result={'error':'Budget exceeded'},latency_s=time.monotonic()-start)
            raise
        except Exception as exc:
            result={'ok':False,'error':sanitize(exc)}
        args = args if isinstance(args,dict) else {}
        failed=result.get('ok') is False or result.get('verdict')=='contradicted'
        correction=None
        if not failed and name in ('check_fit','commit_cue','propose_cue','draft_description','translate_hindi','drop_gap'):
            for failure in self.pending_failures:
                if failure['gap_id']==args.get('gap_id') or (failure['gap_id'] is None and name=='translate_hindi'):
                    correction=failure['step']; self.pending_failures.remove(failure); break
        result={**result,'state':{'committed':list(self.cues),'remaining':[g['id'] for g in self.gaps if g.get('narratable',True) and g['id'] not in self.cues and g['id'] not in self.dropped],'skipped_too_short':[g['id'] for g in self.gaps if not g.get('narratable',True)],'needs_verification':list(self.needs_verification()),'budget':{'turns':max(0,self.cfg['agent']['max_steps']-self.turn-1),'inspections':self.cfg['agent']['max_inspections']-self.counts['inspections'],'verifications':self.cfg['agent']['max_verifications']-self.counts['verifications']}}}
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
        for g in self.gaps:
            gid=g['id']
            if gid in self.cues or gid in self.dropped or not g.get('narratable',True):
                continue
            skip=self.rejected.get(gid,[])
            candidate=self.candidates.get(gid)
            if candidate and not any(similarity(candidate,r)>=.8 for r in skip):
                result=self.commit_cue(gid,candidate)
                if result['ok']:
                    note(f'Gap {gid}: committed best fitting candidate "{candidate}"','commit_cue',args={'gap_id':gid}); continue
                note(f"Gap {gid}: candidate rejected ({'; '.join(result['problems'])})",'commit_cue',False)
            draft=self.drafts.get(gid)
            if draft and not any(similarity(draft,r)>=.8 for r in skip):
                fit=self.check_fit(gid,draft,'en')
                text=draft
                if not fit['ok']:
                    words=draft.split()[:fit['suggested_max_words']]
                    text=' '.join(words).rstrip(' ,;:.!?-')+'.' if words else ''
                result=self.commit_cue(gid,text) if text else {'ok':False,'problems':['empty after trimming']}
                if result['ok']:
                    note(f'Gap {gid}: committed latest draft'+('' if text==draft else ' shortened to fit')+f': "{text}"','commit_cue',args={'gap_id':gid}); continue
                note(f"Gap {gid}: shortened draft still unusable ({'; '.join(result['problems'])})",'commit_cue',False)
            self.drop_gap(gid,'Fallback: no fitting candidate or draft')
            note(f'Gap {gid}: dropped, no fitting candidate or draft','drop_gap',args={'gap_id':gid})
        for gid in sorted(self.needs_verification()):
            if gid not in self.cues: continue
            try:
                result=self.verify_claim(gap_id=gid,claim=self.cues[gid]['en'])
            except Exception as exc:
                note(f'Gap {gid}: unverified, verification unavailable ({sanitize(exc)})','verify_claim',False); break
            if result.get('ok') is False:
                note(f"Gap {gid}: unverified, {result['error']}",'verify_claim',False); break
            if result['verdict']=='contradicted':
                self.drop_gap(gid,'Fallback: claim contradicted by verification')
                note(f'Gap {gid}: contradicted by verification; dropped','verify_claim',False,result=compact(result))
            else:
                note(f"Gap {gid}: verification {result['verdict']}",'verify_claim',result=compact(result))
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
        roles={r:sum(s['cost_usd'] for s in self.steps if s.get('cost_role',s['role'])==r) for r in ('orchestrator','perceive','verify','draft','translate')}
        if self.client.usage:
            roles={r:sum(u['cost_usd'] for u in self.client.usage if u.get('cost_role',{'orchestrate':'orchestrator','fit':'draft','edit':'translate'}.get(u['stage'],u['stage']))==r) for r in roles}
        self.report.update(usage=self.client.usage,cost_by_role=roles,billed_to='nvidia-dev free tier (dev only)' if self.cfg['provider']=='nvidia-dev' else 'mock (offline)' if self.mock else 'nebius token factory',cost_per_minute_usd=cost/(self.duration/60),agent_stats=summary,estimated_cost_usd=cost,
            would_be_token_factory_cost_usd=cost,reserved_spend_usd=self.guard.spent,cost_per_minute=cost/(self.duration/60),latency_s=summary['total_latency_s'])
        (self.out/'report.json').write_text(json.dumps(self.report,ensure_ascii=False,indent=2))


def run_agent(path,out_dir,provider=None,langs=('en','hi'),max_steps=None,budget_usd=None,on_step=None,*,config=None,client=None,orchestrator=None,orchestrator_model='ultra'):
    """Synchronous streaming API; callback gets each JSON-serializable trace step."""
    cfg=resolve_provider(config or load_config(),provider)
    if orchestrator_model=='super':
        if 'orchestrate_alt' not in cfg['models']:
            raise ValueError('Super orchestrator is available with nebius only')
        cfg['models']['orchestrate']=cfg['models']['orchestrate_alt']
    if isinstance(langs,str):
        langs=langs.split(',')
    if not langs or any(l not in ('en','hi') for l in langs):
        raise ValueError('Supported languages: en,hi')
    steps=cfg['agent']['max_steps'] if max_steps is None else max_steps
    if not isinstance(steps,int) or steps<0:
        raise ValueError('max_steps must be nonnegative integer')
    cfg['agent']['max_steps']=steps
    guard=SpendGuard(cfg['agent']['budget_usd'] if budget_usd is None else budget_usd)
    a=Agent(path,out_dir,cfg,langs,guard,on_step,client)
    planner=orchestrator or (MockOrchestrator() if a.mock else Orchestrator(a.client))
    messages=[{'role':'system','content':SYSTEM},{'role':'user','content':f'Describe this {a.duration:.2f}s video. Languages: {langs}. Maximum tool turns: {steps}.'}]
    stop='orchestrator stopped early (max turns, timeout or no tool calls)'
    try:
        for turn in range(steps):
            a.turn=turn
            if steps-turn==3:
                messages.append({'role':'system','content':'3 turns left: commit what you have, translate, finalize'})
            if time.monotonic()-a.started>cfg['agent']['timeout_s']:
                a.report['issues'].append('Wall-clock timeout reached'); break
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
