# Real run: orchestrator re-inspection loop, self-authored cue text, fallback drops (after fix3)

**Status:** fixed offline (tests/test_fix4.py); real effect unmeasured until a new authorized run.

**Evidence:** NVIDIA dev endpoint, NASA clip 0-110 s (10 slots), trace in
`blog-assets/15_2026-10-28_agent_v4_fix3_real_nvidia-dev_4clips/nasa_chile_harvest_0000-0150/`.

| Metric | Observed |
|---|---|
| Orchestrator turns | 36 (budget 36) |
| `inspect_video_segment` calls | 31 for 10 slots (10 + 2 full re-inspection rounds) |
| `draft_description` calls | 0 |
| `propose_cue` calls | 3 |
| Cost | $0.209 total, $0.197 orchestration |
| Result | 2 cues for 110 s, coverage 13 % |

**What happened**
1. Ultra inspected all 10 slots. `compact_history` then replaced the old inspection results by one-line summaries
   that held no events, so it believed it had no evidence and re-inspected all 10 slots twice more.
2. It finally wrote cue text itself in `propose_cue` and invented details absent from the VL evidence
   ("typing on a laptop", "window showing Earth's blue curve"); verification contradicted one.
3. The fallback finisher dropped 7 slots with "no fitting candidate or draft" although inspection events existed
   for every one of them (it never drafted, it only committed existing candidates/drafts).

**Fixes**
- Evidence board: events stay in agent state; a refreshed `[EVIDENCE BOARD ...]` user message (per gap: <= 3 events,
  <= 160 chars, plus draft and committed text, plus `next:`) is appended each turn, so it survives compaction. Compaction
  summaries of inspections say "events stored on evidence board for gap N".
- Re-inspecting a range already covered >= 70 % returns `{"ok":false,"error":"already inspected","see":...,"next":"draft_description(gap_ids=[...])"}`
  with no events; after 2 such refusals the tool state carries `next_action` naming the gaps to draft. Identical
  (tool,args) calls from the 3rd on are refused likewise. Counted as `agent_stats.repeat_refusals`.
- Cue text not produced by `draft_description` for the gap (token Jaccard < 0.6 and not a word-deletion subset of any
  draft) is committed but forced into `needs_verification` and flagged in the result; counted as
  `agent_stats.orchestrator_authored_cues`. Prompt and tool descriptions forbid writing cue text.
- Fallback finisher drafts every evidence-bearing gap without candidate/draft in ONE batched `draft_description(gap_ids)`
  (skipped on budget stop or past the deadline), then fits/trims/commits/verifies, and only then drops.
- Prompt batching guidance (4 inspections per turn, one batched draft, proposals in one turn); the mock orchestrator
  now follows it: the 10-slot NASA mock finishes in <= 12 turns.
