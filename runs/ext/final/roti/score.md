# Extended AD score

- Key-event coverage: 100.00%
- Action-step coverage: 50.60%
- Hallucinated claims: 17
- Chronology errors: 14
- Confusing parts explained: 75.00%
- Mean fluency: 4.62/5
- Maximum source span without a pause: 23.987 s
- Pauses inside speech: 0
- Pause at cut/speech boundary: 50.00%
- Total added time: 109.137 s
- Frame audit of judge flags: 1 contradicted, 5 uncertain, 14 supported on stills

## Cue windows

### Cue 1: [0.000, 0.500] s

A wooden mixing bowl holds flour on a white countertop. The cook, in a checkered shirt and black apron, mixes the flour with their right hand while steadying the bowl with their left.

Matched GT steps: none
Unsupported claims: A wooden mixing bowl holds flour on a white countertop; The cook, in a checkered shirt and black apron, mixes the flour with their right hand while steadying the bowl with their left
Chronology errors: The cook, in a checkered shirt and black apron, mixes the flour with their right hand while steadying the bowl with their left (Mixing flour in a wooden bowl occurs later in the video (around 15-20s), not at 0-0.5s. The shirt is striped, not checkered.)
Frame audit: SUPPORTED: A wooden mixing bowl holds flour on a white countertop (The stills show a wooden bowl containing white flour on a white, distressed countertop.); SUPPORTED: The cook, in a checkered shirt and black apron, mixes the flour with their right hand while steadying the bowl with their left (The stills show a person in a checkered shirt and black apron using their right hand to mix flour in the bowl while their left hand holds the bowl steady.)
Fluency: 4/5 — The cue is grammatically correct and flows naturally as spoken English, with clear sentence structure and appropriate vocabulary, despite factual inaccuracies.

### Cue 2: (0.500, 23.362] s

The cook pours lukewarm water from the glass pitcher into the flour and mixes it by hand, adding more water and mixing again. Then oil is poured from a small white bowl onto the nearly formed dough, and the cook kneads it with a gloved right hand until a cohesive ball forms.

Matched GT steps: event `evt1` (yes): Person puts on black glove on right hand; step `seg2.a1` (yes): Person puts on black glove on right hand while holding left wrist (15.85s).; step `seg2.a2` (yes): Person adjusts black glove on right hand (16s).; step `seg2.a3` (yes): Person holds gloved hand over bowl, preparing to mix dough (17s).; step `seg2.a4` (yes): Person begins mixing/kneading dough in wooden bowl with gloved hand (18-22s).; step `seg2.a5` (yes): Child appears watching nearby (23s).; step `seg2.a6` (partial): Person pours liquid (oil) from spoon into wooden bowl containing dough (24-26s).
Unsupported claims: The cook pours lukewarm water from the glass pitcher into the flour and mixes it by hand, adding more water and mixing again.; Then oil is poured from a small white bowl onto the nearly formed dough, and the cook kneads it with a gloved right hand until a cohesive ball forms.
Chronology errors: The cook pours lukewarm water from the glass pitcher into the flour and mixes it by hand, adding more water and mixing again. (This describes actions from an earlier segment (seg1, 0-15s) not visible in the current cue window (0.5-23.362s), which shows dough already formed on a silicone mat.); Then oil is poured from a small white bowl onto the nearly formed dough, and the cook kneads it with a gloved right hand until a cohesive ball forms. (The oil pouring (seg2.a6) occurs at 24-26s, after the cue window ends at 23.362s; the kneading (seg2.a4) occurs at 18-22s, before the oil, not after as the cue implies.)
Frame audit: SUPPORTED: The cook pours lukewarm water from the glass pitcher into the flour and mixes it by hand, adding more water and mixing again. (The stills show water being poured from a clear glass pitcher into a bowl of flour, the cook mixing by hand, then pouring more water from the pitcher and continuing to mix by hand.); CONTRADICTED: Then oil is poured from a small white bowl onto the nearly formed dough, and the cook kneads it with a gloved right hand until a cohesive ball forms. (The stills show the dough being kneaded with a gloved right hand and forming a cohesive ball, but no oil is poured from a small white bowl; the small white bowl on the table appears to contain a spoon and is not shown being poured.)
Fluency: 4/5 — The cue is well-structured and uses natural spoken English with clear sequencing, but contains factual inaccuracies relative to the visual evidence.

### Cue 3: (23.362, 25.666] s

The cook finishes kneading the dough into a smooth ball. A second person pours oil from a small bowl into a spoon held over the wooden bowl.

