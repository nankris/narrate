# Narrate director trace (v2)

Clip: `nasa_chile_harvest_0000-0150.mp4` · 110.0 s · provider `nebius` · Ultra calls 4/6 · cost $0.0497

## Run summary

- **Model calls:** Ultra 4/6 · Super VL 22 · Nano tighten 0
- **Cost:** $0.0497 (Ultra $0.0308, timeline $0.0146, verify $0.0019, Nano $0.0000)
- **Cues:** 7 committed of 10 narratable gaps · average budget use 74 % · repairs 2 · Nano-tightened 0 · within word tolerance 0
- **Silent by choice:** none
- **Dropped:** gap 0 (dropped after repair: Unverified title-only claim (astronaut, space). Fix: remove claims t); gap 8 (dropped after repair: Unverified title-only claim (astronaut). Fix: remove claims taken on); gap 9 (dropped after repair: Unverified title-only claim (astronaut). Fix: remove claims taken on)
- **Round 7 robustness:** punctuation fixed 0 · final pass rescued 3 (soft-kept 3, length fallback 0) · failed silence rescues back to silent 0
- **Coverage:** 7/10 narratable gaps narrated (70 %; 70 % excluding 0 silent by choice; target 75 % — BELOW TARGET)
- **Video title (UNVERIFIED user context, never evidence):** “Astronauts harvest, eat first chile pepper crop on space station”

## Stages

| stage | model(s) | calls | tokens in / out | cost $ | s | output |
|---|---|---|---|---|---|---|
| ✓ gaps | — | 0 | 0 / 0 | 0.0000 | 1.3 | 10 narratable slots of 10, 10 long enough; detector silero-onnx; speech 4%; measured voice wps en 3.708 hi 5.2; English budgets at 2.6 words/s (natural narrator), fit judged by measured seconds |
| ✓ shots | — | 0 | 0 / 0 | 0.0000 | 0.5 | 4 shot cuts; 10 perception windows of ~12 s 0-11s, 11-22s, 22-33s, 33-44s, 44-55s, 55-66s, 66-77s, 77-88s, 88-99s, 99-110s; est. Super VL timeline cost $0.0266 (upper bound from config prices) |
| ✓ scene | Nemotron-3.5-Super-VL | 1 | 2355 / 215 | 0.0009 | 5.1 | setting: Indoor spacecraft module with equipment panels, blue surfaces, artificial lighting. / people: Person in black shirt and blue gloves, interacting with plants inside a lit growth chamber; Person in black shirt and blue gloves, transferring samples from vial onto black surface |
| ✓ timeline | Nemotron-3.5-Super-VL | 10 | 23869 / 3912 | 0.0107 | 74.6 | 40 events from 10 windows ({'video': 10, 'absolute': 9, 'mixed': 1}); 0 with subtitles (speech, never read) |
| ✓ zoom | Nemotron-3.5-Super-VL | 6 | 8745 / 811 | 0.0034 | 23.8 | 3 zoom looks (28-31s plant inside growth chamber; 77-83s astronauts handling a small object toget; 88-94s handling a small green plant): 4 new events ['e41', 'e42', 'e43', 'e44'] |
| ✓ bible | Nemotron-3-Ultra-550b-a55b | 1 | 4744 / 1187 | 0.0083 | 4.6 | place: space station / setting: Space station module with plant growth chamber and work surfaces / cast: astronaut in black shirt and blue gloves, astronaut in blue polo shirt, astronaut in green shirt, astronaut in dark shirt, astronaut in foreground / goal: harvest and examine first chili pepper crop / story: An astronaut tends plants in a space station growth chamber, then a red chili pepper is |
| ✓ cast_look | Nemotron-3.5-Super-VL | 2 | 3776 / 299 | 0.0014 | 7.2 | astronaut in black shirt and blue gloves: man; astronaut in blue polo shirt: man; astronaut in green shirt: man; astronaut in dark shirt: man; astronaut in foreground: man |
| ✓ relook | Nemotron-3.5-Super-VL | 1 | 1154 / 288 | 0.0006 | 4.2 | 1 focused re-looks (107-110s crew tasting or eating the harvested chili pepper): 3 new events ['e45', 'e46', 'e47'] |
| ✓ assign | — | 0 | 0 / 0 | 0.0000 | 0.0 | 8 gaps carry a story beat; 45 of 47 events inside narratable gaps; 2 in speech (context only); per gap {0: 4, 1: 4, 2: 5, 3: 4, 4: 5, 5: 4, 6: 5, 7: 5, 8: 3, 9: 6} |
| ✓ script | Nemotron-3-Ultra-550b-a55b | 1 | 8296 / 526 | 0.0099 | 24.2 | 10 gaps scripted in one call: {'failed': 6, 'pending': 4} |
| ✓ verify | Nemotron-3.5-Super-VL | 1 | 3038 / 189 | 0.0011 | 19.0 | 4 cues checked on stills inside their gaps: {'supported': 4} |
| ✓ repair_1 | Nemotron-3-Ultra-550b-a55b | 1 | 5028 / 427 | 0.0063 | 8.7 | round 1: 6 failed cues sent to Ultra: {'failed': 6} |
| ✓ repair_2 | Nemotron-3-Ultra-550b-a55b | 1 | 5028 / 439 | 0.0063 | 17.2 | round 2: 6 failed cues sent to Ultra: {'failed': 6} |
| ✓ rescue | Nemotron-3.5-Super-VL | 1 | 2398 / 153 | 0.0009 | 3.9 | final pass (no Ultra): 0 Nano strikes; {'verified': 3, 'committed': 3}; soft-kept 3, length fallback 0 |
| ✓ render | — | 0 | 0 / 0 | 0.0000 | 2.2 | 7 cues rendered (en: 7); 0 gaps silent by choice |

