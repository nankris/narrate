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
- 22:06 IST: commit 7f04e74. Launched roti_e6, lecture_e6; rescoring e5 with fixed judge.
- 22:14 IST: added st_text_stills (OCR from stills), scorer --frame-audit. Spend so far ~$0.57. Launched lecture_e7; frame-audit scoring roti_e6.
- 22:19 IST: roti_e6 ($0.0431) 8/8 pauses; judge-flagged 17 claims/14 chronology, frame audit on stills: 1 contradicted, 5 uncertain, 14 supported. roti_e7 ($0.0698) regressed: Ultra cited wrong window ids, 7/8 dropped. Final roti = e6.
- lecture_e7 ($0.0161): text_stills fixed flicker (4 readings corrected); 3 cues; still has timing errors ("until ten seconds", change is 15 s) and invented "left edge cropping". Final lecture = e7.
- Next: Magnific TTS (voice 1076) for roti_e6 + lecture_e7, render into runs/ext/final/.
- 22:22 IST: Magnific TTS voice 1076 (eleven_turbo_v2_5, stab .45, sim .85, boost) for 11 cues = 235 credits. Rendered runs/ext/final/{roti,lecture}.
- 22:24 IST: ffprobe showed video stream 15.3 s short (closing freeze dropped by tpad). Fixed with loop filter + test; re-rendered: roti 223.29 s, lecture 61.62 s, video == audio.
- 22:26 IST: README, DEMO_PLAN_v2 lead, issues-found/extended-ad-round8.md, blog note + INDEX, spend log (~$0.707), ledger.

## Stream A timing and roti corrections (2026-10-29, offline)

- Fixed extended pause anchoring so an event's `t_end` takes precedence over a generic `t`; important-event and story-beat
  freezes are now planned only after the described action has ended. The source-end closing freeze from Round 8c is unchanged.
- Rendered pause plans now retain accepted evidence IDs and deterministic `evidence_times`, making chronology independently
  auditable without a model call. `scripts/check_extended_timing.py` rejects missing timing and any evidence ending after its
  pause (default tolerance 50 ms).
- Added writer/repair guardrails and hard post-write checks for three reviewed roti failures: dough is rolled/coiled rather
  than "twisted", the flat bowl cover is a plate, and an oil-pour event cannot be narrated in more than one cue.
- `scripts/correct_extended_cached.py` records the manual frame-review corrections for the final roti and lecture text
  artifacts and can reproduce them deterministically. These lines are explicitly human corrections, not model output.
  It does **not** alter the cached MP4/M4A narration, whose audio still contains the old wording; use the corrected VTT,
  transcript, and pause plan for text demos until narration is re-rendered from an approved offline voice.
- Run the offline timing check:

  `.venv/bin/python scripts/check_extended_timing.py runs/ext/final/roti runs/ext/final/lecture`

  Current result: both runs PASS; every cue follows all cited evidence.
- Focused regressions: `29 passed` across the new timing/roti tests plus Round 8/8b tests.
