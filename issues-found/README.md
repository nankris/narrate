# Issues found

Status index verified against the code at `b90aca3` (2026-10-28). `fixed` means an
in-repository commit or regression test demonstrates the fix. `documented` means
the note records evidence or a known limitation but does not claim that the
underlying behaviour is resolved.

| File | Status | Verification / remaining work |
|---|---|---|
| [agent-probes.md](agent-probes.md) | documented | Records externally supplied development-probe findings; Token Factory remains untested. |
| [mock.md](mock.md) | documented | Mock output is intentionally deterministic orchestration evidence, not perception-quality evidence. |
| [provider.md](provider.md) | open | Real media schema, model availability, token accounting, and cost still require an authorized provider run. |
| [real-run-dev-cost-zero.md](real-run-dev-cost-zero.md) | fixed | `tests/test_agent.py::test_cost_report_is_list_cost` verifies list-cost and billing metadata reporting. |
| [real-run-dotted-json-keys.md](real-run-dotted-json-keys.md) | fixed | `tests/test_agent.py::test_overlap_cache_and_normalized_verdict` covers normalized verdict keys and values. |
| [real-run-empty-tool-notes.md](real-run-empty-tool-notes.md) | fixed | Commit `f64f963` made tool notes required and retained assistant content; covered by `tests/test_agent.py::test_required_notes_and_unicode`. |
| [real-run-fix4-propose-loop.md](real-run-fix4-propose-loop.md) | fixed | `tests/test_fix5.py` covers effective limits, enforced drafts, auto-redrafting, and inspection deduplication. |
| [real-run-hindi-word-budget.md](real-run-hindi-word-budget.md) | fixed | `tests/test_agent.py::test_hindi_duration_retry_and_warning` verifies measured-duration retry and missing-language warnings. |
| [real-run-long-gaps-one-cue.md](real-run-long-gaps-one-cue.md) | fixed | `tests/test_fix3.py::test_detect_splits_long_gaps_into_slots` and `::test_overlong_cue_rejected` cover slotting and cue caps. |
| [real-run-missing-note-validation.md](real-run-missing-note-validation.md) | fixed | `tests/test_fix6.py` covers missing notes, useful validation errors, unknown gap IDs, and no-gap inspection. |
| [real-run-never-commit.md](real-run-never-commit.md) | fixed | `tests/test_fix2.py::test_fallback_commits_best_candidate_without_any_commit_call` covers fallback commit recovery. |
| [real-run-orchestration-cost.md](real-run-orchestration-cost.md) | documented | Batching and compact state are implemented, but real cost reduction remains unmeasured. |
| [real-run-orchestrator-input-growth.md](real-run-orchestrator-input-growth.md) | documented | `tests/test_fix3.py::test_orchestrator_input_bounded_over_25_mock_turns` proves offline mitigation; real token growth remains unmeasured. |
| [real-run-reinspection-loop.md](real-run-reinspection-loop.md) | fixed | `tests/test_fix4.py` covers the evidence board, repeat refusals, grounded-text checks, and batched fallback drafting. |
| [real-run-static-text-motion.md](real-run-static-text-motion.md) | open | Frame verification reduces risk but does not reliably distinguish static text from motion; broader evaluation is pending. |
| [real-run-step-exhaustion.md](real-run-step-exhaustion.md) | fixed | Commit `f64f963` added turn-based limits, a completion nudge, and bounded fallback translation; `tests/test_agent.py::test_append_only_batch_turns_and_nudge` covers the loop behaviour. |
| [real-run-unnarratable-coverage.md](real-run-unnarratable-coverage.md) | fixed | `tests/test_agent.py::test_narratable_coverage` verifies that coverage considers narratable windows only. |
| [real-run-utf8-truncation.md](real-run-utf8-truncation.md) | fixed | Commit `f64f963` changed response truncation to character slicing; `tests/test_agent.py::test_required_notes_and_unicode` is the Unicode regression. |
| [real-run-verify-unused.md](real-run-verify-unused.md) | fixed | Verification enforcement and contradiction handling are covered by `tests/test_fix2.py` verification tests. |
| [real-run-wrong-event-drafts.md](real-run-wrong-event-drafts.md) | fixed | `tests/test_fix2.py::test_draft_context_limited_to_gap_window` and `::test_inspect_converts_relative_vl_times` cover event selection and timestamp normalization. |
| [speech.md](speech.md) | open | VAD is not dialogue ground truth, short gaps remain unusable, and Hindi voice quality lacks a listening study. |