## Scene bible

- **Place:** space station · **Goal:** harvest and examine first chili pepper crop
- **Setting:** Space station module with plant growth chamber and work surfaces
- **Cast:** astronaut in black shirt and blue gloves (tends plants in growth chamber, later handles pepper and camera; apparent gender: man (clearly visible at 12 s: short gray hair and side profile visible at plant chamber)); astronaut in blue polo shirt (holds and passes small objects, examines plant closely, smiles; apparent gender: man (clearly visible at 77 s: short hair and face clearly visible in blue polo)); astronaut in green shirt (receives green object, watches plant examination with hands clasped, smiles; apparent gender: man (clearly visible at 77 s: short dark hair and face clearly visible in dark shirt)); astronaut in dark shirt (stands beside blue-shirted astronaut, reaches toward objects; apparent gender: man (clearly visible at 86 s: short hair, masculine face, dark shirt)); astronaut in foreground (receives and passes objects, partially blocks view later; apparent gender: man (clearly visible at 86 s: short gray hair, masculine face, black shirt))
- **Story:** An astronaut tends plants in a space station growth chamber, then a red chili pepper is harvested and photographed on a labeled board, followed by the crew gathering to pass and closely examine a small green plant together.
- **Objects:** plant growth chamber, green leafy plants, equipment panels, control panel, black work surface, yellow tape, white label, red chili pepper, black camera, small green plant, white cable, black object
- **Subtitles present (never read):** False
- **Beats:** 0s astronaut tends plants in illuminated growth chamber (routine plant care in space station module) [e1, e2, e3, e4, e5]; 14s astronaut checks control panel then leaves chamber area (adjusts equipment before stepping away) [e6, e7, e8]; 22s astronaut returns for repeated plant care sessions (multiple rounds of tending the same plants) [e9, e10, e11, e12, e13, e14]; 55s astronaut operates control panel and exits (final chamber interaction before harvest) [e21, e22]; 61s harvested red chili pepper displayed on labeled board (first pepper crop presented for documentation) [e23]; 64s astronaut presses pepper flat and photographs it with camera (documents the harvested pepper) [e24, e25, e26, e27, e28]; 77s crew gathers and passes small objects then examines green plant together (shared inspection of another plant specimen) [e29, e30, e31, e32, e33, e34]
- **Object names:** red chili pepper (not pepper, chili pepper, red chili; from 61s); small green plant (not plant, green plant, small object, green object; from 77s)
- **Looked for again:** 108-110s crew tasting or eating the harvested chili pepper
- **Beats per gap:** gap 0: astronaut tends plants in illuminated growth chamber (routine plant care in space station module); gap 1: astronaut tends plants in illuminated growth chamber (routine plant care in space station module); astronaut checks control panel then leaves chamber area (adjusts equipment before stepping away); gap 2: astronaut returns for repeated plant care sessions (multiple rounds of tending the same plants); gap 3: astronaut returns for repeated plant care sessions (multiple rounds of tending the same plants); gap 4: astronaut operates control panel and exits (final chamber interaction before harvest); gap 5: astronaut operates control panel and exits (final chamber interaction before harvest); harvested red chili pepper displayed on labeled board (first pepper crop presented for documentation); astronaut presses pepper flat and photographs it with camera (documents the harvested pepper); gap 6: astronaut presses pepper flat and photographs it with camera (documents the harvested pepper); crew gathers and passes small objects then examines green plant together (shared inspection of another plant specimen); gap 7: crew gathers and passes small objects then examines green plant together (shared inspection of another plant specimen)

