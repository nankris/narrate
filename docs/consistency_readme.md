# README consistency check

Checked against the five shipped `samples/cached_runs/*/report.json` files and `config.yaml` on 2026-10-28. Displayed results are rounded from report values; stage costs are sums of `usage[].cost_usd`. “Model latency” is `latency_s`, not end-to-end wall time.

| README claim | Source | Result |
|---|---|---|
| Default and cached-run provider is Nebius Token Factory | `config.yaml` `default_provider`; every report's `provider`, `dev_only`, `billed_to` | Fixed: removed stale NVIDIA-dev and pending-run wording; all caches say `nebius`, `false`, and `nebius token factory`. |
| Nebius and NVIDIA-dev base URLs, key environment names, final/dev status | `config.yaml` `providers` | OK. |
| Model IDs for orchestration/edit, perception, drafting, and alternate orchestration | `config.yaml` `providers.*.models`; every report's `usage[].model` | OK; current-cache table now describes the exact Ultra, Super VL, and Nano IDs actually present. Continuous speech correctly lists only Ultra usage. |
| Thinking is disabled | `config.yaml` provider and stage `thinking` fields | OK. |
| Token prices and cached-input prices | `config.yaml` `prices` | OK. |
| Cached-token behavior | every report's `usage[].cached_tokens` | Fixed: each call is `0`; README now says no cache discount was observed and removes speculative caching claims. |
| Maximum video duration, UI upload size, live-run cost/turn/time limits, session/day caps | `config.yaml` `max_duration` and `ui`; UI implementation for 50 MB | OK. |
| Gap and cue limits: 1.5 s minimum, 12 s slots, 8 s cues, six scene frames | `config.yaml` `agent.min_gap_s`, `max_slot_s`, `max_cue_s`, `scene_frames` | OK. |
| Cooking results: duration, 41 turns, 10/12 cues/gaps, 52%/55%, zero overlaps, 3/2/0 verification, no fallback, $0.332, $0.17/min, 162 s | `samples/cached_runs/cooking_roti_0028-0148/report.json` | Fixed: added gaps, cost/minute and latency; retained correctly rounded values. |
| NASA results: duration, 22 turns, 10/10, 53%/67%, zero overlaps, 4/1/1 verification, no fallback, $0.178, $0.10/min, 115 s | `samples/cached_runs/nasa_chile_harvest_0000-0150/report.json` | Fixed: added the report's one unverified claim, cost/minute and latency. |
| Tears of Steel results: duration, 16 turns, 8/8, 50%/58%, zero detected overlaps, 4/1/0 verification, no fallback, $0.134, $0.08/min, 83 s | `samples/cached_runs/tears_of_steel_0015-0155/report.json` | Fixed: removed stale dev-cache and subtitle-derived figures; retained correctly rounded current values. |
| Synthetic kitchen results: duration, 17 turns, 3/4, 32%/42%, zero overlaps, 2/0/0 verification, no fallback, $0.099, $0.20/min, 171 s | `samples/cached_runs/sample_kitchen/report.json` | Fixed: replaced stale 8-turn, four-cue dev result with shipped cache. |
| Continuous-speech results: duration, 2 turns, 0/0, 0%/0%, zero overlaps/verifications, no fallback, $0.007, $0.01/min, 3 s | `samples/cached_runs/failure_continuous_speech/report.json` | Fixed: old table said 3 turns, $0.010 and 27 s. |
| Per-stage call counts, tokens, costs, and totals for all five runs | each report's `usage` and `estimated_cost_usd` | Fixed: replaced the stale four-row development-endpoint cost table with all shipped caches. |
| Orchestration share is 88–95% for cue-producing caches | each report's `cost_by_role.orchestrator / estimated_cost_usd` | Fixed from stale 86–96% range. |
| Every cache is complete and did not use fallback finalization | every report's `status` and `fallback_finalize` | OK; now stated explicitly. |
| Contradicted/unverified limitation totals are four/one | every report's `agent_stats.verifications` | Fixed: removed stale named-title examples and summed shipped reports. |
| Cost/latency range for the shipped 100–110 s caches | NASA and Tears reports' `estimated_cost_usd`, `latency_s` | Fixed to $0.134–$0.178 and 83–115 s; removed dev-endpoint queue/stall claims. |
| Samples shown by the UI are cached real Nebius runs | every report's `provider` and `dev_only` | Fixed: removed the stale “NVIDIA DEV badge” claim. |
| Output artifact, agent-flow, safety-rail, TTS, licensing, and CLI behavior claims | `config.yaml`, repository implementation and named repository files | OK where not report metrics; no shipped-cache number conflicts found. |

Stale historical run tables, “run still pending,” the named “SIMULATION READY” anecdote, and subtitle-derived overlap/coverage numbers were removed because they are not claims supported by the shipped reports.
