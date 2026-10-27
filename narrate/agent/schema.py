"""Public OpenAI function schemas; additional properties are rejected."""
S = {'type':'string'}
N = {'type':'number'}
I = {'type':'integer'}
DEFINITIONS = {
 'detect_speech_gaps': ({}, []),
 'inspect_video_segment': ({'start':N,'end':N,'focus':S}, ['start','end']),
 'verify_claim': ({'gap_id':I,'start':N,'end':N,'claim':S}, ['claim']),
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
DESCRIPTIONS = {
 'detect_speech_gaps': 'Find speech-free gaps with their effective word limit max_words_en/max_words_hi. Gaps with narratable=false (too short) must be skipped.',
 'inspect_video_segment': 'Inspect a video segment with the vision model; returns events with absolute timestamps and confidence. Events are stored on the evidence board; re-inspecting a covered range is refused. Up to 4 per turn in parallel.',
 'verify_claim': 'Check a claim against frames. Pass gap_id (or start/end) and the claim. REQUIRED before finalize for cues with low-confidence events, on-screen text, numbers, quotes or names. A contradicted claim uncommits the cue.',
 'draft_description': 'Cheap: draft cue text from stored evidence. Pass gap_ids=[...] to draft many gaps in ONE call. The max_words and on-screen text are applied and enforced for you; propose the returned text. Use this (not hand-editing) when a proposal fails: gap_ids=[id], max_words=N.',
 'measure_tts_duration': 'EXPLORATION ONLY: measure spoken duration. Commits nothing; prefer propose_cue.',
 'check_fit': 'EXPLORATION ONLY: check text against a gap budget. Commits nothing; a passing English text is only remembered as a candidate. Prefer propose_cue.',
 'commit_cue': 'Fit-check and commit an English cue (same as propose_cue).',
 'propose_cue': 'PREFERRED: fit-check and commit an English cue in one call. Rejects duplicates of other cues. Use text from draft_description; rephrased or self-authored text must pass verify_claim before finalize. The 2nd failed proposal for a gap auto-redrafts it; after 3 failures the gap is refused (drop_gap or move on).',
 'finalize': 'Finish. Refused while cues still need verify_claim or high-importance events are uncovered.',
}
TOOLS = [{'type':'function','function':{'name':name,'description':DESCRIPTIONS.get(name,name.replace('_',' ')),
          'parameters':{'type':'object','properties':{**props,'note':{'type':'string','pattern':r'^\s*\S+(?:\s+\S+){0,24}\s*$','description':'At most 25 words: action and purpose, or lesson from last observation.'}},'required':required+['note'],'additionalProperties':False}}}
         for name,(props,required) in DEFINITIONS.items()]
