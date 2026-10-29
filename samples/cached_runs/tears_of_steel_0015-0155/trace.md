# Narrate director trace (v2)

Clip: `tears_of_steel_0015-0155.mp4` · 100.0 s · provider `nebius` · Ultra calls 3/6 · cost $0.0345

## Run summary

- **Model calls:** Ultra 3/6 · Super VL 15 · Nano tighten 1
- **Cost:** $0.0345 (Ultra $0.0200, timeline $0.0109, verify $0.0026, Nano $0.0000)
- **Cues:** 8 committed of 8 narratable gaps · average budget use 91 % · repairs 1 · Nano-tightened 1 · within word tolerance 3
- **Silent by choice:** none
- **Dropped:** none
- **Round 7 robustness:** punctuation fixed 2 · final pass rescued 0 (soft-kept 0, length fallback 0) · failed silence rescues back to silent 0
- **Coverage:** 8/8 narratable gaps narrated (100 %; 100 % excluding 0 silent by choice; target 75 %)

## Stages

| stage | model(s) | calls | tokens in / out | cost $ | s | output |
|---|---|---|---|---|---|---|
| ✓ gaps | — | 0 | 0 / 0 | 0.0000 | 2.5 | 8 narratable slots of 9, 8 long enough; detector silero-onnx; speech 27%; measured voice wps en 3.635 hi 5.2; English budgets at 2.6 words/s (natural narrator), fit judged by measured seconds |
| ✓ shots | — | 0 | 0 / 0 | 0.0000 | 1.1 | 18 shot cuts; 9 perception windows of ~12 s 0-10s, 10-22s, 22-33s, 33-44s, 44-55s, 55-67s, 67-77s, 77-89s, 89-100s; est. Super VL timeline cost $0.0241 (upper bound from config prices) |
| ✓ scene | Nemotron-3.5-Super-VL | 1 | 2287 / 243 | 0.0009 | 4.2 | setting: Industrial outdoor area with smokestacks and a canal bridge lined with buildings. / people: Man in black leather jacket standing on a bridge., gesturing with both hands while talking.; Person with reddish-brown hair in blue jacket and dark vest on the bridge., leaning on a railing and holdi |
| ✓ timeline | Nemotron-3.5-Super-VL | 9 | 22084 / 3299 | 0.0096 | 34.3 | 33 events from 9 windows ({'video': 9, 'absolute': 9}); 0 with subtitles (speech, never read) |
| ✓ bible | Nemotron-3-Ultra-550b-a55b | 1 | 3888 / 1729 | 0.0091 | 6.3 | place: industrial city / setting: Industrial city with smokestacks, a canal bridge, and a hovering airship / cast: a man in a black leather jacket, a woman in a blue jacket and dark vest, a person with curly hair and glasses, a man with a mechanical eye, a shooter in a dark jacket, an older person with white hair / goal: ? / story: Two people converse on a bridge in an industrial city; forty years |
| ✓ relook | Nemotron-3.5-Super-VL | 2 | 3982 / 132 | 0.0013 | 9.6 | 2 focused re-looks (10-22s the device with a long handle the woman holds — its shape an; 58-62s the two figures seated at the table with a candle — their fa): 1 new events ['e34'] |
| ✓ assign | — | 0 | 0 / 0 | 0.0000 | 0.0 | 7 gaps carry a story beat; 25 of 34 events inside narratable gaps; 9 in speech (context only); per gap {0: 3, 2: 2, 3: 2, 4: 3, 5: 3, 6: 5, 7: 3, 8: 4} |
| ✓ script | Nemotron-3-Ultra-550b-a55b | 1 | 7323 / 472 | 0.0087 | 66.7 | 8 gaps scripted in one call: {'pending': 7, 'failed': 1} |
| ✓ tighten | NVIDIA-Nemotron-3-Nano-30B-A3B | 1 | 359 / 48 | 0.0000 | 16.4 | over-budget cues shortened by Nano (one cue per call, up to 3 options, <= 2 attempts): {'pending': 1} |
| ✓ verify | Nemotron-3.5-Super-VL | 2 | 6013 / 489 | 0.0022 | 20.6 | 8 cues checked on stills inside their gaps: {'supported': 7, 'contradicted': 1} |
| ✓ repair_1 | Nemotron-3-Ultra-550b-a55b | 1 | 1879 / 91 | 0.0022 | 9.2 | round 1: 1 failed cues sent to Ultra: {'pending': 1} |
| ✓ verify_1 | Nemotron-3.5-Super-VL | 1 | 1108 / 75 | 0.0004 | 1.7 | 1 cues checked on stills inside their gaps: {'supported': 1} |
| ✓ render | — | 0 | 0 / 0 | 0.0000 | 2.8 | 8 cues rendered (en: 8); 0 gaps silent by choice |