## Timeline (47 events; ~~refuted~~)

| id | time | gap | what | on screen | said |
|---|---|---|---|---|---|
| e1 | 0.0-2.0 | 0 | A person wearing a black shirt and blue gloves reaches toward a lit plant growth chamber inside a spacecraft module, with green plants visible through the window and equipment panels surrounding the area. |  |  |
| e2 | 2.0-5.0 | 0 | The person fully enters the frame, standing in front of the plant growth chamber and extending both gloved hands toward the plants inside. |  |  |
| e3 | 5.0-8.0 | 0 | The person uses both gloved hands to touch and adjust the green leafy plants inside the illuminated growth chamber. |  |  |
| e4 | 8.0-11.0 | 0 | The person continues to tend to the plants inside the chamber, moving their gloved hands among the foliage while facing the equipment. |  |  |
| e5 | 11.0-14.0 | 1 | The person in the black shirt and blue gloves continues to tend to the green leafy plants inside the illuminated growth chamber, moving their gloved hands among the foliage. |  |  |
| e6 | 14.0-17.0 | 1 | The person reaches toward the right side of the growth chamber, appearing to interact with a control or latch on the equipment panel. |  |  |
| e7 | 17.0-20.0 | 1 | The person turns away from the growth chamber and begins walking toward the right side of the frame, leaving the plant area. |  |  |
| e8 | 20.0-22.0 | 1 | The person is no longer visible in the frame, leaving only the illuminated growth chamber with green plants and surrounding equipment panels in view. |  |  |
| e9 | 22.0-25.0 | 2 | The person in a black shirt and blue gloves reaches into the illuminated growth chamber and touches the green plants inside. |  |  |
| e10 | 25.0-28.0 | 2 | The person continues to handle the plants within the growth chamber, moving their gloved hands among the leaves. |  |  |
| e11 | 28.0-31.0 | 2 | The person keeps their hands inside the growth chamber, adjusting or inspecting the green plants. |  |  |
| e41 | 28.0-31.0 | 2 | A person wearing blue gloves and a black shirt handles a white cable and a black object near a window with plants visible outside. |  |  |
| e12 | 31.0-33.0 | 2 | The person withdraws their hands from the growth chamber and steps back, leaving the plants visible inside. |  |  |
| e13 | 33.0-36.0 | 3 | A person in a black shirt and blue gloves reaches into the lit growth chamber with both hands and adjusts the green leafy plants inside. |  |  |
| e14 | 36.0-39.0 | 3 | The person continues to manipulate the plants with both gloved hands, moving leaves and stems within the chamber. |  |  |
| e15 | 39.0-42.0 | 3 | The person keeps both hands inside the growth chamber, tending to the green plants under the bright light. |  |  |
| e16 | 42.0-44.0 | 3 | The person withdraws both hands from the growth chamber and steps back, leaving the plants visible inside. |  |  |
| e17 | 44.0-47.0 | 4 | A person in a black shirt and blue gloves reaches into a lit growth chamber and adjusts the green plants inside. |  |  |
| e18 | 47.0-50.0 | 4 | The person continues to tend to the plants, moving their gloved hands among the leaves under the bright light. |  |  |
| e19 | 50.0-53.0 | 4 | The person keeps both hands inside the growth chamber, manipulating the foliage. |  |  |
| e20 | 53.0-55.0 | 4 | The person withdraws both hands from the growth chamber and steps back, leaving the plants visible inside. |  |  |
| e21 | 55.0-58.0 | 4 | The person in the black shirt and blue gloves reaches toward the control panel on the right side of the illuminated plant growth chamber and appears to press a button or toggle a switch. |  |  |
| e22 | 58.0-61.0 | 5 | The person steps back and exits the frame to the right, leaving the plant growth chamber with its green foliage visible and lit. |  |  |
| e23 | 61.0-64.0 | 5 | The camera cuts to a top-down view of a black work surface where a red chili pepper lies on yellow tape next to a small white label reading 'WEST INDIAN'. | WEST INDIAN |  |
| e24 | 64.0-66.0 | 5 | The person's gloved hands enter the frame and press down on the red chili pepper, flattening it against the black surface. |  |  |
| e25 | 66.0-69.0 | 5 | A person wearing blue gloves holds a black camera above a black board where a red chili pepper is taped next to a white label reading 'WEST INDIAN'. | WEST INDIAN |  |
| e26 | 69.0-72.0 | 6 | The person continues to hold the camera steady, pointing its lens directly at the red chili pepper on the black board. | WEST INDIAN |  |
| e27 | 72.0-75.0 | 6 | The person lifts the camera upward and away from the black board, leaving the red chili pepper and label visible. | WEST INDIAN |  |
| e28 | 75.0-77.0 | 6 | The black board with the taped red chili pepper and 'WEST INDIAN' label remains stationary in the frame. | WEST INDIAN |  |
| e29 | 77.0-80.0 | 6 | A person in a blue shirt and a person in a black shirt stand in a spacecraft module, each holding a small object and passing it between them while a third person in black watches from the foreground. |  |  |
| e42 | 77.6-78.8 | 6 | A man in a blue polo shirt holds a small object in both hands while another person in a dark shirt stands beside him, with no cutting, breaking, opening, pouring, handing over, biting, or eating visible. |  |  |
| e43 | 80.0-81.2 | speech | The man in the blue polo shirt holds the small object while the person in the dark shirt reaches toward it, with no cutting, breaking, opening, pouring, handing over, biting, or eating visible. |  |  |
| e30 | 80.0-83.0 | speech | The person in the black shirt extends their arm to hand the object to the person in the foreground, who reaches out to receive it. |  |  |
| e31 | 83.0-86.0 | 7 | The person in the foreground holds the object while the two standing people continue to gesture and interact around them. |  |  |
| e32 | 86.0-88.0 | 7 | The person in the foreground passes the object back toward the standing person in the blue shirt, who takes it. |  |  |
| e33 | 88.0-91.0 | 7 | A group of people in a spacecraft module gather around a small green plant, with one person in a black shirt holding it while others reach out to touch the leaves. |  |  |
| e44 | 88.6-94.0 | 7 | A person in a blue shirt hands a small green object to a person in a green shirt, and the person in the green shirt takes it with both hands. |  |  |
| e34 | 91.0-94.0 | 7 | The person in the black shirt continues to hold the plant steady while the person in the blue shirt leans in closely to inspect it, and another person in a dark shirt reaches toward the foliage. |  |  |
| e35 | 94.0-97.0 | 8 | The person in the black shirt pulls the plant slightly away from the group while the person in the blue shirt maintains a close view, and the person in the green shirt watches with hands clasped. |  |  |
| e36 | 97.0-99.0 | 8 | The person in the black shirt brings the plant back toward the center of the group, and the person in the blue shirt reaches out again to touch the leaves while the person in the green shirt smiles. |  |  |
| e37 | 99.0-102.0 | 8 | A person in a black shirt and blue gloves holds a green plant while a person in a blue shirt reaches out to touch its leaves, and a person in a green shirt watches with hands clasped. |  |  |
| e38 | 102.0-105.0 | 9 | A person in a blue shirt enters the foreground with their back to the camera, partially blocking the view of the group examining the plant. |  |  |
| e39 | 105.0-108.0 | 9 | The person in the black shirt continues to hold the plant while the person in the blue shirt in the background gestures with both hands raised. |  |  |
| e45 | 107.0-108.0 | 9 | A person in a black shirt and blue gloves holds a small green chili pepper up to their mouth and takes a bite while others watch in the spacecraft module. |  |  |
| e46 | 108.0-109.0 | 9 | The person chews the chili pepper and makes a facial reaction, grimacing slightly as they process the taste. |  |  |
| e40 | 108.0-110.0 | 9 | The person in the blue shirt in the background points toward equipment on the wall while the person in the black shirt still holds the plant. |  |  |
| e47 | 109.0-110.0 | 9 | The person continues to chew and swallow while looking toward the camera, finishing the bite of the chili pepper. |  |  |