Matched GT steps: step `seg2.a5` (yes): Child appears watching nearby (23s).; step `seg2.a6` (partial): Person pours liquid (oil) from spoon into wooden bowl containing dough (24-26s).
Unsupported claims: The cook finishes kneading the dough into a smooth ball; A second person pours oil from a small bowl into a spoon held over the wooden bowl
Chronology errors: The cook finishes kneading the dough into a smooth ball (Finishing kneading into a smooth ball occurs earlier (18-22s per seg2.a4) or later (27-33s per seg2.a7), not in the 23.362-25.666s window where oil pouring happens.); A second person pours oil from a small bowl into a spoon held over the wooden bowl (Ground truth shows the same person (not a second person) pours oil from a spoon into the wooden bowl at 24-26s; cue misstates direction, vessel, and actor.)
Frame audit: SUPPORTED: The cook finishes kneading the dough into a smooth ball (The first still shows the cook kneading dough in the wooden bowl, and the second still shows the dough as a smooth ball in the bowl, indicating the kneading is finished.); SUPPORTED: A second person pours oil from a small bowl into a spoon held over the wooden bowl (The stills show a second person holding a small bowl of oil and pouring it into a spoon held over the wooden bowl containing the dough.)
Fluency: 4/5 — Grammatically correct and coherent narration, but contains factual inaccuracies and misdescriptions of actions.

### Cue 4: (25.666, 48.800] s

The cook pours oil from a glass bowl onto the dough and kneads it into a smooth ball, then lifts it onto the white wooden countertop. Flour is sprinkled on the silicone mat, the dough is pressed flat, cut into portions with a knife, and each piece is rolled into a ball and lined up on the mat.

Matched GT steps: event `evt2` (yes): OLINNO silicone mat with cm guides placed on counter; event `evt3` (yes): Person cuts flattened dough into smaller pieces with knife; step `seg3.a1` (yes): Woman holds up large brown silicone baking mat with circular guides, places it flat on counter, smooths it down while girl watches (35.65-37s).; step `seg3.a2` (yes): Person sprinkles white powder (flour) from hand onto center of silicone mat (38.05s).; step `seg3.a3` (yes): Person continues sprinkling white powder across mat surface (38.05s).; step `seg3.a4` (yes): Woman presses and flattens ball of dough on floured silicone mat with both hands while girl watches (39.0s).; step `seg3.a5` (yes): Person continues pressing and shaping dough on mat (40s).; step `seg3.a6` (yes): Person uses knife to cut flattened dough into smaller pieces (41s).; step `seg3.a7` (yes): Person arranges cut dough pieces into rounded balls on mat (42.25s).; step `seg3.a8` (yes): Person picks up one dough ball and shapes it with both hands (42.25s).; step `seg3.a9` (yes): Person rolls dough between palms to form smooth ball, places it on mat with other shaped pieces (43s).; step `seg3.a10` (yes): Person continues rolling and shaping dough into round ball using both hands on mat (45s).; step `seg3.a11` (yes): Person finishes shaping dough ball and places it on left side of mat next to other formed balls (46s).; step `seg3.a12` (yes): Person picks up another piece of dough and rolls it between palms to form a ball (47s).; step `seg3.a13` (yes): Person places newly formed dough ball onto mat with others (48s).
Unsupported claims: The cook pours oil from a glass bowl onto the dough and kneads it into a smooth ball; then lifts it onto the white wooden countertop
Chronology errors: The cook pours oil from a glass bowl onto the dough and kneads it into a smooth ball (This action (pouring oil, kneading in bowl) occurs in segment 2 at 24-34s, before the current cue window (25.666-48.8s). The cue narrates it as current.); then lifts it onto the white wooden countertop (The dough ball is moved from the wooden bowl to the silicone mat on the counter at 35.65s (seg3.a1), not lifted onto the countertop as a separate action after kneading. The cue places this after the kneading claim, but the mat placement is the transition.)
Frame audit: UNCERTAIN: The cook pours oil from a glass bowl onto the dough and kneads it into a smooth ball (The stills show the cook kneading dough in a wooden bowl, but no glass bowl or oil-pouring action is visible in the provided frames.); SUPPORTED: then lifts it onto the white wooden countertop (The stills show the dough being kneaded in a bowl on the white wooden countertop, and subsequent frames show the dough being worked on the countertop surface, consistent with it being placed there.)
Fluency: 5/5 — The cue is well-structured, uses natural spoken English flow, varied vocabulary, and clear temporal sequencing with no disfluencies.