## Scene bible

- **Place:** industrial city · **Goal:** —
- **Setting:** Industrial city with smokestacks, a canal bridge, and a hovering airship
- **Cast:** a man in a black leather jacket (gestures with both hands while talking on the bridge; gender male); a woman in a blue jacket and dark vest (leans on the bridge railing holding a device with a long handle; reddish-brown hair; gender female); a person with curly hair and glasses (looks focused behind equipment emitting pink and green light; gender not visible); a man with a mechanical eye (leans over the brain-shaped object on a table; gender male); a shooter in a dark jacket (aims a large scoped rifle from a rooftop; gender not visible); an older person with white hair (lies on the rooftop beside the shooter near candles and bags; gender not visible)
- **Story:** Two people converse on a bridge in an industrial city; forty years later a simulation activates a brain-shaped object under energy rings; a title card reads TEARS OF STEEL; then a shooter on a rooftop aims at a massive airship firing weapon
- **Objects:** bridge railing, brain-shaped object, glass dome, large futuristic airship, city rooftops, trees, control panel with holographic overlays, newspaper, scoped rifle, candles, bags
- **Subtitles present (never read):** False
- **Beats:** 0s The film opens on glowing industrial pipes before revealing the sprawling cityscape (establishes the industrial setting) [e1, e2, e3]; 10s A man and a woman talk and gesture on a canal bridge (introduces the two characters in the present day) [e4]; 24s The scene jumps to a dark interior where orange and blue wireframe figures face each other (signals a shift to a future or virtual space) [e6]; 26s A time card reads 40 YEARS LATER (marks the temporal leap) [e7]; 33s A hand operates a holographic control panel, shifting the interface to a complex grid (initiates the simulation sequence) [e11]; 38s The word SIMULATION appears behind two people at a workstation with glowing equipment (confirms the simulation has begun) [e13]; 44s A brain-shaped object rotates on a platform surrounded by purple energy rings (climax of the simulation — the brain object is activated) [e14]; 47s The screen fades to black and the title TEARS OF STEEL appears (ends the simulation sequence and titles the film) [e16, e17]; 55s An airship hovers over the industrial city as smoke rises from smokestacks (re-establishes the city in the later time period) [e18]; 62s A close-up shows a newspaper headline reading ROBOTICIST KILLER ROBOTS (hints at the conflict driving the later events) [e20]; 67s A shooter on a rooftop aims a scoped rifle at the distant airship (sets up the confrontation) [e21, e22, e23, e24]; 89s Bright flashes erupt from the airship as it fires weapons over the city (the airship attacks, escalating the conflict) [e30, e31, e32, e33]
- **Object names:** brain-shaped object (not brain-shaped cake, brain object; from 44s); large futuristic airship (not large aircraft, floating mechanical object, mechanical airship; from 55s); scoped rifle (not large scoped rifle, futuristic rifle; from 67s)
- **Looked for again:** 10-22s the device with a long handle the woman holds — its shape and any readout; 58-62s the two figures seated at the table with a candle — their faces and what they are doing
- **Beats per gap:** gap 0: The film opens on glowing industrial pipes before revealing the sprawling cityscape (establishes the industrial setting); gap 2: A hand operates a holographic control panel, shifting the interface to a complex grid (initiates the simulation sequence); gap 3: The word SIMULATION appears behind two people at a workstation with glowing equipment (confirms the simulation has begun); A brain-shaped object rotates on a platform surrounded by purple energy rings (climax of the simulation — the brain object is activated); gap 4: The screen fades to black and the title TEARS OF STEEL appears (ends the simulation sequence and titles the film); An airship hovers over the industrial city as smoke rises from smokestacks (re-establishes the city in the later time period); gap 5: A close-up shows a newspaper headline reading ROBOTICIST KILLER ROBOTS (hints at the conflict driving the later events); A shooter on a rooftop aims a scoped rifle at the distant airship (sets up the confrontation); gap 6: A shooter on a rooftop aims a scoped rifle at the distant airship (sets up the confrontation); gap 8: Bright flashes erupt from the airship as it fires weapons over the city (the airship attacks, escalating the conflict)

## Timeline (34 events; ~~refuted~~)

