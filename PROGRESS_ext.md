# Extended AD progress (Round 8c), live log

- 22:05 IST: Codex pid 631894 runs in /workspace/hackathons/night-shift/worktrees/narrate (another driver), not narrate_opus. Left alone.
- roti_e5 ($0.0345): 8/8 pauses, +111.6 s. lecture_e5 ($0.0160): 3 pauses.
- Scorer audit, roti_e5 (25 hallucinations / 18 chronology errors):
  - Single judge call hit 5000 output tokens, JSON truncated, all targets "omitted". Fixed: one call per cue window.
  - Most flags are judge artifacts: it quoted GROUND-TRUTH steps as "unsupported claims", and flagged static setting
    facts and frozen-frame descriptions as chronology errors. Fixed: claims must be quoted from cue text (>=70% word
    overlap filter) + prompt rules for static facts / frozen-frame tolerance.
  - Real errors confirmed on frames: glove on left hand (frames: right), "twisted the ends" (caption "roll it up"),
    "white bowl" cover (it is a plate), "brushed" vs poured oil over buns. Lecture: OCR flicker narrated ("drops FOR",
    "- ROOM AD"); frames 20-29.7 s show the static "SLIDE 2 - NO ROOM FOR AD".
- Pipeline fixes: word budget soft to 65 (hard), camera language hard check, verifier now sees 5 stills spread across
  the cue window (was 2 at the pause), writer told to ignore text flicker and avoid handedness unless consistent.
