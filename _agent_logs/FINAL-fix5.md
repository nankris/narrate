# FINAL fix5

## Changes
1. One limit per gap: `Agent.max_words(g,lang)` = min(word budget, words fitting `min(0.9*gap, max_cue_s)`); stored as `max_words_en/hi`, returned by `detect_speech_gaps` (replaces word_budget_* in its output), shown on the board, used by drafter and `suggested_max_words`. `check_fit` no longer rejects a text within `max_words` on the cap estimate unless measured TTS > gap x `max_atempo`; word-budget check still uses the raw budget.
2. Drafter (`draft_batch`, used by batched and single `draft_description`): sends per-gap `max_words` + `on_screen_text`, new instruction (verbatim on-screen text, <= max_words, only this gap). Server-side enforcement: one batched re-ask of failing gaps only ("HARD LIMIT"), then deterministic fallback (`Title: "..."`, else word-boundary truncation). Returned cues carry `max_words`.
3. `propose_cue`/`commit_cue`: 2nd failure for a gap auto-redrafts (fit model, suggested limit) and commits on success (`auto_redrafted: true`); 1st failure hints `draft_description(gap_ids=[id], max_words=N)`; after 3 failures the next call is refused with `next: "drop_gap or move on"` (counts in `repeat_refusals`). Fallback finisher uses the raw `_commit`. Prompt, tool descriptions and `next_action` no longer say "delete words only"; rephrased text still goes to `needs_verification`.
4. Inspect: refusal is now gap-based (`owned_gaps` = gaps >=50 % inside the range): refused when all have events and were already inspected (pre-roll variants, sub-ranges), plus a symmetric overlap rule on non-empty cached results. Zero-event (frames-fallback) inspections count as tries; one retry allowed; board says "no events found (inspected)"; `next_action` suggests `drop_gap` after two empty tries.
5. `agent_stats.auto_redrafts`, `agent_stats.draft_overlimit`.
Docs: `issues-found/real-run-fix4-propose-loop.md` + README entry.

## Tests
126 passed in ~88 s (`.venv/bin/python -m pytest -q`); 10 new in `tests/test_fix5.py` (limits, enforcement, re-ask scope, auto-redraft, 3-fail refusal, pre-roll/empty inspection, kitchen-like run: 4 cues, <=8 turns, <=6 propose_cue; NASA mock <=12 turns still passes). Secret scan: CLEAN.
Existing tests touched: `test_fix4` prompt/tool-text assertions (rule text changed on purpose), `test_fix2` draft-context gap widened from 1.1 s to 3 s (a 1.1 s gap now has limit 1 word, so the fake 3-word draft was truncated). SYSTEM prompt trimmed to keep `test_fix3` input-size bound.

## Not done
- No real-provider run; turn/cost effects of auto-redraft and enforcement are unmeasured. Cached samples not regenerated.
- Hindi limit (`max_words_hi`) is exposed but `check_fit` for hi still only uses duration, as before.
- Deterministic fallback text ("Title: ...") is terse and not verified beyond the usual `needs_verification` (quoted text triggers verify_claim).
- The re-ask uses one extra fit call per batch when drafts are over limit; a stubborn drafter always pays it.
