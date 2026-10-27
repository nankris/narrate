"""Public OpenAI function schemas; additional properties are rejected."""
S = {'type':'string'}
N = {'type':'number'}
I = {'type':'integer'}
DEFINITIONS = {
 'detect_speech_gaps': ({}, []),
 'inspect_video_segment': ({'start':N,'end':N,'focus':S}, ['start','end']),
 'verify_claim': ({'start':N,'end':N,'claim':S}, ['start','end','claim']),
 'draft_description': ({'gap_ids':{'type':'array','items':I},'gap_id':I,'context_events':{'type':'array','items':{'type':'object'}},'max_words':I,'avoid_repeating':S}, []),
 'measure_tts_duration': ({'text':S,'lang':{'type':'string','enum':['en','hi']}}, ['text','lang']),
 'check_fit': ({'gap_id':I,'text':S,'lang':{'type':'string','enum':['en','hi']}}, ['gap_id','text','lang']),
 'commit_cue': ({'gap_id':I,'text':S}, ['gap_id','text']),
 'propose_cue': ({'gap_id':I,'text':S}, ['gap_id','text']),
 'drop_gap': ({'gap_id':I,'reason':S}, ['gap_id','reason']),
 'translate_hindi': ({'cue_ids':{'type':'array','items':I},'max_words':I}, []),
 'render_preview': ({'start':N,'end':N,'lang':{'type':'string','enum':['en','hi']}}, ['start','end','lang']),
 'finalize': ({}, []),
}
TOOLS = [{'type':'function','function':{'name':name,'description':name.replace('_',' '),
          'parameters':{'type':'object','properties':{**props,'note':{'type':'string','pattern':r'^\s*\S+(?:\s+\S+){0,24}\s*$','description':'At most 25 words: action and purpose, or lesson from last observation.'}},'required':required+['note'],'additionalProperties':False}}}
         for name,(props,required) in DEFINITIONS.items()]
