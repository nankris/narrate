# Narrate director trace (v2)

Clip: `cooking_roti_0028-0148.mp4` · 119.9 s · provider `nebius` · Ultra calls 4/6 · cost $0.0406

## Run summary

- **Model calls:** Ultra 4/6 · Super VL 20 · Nano tighten 17
- **Cost:** $0.0406 (Ultra $0.0221, timeline $0.0121, verify $0.0036, Nano $0.0006)
- **Cues:** 11 committed of 12 narratable gaps · average budget use 95 % · repairs 2 · Nano-tightened 2 · within word tolerance 1
- **Silent by choice:** none
- **Dropped:** gap 7 (dropped (still over budget after Nano tighten and Ultra repair): over budget: 6 words, max)
- **Round 7 robustness:** punctuation fixed 0 · final pass rescued 1 (soft-kept 0, length fallback 1) · failed silence rescues back to silent 0
- **Coverage:** 11/12 narratable gaps narrated (92 %; 92 % excluding 0 silent by choice; target 75 %)
- **Video title (UNVERIFIED user context, never evidence):** “How To Make Soft Layered Roti - Paratha”

## Stages

| stage | model(s) | calls | tokens in / out | cost $ | s | output |
|---|---|---|---|---|---|---|
| ✓ gaps | — | 0 | 0 / 0 | 0.0000 | 2.5 | 12 narratable slots of 13, 12 long enough; detector silero-onnx; speech 37%; measured voice wps en 3.732 hi 5.2; English budgets at 2.6 words/s (natural narrator), fit judged by measured seconds |
| ✓ shots | — | 0 | 0 / 0 | 0.0000 | 1.6 | 11 shot cuts; 10 perception windows of ~12 s 0-12s, 12-24s, 24-36s, 36-48s, 48-60s, 60-72s, 72-84s, 84-96s, 96-108s, 108-120s; est. Super VL timeline cost $0.0283 (upper bound from config prices) |
| ✓ scene | Nemotron-3.5-Super-VL | 1 | 2359 / 169 | 0.0009 | 4.4 | setting: Indoor kitchen counter with white wooden surface and flour-dusted mat. / people: Person wearing black apron and striped long-sleeve shirt., kneading dough, rolling dough balls, rolling flat dough. / activity: mixing and shaping dough for bread or buns. / ingredients: flour, oil / tools: woo |
| ✓ timeline | Nemotron-3.5-Super-VL | 10 | 25893 / 3578 | 0.0110 | 52.2 | 37 events from 10 windows ({'video': 10, 'absolute': 10}); 26 with subtitles (speech, never read) |
| ✓ zoom | Nemotron-3.5-Super-VL | 2 | 3025 / 195 | 0.0011 | 5.0 | 1 zoom looks (10-12s mixing dough in wooden bowl): 1 new events ['e38'] |
| ✓ bible | Nemotron-3-Ultra-550b-a55b | 1 | 4311 / 1046 | 0.0074 | 4.5 | place: home kitchen / setting: Indoor kitchen counter with white wooden surface and flour-dusted silicone mat. / cast: the cook / goal: soft layered roti (paratha) / story: The cook mixes flour and water, kneads in oil, divides the dough into balls, rests them covered, then rolls each ball into a thin circle, brushes with oil and flour, coils it into a spiral, and finally flattens the spirals into |
| ✓ cast_look | Nemotron-3.5-Super-VL | 2 | 4296 / 94 | 0.0014 | 6.0 | the cook: woman |
| ✓ assign | — | 0 | 0 / 0 | 0.0000 | 0.0 | 11 gaps carry a story beat; 22 of 38 events inside narratable gaps; 16 in speech (context only); per gap {1: 5, 2: 2, 3: 1, 4: 1, 5: 2, 6: 1, 7: 1, 8: 2, 9: 1, 10: 1, 11: 3, 12: 2} |
| ✓ script | Nemotron-3-Ultra-550b-a55b | 1 | 8095 / 543 | 0.0097 | 64.8 | 12 gaps scripted in one call: {'pending': 8, 'failed': 4} |
| ✓ tighten | NVIDIA-Nemotron-3-Nano-30B-A3B | 8 | 2882 / 457 | 0.0003 | 285.1 | over-budget cues shortened by Nano (one cue per call, up to 3 options, <= 2 attempts): {'rejected': 5, 'still_over': 4} |
| ✓ verify | Nemotron-3.5-Super-VL | 2 | 6019 / 488 | 0.0022 | 68.1 | 8 cues checked on stills inside their gaps: {'supported': 8} |
| ✓ repair_1 | Nemotron-3-Ultra-550b-a55b | 1 | 2446 / 191 | 0.0030 | 21.5 | round 1: 4 failed cues sent to Ultra: {'failed': 4} |
| ✓ tighten_1 | NVIDIA-Nemotron-3-Nano-30B-A3B | 7 | 2525 / 386 | 0.0002 | 41.8 | over-budget cues shortened by Nano (one cue per call, up to 3 options, <= 2 attempts): {'pending': 2, 'rejected': 4, 'still_over': 2} |
| ✓ verify_1 | Nemotron-3.5-Super-VL | 1 | 1678 / 116 | 0.0006 | 3.7 | 2 cues checked on stills inside their gaps: {'supported': 2} |
| ✓ repair_2 | Nemotron-3-Ultra-550b-a55b | 1 | 1679 / 93 | 0.0020 | 10.0 | round 2: 2 failed cues sent to Ultra: {'failed': 1, 'pending': 1} |
| ✓ tighten_2 | NVIDIA-Nemotron-3-Nano-30B-A3B | 2 | 714 / 97 | 0.0001 | 11.5 | over-budget cues shortened by Nano (one cue per call, up to 3 options, <= 2 attempts): {'rejected': 2, 'still_over': 1} |
| ✓ verify_2 | Nemotron-3.5-Super-VL | 1 | 1032 / 58 | 0.0004 | 2.5 | 1 cues checked on stills inside their gaps: {'contradicted': 1} |
| ✓ rescue | Nemotron-3.5-Super-VL | 1 | 1036 / 58 | 0.0004 | 2.2 | final pass (no Ultra): 0 Nano strikes; {'verified': 1, 'committed': 1}; soft-kept 0, length fallback 1 |
| ✓ render | — | 0 | 0 / 0 | 0.0000 | 2.4 | 11 cues rendered (en: 10); 0 gaps silent by choice |

