# Extended AD score

- Key-event coverage: 100.00%
- Action-step coverage: 50.00%
- Hallucinated claims: 8
- Chronology errors: 2
- Confusing parts explained: 100.00%
- Mean fluency: 4.67/5
- Maximum source span without a pause: 15.026 s
- Pauses inside speech: 1
- Pause at cut/speech boundary: 100.00%
- Total added time: 34.514 s
- Frame audit of judge flags: 0 contradicted, 2 uncertain, 6 supported on stills

## Cue windows

### Cue 1: [0.000, 3.105] s

A dark blue slide displays the white title "CONTINUOUS SPEECH - SLIDE 1" in the upper left corner. The slide remains unchanged through the first three seconds.

Matched GT steps: none
Unsupported claims: dark blue slide; white title "CONTINUOUS SPEECH - SLIDE 1" in the upper left corner; The slide remains unchanged through the first three seconds
Chronology errors: none
Frame audit: SUPPORTED: dark blue slide (The stills show a dark blue/teal background.); SUPPORTED: white title "CONTINUOUS SPEECH - SLIDE 1" in the upper left corner (The white text appears in the upper left area of the slide in all stills.); SUPPORTED: The slide remains unchanged through the first three seconds (The stills from 0.31s to 3.10s show the identical slide with no changes.)
Fluency: 5/5 — The cue is grammatically correct, flows naturally, and uses clear spoken English.

### Cue 2: (3.105, 18.131] s

The first slide persists until ten seconds, then a new dark blue slide appears with the white title "SLIDE 2 - NO ROOM FOR AD" in the upper left corner. That second title is now frozen on screen.

Matched GT steps: event `evt1` (yes): Slide text changes from 'CONTINUOUS SPEECH - SLIDE 1' to 'SLIDE 2 - NO ROOM FOR AD'.; step `seg1.a1` (yes): Static title slide displayed reading 'CONTINUOUS SPEECH - SLIDE 1'.
Unsupported claims: a new dark blue slide appears; white title "SLIDE 2 - NO ROOM FOR AD" in the upper left corner; That second title is now frozen on screen
Chronology errors: none
Frame audit: SUPPORTED: a new dark blue slide appears (The still at 18.131 seconds shows a new dark blue slide after the first slide persisted through 13.623 seconds.); SUPPORTED: white title "SLIDE 2 - NO ROOM FOR AD" in the upper left corner (The still at 18.131 seconds shows the white title "SLIDE 2 - NO ROOM FOR AD" in the upper left corner.); SUPPORTED: That second title is now frozen on screen (The last still is the frozen frame the cue is spoken over and it shows the second title on screen.)
Fluency: 5/5 — The cue is grammatically correct, flows naturally, and uses precise language appropriate for a professional narration.

### Cue 3: (18.131, 30.000] s

The second slide holds steady until twenty-two seconds, when its left edge begins cropping away. The title still reads "SLIDE 2 - NO ROOM FOR AD" as the cropping starts.

Matched GT steps: none
Unsupported claims: The second slide holds steady until twenty-two seconds, when its left edge begins cropping away.; The title still reads "SLIDE 2 - NO ROOM FOR AD" as the cropping starts.
Chronology errors: The second slide holds steady until twenty-two seconds, when its left edge begins cropping away. (The ground truth for this window (18.131s to 30.0s) shows a static teal background with white text; no slide transition or cropping occurs in this window.); The title still reads "SLIDE 2 - NO ROOM FOR AD" as the cropping starts. (The ground truth for this window does not show a slide with this title or any cropping animation; it describes a static background.)
Frame audit: UNCERTAIN: The second slide holds steady until twenty-two seconds, when its left edge begins cropping away. (The stills at 19.288, 21.602, 23.916, 26.229, and 29.7 seconds all show the full slide with the same title and no visible cropping, so the start of cropping at 22 seconds cannot be confirmed from the provided frames.); UNCERTAIN: The title still reads "SLIDE 2 - NO ROOM FOR AD" as the cropping starts. (The title is clearly visible in the stills before 22 seconds, but no still shows the moment cropping starts, so whether the title remains readable at that exact moment cannot be determined.)
Fluency: 4/5 — The cue is grammatically correct and flows naturally as spoken English, with clear temporal markers and descriptive language.