### Cue 5: (48.800, 70.000] s

The cook places a dough ball on the floured silicone mat, presses it flat, and rolls it into a long thin oval with a wooden pin. More flour is sprinkled from a small dish over the flattened dough.

Matched GT steps: step `seg3.a14` (yes): Person sprinkles flour onto mat while holding dough ball (48.85s).; step `seg4.a1` (yes): Person sprinkles flour onto mat while holding dough ball (48.85-52.25s, repeated cycles).; step `seg4.a2` (yes): Person places dough ball on center of floured mat (50s).; step `seg4.a3` (yes): Person presses dough ball flat with both hands (51s).; step `seg4.a4` (yes): Person flattens dough ball on mat with both hands (52s).; step `seg4.a5` (yes): Person uses wooden rolling pin to roll out flattened dough on mat (52.25s).; step `seg4.a6` (yes): Person rolls dough ball flat with rolling pin on floured mat, four additional dough balls waiting to left (53-54s).; step `seg4.a7` (yes): Person continues rolling dough into longer, thinner oval shape (55s).; step `seg4.a8` (yes): Person rolls dough back and forth to elongate further (55-58s).; step `seg4.a13` (yes): Person sprinkles flour from above onto dough sheet and surrounding mat (66s).; step `seg4.a14` (partial): Person reaches right hand into glass flour container, scoops handful (67s).; step `seg4.a15` (yes): Person sprinkles flour over dough sheet from hand (68s).
Unsupported claims: from a small dish
Chronology errors: none
Frame audit: SUPPORTED: from a small dish (A small glass dish containing flour is visible on the mat next to the dough balls, consistent with flour being sprinkled from a small dish.)
Fluency: 5/5 — The cue is grammatically correct, flows naturally, and uses appropriate vocabulary for describing a cooking process. No disfluencies or awkward phrasing.

### Cue 6: (70.000, 83.940] s

The cook folds the dough strip in half and rolls it into a thin rope. They then pinch and twist it tightly into a coiled spiral, pressing the end down to secure the shape.

Matched GT steps: event `evt5` (yes): Person rolls dough rope into spiral (cinnamon roll style); step `seg5.a1` (partial): Person rolls piece of dough into long, thin rope on baking mat using hands (75s).; step `seg5.a2` (partial): Person continues rolling dough into long, thin rope on mat (77s).; step `seg5.a5` (yes): Person rolls dough rope up from one end, similar to rolling a cinnamon roll (80s).; step `seg5.a6` (yes): Person continues rolling dough into spiral shape (81s).
Unsupported claims: The cook folds the dough strip in half; pinch and twist it tightly into a coiled spiral; pressing the end down to secure the shape
Chronology errors: The cook folds the dough strip in half and rolls it into a thin rope. They then pinch and twist it tightly into a coiled spiral, pressing the end down to secure the shape. (In the source window (70-83.94s), the dough is already a long rope by 75s (seg5.a1); folding a strip in half occurs earlier (seg4.a17 at 70s shows folding top edge of sheet). The spiral rolling occurs at 80-81s (seg5.a5-6), not after a fold-then-roll sequence within this window. Pressing the end down to secure is not visible; at 82s the person starts rolling a ball (seg6.a1).)
Frame audit: SUPPORTED: The cook folds the dough strip in half (The stills show the cook handling a long dough strip and folding it over itself.); SUPPORTED: pinch and twist it tightly into a coiled spiral (The stills show the cook pinching and twisting the dough into a spiral shape.); SUPPORTED: pressing the end down to secure the shape (The stills show the cook pressing the end of the twisted dough down onto the mat.); SUPPORTED: The cook folds the dough strip in half and rolls it into a thin rope. They then pinch and twist it tightly into a coiled spiral, pressing the end down to secure the shape. (The stills show the full sequence: folding, rolling into a rope, twisting into a spiral, and pressing the end down.)
Fluency: 5/5 — The cue is grammatically correct, flows naturally, and uses precise culinary language (folds, rolls, pinch, twist, coiled spiral, secure the shape) with native-like fluency.

### Cue 7: (83.940, 107.927] s

The twisted dough balls are placed in a brown bowl, oiled with a spoon, and covered with an inverted white bowl to rest for 35 minutes. The cover is lifted to reveal six rested balls. One ball is taken to the floured mat and rolled into a round disc with a wooden pin.