## Scene bible

- **Place:** home kitchen · **Goal:** soft layered roti (paratha)
- **Setting:** Indoor kitchen counter with white wooden surface and flour-dusted silicone mat.
- **Cast:** the cook (wearing black apron and striped long-sleeve shirt; apparent gender: woman (clearly visible at 36 s: face and hair visible at 36.2s, same striped shirt and black))
- **Story:** The cook mixes flour and water, kneads in oil, divides the dough into balls, rests them covered, then rolls each ball into a thin circle, brushes with oil and flour, coils it into a spiral, and finally flattens the spirals into round rotis 
- **Objects:** flour, lukewarm water, oil, wooden bowl, glass pitcher, small white bowl, small glass dish, silicone baking mat, wooden rolling pin, spoon, knife, brown bowl, white bowl (lid)
- **Subtitles present (never read):** True
- **Beats:** 0s The cook mixes flour and lukewarm water in a wooden bowl to form a shaggy dough. (hydrates the flour so gluten can develop) [e1, e2, e3, e4, e38, e5]; 12s Oil is poured in and the dough is kneaded into a smooth, cohesive ball. (the oil tenderizes the dough and the kneading builds structure) [e6, e7, e8, e9]; 24s A second splash of oil is worked in and the dough is finished as a single round ball. (ensures the dough is supple before portioning) [e10, e11, e12]; 36s The dough is turned onto a floured mat, cut into pieces, and each piece is rolled into a small ball. (creates even portions for the layered rotis) [e13, e14, e15]; 48s Each ball is pressed flat, rolled into a long thin oval, brushed with oil, dusted with flour, folded in half, and coiled (the oil-flour layers and spiral coil create the signature flaky layers) [e16, e17, e18, e19, e20, e21]; 84s The spirals are placed in a brown bowl, covered with a white bowl, and left to rest. (resting relaxes the gluten so the spirals can be rolled thin without shrinking b) [e26, e27, e28, e29]; 96s The cover is lifted to reveal six risen dough spirals. (shows the dough has relaxed and puffed slightly during the rest) [e30, e31]; 102s A spiral is floured and rolled out into a thin, even circle—the finished roti ready for the pan. (final flattening turns the coiled layers into a flat bread that will puff when c) [e32, e33, e34, e35, e36, e37]
- **Object names:** white bowl (lid) (not white bowl; from 90s)
- **Looked for again:** —
- **Beats per gap:** gap 1: The cook mixes flour and lukewarm water in a wooden bowl to form a shaggy dough. (hydrates the flour so gluten can develop); Oil is poured in and the dough is kneaded into a smooth, cohesive ball. (the oil tenderizes the dough and the kneading builds structure); gap 2: Oil is poured in and the dough is kneaded into a smooth, cohesive ball. (the oil tenderizes the dough and the kneading builds structure); gap 3: A second splash of oil is worked in and the dough is finished as a single round ball. (ensures the dough is supple before portioning); gap 4: The dough is turned onto a floured mat, cut into pieces, and each piece is rolled into a small ball. (creates even portions for the layered rotis); gap 5: Each ball is pressed flat, rolled into a long thin oval, brushed with oil, dusted with flour, folded in half, and coiled (the oil-flour layers and spiral coil create the signature flaky layers); gap 6: Each ball is pressed flat, rolled into a long thin oval, brushed with oil, dusted with flour, folded in half, and coiled (the oil-flour layers and spiral coil create the signature flaky layers); gap 8: The spirals are placed in a brown bowl, covered with a white bowl, and left to rest. (resting relaxes the gluten so the spirals can be rolled thin without shrinking b); gap 9: The spirals are placed in a brown bowl, covered with a white bowl, and left to rest. (resting relaxes the gluten so the spirals can be rolled thin without shrinking b); gap 10: The cover is lifted to reveal six risen dough spirals. (shows the dough has relaxed and puffed slightly during the rest); gap 11: A spiral is floured and rolled out into a thin, even circle—the finished roti ready for the pan. (final flattening turns the coiled layers into a flat bread that will puff when c); gap 12: A spiral is floured and rolled out into a thin, even circle—the finished roti ready for the pan. (final flattening turns the coiled layers into a flat bread that will puff when c)

