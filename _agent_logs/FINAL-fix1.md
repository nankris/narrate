# First real run fixes

Implemented against bf693ad after reading BLOG_NOTES 23:30 and the staged trace.json, trace.md, report.json.

- Required <=25-word tool notes; stripped before dispatch and retained prominently in traces, alongside assistant content.
- Append-only history, parallel-call request support, ordered batches, overlap cache, batched drafting, propose_cue, compact structured state, cheaper Super option and cached-token rates.
- Hindi duration-first fit, one Ultra retry with explicit limits, warning-only missing Hindi after retry and coverage reporting.
- Normalized JSON keys/verdicts, character-based truncation, narratable-event coverage, per-call list costs and role totals.
- 30-turn default, three-turn nudge, fallback translation subject to remaining budget/time.
- Piper auto selection, separate bounded CLI process, two downloaded voices in ignored voices/, backend per cue. piper-tts 1.8.0 installed in .venv. English/Hindi synthesis smoke: 1.30 s / 1.88 s. Hindi model is non-commercial; Piper GPL-3.0 is documented.
- README real-run cost comparison and individual issue records; static-text motion hallucination remains open.

Validation: full offline suite 60 passed in 30.28 s. Follow-up agent tests: 29 passed in 15.07 s, covering final detection-result compaction and translation-state changes. Scripted sample: 9 orchestrator turns, four committed cues, four inspections, two corrections, no fallback, zero detected speech overlap, 100% narratable high-importance temporal coverage. Silent-test English/Hindi gap occupancy 44.74%/59.66%; these are control-flow results, not voice or accessibility quality metrics.

No real LLM provider calls, no subagents, no push/remotes/publishing. Network used only for pip installation and the explicitly allowed Piper model/config downloads. Pre-existing untracked codex-*.final.md logs were left untouched. Real provider savings and native Hindi quality remain unmeasured.
