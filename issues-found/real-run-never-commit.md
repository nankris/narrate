# never-commit

Status: **fixed**

Symptom (Tears of Steel real run): the orchestrator looped measure_tts_duration + check_fit (ok=true several times) but never called propose_cue/commit_cue; an exception then ended the run and the fallback finalize emitted zero cues.

Root cause: check_fit/measure_tts_duration looked like commit steps but are read-only, the prompt did not say so, and the fallback finisher only translated/finalized what was already committed.

Fix: check_fit records the passing English text as the gap's best candidate and answers `next: call propose_cue/commit_cue to commit`; prompt and tool descriptions mark propose_cue as preferred and the others exploration-only; the fallback finisher (role `fallback`) commits best candidate, else a deterministically trimmed latest draft, else drops the gap with a reason.

Tests: `test_check_fit_records_candidate_and_points_to_commit`, `test_fallback_commits_best_candidate_without_any_commit_call`, `test_fallback_trims_draft_or_drops`, `test_prompt_prefers_propose_cue`.
