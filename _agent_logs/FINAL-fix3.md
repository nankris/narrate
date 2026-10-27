# FINAL fix3

## Changes
1. Long gaps -> slots: `detect_speech_gaps` splits narratable gaps > `agent.max_slot_s` (12) into equal 6-12 s slots (own id, `parent_gap`, own word budget). `media.scene_cuts` (ffmpeg scene select + showinfo, 5 fps/320 px, 60 s timeout, [] on failure) and `media.split_slots` snap boundaries to cuts within +-2 s while keeping slots 4-12 s. `max_inspections` raised to slots+2 when needed. NASA: 10 slots.
2. `agent.max_cue_s` (8.0): English cues longer than min(slot*0.9, max_cue_s) are rejected with "cue too long for a single description; keep it under N s"; `suggested_max_words` follows that limit.
3. `compact_history` (models.py): last `agent.history_turns` (6) turns verbatim, older tool results/arguments become one-line summaries, tool_call/tool pairing preserved, system+task untouched. Offline: 25 turns stay < 12 kB, ~285 chars/turn growth after the window (not flat).
4. Turn budget: unless `max_steps` is explicit, steps = max(configured, min(60, max(30, 6+3*slots))) once gaps exist (NASA: 36). Budget guard unchanged.
5. Mock: added `samples/nasa_chile_harvest_0000-0150.scenes.json` (synthetic placeholder scenes, mock only) -> NASA mock = 10 cues (was 1); kitchen unchanged (3 cues, 1 contradicted, 2 corrections). Cached mock runs regenerated (12.0 MB).
Docs: issues-found/real-run-long-gaps-one-cue.md, real-run-orchestrator-input-growth.md, README index. New tests: tests/test_fix3.py (11).

## Tests
104 passed (full suite; 288 s when run alongside other load, ~67 s alone). Secret scan: CLEAN.

## Not done
- No real-provider run: real coverage/token/cost effects unmeasured.
- Scene-cut snapping untested on real footage here (NASA mock run found no snappable cuts); only unit-tested.
- History growth reduced (~285 chars/turn), not eliminated; no front "state summary" message added (latest state rides in recent tool results; gap table is kept in the detect summary).
- Orchestrator prompt only lightly updated about slots; real models may still need tuning. The user prompt's "Maximum tool turns" shows the pre-scaling number.
