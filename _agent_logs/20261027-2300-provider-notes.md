# Provider implementation notes

Baseline: 4043ce0. Read README, configuration, all narrate Python modules, tests, and sample/smoke scripts before editing.

Implemented provider-specific model catalogs, runtime key selection, strict fallback policy, endpoint overrides, per-model JSON/reasoning controls, inference rate limiting, media-aware reservations, response-only debug logs, and session JSON-mode rejection memory. No real provider requests were made. Credentials were neither available nor inspected; tests inject fake runtime values and fake SDK objects.

Perception drops/counts malformed events, coerces numeric strings, clamps end times, and falls back from video on errors or no valid events. Separate-frame input is capped at 16. Gap requests include temporal context, screen text, event indices, and deduplication assignments; batch prompts track earlier cues, with explicit previous cues on shorter retries. Editor receives all events and retains valid edits per language/cue.

Mock scene sidecar reflects the synthetic titles and moving shape, rather than claiming filmed kitchen actions. Simulated usage exercises comparable Token Factory cost reporting while charged mock cost stays zero. Regenerated both narrated videos and text/report artifacts.

Review caught future screen text being selected ahead of current scenes; temporal event assignment now takes precedence. Error diagnostics deliberately retain exception type and status only, avoiding provider bodies that could echo credentials or base64 media.

Validation: 30 offline tests passed in 15.71 seconds. git diff --check passed. Real-provider behavior remains unverified; scripts are provided for explicit later execution. Existing untracked _agent_logs/codex-core.final.md was left untouched and excluded from this commit.