Matched GT steps: event `evt6` (yes): Person pours oil over dough balls in bowl; event `evt7` (yes): Person covers bowl with white plate for resting; step `seg6.a7` (yes): Six shaped dough balls rest in brown bowl on floured mat (88.05s).; step `seg6.a8` (yes): Person pours oil over dough balls in bowl (89s).; step `seg6.a9` (yes): Person finishes pouring oil over dough balls (90s).; step `seg7.a3` (yes): Person places white plate upside down over bowl of dough to cover it (94s).; step `seg7.a4` (yes): Person holds white plate steady over bowl (95s).; step `seg7.a5` (partial): Person continues holding plate over bowl (96.05s).; step `seg8.a4` (yes): Person places dough ball onto center of baking mat (104s).; step `seg8.a5` (yes): Person presses dough ball flat with fingers on mat (105s).; step `seg8.a6` (yes): Person rolls dough back and forth with rolling pin to flatten (105.65s).; step `seg8.a7` (yes): Person continues rolling dough flat on mat (106s).
Unsupported claims: The twisted dough balls are placed in a brown bowl, oiled with a spoon, and covered with an inverted white bowl to rest for 35 minutes. The cover is lifted to reveal six rested balls. One ball is taken to the floured mat and rolled into a round disc with a wooden pin.
Chronology errors: The cover is lifted to reveal six rested balls. (Ground truth shows the cover is placed at 94s and held through 96.05s within this window; the cover is not lifted until after 107.927s.); rest for 35 minutes (The 35-minute rest is not shown within this window (83.94-107.927s); the cover remains on the bowl through the window's end.)
Frame audit: UNCERTAIN: The twisted dough balls are placed in a brown bowl, oiled with a spoon, and covered with an inverted white bowl to rest for 35 minutes. The cover is lifted to reveal six rested balls. One ball is taken to the floured mat and rolled into a round disc with a wooden pin. (The stills show dough balls in a brown bowl, an inverted white bowl being placed, and dough being rolled with a wooden pin, but the oiling with a spoon, the 35-minute rest duration, the count of six balls, and the lifting of the cover are not visible in the provided frames.); UNCERTAIN: The cover is lifted to reveal six rested balls. (The stills show an inverted white bowl being placed over the dough and later dough balls in the brown bowl, but the lifting of the cover and the exact count of six balls are not shown.); UNCERTAIN: rest for 35 minutes (The stills show a white bowl covering the dough with an on-screen caption reading "an hour," not 35 minutes, and no timing information confirms 35 minutes.)
Fluency: 5/5 — The cue is well-structured, uses precise culinary vocabulary (twisted dough balls, floured mat, wooden pin), and flows naturally as spoken English narration.

### Cue 8: (107.927, 119.919] s

The cook rolls the dough back and forth into a larger round disc, lifts and flips it over, then continues rolling it thinner and more circular. The finished thin round roti lies on the mat marked with measurement circles and the title "Roll the rotis".

Matched GT steps: none
Unsupported claims: The cook rolls the dough back and forth into a larger round disc; lifts and flips it over; then continues rolling it thinner and more circular; The finished thin round roti lies on the mat marked with measurement circles and the title "Roll the rotis"
Chronology errors: The cook rolls the dough back and forth into a larger round disc (This action (rolling back and forth into larger disc) occurs at 113-114s (seg8.a13, seg8.a14), before the cue window.); lifts and flips it over (This action (lift and flip) occurs at 111s (seg8.a11), before the cue window.); then continues rolling it thinner and more circular (This action (continuing to roll thinner) occurs at 112-114s (seg8.a12, seg8.a13, seg8.a14), before the cue window.); The finished thin round roti lies on the mat marked with measurement circles and the title "Roll the rotis" (The finished roti on the mat is the state resulting from actions completed by 114s (seg8.a14), before the cue window.)
Frame audit: SUPPORTED: The cook rolls the dough back and forth into a larger round disc (The stills show the rolling pin moving over the dough and the dough becoming a larger round disc on the mat.); SUPPORTED: lifts and flips it over (A still shows the cook's hand lifting and turning the dough over on the mat.); SUPPORTED: then continues rolling it thinner and more circular (The stills show the dough being rolled again and appearing thinner and more circular.); UNCERTAIN: The finished thin round roti lies on the mat marked with measurement circles and the title "Roll the rotis" (The stills show the mat with measurement circles, but the title "Roll the rotis" is not visible in any still.)
Fluency: 5/5 — The cue text is grammatically correct, flows naturally, and uses appropriate vocabulary for describing a cooking process.
