# Narrate — Devpost draft (not submitted)

## Tagline

Extended audio description that pauses, explains what just happened, and resumes.

## Inspiration

Ordinary audio description has to fit between dialogue. Lectures, tutorials, and fast scenes often leave no safe gap, so the
choice becomes omitting important visual information or talking over the speaker. Narrate adds an extended mode for that case:
it pauses at a safe boundary, describes completed events, then resumes the source.

## What it does

Narrate turns a video into an extended audio-described video, an audio-only track, WebVTT cues, a transcript, a machine-readable
report, and a public execution trace. The intended chronology contract is “pause after the event ends; describe only what has
already happened.” That contract is being repaired and remains subject to human review.

The original in-gap mode remains available for English and Hindi. It detects speech-free windows, inspects the matching video,
drafts concise descriptions, measures spoken duration, checks risky claims against still frames, and refuses unsafe cues.

## How we built it

Narrate is a Python agent using NVIDIA Nemotron models through Nebius Token Factory. Nemotron Super VL analyzes video and still
frames; Nemotron Ultra plans, writes, edits, and translates; Nemotron Nano handles economical constrained drafting in the in-gap
agent. Deterministic code performs speech detection, pause placement, duration fitting, overlap checks, spend limits, rendering,
and report generation. Every model decision is inspectable in `trace.json` and `trace.md`.

## Shipped cached evidence

These values come directly from `runs/ext/final/*/report.json` on October 29, 2026:

| Clip | Source → output | Pauses | Detected speech overlaps | Estimated cost | Model latency |
|---|---:|---:|---:|---:|---:|
| Roti tutorial | 119.9 s → 229.1 s | 8 | 0 | $0.043 | 114.7 s |
| Continuous-speech lecture | 30.0 s → 64.5 s | 3 | 0 | $0.016 | 35.4 s |

“Zero overlaps” means zero overlap with Narrate's own detected speech regions, not a human certification. The cached cue wording
and chronology are still being audited. Any accuracy score, user-impact statistic, hosted URL, production throughput, or
Token Factory cache-discount claim is **unverified and intentionally omitted**.

## Challenges and lessons

The hard problem was temporal truth, not fluent prose. A description can be visually plausible yet premature if it reveals an
event before the viewer reaches it. Static text, repeated cooking actions, speech boundaries, and long agent histories all
created distinct failure modes. We publish those failures in `issues-found/` and keep human review in the workflow.

## What is next

Finish the chronology repair, re-run the two extended samples, have an accessibility reviewer edit every cue, add Hindi to
extended mode, and only then consider a hosted live demo. The repository already includes a local, key-free cached-samples demo.

Narrate supports work toward WCAG 2.x audio-description criteria; it is an assistive drafting tool, not a compliance guarantee.