## Script, verification and repairs

| gap | time | words | outcome | English | evidence | Hindi |
|---|---|---|---|---|---|---|
| 0 | 0.1-11.4 | 19 | dropped after repair: Unverified title-only claim (astronaut, space). Fix: remove claims taken only from the title |  |  |  |
| 1 | 11.4-22.7 | 10/19 | supported | He checks the control panel, then leaves the chamber area. | e5, e6, e7, e8 |  |
| 2 | 22.7-34.0 | 20/19 | supported | The person in a black shirt and blue gloves handles a white cable and black object near the chamber window. | e9, e10, e11, e41, e12 |  |
| 3 | 34.0-45.3 | 12/19 | supported | He reaches in again with both gloved hands to adjust the plants. | e13, e14, e15, e16 |  |
| 4 | 45.3-56.6 | 19/19 | uncertain-consistent | The person in a black shirt and blue gloves operates the control panel and steps back, exiting the frame. | e17, e18, e19, e20, e21 |  |
| 5 | 56.6-67.9 | 13/19 | supported | A harvested red chili pepper appears on a black board labeled WEST INDIAN. | e22, e23, e24, e25 |  |
| 6 | 67.9-79.2 | 13/19 | supported | The person presses the pepper flat, then photographs it with a black camera. | e26, e27, e28, e29, e42 |  |
| 7 | 84.1-92.7 | 11/19 | supported | Crew members gather, passing the small green plant for close inspection. | e31, e32, e33, e44, e34 |  |
| 8 | 92.7-101.3 | 19 | dropped after repair: Unverified title-only claim (astronaut). Fix: remove claims taken only from the title |  |  |  |
| 9 | 101.3-109.9 | 19 | dropped after repair: Unverified title-only claim (astronaut). Fix: remove claims taken only from the title |  |  |  |