## Timeline (38 events; ~~refuted~~)

| id | time | gap | what | on screen | said |
|---|---|---|---|---|---|
| e1 | 0.0-2.0 | speech | A person wearing a black apron and striped long-sleeve shirt mixes white flour inside a large wooden bowl with their right hand while holding the bowl steady with their left hand. |  |  |
| e2 | 2.0-6.0 | speech | The person picks up a clear glass pitcher and pours lukewarm water into the wooden bowl of flour, then sets the pitcher down. |  | Use lukewarm water and add it just as much as you need |
| e3 | 6.0-8.0 | 1 | The person uses their right hand to mix the water into the flour inside the wooden bowl. |  |  |
| e4 | 8.0-10.0 | 1 | The person picks up the glass pitcher again and pours more water into the bowl while continuing to mix with their right hand. |  |  |
| e38 | 10.0-12.0 | 1 | A person in a black apron and checkered shirt mixes flour in a wooden bowl with their right hand while steadying the bowl with their left hand. |  |  |
| e5 | 10.0-12.0 | 1 | The person mixes the flour and water together with their right hand inside the wooden bowl as the dough begins to come together. |  |  |
| e6 | 12.0-15.0 | 1 | The person pours oil from a small white bowl onto the dough in the wooden bowl while the dough is nearly done. |  | nearly done, |
| e7 | 15.0-18.0 | 2 | The person kneads the dough with both hands inside the wooden bowl, incorporating the oil into the mixture. |  | add a little bit of oil |
| e8 | 18.0-21.0 | 2 | The person continues to knead the dough, pressing and folding it within the wooden bowl. |  | and then knead it |
| e9 | 21.0-24.0 | speech | The person finishes kneading the dough, which now forms a cohesive ball in the wooden bowl. |  | for a few minutes. |
| e10 | 24.0-27.0 | speech | The person pours oil from a small glass dish into the wooden bowl containing the dough ball, then sets the empty dish aside. |  | teaspoon of oil |
| e11 | 27.0-31.0 | 3 | The person presses and folds the dough inside the wooden bowl with a gloved hand, incorporating the oil into the dough. |  |  |
| e12 | 31.0-36.0 | speech | The person finishes shaping the dough into a smooth round ball in the wooden bowl as a young child watches from the right side of the frame. |  | Our dough is ready now I'm using a |
| e13 | 36.0-39.0 | speech | The person sprinkles flour from both hands onto the silicone mat, then places a large piece of dough in the center and presses it flat with both palms. |  | sprinkling some flour on it |
| e14 | 39.0-43.0 | speech | The person uses a knife to cut the flattened dough into several smaller pieces and then rolls each piece into a ball between their palms. |  | divide the dough into smaller balls |
| e15 | 43.0-48.0 | 4 | The person arranges the finished dough balls in a row on the left side of the mat and continues rolling the remaining piece into a smooth round ball. |  | balls |
| e16 | 48.0-51.0 | 5 | The person places a dough ball in the center of the floured mat and presses it flat with both palms to begin shaping it. |  |  |
| e17 | 51.0-55.0 | 5 | The person uses a wooden rolling pin to roll the flattened dough into a long, thin oval shape on the mat. |  |  |
| e18 | 55.0-60.0 | speech | The person continues rolling the dough back and forth to make it as thin as possible, then sets the rolling pin aside and picks up a spoon with oil. |  | Roll the dough into rotis as possible |
| e19 | 60.0-63.0 | speech | The person brushes oil over the surface of the long, flattened dough using a spoon, spreading it evenly across the dough on the silicone mat. |  | You can use oil of your choice, |
| e20 | 63.0-67.0 | speech | The person sprinkles flour from a glass dish onto the oiled dough and rubs it in with their hands. |  | or even butter if you like more flour |
| e21 | 67.0-72.0 | 6 | The person folds the long strip of dough in half lengthwise and begins rolling it up tightly into a spiral shape. |  | Just roll |
| e22 | 72.0-75.0 | speech | The person continues rolling the long strip of dough into a tight spiral on the floured mat, using both hands to tuck and press the dough as it coils. |  | As shown |
| e23 | 75.0-78.0 | 7 | The person finishes forming the spiral and places the rolled dough ball onto the mat next to the other prepared dough balls. |  | Now I'll |
| e24 | 78.0-81.0 | speech | The person picks up a new portion of dough and begins rolling it into a long strip with their palms on the mat. |  | like a cinnamon |
| e25 | 81.0-83.9 | 8 | The person continues rolling the dough strip back and forth to elongate it, preparing it for the next shaping step. |  | roll |
| e26 | 83.9-86.9 | 8 | The person places the rolled dough ball into a brown bowl already containing several other dough balls. |  | Add a little |
| e27 | 86.9-89.9 | speech | The person presses down on the dough balls in the bowl with both hands to arrange them. |  | oil on top |
| e28 | 89.9-92.9 | 9 | The person places a white bowl upside down over the brown bowl to cover the dough. |  | Cover it and let it rest |
| e29 | 92.9-95.9 | speech | The person adjusts the white bowl covering the dough to ensure it sits securely. |  | for half |
| e30 | 95.9-98.9 | speech | The person lifts the white bowl off the brown bowl, revealing six risen dough balls inside, then sets the white bowl aside. |  | an hour |
| e31 | 98.9-101.9 | 10 | The person gestures over the bowl of risen dough balls with both hands, then reaches toward a glass dish of flour. |  | I let it rest to 35 minutes |
| e32 | 101.9-104.9 | speech | The person takes one dough ball from the brown bowl, places it on the floured mat, and dusts it with flour from the glass dish. |  | Now we'll make |
| e33 | 104.9-107.9 | 11 | The person uses a wooden rolling pin to flatten the dough ball into a round disc on the mat. |  | the rotis |
| e34 | 107.9-110.9 | 11 | The person rolls the dough back and forth with a wooden rolling pin on a floured silicone mat, flattening it into a larger round disc. |  |  |
| e35 | 110.9-113.9 | 11 | The person lifts the rolling pin, flips the dough over with both hands, and places it back down on the mat. |  |  |
| e36 | 113.9-116.9 | 12 | The person rolls the flipped dough again with the wooden rolling pin, expanding it into a thin, even circle. |  |  |
| e37 | 116.9-119.9 | 12 | The person finishes rolling and the fully flattened round dough rests on the mat as the text "Roll the rotis" appears on screen. | Roll the rotis |  |

