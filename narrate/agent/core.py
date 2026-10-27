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
        return [{**s,'what':s.get('action',''),'confidence':1.0,'mock':True} for s in self.scenes
                if s['t_start'] < end and s['t_end'] > start] or [
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
        self.speech=result['speech']; self.gaps=[]
        for i,g in enumerate(result['gaps']):
            start,end = g['start']+.08,g['end']-.08
            self.gaps.append({'id':i,'start':start,'end':end,'duration':end-start,
                **{'word_budget_'+lang:word_budget(end-start,self.cfg['words_per_second'][lang],self.cfg['word_margin']) for lang in ('en','hi')}})
        self.report.update(detector=result['detector'],speech_ratio=result['speech_ratio'],detector_fallback_reason=result['fallback_reason'])
        if not self.gaps:
            self.report['issues'].append('Cannot narrate safely without extended AD (pause-the-video): no usable speech-free gaps.')
        return {'gaps':[{k:g[k] for k in ('id','start','end','word_budget_en','word_budget_hi')} for g in self.gaps], 'detector':result['detector'],'speech_ratio':result['speech_ratio']}

    def segment(self,start,end):
        if not all(math.isfinite(x) for x in (start,end)) or not 0 <= start < end <= self.duration:
            raise ValueError('Invalid segment bounds')

    def inspect_video_segment(self,start,end,focus=''):
        self.segment(start,end)
        key=(start,end,focus)
        for (s,e,_),cached in self.cache.items():
            if max(0,min(end,e)-max(start,s))/(end-start)>=.7:
                return {**cached,'cached':True,'reminder':'Already inspected >=70% of this range; use cached evidence.'}
        if self.counts['inspections'] >= self.cfg['agent']['max_inspections']:
            return {'ok':False,'error':'Inspection cap reached'}
        self.counts['inspections']+=1
        data={'duration':end-start,'instruction':'Inspect this segment. Return events with absolute t_start/t_end, what, on_screen_text, importance 1-5, confidence 0-1. Segment starts at '+str(start),'focus':focus}
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
        valid=[]
        for event in result.get('events',[]):
            try:
                s,e=float(event['t_start']),float(event['t_end'])
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
        result={'events':valid,'modality':modality}
        self.cache[key]=result
        return result

    def verify_claim(self,start,end,claim):
        self.segment(start,end)
        if self.counts['verifications'] >= self.cfg['agent']['max_verifications']:
            return {'ok':False,'error':'Verification cap reached'}
        self.counts['verifications']+=1
        media=None if self.mock else separate_frames(self.path,[start,start+(end-start)/2,max(start,end-.1)])
        mock={'verdict':'contradicted' if 'blue dot' in claim else 'uncertain',
              'evidence':'MOCK sidecar describes title and yellow shape; no blue dot or fading text.'}
        result=self.submodel('perceive',{'duration':end-start,'instruction':'Use these FRAMES only. Verify the claim; return {verdict: supported|contradicted|uncertain, evidence: string}. Do not infer motion between stills.','claim':claim},media,mock)
        result=normalize_json(result)
        result['verdict']=str(result.get('verdict','')).strip().lower()
        if result.get('verdict') not in ('supported','contradicted','uncertain'):
            return {'ok':False,'error':'Invalid verification response'}
        return {**result,'modality':'frames'}

    def gap(self,gap_id):
        return next(g for g in self.gaps if g['id']==gap_id)

    def draft_description(self,gap_id=None,context_events=None,max_words=None,avoid_repeating='',gap_ids=None):
        if gap_ids is not None:
            gaps=[self.gap(i) for i in gap_ids]
            return self.submodel('fit',{'instruction':'Draft one English cue per gap, obey word_budget_en. Return {cues:[{id,text}]}. Only use associated events; no future events.', 'gaps':gaps,'events':self.events},mock_result={'cues':[{'id':g['id'],'text':self.mock_line(self.mock_events(g['start'],g['end']),g['word_budget_en'])} for g in gaps]})
        g=self.gap(gap_id)
        limit=max(1,min(max_words or g['word_budget_en'],g['word_budget_en']))
        mock_text=self.mock_line(context_events or self.mock_events(g['start'],g['end']),limit)
        if self.mock and getattr(self,'inject_overbudget',False):
            mock_text='word '*(g['word_budget_en']+5)
            self.inject_overbudget=False
        result=self.submodel('fit',{'instruction':'Write ONE English line of audio description <= max_words. Return {text: string}. Use supplied facts only.','gap':g,'events':context_events,'max_words':limit,'avoid_repeating':avoid_repeating},mock_result={'text':mock_text})
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
        return {'ok':not problems,'problems':problems,'suggested_max_words':suggested,'seconds':seconds,'overlap_seconds':overlap}

    def commit_cue(self,gap_id,text):
        result=self.check_fit(gap_id,text,'en')
        if not result['ok']:
            return result
        g=self.gap(gap_id)
        self.translation_done=False
        self.cues[gap_id]={**g,'en':text}
        self.dropped.pop(gap_id,None)
        return {'ok':True,'cue':self.cues[gap_id]}

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
        for c in list(self.cues.values()):
            for lang in self.langs:
                if not c.get(lang):
                    (warnings if lang=='hi' and self.translation_done else problems).append(f"Cue {c['id']}: missing {lang}")
                elif not self.check_fit(c['id'],c[lang],lang)['ok']:
                    problems.append(f"Cue {c['id']}: invalid {lang}")
        associated=lambda e,g: g['start']<=e['t_end']+6 and g['end']>e['t_start']
        high=[e for e in self.events if e['importance']>=4 and any(associated(e,g) for g in self.gaps)]
        # Temporal association is explicitly a proxy, not semantic coverage verification.
        uncovered=[e for e in high if not any(associated(e,c) for c in self.cues.values())]
        if uncovered:
            problems.append(f'{len(uncovered)} high-importance events lack an associated cue')
        if problems and self.rejections<2 and not force:
            self.rejections+=1
            return {'ok':False,'problems':problems,'uncovered_events':uncovered,'rejection':self.rejections}
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
        self.report.update(status='complete',cues=list(self.cues.values()),tracks=tracks,gaps=self.gaps,speech=self.speech,
            cues_committed=len(self.cues),cues_dropped=len(self.dropped),dropped_gaps=self.dropped,
            overlaps_with_speech=sum(self.check_fit(c['id'],c[l],l)['overlap_seconds']>0 for c in self.cues.values() for l in self.langs if c.get(l)),
            gap_coverage_percent={l:100*sum(c['end']-c['start'] for c in track)/max(.001,sum(g['duration'] for g in self.gaps)) for l,track in tracks.items()},
            high_importance_covered_percent=100*(len(high)-len(uncovered))/len(high) if high else 100,
            coverage_method='temporal association proxy; not semantic verification',uncovered_events=uncovered)
        self.done=True
        return {'ok':True,'warnings':problems+warnings,'outputs':str(self.out)}

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
        result={**result,'state':{'committed':list(self.cues),'remaining':[g['id'] for g in self.gaps if g['id'] not in self.cues and g['id'] not in self.dropped],'budget':{'turns':max(0,self.cfg['agent']['max_steps']-self.turn-1),'inspections':self.cfg['agent']['max_inspections']-self.counts['inspections'],'verifications':self.cfg['agent']['max_verifications']-self.counts['verifications']}}}
        sid=self.trace('tool',note=note,tool_name=name,args=compact(args),result=compact(result),ok=not failed,
            latency_s=time.monotonic()-start,correction=correction is not None,corrects_step=correction)
        if failed:
            gid=args.get('gap_id')
            if name=='verify_claim':
                gid=next((g['id'] for g in self.gaps if g['start']==args.get('start')),None)
            self.pending_failures.append({'step':sid,'gap_id':gid})
        return result

    def save(self):
        cost=sum(u['cost_usd'] for u in self.client.usage) if self.client.usage else sum(s['cost_usd'] for s in self.steps)
        summary={'tool_calls':dict(Counter(s['tool_name'] for s in self.steps if s['role']=='tool')),
            'corrections':sum(s['correction'] for s in self.steps),
            'verifications':dict(Counter(s['result']['verdict'] for s in self.steps if s['role']=='tool' and isinstance(s['result'],dict) and 'verdict' in s['result'])),
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
    except Exception as exc:
        a.report['issues'].append('Agent stopped: '+sanitize(exc))
    finally:
        if not a.done:
            a.report['fallback_finalize']=True
            start=time.monotonic()
            if 'hi' in a.langs and not a.translation_done:
                try: a.execute('translate_hindi',{'note':'Translate committed cues before fallback finalization.'})
                except Exception: a.report['issues'].append('Fallback Hindi translation unavailable within remaining budget/time')
            result=a.finalize(force=True)
            a.trace('tool',tool_name='finalize',note='Deterministic fallback finisher',result=result,latency_s=time.monotonic()-start)
        a.save()
    return a.report