| id | time | gap | what | on screen | said |
|---|---|---|---|---|---|
| e1 | 0.0-3.0 | 0 | A close-up view of large industrial pipes with bright light shining through them, creating a glowing effect. |  |  |
| e2 | 3.0-6.0 | 0 | The camera pulls back to reveal a sprawling industrial cityscape with smokestacks and a bridge under a bright sky. | This film is supported by the Netherlands Film Fund |  |
| e3 | 6.0-10.0 | 0 | The industrial skyline remains visible as the funding credit text fades away, leaving only the cityscape. |  |  |
| e34 | 10.0-12.0 | speech | The woman in the blue jacket and dark vest holds a device with a long handle in her right hand, extending it toward the man in the black leather jacket; the device has a claw-like end and no visible readout. |  |  |
| e4 | 10.0-12.2 | speech | A man in a black leather jacket and a woman in a blue jacket stand on a bridge railing, talking and gesturing with their hands as they face each other. |  |  |
| e5 | 22.2-24.2 | speech | A man in a black leather jacket and a woman in a blue jacket stand on a bridge railing, talking and gesturing with their hands as they face each other. |  |  |
| e6 | 24.2-26.2 | speech | The camera cuts to a dark, industrial interior where two glowing wireframe figures, one orange and one blue, stand facing each other. |  |  |
| e7 | 26.2-28.2 | speech | The text "40 YEARS LATER" appears in white capital letters over the dark industrial scene with the glowing figures. | 40 YEARS LATER |  |
| e8 | 28.2-30.2 | speech | The glowing orange and blue wireframe figures remain visible in the dark industrial space as the text fades. |  |  |
| e9 | 30.2-32.2 | speech | A green holographic interface with a grid and a triangular play symbol appears over the figures. |  |  |
| e10 | 32.2-33.3 | 2 | The green holographic interface continues to display over the dark industrial background with the figures. |  |  |
| e11 | 33.3-35.3 | 2 | A hand presses buttons on a control panel covered in green holographic overlays, causing the interface to shift and display new data. |  |  |
| e12 | 35.3-38.3 | speech | A person with curly hair and glasses looks forward with a focused expression while standing behind equipment emitting pink and green light. |  |  |
| e13 | 38.3-41.3 | 3 | Two people in white hoodies stand at a workstation with glowing green and pink equipment as the word "SIMULATION" appears in large letters behind them. | SIMULATION |  |
| e14 | 41.3-44.4 | 3 | A brain-shaped object sits on a rotating platform surrounded by purple energy rings and wires, with a person's face visible in the background. |  |  |
| e15 | 44.4-47.0 | speech | A man with a mechanical eye leans over a brain-shaped object on a table, surrounded by purple energy rings and wires, while another person's hands are visible on either side. |  |  |
| e16 | 47.0-50.0 | 4 | The screen fades to black and the title "TEARS OF STEEL" appears in metallic letters. | TEARS OF STEEL |  |
| e17 | 50.0-55.0 | 4 | The title "TEARS OF STEEL" remains centered on a black background. | TEARS OF STEEL |  |
| e18 | 55.0-58.0 | 4 | A wide shot shows an industrial city skyline with smokestacks emitting smoke and a large airship hovering above the buildings. |  |  |
| e19 | 58.0-62.0 | 5 | The camera moves inside a dark structure where two figures sit at a table with a candle between them, viewed through hanging cables. |  |  |
| e20 | 62.0-66.7 | 5 | A close-up shows a person holding a newspaper with the headline "ROBOTICIST KILLER ROBOTS" over their face while another hand rests nearby. | ROBOTICIST KILLER ROBOTS |  |
| e21 | 66.7-69.0 | 5 | A person in a blue jacket aims a large scoped rifle from behind a railing, looking through the scope at a distant target. |  |  |
| e22 | 69.0-72.0 | 6 | The view shifts to a circular scope showing a large, complex mechanical structure with multiple antennae and figures standing on it. |  |  |
| e23 | 72.0-75.0 | 6 | The mechanical structure, resembling a floating platform with many protrusions, hovers above a cityscape with red-roofed buildings. |  |  |
| e24 | 75.0-77.4 | 6 | The floating mechanical object drifts slowly over the dense urban area as the scope view remains fixed on it. |  |  |
| e25 | 77.4-79.0 | 6 | A close-up shows a person looking through the scope of a futuristic rifle, their eye visible beside the weapon as they aim. |  |  |
| e26 | 79.0-81.0 | 6 | Through the rifle scope, a large mechanical airship hovers above a cityscape with red-roofed buildings, its lights glowing. |  |  |
| e27 | 81.0-83.0 | 7 | The camera pulls back to reveal the shooter in a dark jacket lying on a rooftop, aiming the rifle toward the airship. |  |  |
| e28 | 83.0-85.0 | 7 | An older person with white hair lies on the rooftop beside the shooter, appearing to rest or sleep near candles and bags. |  |  |
| e29 | 85.0-88.9 | 7 | The view returns through the rifle scope to the airship hovering over the city, maintaining focus on the target. |  |  |
| e30 | 88.9-92.0 | 8 | Through a rifle scope, a large airship hovers over a city as bright flashes erupt from its side, indicating it is firing weapons. |  |  |
| e31 | 92.0-95.0 | 8 | The airship continues to fire as it tilts and moves across the sky above the rooftops. |  |  |
| e32 | 95.0-98.0 | 8 | The airship flies lower over the city, still emitting bright flashes from its weapons. |  |  |
| e33 | 98.0-100.0 | 8 | The airship passes over the cityscape, its lights and weapon flashes still visible through the scope. |  |  |

