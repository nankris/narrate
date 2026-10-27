# real-run-long-gaps-one-cue

Status: **fixed** (offline regression tests in `tests/test_fix3.py`; real re-run pending)

Evidence: NVIDIA dev endpoint run after fix2 on `nasa_chile_harvest_0000-0150.mp4` (ambient audio only).

VAD produced two gaps, 0.08-79.17 s and 84.1-109.9 s. The agent wrote ONE 47-word cue (14.7 s of speech after the
atempo squeeze) per gap, so ~65 s of visuals stayed undescribed (gap coverage 29%).

Fixes:
- `detect_speech_gaps` splits any narratable gap longer than `agent.max_slot_s` (12 s) into consecutive slots of
  roughly equal length (6-12 s). Each slot has its own gap id, a `parent_gap` field and a word budget based on its own
  duration. NASA now yields 10 slots (7 + 3).
- Boundaries snap to the nearest scene cut within +-2 s (`media.scene_cuts`: ffmpeg `select='gt(scene,0.3)'` +
  `showinfo` on a 5 fps, 320 px stream, 60 s timeout, `[]` on any failure -> equal splits), only if every slot stays
  within 4-12 s.
- `agent.max_inspections` is raised to slots+2 when needed (one inspection per slot).
- Overlong cues: `agent.max_cue_s` (8.0). English cues whose measured TTS exceeds `min(slot*0.9, max_cue_s)` are
  rejected by `check_fit`/`propose_cue` with "cue too long for a single description; keep it under N s".

Mock demo: NASA now commits 10 cues (was 1); kitchen unchanged (3 cues, a correction, a contradicted verification).
Real coverage after the change is unmeasured.
