# verify-unused

Status: **fixed**

Symptom: in all four real runs verify_claim was never called, so on-screen text and low-confidence claims were published unchecked.

Root cause: verification was only advice in the prompt; nothing in finalize required it.

Fix: committed cues whose supporting events have confidence < `agent.verify_below` (0.75) or whose text has quotes, digits or mid-sentence capitalised words must be verified (`verify_claim(gap_id, claim)`) before a non-forced `finalize` succeeds (`needs_verification`). Contradicted verdicts uncommit the cue and block the same text. The fallback finisher verifies if budget allows, else reports `unverified`. Capped by `agent.max_verifications` (8); `agent_stats.verifications = {verified, contradicted, unverified}`.

Tests: `test_finalize_requires_verification_for_text_and_numbers`, `test_low_confidence_triggers_and_plain_text_does_not`, `test_contradicted_uncommits_and_blocks_same_text`, `test_verification_cap_does_not_deadlock_and_fallback_marks_unverified`, `test_fallback_runs_verification_and_drops_contradicted`.
