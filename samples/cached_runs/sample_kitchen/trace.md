# Narrate director trace (v2)

Clip: `sample_kitchen.mp4` · 30.0 s · provider `nebius` · Ultra calls 2/6 · cost $0.0115

## Run summary

- **Model calls:** Ultra 2/6 · Super VL 5 · Nano tighten 1
- **Cost:** $0.0115 (Ultra $0.0066, timeline $0.0030, verify $0.0011, Nano $0.0000)
- **Cues:** 4 committed of 4 narratable gaps · average budget use 96 % · repairs 0 · Nano-tightened 1 · within word tolerance 1
- **Silent by choice:** none
- **Dropped:** none
- **Round 7 robustness:** punctuation fixed 0 · final pass rescued 0 (soft-kept 0, length fallback 0) · failed silence rescues back to silent 0
- **Coverage:** 4/4 narratable gaps narrated (100 %; 100 % excluding 0 silent by choice; target 75 %)

## Stages

| stage | model(s) | calls | tokens in / out | cost $ | s | output |
|---|---|---|---|---|---|---|
| ✓ gaps | — | 0 | 0 / 0 | 0.0000 | 0.7 | 4 narratable slots of 4, 4 long enough; detector silero-onnx; speech 42%; measured voice wps en 3.51 hi 5.2; English budgets at 2.6 words/s (natural narrator), fit judged by measured seconds |
| ✓ shots | — | 0 | 0 / 0 | 0.0000 | 0.1 | 0 shot cuts; 3 perception windows of ~12 s 0-10s, 10-20s, 20-30s; est. Super VL timeline cost $0.0074 (upper bound from config prices) |
| ✓ scene | Nemotron-3.5-Super-VL | 1 | 2343 / 87 | 0.0008 | 3.4 | setting: dark teal screen with yellow outline / activity: title cards indicate cooking steps |
| ✓ timeline | Nemotron-3.5-Super-VL | 3 | 6475 / 1124 | 0.0030 | 10.3 | 10 events from 3 windows ({'video': 3, 'absolute': 3}); 0 with subtitles (speech, never read) |
| ✓ bible | Nemotron-3-Ultra-550b-a55b | 1 | 1726 / 410 | 0.0030 | 2.0 | place: title card screen / setting: dark teal screen with moving yellow rectangle and text cards / cast: no recurring people / goal: show cooking steps via title cards / story: A title card announces a person entering a kitchen, then a yellow rectangle moves across a dark teal screen before a final card reads 'Stir and serve'. / 4 beats |
| ✓ assign | — | 0 | 0 / 0 | 0.0000 | 0.0 | 4 gaps carry a story beat; 6 of 10 events inside narratable gaps; 4 in speech (context only); per gap {0: 1, 1: 2, 2: 2, 3: 1} |
| ✓ script | Nemotron-3-Ultra-550b-a55b | 1 | 3163 / 159 | 0.0036 | 24.4 | 4 gaps scripted in one call: {'pending': 3, 'failed': 1} |
| ✓ tighten | NVIDIA-Nemotron-3-Nano-30B-A3B | 1 | 358 / 49 | 0.0000 | 18.7 | over-budget cues shortened by Nano (one cue per call, up to 3 options, <= 2 attempts): {'pending': 1} |
| ✓ verify | Nemotron-3.5-Super-VL | 1 | 2941 / 243 | 0.0011 | 3.0 | 4 cues checked on stills inside their gaps: {'supported': 4} |
| ✓ render | — | 0 | 0 / 0 | 0.0000 | 0.8 | 4 cues rendered (en: 4); 0 gaps silent by choice |

## Scene bible

