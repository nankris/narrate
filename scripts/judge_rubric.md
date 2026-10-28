# Narrate judge rubric (DCMP-style)

Score each spoken cue against the video frames inside its cue window and against the complete narration track. Use integers
from 0 to 10 for each category. A skipped gap is not a cue: judge whether the silence was appropriate under Story and
prioritisation. Do not reward details that are plausible but not visible.

## Per-cue scores

### 1. Accuracy against frames (30%)

- **9-10:** Every person, object, action, state, spatial relation, number and quoted on-screen text is supported by the frames
  in the cue window. Timing is exact and no future or earlier event leaks into the cue.
- **7-8:** Substantively correct, with at most one harmless imprecision that does not change the action or story.
- **4-6:** The main action is recognisable, but a material detail is unsupported, vague or assigned to the wrong moment.
- **1-3:** Mostly wrong, speculative, or describes another shot.
- **0:** Fabricated or unrelated to the visible content.

### 2. Story and prioritisation (20%)

- **9-10:** Selects the most useful new visual information, establishes place and people early, and clearly advances the
  action, result or goal. Silence is used when speech already conveys the point or nothing important changes.
- **7-8:** Good choice of detail and progression, but misses a useful result or story link.
- **4-6:** Describes a visible fact but gives it the wrong priority, omits a major beat, or spends the gap on trivia.
- **1-3:** Obscures the story through poor selection; important action is repeatedly left undescribed.
- **0:** Provides no useful access to the story.

### 3. Redundancy and integration with programme audio (10%)

- **9-10:** Adds only information unavailable from prior cues or nearby dialogue; references remain clear without needless
  re-establishment.
- **7-8:** Minor repeated wording or one unnecessary reminder.
- **4-6:** Repeats an earlier cue or paraphrases dialogue instead of adding visual information.
- **1-3:** Persistent repetition, subtitle reading, or narration that competes with the programme.
- **0:** Almost entirely duplicate or spoken-content transcription.

### 4. Timing and speakability (15%)

- **9-10:** Starts and ends inside the available silence, fits at a natural rate, and lands before the next important sound.
- **7-8:** Fits cleanly with only slight density or an avoidable pause.
- **4-6:** Technically fits only with conspicuous speed-up, or its placement weakens comprehension.
- **1-3:** Overlaps speech or cannot be spoken intelligibly in the window.
- **0:** Effectively unusable at the assigned time.

### 5. Native, natural English fluency (15%)

- **9-10:** Idiomatic, concise spoken English that sounds like a professional audio describer: complete natural sentences,
  specific verbs, smooth reference to people, and no translationese.
- **7-8:** Natural and grammatical, with a slightly stiff or generic phrase.
- **4-6:** Understandable but caption-like, awkward or non-idiomatic. Deduct here for clipped fragments.
- **1-3:** Repeated fragments, unnatural word order, or generic **“Person …” / “A person …”** subjects.
- **0:** Incoherent or not usable English.

### 6. Hindi naturalness (10%; bilingual track only)

- **9-10:** Fluent, everyday spoken Hindi in Devanagari, naturally re-expressed rather than literally translated, with correct
  agreement and context-appropriate vocabulary.
- **7-8:** Natural overall, with one stiff choice or minor agreement issue.
- **4-6:** Understandable but literal, headline-like, overly formal, or inconsistently gendered.
- **1-3:** Persistent transliteration, unnatural grammar, fragments, or meaning distorted by translation.
- **0:** Missing when required, largely non-Hindi, or unintelligible.

For an English-only track, redistribute the Hindi 10% proportionally across the other categories. Equivalently:

`English-only cue = (30A + 20S + 10R + 15T + 15E) / 90`

For a bilingual track:

`Bilingual cue = (30A + 20S + 10R + 15T + 15E + 10H) / 100`

Each result is on a 0-10 scale. Report one decimal place.

## Overall score

1. Compute the duration-weighted mean of per-cue scores (use the cue window duration).
2. Score **coverage** from 0-10: 10 when all important narratable beats are described or explicitly and appropriately left
   silent; reduce it in proportion to important unexplained omissions. Do not penalise stated no-new-information silence.
3. Apply track-level critical penalties after reviewing the whole video:
   - subtract **1.0** for any unsupported cue that materially changes the story;
   - subtract **1.0** if narration repeatedly overlaps dialogue;
   - subtract **0.5** if the opening never establishes an available place/person context;
   - subtract **0.5** for repeated fragmentary or “Person …” English.

`Overall = clamp(0, 10, 0.85 × duration-weighted cue mean + 0.15 × coverage − critical penalties)`

Alongside the number, cite the cue time and visible frame evidence for every score below 7 and name the single highest-impact
improvement. Accuracy is a gate: a polished sentence cannot compensate for an unsupported visual claim.
