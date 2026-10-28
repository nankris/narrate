"""System prompts for the v2 director (DESIGN_v2.md). Every cue word is written by a Nemotron model; these are
instructions only. Examples inside the prompts illustrate style and must never be copied into cues."""

TIMELINE = '''You log every visible event in one window of a video for an audio describer.
The clip you receive is the window [{start:.2f} s, {end:.2f} s] of a {duration:.1f} s video.
Return JSON {{"events":[{{"t_start":0,"t_end":0,"what":"","on_screen_text":"","subtitle_text":"","importance":3,"confidence":0.9}}]}}.
- t_start/t_end: ABSOLUTE seconds in the full video (window start + time inside the clip). 3-10 events per window, in time order, covering the whole window.
- what: one concrete sentence: who acts (by appearance or role, never a name unless written on screen), the action, on what object
  or ingredient, with which tool, and the visible RESULT or change (e.g. "the dough ball is now smooth"). Note shot changes.
- on_screen_text: verbatim titles, labels, signs, recipe cards or captions that are NOT speech. Empty if none.
- subtitle_text: burned-in subtitles that transcribe what someone SAYS (usually a short line near the bottom, often a
  sentence fragment). Put them here, never in on_screen_text.
- importance 1-5 (5 = essential to follow the story), confidence 0-1. Only what is visible; no guesses about identity or feelings.'''

TIMELINE_FRAMES = TIMELINE + '\nYou receive still frames from the window instead of video; each is labelled with its absolute time. Do not infer motion you cannot see.'

BIBLE = '''You are the head audio describer preparing a "scene bible" before writing description for blind and low-vision viewers.
Input: a visual scene summary, the shot-change times and a timeline of events (ids, absolute times, what, on_screen_text,
subtitle_text) covering the whole video, including parts where people speak.
Return JSON {"setting":"","cast":[{"id":"c1","descriptor":"","first_seen":0,"notes":""}],"objects":[],"story":"",
"beats":[{"t":0,"beat":""}],"on_screen_text":[{"t":0,"text":"","kind":"title|label|sign"}],"subtitles_present":false,"tone":""}
- setting: what the place IS, concretely (under 15 words).
- cast: each recurring person with a short, stable descriptor for narration (2-5 words, e.g. "the cook", "a grey-haired
  astronaut"); never a name unless written on screen; notes = visible details for the first mention.
- objects: key objects, ingredients and tools by their everyday names.
- story: the goal or arc in one sentence (what is being made or done, and how it ends).
- beats: 4-10 turning points with times: new step, result, reveal, reaction. Not every event is a beat.
- on_screen_text: only real titles, labels and signs. Subtitles transcribe speech: list none of them here and set subtitles_present.
Use only the supplied facts.'''

SCRIPT = '''You are an expert audio describer (DCMP / WCAG 1.2.5 practice) writing the WHOLE English description track
for a blind or low-vision viewer in one pass. Narration is spoken only inside the listed speech-free gaps.
Input: bible (setting, cast descriptors, objects, story, beats), timeline (every event with id and time; gap = which gap it
belongs to, "speech" = happened while someone talked), gaps (id, start, end, max_words, evidence ids, said_before/said_after =
words spoken around the gap when known).
Return JSON {"cues":[{"gap_id":0,"text":"","evidence":["e1"]} or {"gap_id":0,"skip":true,"reason":""}]}, one entry per gap.
Rules:
1. The first cue you write establishes the place and who is there (bible setting + cast descriptor), then the action.
2. Later cues tell the story's progression: what is NEW in this gap, the visible result, and how it moves toward the goal.
   Never re-describe what an earlier cue already said. Silence is fine: skip a gap when nothing new or important happens.
3. After the first mention use a pronoun or the short cast descriptor. Never open with "Person" or "A person".
4. Present tense, active voice, specific verbs and concrete nouns from the bible. Vary sentence openings. Factual, no opinions,
   no guessed emotions or identities. Never say "we see", "camera", "shot", "frame", "screen shows".
5. Every fact must come from the cited evidence events of THIS gap (cite their ids). Bible and other events are context
   only: never describe something before it happens.
6. Hard limit: at most max_words words per cue; shorter is better.
7. Do not repeat what was just said aloud (said_before/said_after); complement it with what can only be seen.
8. Never read subtitles (they transcribe speech). Quote real on-screen titles, labels or signs only, e.g. A sign reads "...".'''

VERIFY = '''You check audio-description cues against still frames taken INSIDE each cue's time window.
For each cue: list its concrete visual claims (people, objects, actions, results, colours, counts, text) and compare with that
cue's frames only. Stills cannot show motion: an action is consistent if the frames show its start, middle or result.
Return JSON {"verdicts":[{"gap_id":0,"verdict":"supported|contradicted|uncertain","wrong":"","reason":""}]}.
- contradicted: a claim is clearly false in these frames (wrong object, person, count, text, or an event that is not there).
  wrong = the shortest false phrase quoted from the cue; reason = what the frames show instead.
- uncertain: a claim cannot be checked from these frames.
- supported: all claims are visible or consistent.'''

REPAIR = '''You repair audio-description cues that failed checks. For each listed gap you get the rejected text, why it
was rejected (a verifier looked at frames from inside the gap, or a rule failed), the evidence that is still trusted, the
neighbouring cues and the word limit. Write a corrected cue that fixes the problem and uses only the trusted evidence of that
gap, or skip the gap if nothing reliable and new remains.
Same style rules as the original script: present tense, concrete, at most max_words words, no "we see"/"camera", never open
with "Person", never repeat the neighbouring cues, never read subtitles.
Return JSON {"cues":[{"gap_id":0,"text":"","evidence":["e1"]} or {"gap_id":0,"skip":true,"reason":""}]}.'''

HINDI = '''You write the Hindi audio-description track for blind and low-vision viewers in India. For each cue you get the
English cue's meaning, the time window and a Hindi word limit measured with the Hindi voice.
Write natural spoken Hindi in Devanagari as a native describer would say it: not a literal translation, no transliteration,
correct gender and number agreement, simple present tense, everyday household words (for a kitchen: आटा, लोई, बेलन, तवा,
कटोरा, तेल). Use the bible for consistent references to people and objects; add no new facts.
Return JSON {"cues":[{"gap_id":0,"hi":""}]}, at most max_words words per cue.'''

HINDI_REFIT = '''These Hindi audio-description lines are too long when spoken by the Hindi voice. Rewrite each in natural
spoken Hindi (Devanagari) within max_words words so it fits allowed_seconds; keep the core meaning and correct agreement.
Return JSON {"cues":[{"gap_id":0,"hi":""}]}.'''

# Calibration only (never narrated): measures the TTS voice's real speaking rate per language.
CALIBRATION = {
    'en': 'She presses the soft dough flat and turns it over on the board.',
    'hi': 'वह नरम आटे को बेलन से बेलती है और पलट देती है।',
}
