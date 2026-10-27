# Real run after fix4: propose loop and cost regression

**Status:** fixed offline (`tests/test_fix5.py`); not yet re-measured against the real endpoint.

Real runs on the NVIDIA dev endpoint after the fix4 changes (evidence board, re-inspection refusals):

| clip | fix3 | fix4 |
|---|---|---|
| sample_kitchen (30 s, 4 gaps of 4-5 s) | 12 turns, 4 cues, $0.082 | 30 turns, 2 cues, $0.237; 38 `propose_cue` calls, 23 `repeat_refusals`; 2 gaps dropped "word budget exceeded despite maximal shortening" |
| Tears of Steel | 14 turns, $0.082 | 30 turns, 5 cues, $0.198; 26 `inspect_video_segment` calls for ~9 gaps |
| NASA | 2 cues, 13 % coverage | 7 cues, 41 % coverage, but 36 turns, $0.322, 47 `propose_cue` calls |

## Root causes (kitchen trace)
1. **Batched drafts ignored per-gap limits.** 13-14 word drafts for 8-9 word budgets, and the on-screen text ("A person enters a kitchen", "STEP 1 - chop onions", importance 5) was dropped.
2. **Two inconsistent limits.** `word_budget_en` (8) vs the single-cue cap ("under 3.6 s" for a 4.04 s gap). An 8-word line passed the word budget, failed the cap at 3.74 s, and `suggested_max_words=7` never reached the drafter, so the orchestrator retried near-identical text.
3. **"Shorten only by deleting words"** made the orchestrator hand-trim for 6+ turns instead of asking for a redraft.
4. **Near-duplicate inspections** (pre-roll variants, sub-ranges, empty frames-fallback results) were not recognised.

## Fix
- One `max_words_en/hi` per gap = min(word budget, words that fit the cap); in `detect_speech_gaps`, the board, drafter and `suggested_max_words`. A text within the limit is no longer rejected on the estimate alone (only when measured TTS exceeds gap x `max_atempo`).
- Drafter gets `max_words` + on-screen text, quotes it verbatim; over-limit drafts are re-asked once (failing gaps only), then replaced deterministically (`Title: "..."`, else word-boundary truncation). `agent_stats.draft_overlimit` counts them.
- 2nd failed `propose_cue` for a gap auto-redrafts (`auto_redrafted: true`, `agent_stats.auto_redrafts`); a 4th attempt after 3 failures is refused with `next: "drop_gap or move on"`.
- Prompt/tool text no longer says "delete words only"; rephrased text still needs `verify_claim`.
- Inspection refusal is gap-based (a gap with events is not re-inspected; a zero-event gap gets one retry), and the board says "no events found".