## Script, verification and repairs

| gap | time | words | outcome | English | evidence | Hindi |
|---|---|---|---|---|---|---|
| 1 | 6.2-15.8 | 19/19 | supported | In a home kitchen, the cook mixes flour and lukewarm water in a wooden bowl, then pours in oil. | e3, e4, e38, e5, e6 |  |
| 2 | 15.8-21.6 | 13/12 | supported | She kneads the dough with both hands until it forms a smooth ball. | e7, e8 |  |
| 3 | 25.6-31.8 | 12/13 | supported | A second splash of oil is pressed and folded into the dough. | e11 |  |
| 4 | 42.4-48.8 | 13/13 | supported | The cook cuts the dough into pieces and rolls each into a ball. | e15 |  |
| 5 | 48.8-54.4 | 12/12 | supported | A ball is pressed flat and rolled into a long thin oval. | e16, e17 |  |
| 6 | 67.2-71.4 | 8/8 | supported | The cook folds the strip into a spiral. | e21 |  |
| 7 | 75.6-78.0 | 4 | dropped (still over budget after Nano tighten and Ultra repair): over budget: 6 words, max 4. Fix: cut at least 2 words (keep the subject and the main action; drop a secondary action, colours or positions) |  |  |  |
| 8 | 80.8-88.0 | 10/15 | supported | Another strip is rolled long and coiled into a spiral. | e25, e26 |  |
| 9 | 90.1-93.1 | 5/5 | supported | The cook covers the bowl. | e28 |  |
| 10 | 99.9-103.2 | 8/6 | supported | The lid lifts to show six dough spirals. | e31 |  |
| 11 | 105.6-112.7 | 11/15 | supported | A floured ball is rolled out into a thin round disc. | e33, e34, e35 |  |
| 12 | 112.7-119.8 | 11/15 | supported | The dough is flipped and rolled into a final even circle. | e36, e37 |  |