### Cue history (script → verify → repair)

- gap 0 · script: "In the space station, the astronaut in a black shirt and blue gloves tends green plants inside the illuminated growth chamber." → Unverified title-only claim (astronaut, space). Fix: remove claims taken only from the title
- gap 0 · repair_1: "In the space station, the astronaut in a black shirt and blue gloves tends green plants inside the illuminated growth chamber." → Unverified title-only claim (astronaut, space). Fix: remove claims taken only from the title
- gap 0 · repair_2: "In the space station, the astronaut in a black shirt and blue gloves tends green plants inside the illuminated growth chamber." → Unverified title-only claim (astronaut, space). Fix: remove claims taken only from the title
- gap 0 · drop: → Unverified title-only claim (astronaut, space). Fix: remove claims taken only from the title
- gap 1 · script: "He checks the control panel, then leaves the chamber area." → ok
- gap 2 · script: "The astronaut returns, handling a white cable and black object near the chamber window." → Unverified title-only claim (astronaut). Fix: remove claims taken only from the title
- gap 2 · repair_1: "The astronaut returns, handling a white cable and black object near the chamber window." → Unverified title-only claim (astronaut). Fix: remove claims taken only from the title
- gap 2 · repair_2: "The person in a black shirt and blue gloves handles a white cable and black object near the chamber window." → Banned phrasing: generic "Person" opener or subject. Fix: use the cast descriptor or a pronoun
- gap 2 · rescue: "The person in a black shirt and blue gloves handles a white cable and black object near the chamber window." → Banned phrasing: generic "Person" opener or subject. Fix: use the cast descriptor or a pronoun
- gap 3 · script: "He reaches in again with both gloved hands to adjust the plants." → ok
- gap 4 · script: "The astronaut operates the control panel and steps back, exiting the frame." → Unverified title-only claim (astronaut). Fix: remove claims taken only from the title
- gap 4 · repair_1: "The astronaut operates the control panel and steps back, exiting the frame." → Unverified title-only claim (astronaut). Fix: remove claims taken only from the title
- gap 4 · repair_2: "The person in a black shirt and blue gloves operates the control panel and steps back, exiting the frame." → Banned phrasing: generic "Person" opener or subject. Fix: use the cast descriptor or a pronoun
- gap 4 · rescue: "The person in a black shirt and blue gloves operates the control panel and steps back, exiting the frame." → Banned phrasing: generic "Person" opener or subject. Fix: use the cast descriptor or a pronoun
- gap 5 · script: "A harvested red chili pepper appears on a black board labeled WEST INDIAN." → ok
- gap 6 · script: "The astronaut presses the pepper flat, then photographs it with a black camera." → Unverified title-only claim (astronaut). Fix: remove claims taken only from the title
- gap 6 · repair_1: "The astronaut presses the pepper flat, then photographs it with a black camera." → Unverified title-only claim (astronaut). Fix: remove claims taken only from the title
- gap 6 · repair_2: "The person presses the pepper flat, then photographs it with a black camera." → Banned phrasing: generic "Person" opener or subject. Fix: use the cast descriptor or a pronoun
- gap 6 · rescue: "The person presses the pepper flat, then photographs it with a black camera." → Banned phrasing: generic "Person" opener or subject. Fix: use the cast descriptor or a pronoun
- gap 7 · script: "Crew members gather, passing the small green plant for close inspection." → ok
- gap 8 · script: "The blue-shirted astronaut leans in, touching the leaves while others watch." → Unverified title-only claim (astronaut). Fix: remove claims taken only from the title
- gap 8 · repair_1: "The blue-shirted astronaut leans in, touching the leaves while others watch." → Unverified title-only claim (astronaut). Fix: remove claims taken only from the title
- gap 8 · repair_2: "The blue-shirted astronaut leans in, touching the leaves while others watch." → Unverified title-only claim (astronaut). Fix: remove claims taken only from the title
- gap 8 · drop: → Unverified title-only claim (astronaut). Fix: remove claims taken only from the title
- gap 9 · script: "The black-gloved astronaut bites the chili pepper, grimacing as he chews." → Unverified title-only claim (astronaut). Fix: remove claims taken only from the title
- gap 9 · repair_1: "The black-gloved astronaut bites the chili pepper, grimacing as he chews." → Unverified title-only claim (astronaut). Fix: remove claims taken only from the title
- gap 9 · repair_2: "The black-gloved astronaut bites the chili pepper, grimacing as he chews." → Unverified title-only claim (astronaut). Fix: remove claims taken only from the title
- gap 9 · drop: → Unverified title-only claim (astronaut). Fix: remove claims taken only from the title

## Issues

- Establishing gap 0 has no verified cue
- Coverage guard: 7 of 10 narratable gaps narrated (70 % excluding silent-by-choice; target 75 %)
