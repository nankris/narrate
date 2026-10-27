# real-run-orchestrator-input-growth

Status: **mitigated** (offline test; real token numbers need a new authorized run)

Evidence: NVIDIA dev run after fix2. Ultra input tokens grew ~200 tokens per turn (2.9k -> 9.0k over 30 turns) with 0
cached tokens on this endpoint; orchestrator input was 96% of run cost.

Fix: `compact_history` (`narrate/agent/models.py`) runs before every orchestrator turn. The last `agent.history_turns`
(6) turns stay verbatim; older assistant/tool messages are shrunk to one-liners (tool, gap id, ok/verdict, first
problem; `detect_speech_gaps` keeps a compact gap table). Every tool_call keeps its tool message, so the OpenAI pairing
stays valid. System prompt and task message are untouched (prefix-cache friendly).

Measured offline over 25 mock turns: serialized history stays under 12 kB and grows ~285 chars/turn after the window
fills, vs several kB/turn of full tool results before. Growth is reduced, not eliminated: each old turn still costs a
summary line.

Turn budget: default `max_steps` becomes `max(30, 6+3*narratable_slots)` capped at 60 once gaps are detected, unless
`--max-steps` is given.
