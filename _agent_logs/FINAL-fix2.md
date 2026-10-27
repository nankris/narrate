# FINAL fix2

Tests: 89 passed (64 before, 25 new in tests/test_fix2.py), ~42 s. Secret scan: CLEAN. No real API calls.

## Per item
1. **Never-commit**: `check_fit` (en, ok) records `state.candidates[gap]` and returns `next: call propose_cue/commit_cue to commit`. New `Agent.fallback_finish` (role `fallback` trace steps) runs on any stop: commits best candidate, else latest draft (trimmed to `suggested_max_words`, ends with '.'), else drops the gap with a reason; then verifies pending cues (budget permitting), translates, force-finalizes. Prompt + tool descriptions: propose_cue preferred, check_fit/measure_tts_duration exploration only.
2. **Retries**: `llm.call_with_retry` (5xx/429/timeouts/connection errors, 3 attempts, 1s/2s backoff, injectable `client.sleep`, `client.on_retry` -> `system` trace step "retry after HTTP 500"). Used by `Client.call` and `Orchestrator.next`; other 4xx not retried; 400 JSON fallback kept. Exhaustion -> fallback finisher.
3. **Wrong-event drafts**: draft context = inspected events overlapping gap start-1.0..end+0.5 plus <=2 earlier (<=10 s before) tagged "earlier, context only"; batch drafts get per-gap events. Inspect timestamps: root cause of 24.52-26.04 was the 6 s pre-roll window (prompt now uses 2 s), not an offset; added `absolute_times` heuristic for clip-relative VL answers (documented in code/issue).
4. **Sorted VTT/transcripts** (`write_texts` sorts, numbers 1..n; report cues sorted; render order sorted).
5. **Tiny gaps**: `agent.min_gap_s` 1.5; `narratable:false, reason:"too short"`; check_fit/propose_cue/draft return ok=false immediately; state lists `skipped_too_short`; mock script and coverage skip them.
6. **Enforced verification**: `verify_claim(gap_id | start/end, claim)`; finalize returns `needs_verification` until done (unless cap reached); contradicted -> uncommit + redraft hint + same text blocked; fallback verifies or reports `unverified`; `agent_stats.verifications={verified,contradicted,unverified}`; config `verify_below` 0.75, `max_verifications` 8.
7. **Duplicates**: token Jaccard >= 0.8 vs other cues -> ok=false, "duplicate of gap N".
8. **Coverage**: only high-importance events overlapping narratable gap windows; `events_in_speech_regions` reported separately.
9. **Pricing**: fit_alt 0.06/0.24/0.03 with comment about the 0.15/0.6/0.1 fast tier.
Mock script now shows check_fit failure -> shorter redraft, contradicted verify -> redraft, propose_cue, verification before finalize, duplicate-title gap dropped. Kitchen mock: 3 cues, sorted VTT, 1 supported + 1 contradicted verification. Cached mock runs regenerated (scripts/build_cached_runs.py --provider mock); UI tests pass. README + issues-found (3 entries + index) updated; UI trace icons for `fallback`/`system`.

## Not done / caveats
- Nothing run against real providers; retry/verification heuristics are only offline-tested.
- Verification gate is a regex heuristic; "supporting events" are approximated by events overlapping the gap window.
- Cached mock runs for ToS/NASA have fewer cues (1-2) because the mock sidecar text repeats across gaps and duplicates are now dropped; mock `verify` only returns "supported" when the claim matches sidecar text.
- Backoff default is 3 attempts => sleeps 1s,2s (the 4s step is used only if `agent.retry_attempts` is raised).