- **Place:** title card screen · **Goal:** show cooking steps via title cards
- **Setting:** dark teal screen with moving yellow rectangle and text cards
- **Cast:** 
- **Story:** A title card announces a person entering a kitchen, then a yellow rectangle moves across a dark teal screen before a final card reads 'Stir and serve'.
- **Objects:** yellow rectangular outline
- **Subtitles present (never read):** False
- **Beats:** 0s title card announces a person entering a kitchen (sets up the cooking scenario) [e1]; 3s yellow rectangle begins moving across the screen (visual progression between steps) [e3, e4, e5]; 14s rectangle pauses at right edge (holds before next instruction) [e6]; 20s final instruction 'Stir and serve' appears (completes the cooking step sequence) [e7, e8, e9, e10]
- **Object names:** —
- **Looked for again:** —
- **Beats per gap:** gap 0: yellow rectangle begins moving across the screen (visual progression between steps); gap 1: yellow rectangle begins moving across the screen (visual progression between steps); rectangle pauses at right edge (holds before next instruction); gap 2: final instruction 'Stir and serve' appears (completes the cooking step sequence); gap 3: final instruction 'Stir and serve' appears (completes the cooking step sequence)

## Timeline (10 events; ~~refuted~~)

| id | time | gap | what | on screen | said |
|---|---|---|---|---|---|
| e1 | 0.0-1.0 | speech | A dark teal screen displays the white text 'A person enters a kitchen' in the upper left corner, with a small yellow rectangular outline in the lower left. | A person enters a kitchen |  |
| e2 | 1.0-3.0 | speech | The white text disappears, leaving only the dark teal background and the yellow rectangular outline in the lower left. |  |  |
| e3 | 3.0-6.0 | speech | The yellow rectangular outline shifts slightly upward and to the right on the dark teal background. |  |  |
| e4 | 6.0-12.0 | 0 | The yellow rectangular outline continues to move toward the center of the dark teal screen. |  |  |
| e5 | 12.0-14.0 | 1 | The yellow rectangular outline reaches the right edge of the screen and stops moving. |  |  |
| e6 | 14.0-20.0 | 1 | The yellow rectangular outline remains stationary at the right edge of the dark teal screen. |  |  |
| e7 | 20.0-21.0 | 2 | The text 'Stir and serve' appears in the top left corner while the yellow rectangular outline remains on the right side of the dark teal screen. | Stir and serve |  |
| e8 | 21.0-24.0 | 2 | The yellow rectangular outline stays stationary on the right side of the screen with the text 'Stir and serve' visible in the top left. | Stir and serve |  |
| e9 | 24.0-27.0 | speech | The yellow rectangular outline moves from the right side toward the center of the screen while the text 'Stir and serve' remains in the top left. | Stir and serve |  |
| e10 | 27.0-30.0 | 3 | The yellow rectangular outline continues moving leftward across the screen, now positioned near the center-left, with the text 'Stir and serve' still visible. | Stir and serve |  |

## Script, verification and repairs

| gap | time | words | outcome | English | evidence | Hindi |
|---|---|---|---|---|---|---|
| 0 | 4.7-8.7 | 9/8 | supported | A yellow rectangle moves across a dark teal screen. | e4 |  |
| 1 | 11.9-16.6 | 8/10 | supported | The rectangle reaches the right edge and pauses. | e5, e6 |  |
| 2 | 19.9-24.7 | 9/10 | supported | Text reads Stir and serve in the top left. | e7, e8 |  |
| 3 | 27.4-29.9 | 4/4 | supported | The rectangle moves leftward. | e10 |  |

### Cue history (script → verify → repair)

- gap 0 · script: "A yellow rectangle moves across a dark teal screen." → ok
- gap 1 · script: "The rectangle reaches the right edge and pauses." → ok
- gap 2 · script: "Text reads Stir and serve in the top left." → ok
- gap 3 · script: "The rectangle shifts leftward toward the center." → over budget: 7 words, max 4. Fix: cut at least 3 words (keep the subject and the main action; drop a secondary action, colours or positions)
- gap 3 · tighten: "The rectangle moves leftward." → ok