## Script, verification and repairs

| gap | time | words | outcome | English | evidence | Hindi |
|---|---|---|---|---|---|---|
| 0 | 0.1-9.1 | 20/19 | supported | Glowing industrial pipes fill the frame before pulling back to reveal a sprawling city of smokestacks and a canal bridge. | e1, e2, e3 |  |
| 2 | 32.5-34.9 | 3/4 | supported | The grid shifts. | e10, e11 |  |
| 3 | 39.0-45.6 | 16/14 | supported | The word SIMULATION appears behind two workers as a brain-shaped object rotates inside purple energy rings. | e13, e14 |  |
| 4 | 47.6-59.0 | 18/19 | supported | The title TEARS OF STEEL fades in on black, then an airship hovers over the smoking industrial city. | e16, e17, e18 |  |
| 5 | 59.0-69.8 | 21/19 | supported | A newspaper headline reads ROBOTICIST KILLER ROBOTS. A shooter in a dark jacket aims a scoped rifle from a rooftop railing. | e20, e21 |  |
| 6 | 69.8-80.4 | 10/19 | supported | Through the scope the massive airship drifts over red-roofed buildings. | e22, e23, e24 |  |
| 7 | 80.4-89.5 | 19/19 | supported | The shooter in a dark jacket lies prone on the roof. An older person with white hair rests nearby. | e27, e28, e29 |  |
| 8 | 89.5-99.9 | 15/19 | supported | Bright muzzle flashes erupt along the airship hull as it banks lower over the city. | e30, e31, e32, e33 |  |

### Cue history (script → verify → repair)

- gap 0 · script: "Glowing industrial pipes fill the frame before pulling back to reveal a sprawling city of smokestacks and a canal bridge." → ok
- gap 2 · script: "A hand shifts the holographic grid." → over budget: 6 words, max 4. Fix: cut at least 2 words (keep the subject and the main action; drop a secondary action, colours or positions)
- gap 2 · tighten: "A hand shifts the holographic grid." → not shorter (6 words, was 6); rejected
- gap 2 · tighten: "The grid shifts." → ok
- gap 3 · script: "The word SIMULATION appears behind two workers as a brain-shaped object rotates inside purple energy rings." → ok
- gap 4 · script: "The title TEARS OF STEEL fades in on black, then an airship hovers over the smoking industrial city." → ok
- gap 5 · script: "A newspaper headline reads ROBOTICIST KILLER ROBOTS. A shooter on a rooftop aims a scoped rifle at the airship." → ok
- gap 5 · verify: → verifier (contradicted) on frames [60.0, 64.33]: "A shooter on a rooftop aims a scoped rifle at the airship" is wrong; The 60.0s and 64.33s frames show a dark rooftop area with a person crouching, but no scoped rifle is visible and no airship is shown.. Fix: remove or correct only "A shooter on a rooftop aims a scoped rifle at the airship" and keep the rest of the cue
- gap 5 · repair_1: "A newspaper headline reads ROBOTICIST KILLER ROBOTS. A shooter in a dark jacket aims a scoped rifle from a rooftop railing." → ok
- gap 6 · script: "Through the scope the massive airship drifts over red-roofed buildings." → ok
- gap 7 · script: "The shooter in a dark jacket lies prone on the roof. An older person with white hair rests nearby." → ok
- gap 8 · script: "Bright muzzle flashes erupt along the airship hull as it banks lower over the city." → ok
