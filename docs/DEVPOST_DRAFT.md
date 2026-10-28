# DRAFT - NOT SUBMITTED

## Narrate

### Tagline

Audio description that finds the silence, checks the evidence, and speaks in English and Hindi.

### Summary

Narrate is an agent that turns a video into timed audio description for blind and low-vision viewers. It detects speech-free windows, inspects the corresponding video, drafts concise descriptions, measures the real spoken duration, and refuses cues that would overlap dialogue. Risky claims—such as names, numbers, and on-screen text—are checked against still frames before finalization. The result includes English and Hindi description tracks, narrated videos, transcripts, a results report, and a public trace of model calls, costs, tool decisions, and corrections.

The system uses different Nemotron models for planning, visual perception, economical drafting, verification, and translation. Timing and spend limits are enforced in code, while a fallback finisher preserves verified work when an agent run stops early. Narrate is intentionally an assistive drafting tool rather than a compliance guarantee: human review remains necessary. The project was built October 27–30, 2026, for the Apps & Agents track, with both an offline mock path and cached real-run evidence.

### How it is built

Narrate is a Python tool-calling agent. Silero VAD identifies speech and safe gaps; the agent inspects those windows, maintains an evidence board, drafts to a per-gap word budget, synthesizes and measures each cue, independently verifies risky claims, translates accepted cues, and mixes narration while ducking the original audio. WebVTT tracks, transcripts, narrated MP4s, `trace.json`, and `report.json` make the output and the agent's decisions inspectable.

The Token Factory roles and exact model IDs are taken from [`config.yaml`](../config.yaml):

| Config role | Model ID | Job in Narrate |
|---|---|---|
| `perceive` | `nvidia/Nemotron-3.5-Super-VL` | Video inspection, scene context, and still-frame verification |
| `fit` | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | Description drafting to a word budget |
| `fit_alt` | `nvidia/Nemotron-3_5-Lightning` | Alternate fitting/drafting model |
| `edit` | `nvidia/Nemotron-3-Ultra-550b-a55b` | Hindi translation and editing |
| `orchestrate` | `nvidia/Nemotron-3-Ultra-550b-a55b` | Plan–act–observe tool orchestration |
| `orchestrate_alt` | `nvidia/nemotron-3-super-120b-a12b` | Lower-cost alternate orchestrator |

All Token Factory model roles use the OpenAI-compatible base URL `https://api.tokenfactory.nebius.com/v1/`, as configured in `config.yaml`.

### Where Token Factory helped

Token Factory provides one API and one model catalog for the complete agent: visual understanding, economical drafting, multilingual editing, and tool orchestration differ only by model ID. That makes per-role model selection straightforward and lets Narrate reserve the largest model for decisions while using cheaper models for high-volume work. Reported token usage is priced per call, so the same trace can enforce run-level spend limits and show where the budget went. The configuration also supports a lower-cost alternate orchestrator and per-model regional endpoints. Cached-input prices are configured, but the shipped reports record zero cached tokens, so the measured totals below do not claim a cache discount.

### Results

These are real cached Token Factory runs, not mock results. Values are rounded from the named `report.json` source in each row; coverage is the percentage of narratable-gap time occupied by cues, overlaps are measured against Narrate's speech detector, and latency is summed model latency.

| Clip | Turns | Cues / narratable gaps | Coverage EN / HI | Detected overlaps | Verified / contradicted / unverified | Cost | Cost/min | Model latency | Source |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Cooking (roti), 120 s | 41 | 10 / 12 | 52% / 55% | 0 | 3 / 2 / 0 | $0.332 | $0.17 | 162 s | [`report.json`](../samples/cached_runs/cooking_roti_0028-0148/report.json) |
| NASA harvest, 110 s | 22 | 10 / 10 | 53% / 67% | 0 | 4 / 1 / 1 | $0.178 | $0.10 | 115 s | [`report.json`](../samples/cached_runs/nasa_chile_harvest_0000-0150/report.json) |
| Tears of Steel, 100 s | 16 | 8 / 8 | 50% / 58% | 0 | 4 / 1 / 0 | $0.134 | $0.08 | 83 s | [`report.json`](../samples/cached_runs/tears_of_steel_0015-0155/report.json) |
| Kitchen (synthetic), 30 s | 17 | 3 / 4 | 32% / 42% | 0 | 2 / 0 / 0 | $0.099 | $0.20 | 171 s | [`report.json`](../samples/cached_runs/sample_kitchen/report.json) |
| Continuous speech, 30 s | 2 | 0 / 0 | 0% / 0% | 0 | 0 / 0 / 0 | $0.007 | $0.01 | 3 s | [`report.json`](../samples/cached_runs/failure_continuous_speech/report.json) |

The continuous-speech case produced no cues by design: there was no safe narratable gap. All five source reports have `provider: nebius` and `status: complete`.

### Honest limitations

- Visual models can hallucinate motion and on-screen text. Across these reports, verification contradicted four claims and left one unverified; verification reduces risk but does not prove correctness.
- Narrate cannot pause or extend a video. When speech is continuous, it stays silent instead of talking over the speaker.
- Zero detected overlap means zero overlap with the system's own speech regions, not a guarantee that quiet, robotic, or masked speech was detected.
- Coverage measures occupied gap time, not whether the descriptions captured the most useful visual information.
- Agent orchestration dominates measured cost, and end-to-end wall time can exceed the summed model latency shown above.
- The default offline voices can sound robotic, Hindi timing is harder to fit, and every final track still needs human editorial and accessibility review.

