# FINAL fix4

## Changes
1. Evidence board: `Agent.evidence_line/board_text/next_action`; run loop appends one `[EVIDENCE BOARD ...]` user message per turn (previous one stripped), so evidence survives `compact_history`. Inspect results carry `evidence_gaps`; their compaction summary reads "events stored on evidence board for gap N".
2. Re-inspection of a >=70 % covered range -> `{"ok":false,"error":"already inspected","see","next"}` without events, counted in `repeat_refusals`; after 2, state gets `next_action`. Identical (tool,args) 3rd+ call refused (except finalize/detect).
3. Grounded text: `draft_history` per gap; commit with text neither Jaccard>=0.6 nor a token-subset of any draft is "orchestrator-authored" -> added to `needs_verification`, result carries `orchestrator_authored`. Prompt/tool descriptions updated.
4. Fallback finisher: one batched `draft_description(gap_ids)` for evidence gaps lacking candidate/draft (not on budget stop / after deadline), then existing fit/trim/commit/verify, then drop.
5. Prompt batching guidance; MockOrchestrator now inspects all slots, drafts rest in one batched call, packs 4 calls/turn. NASA mock <= 12 turns (test); kitchen behaviour unchanged.
6. `agent_stats.repeat_refusals`, `agent_stats.orchestrator_authored_cues`.
Docs: issues-found/real-run-reinspection-loop.md + README. Tests: tests/test_fix4.py (10); two old tests updated (cached inspect -> refusal; seeded drafts where they propose without drafting).

## Tests
114 passed in ~88 s (`.venv/bin/python -m pytest -q`). Secret scan: CLEAN.

## Not done
- No real-provider run; real turn/cost/coverage effects unmeasured. Cached sample runs not regenerated (lead).
- Board adds ~100-300 chars per gap to each orchestrator input (≈3 kB at 10 slots); not tuned.
- Authored text on a verification cap (8) still lets finalize pass unverified; `max_verifications` not scaled with slots.
- Mock single-word redraft ("+ onscreen") counts as orchestrator-authored in that edge case.
