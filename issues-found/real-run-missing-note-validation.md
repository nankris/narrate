# Real run: missing `note` argument silently disabled every tool (fix5 runs)

**When:** 2026-10-28 01:41–01:50 IST, nvidia-dev, agent v6 (fix5 code). Traces: `blog-assets/17_*`.

**What happened.** Every tool schema requires a short `note` (≤25 words). Part-way through the Tears of Steel run
(step 33 of 64) and the NASA run (step 71 of 113), Ultra started sending tool calls without a usable note. `jsonschema`
rejected each call and the error was sanitised to the bare class name `"ValidationError"`, which tells the model
nothing. Ultra kept retrying draft/inspect/propose with varied arguments until the turn cap:

- Tears of Steel: 16 failed calls in a row, 4 slots dropped by the fallback, coverage 23% (was 32% in v4).
- NASA: 21 failed calls in a row, run hit the 36-turn cap, $0.301.

**Fix (fix6).** `note` is normalised before validation (missing → tool name, longer than 25 words → truncated), and real
argument errors are returned as `invalid arguments: <jsonschema message>` instead of the bare class name.
Test: `tests/test_fix6.py`.