### Cue history (script → verify → repair)

- gap 1 · script: "In a home kitchen, the cook mixes flour and lukewarm water in a wooden bowl, then pours in oil." → ok
- gap 2 · script: "She kneads the dough with both hands until it forms a smooth ball." → ok
- gap 3 · script: "A second splash of oil is pressed and folded into the dough." → ok
- gap 4 · script: "The cook cuts the dough into pieces and rolls each into a ball." → ok
- gap 5 · script: "A ball is pressed flat and rolled into a long thin oval." → ok
- gap 6 · script: "The strip is folded in half and rolled into a tight spiral." → over budget: 12 words, max 8. Fix: cut at least 4 words (keep the subject and the main action; drop a secondary action, colours or positions)
- gap 6 · tighten: "The strip is folded and rolled into a tight spiral." → over budget: 10 words, max 8. Fix: cut at least 2 words (keep the subject and the main action; drop a secondary action, colours or positions)
- gap 6 · tighten: "The strip is folded and rolled into a tight spiral." → not shorter (10 words, was 10); rejected
- gap 6 · repair_1: "The cook folds the strip and rolls it into a spiral." → over budget: 11 words, max 8. Fix: cut at least 3 words (keep the subject and the main action; drop a secondary action, colours or positions)
- gap 6 · tighten_1: "The cook folds the strip into a spiral." → ok
- gap 7 · script: "The spiral is set aside on the mat." → over budget: 8 words, max 4. Fix: cut at least 4 words (keep the subject and the main action; drop a secondary action, colours or positions)
- gap 7 · tighten: "The spiral is set aside on the mat." → not shorter (8 words, was 8); rejected
- gap 7 · tighten: "The spiral is set aside on the mat." → not shorter (8 words, was 8); rejected
- gap 7 · repair_1: "The cook sets the spiral aside." → over budget: 6 words, max 4. Fix: cut at least 2 words (keep the subject and the main action; drop a secondary action, colours or positions)
- gap 7 · tighten_1: "The cook sets the spiral aside." → not shorter (6 words, was 6); rejected
- gap 7 · tighten_1: "The cook sets the spiral aside." → not shorter (6 words, was 6); rejected
- gap 7 · repair_2: "The cook sets the spiral aside." → over budget: 6 words, max 4. Fix: cut at least 2 words (keep the subject and the main action; drop a secondary action, colours or positions)
- gap 7 · tighten_2: "The cook sets the spiral aside." → not shorter (6 words, was 6); rejected
- gap 7 · tighten_2: "The cook sets the spiral aside." → not shorter (6 words, was 6); rejected
- gap 7 · drop: → over budget: 6 words, max 4. Fix: cut at least 2 words (keep the subject and the main action; drop a secondary action, colours or positions)
- gap 8 · script: "Another strip is rolled long and coiled into a spiral." → ok
- gap 9 · script: "The white bowl covers the brown bowl securely." → over budget: 8 words, max 5. Fix: cut at least 3 words (keep the subject and the main action; drop a secondary action, colours or positions)
- gap 9 · tighten: "The white bowl covers the brown bowl securely." → not shorter (8 words, was 8); rejected
- gap 9 · tighten: "The white bowl covers the brown bowl." → over budget: 7 words, max 5. Fix: cut at least 2 words (keep the subject and the main action; drop a secondary action, colours or positions)
- gap 9 · tighten: "The white bowl covers the brown bowl." → not shorter (7 words, was 7); rejected
- gap 9 · repair_1: "The cook covers the brown bowl with the white bowl." → over budget: 10 words, max 5. Fix: cut at least 5 words (keep the subject and the main action; drop a secondary action, colours or positions)
- gap 9 · tighten_1: "The cook covers the bowl with the bowl." → over budget: 8 words, max 5. Fix: cut at least 3 words (keep the subject and the main action; drop a secondary action, colours or positions)
- gap 9 · tighten_1: "The cook covers the bowl." → ok
- gap 10 · script: "The lid lifts to show six risen dough spirals." → over budget: 9 words, max 6. Fix: cut at least 3 words (keep the subject and the main action; drop a secondary action, colours or positions)
- gap 10 · tighten: "The lid lifts to show six risen dough spirals." → not shorter (9 words, was 9); rejected
- gap 10 · tighten: "The lid lifts to show six dough spirals." → over budget: 8 words, max 6. Fix: cut at least 2 words (keep the subject and the main action; drop a secondary action, colours or positions)
- gap 10 · tighten: "The lid lifts to show six dough spirals." → not shorter (8 words, was 8); rejected
- gap 10 · repair_1: "The cook lifts the lid to show six dough spirals." → over budget: 10 words, max 6. Fix: cut at least 4 words (keep the subject and the main action; drop a secondary action, colours or positions)
- gap 10 · tighten_1: "The cook lifts the lid to show six dough spirals." → not shorter (10 words, was 10); rejected
- gap 10 · tighten_1: "The cook lifts the lid to show six dough spirals." → not shorter (10 words, was 10); rejected
- gap 10 · repair_2: "The cook lifts the lid." → ok
- gap 10 · verify: → verifier (contradicted) on frames [100.44, 101.57]: "lifts the lid" is wrong; The frames show a hand reaching into a bowl of dough balls and another hand in a container of flour; no lid is lifted.. Fix: remove or correct only "lifts the lid" and keep the rest of the cue
- gap 10 · rescue: "The lid lifts to show six dough spirals." → over budget: 8 words, max 6. Fix: cut at least 2 words (keep the subject and the main action; drop a secondary action, colours or positions)
- gap 11 · script: "A floured ball is rolled out into a thin round disc." → ok
- gap 12 · script: "The dough is flipped and rolled into a final even circle." → ok
