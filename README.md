# Narrate: an agent that writes audio description

**Upload a video of up to 2 minutes. Narrate returns an audio-description track for blind and low-vision viewers, in English and Hindi.** It writes descriptions only into the moments when nobody is speaking, checks its own claims before it speaks them, and outputs:

- WebVTT description tracks (`ad_en.vtt`, `ad_hi.vtt`) and plain-text transcripts;
- narrated MP4s with the original audio ducked under each description;
- `trace.json` / `trace.md`, the full agent trace (every tool call, model, token count, cost and correction);
- `report.json`, the results card (coverage, overlaps, verifications, cost per minute, latency).

Narrate is a **tool-calling agent built on NVIDIA Nemotron**, designed to run on **Nebius Token Factory**. It was built for the Nebius × NVIDIA hackathon (Apps & Agents track), Oct 27–30 2026. License: Apache-2.0.

> Audio description supports WCAG 2.x SC 1.2.5 (Audio Description, prerecorded). Narrate is an assistive drafting tool, not a compliance certification. Human review is still required.

![Web UI: cached real run with the agent trace and results card](blog-assets/19_2026-10-28_ui_samples.png)

---

## Quickstart (offline, no key, about 2 min)

You need Python 3.13 (tested), `ffmpeg`/`ffprobe`, and `espeak-ng` (with `en` and `hi` voices).

```bash
git clone <this repo> narrate && cd narrate
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install silero-vad --no-deps          # MIT Silero VAD ONNX model, no torch
.venv/bin/python -m pytest -q                       # fully offline
.venv/bin/python -m app.app                         # web UI → http://127.0.0.1:7860 (cached real runs, zero cost)
.venv/bin/python -m narrate agent samples/sample_kitchen.mp4 --out runs/demo --provider mock
```

`--provider mock` is scripted and offline. It exercises the whole agent loop (tools, corrections, verification, fallback, TTS, mixing), but its descriptions are synthetic and its costs are $0. **Never read mock output as a quality or cost number.**

## Real mode

```bash
# Final runs: Nebius Token Factory
export NEBIUS_API_KEY=...            # read from env only, never from files or the browser
.venv/bin/python scripts/smoke_provider.py        # one-command readiness check, ~$0.01, prints READY / NOT READY
.venv/bin/python -m narrate agent my_clip.mp4 --out runs/real --provider nebius --strict --budget-usd 0.50
.venv/bin/python -m narrate agent my_clip.mp4 --out runs/real --provider nebius --orchestrator super   # about 3x cheaper orchestration

# Development only: NVIDIA build endpoint (free tier, 40 rpm)
export NVIDIA_DEV_API_KEY=...
.venv/bin/python -m narrate agent my_clip.mp4 --out runs/dev --provider nvidia-dev --strict
```

| Provider | Key env | Base URL (override: `NARRATE_BASE_URL_NEBIUS` / `_NVIDIA_DEV`) | Use |
|---|---|---|---|
| `nebius` (default) | `NEBIUS_API_KEY` | `https://api.tokenfactory.nebius.com/v1/` | final runs and demo numbers |
| `nvidia-dev` | `NVIDIA_DEV_API_KEY` | `https://integrate.api.nvidia.com/v1` | development testing only; reports are marked `dev_only: true` |
| `mock` | – | – | offline tests and demo |

- If the provider's key is missing, the run exits with code 2 and a clear message. It never falls back to mock silently.
- Each model entry in `config.yaml` can set its own `base_url`, for example a regional data-plane URL such as `https://api.tokenfactory.us-central1.nebius.com/v1/`.
- **`scripts/smoke_provider.py [--provider nebius|nvidia-dev]`** runs the real code paths with tiny inputs. It checks:
  - every configured model ID is served (if not, it suggests similar served IDs);
  - Nano drafting returns JSON;
  - Ultra returns a tool call;
  - Super VL reads on-screen text from a 4 s MP4 sent as `video_url` and from frames.

  Spend cap $0.05; exit 0 means ready. On nvidia-dev it passed all 6 checks for $0.0035. Without a key it exits 2 and makes no calls.
- **Model IDs** live in `config.yaml` (`providers.nebius.models`). You can override one per role without editing files, for example `NARRATE_MODEL_ORCHESTRATE=nvidia/nemotron-3-super-120b-a12b` (roles: `PERCEIVE`, `FIT`, `FIT_ALT`, `EDIT`, `ORCHESTRATE`, `ORCHESTRATE_ALT`).
- `scripts/list_models.py --provider nebius` lists the Nemotron IDs your key can see.
- Every run has a hard spend cap (SpendGuard). Real-mode raw responses are saved, truncated, with no headers. Keys are never logged.

## How the agent works

```mermaid
flowchart LR
    U["Nemotron 3 Ultra<br/>orchestrator<br/>plan → act → observe → reflect"] -->|tool calls| T{tools}
    T --> G["detect_speech_gaps<br/>Silero VAD + slotting"]
    T --> I["inspect_video_segment<br/>Super VL · video"]
    T --> D["draft_description<br/>Nano · word budget"]
    T --> F["check_fit / propose_cue<br/>measured TTS duration"]
    T --> V["verify_claim<br/>Super VL · still frames"]
    T --> H["translate_hindi<br/>Ultra"]
    T --> R["render_preview / finalize"]
    G & I & D & F & V & H & R -->|observations + state| U
```

1. **Plan.** Ultra receives the video facts and a step, spend and time budget. It calls `detect_speech_gaps`: Silero VAD finds speech-free windows, gaps under 1.5 s are skipped, and long gaps are split into 6–12 s slots at scene cuts.
2. **Act.** It inspects each slot with **Super VL**, which watches the actual video segment. What it sees goes onto a persistent **evidence board** that survives history compaction, and re-inspecting a covered slot is refused. Then it drafts all slots in one batched **Nano** call. Every gap has a single `max_words` limit, shared by the drafter and the checker. A draft over the limit is re-asked once and then cut deterministically, keeping any on-screen text first.
3. **Observe.** `propose_cue` synthesises the line with the real TTS voice, measures how long it takes to speak, and checks four things: it fits the gap, it does not overlap speech, it is no longer than 8 s, and it is not a duplicate. Failures come back with reasons. On a second failure the tool redrafts the line itself, so the 550B model never counts words.
4. **Reflect and self-verify.** `finalize` refuses to finish while any risky cue is unverified. Risky means it quotes on-screen text, numbers or names, came from low-confidence perception, or was written by the orchestrator itself. Those claims go to `verify_claim`, which uses a different modality (still frames rather than video). A contradicted claim is un-committed and redrafted.
5. **Hindi.** Ultra translates the cues, then the Hindi lines are re-checked for timing. Hindi runs longer, so fit is measured on the Hindi TTS.
6. **Finish.** The narration is mixed with the original audio ducked, and the tracks, transcripts, report and trace are written.

Safety rails:

- step, spend and wall-clock budgets;
- retries with backoff on HTTP 5xx, 429 and timeouts;
- a deterministic **fallback finisher**: on any stop it commits the best fitting candidates, drafts missing slots in one batched call, verifies if the budget allows, and finalizes;
- cue timestamps come only from detected gaps, so models cannot move narration over speech;
- tool errors are explicit: `invalid arguments: …` or `unknown gap_id N; valid gap ids: […]`. In real runs, opaque errors (`ValidationError`, `StopIteration`) made Ultra retry blindly for 13–21 calls.

The trace is the product's centrepiece. Every step records the role, a short public `note` (required on every tool call; it is not chain-of-thought), arguments, results, model, tokens, cost, latency and correction links. The web UI streams it live.

API: `narrate.agent.run_agent(path, out_dir, provider, langs, max_steps, budget_usd, on_step=callback)`. The old fixed pipeline is kept as a baseline: `python -m narrate pipeline ...`.

## Nemotron, model by model

| Role | Token Factory model | Dev-endpoint model | Why this model |
|---|---|---|---|
| Orchestrator | `nvidia/Nemotron-3-Ultra-550b-a55b` (or `nvidia/nemotron-3-super-120b-a12b` via `--orchestrator super`) | `nvidia/nemotron-3-ultra-550b-a55b` | Reliable multi-step tool calling with parallel calls. It decides what to inspect, what to rewrite and what to verify. |
| Perceive and verify | `nvidia/Nemotron-3.5-Super-VL` | `nvidia/nemotron-3.5-super-vl-120b-a12b` | Accepts **video input** (base64 MP4 `video_url`, confirmed) for perception, and still images for independent verification. |
| Draft | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | `nvidia/nemotron-3.5-lightning-30b-a3b` (Nano is not enabled on the dev key) | Cheap and fast enough to call once per slot or batch, and it follows hard word budgets. |
| Hindi | `nvidia/Nemotron-3-Ultra-550b-a55b` | same | The best multilingual quality of the set; it is one call per run. |

All four run with reasoning disabled through `chat_template_kwargs.enable_thinking=false`. With thinking on, reasoning consumed the whole `max_tokens` budget and returned empty content. `/no_think` alone did not disable it.

**Measured usage per model**, from the final cached runs: NVIDIA dev endpoint, final code, priced at Token Factory list prices. Super VL calls are split into perceive + verify.

| Clip | Ultra orchestrator | Super VL perceive + verify | Lightning draft (Nano on TF) | Ultra Hindi | Total |
|---|---|---|---|---|---|
| Kitchen (synthetic), 30 s | 8 calls, 41.7k in / 0.9k out, $0.045 | 4 + 4 calls, 15.6k in, $0.006 | 2 calls, $0.0002 | 1 call, $0.001 | **$0.052** |
| Tears of Steel, 100 s | 14 calls, 103.2k / 5.5k, $0.120 | 6 + 5 calls, 22.0k, $0.008 | 7 calls, $0.0007 | 2 calls, $0.004 | **$0.171*** |
| NASA harvest, 110 s | 16 calls, 116.6k / 3.7k, $0.124 | 8 + 3 calls, 25.4k, $0.010 | 5 calls, $0.0007 | 1 call, $0.003 | **$0.137** |
| Continuous speech, 30 s | 3 calls, 9.9k / 0.1k, $0.010 | – | – | – | **$0.010** |

\* includes $0.038 charged conservatively for dev-endpoint calls that failed with HTTP 500/503 or stalled. The SpendGuard counts uncertain spend against the cap.

Orchestration is 86–96% of the cost. Its input grows each turn, and the dev endpoint reported 0 cached tokens. That is why `--orchestrator super` exists (Super is $0.30/$0.90 per 1M tokens vs Ultra's $1/$3) and why prompt-prefix caching matters (see below).

## Where Token Factory helps

- **One OpenAI-compatible API for the whole Nemotron family.** The orchestrator, vision, drafting and translation models are just different `model` strings on the same client and key. Per-role model choice is what makes the economics work: the expensive model only plans, and the cheap model writes.
- **Price spread inside one provider.** Per 1M input/output tokens: Nano $0.06/$0.24, Super VL $0.30/$0.90, Ultra $1/$3. Narrate prices every call from reported usage and enforces per-run, per-session and per-day caps.
- **Cached-input pricing** (Ultra $0.12 vs $1.00 per 1M) fits an agent loop, whose prompt prefix (system prompt, tools, state) repeats every turn. Narrate keeps that prefix stable on purpose. *To verify on Token Factory:* the dev endpoint reported 0 cached tokens.
- **Model catalog and regional endpoints.** `/v1/models` and the per-model `base_url` in config cover regional data planes.

**Not yet verified on Token Factory:** every real number in this README comes from the NVIDIA dev endpoint. A `NEBIUS_API_KEY` run is still pending. Video-input acceptance, JSON mode, tool calling, caching and latency may differ there, so treat the costs as *would-be list price*.

## Results card

All figures are real runs on the **NVIDIA dev endpoint (dev only)**, with costs at Token Factory list prices. They are the runs cached in the UI (`samples/cached_runs/`, evidence in `blog-assets/18_*`). Overlaps are counted against Narrate's own speech detection; for Tears of Steel they are also checked against the film's subtitles.

| Clip | Turns | Cues / narratable gaps | Gap coverage EN / HI | Detected overlaps | Verified / contradicted | Cost | Cost per min | Wall time |
|---|---|---|---|---|---|---|---|---|
| Kitchen (synthetic), 30 s | 8 | 4 / 4 | 74% / 76% | 0 | 3 / 0 | $0.052 | $0.10 | 65 s |
| Tears of Steel, 100 s | 14 | 8 / 8 | 60% / 62% | 0 | 4 / 1 | $0.171 | $0.10 | 375 s † |
| NASA harvest, 110 s | 16 | 10 / 10 | 43% / 53% | 0 | 1 / 1 | $0.137 | $0.07 | 174 s |
| Continuous speech, 30 s | 3 | 0 / 0, refused by design | – | 0 | – | $0.010 | – | 27 s |

† includes dev-endpoint HTTP 500/503 retries and a 139 s stall. The fallback finisher then finalized the 8 committed cues.

**Ground truth, Tears of Steel vs its subtitles:** 41.7 s of the 75 s dialogue-free time was narrated (55.6%). **0.39 s** overlapped subtitled dialogue, from one VAD boundary that was the same in every version.

**How we got here.** There were seven real-run rounds. Each one found a failure, which is published in `issues-found/` and `blog-assets/BLOG_NOTES.md`:

| Version | Kitchen | Tears of Steel | NASA |
|---|---|---|---|
| v2: first agent | 8 turns, $0.050 | **0 cues** (HTTP 500 + never committed) | 2 cues |
| v3: fix2 | 11 turns, $0.082 | 30 turns, $0.198, 4 cues | 2 cues, 29% |
| v4: slots | 12 turns, $0.082 | 14 turns, $0.082, 4 cues | **36 turns, 2 cues, re-inspection loop** |
| v5: evidence board | **30 turns, $0.237, 2 cues** (propose loop) | 30 turns, 5 cues | 36 turns, 7 cues |
| v6: one word limit | 7 turns, $0.045 | 25 turns, 4 cues (**missing-note lockup**) | 36 turns, 8 cues |
| v7: final | 8 turns, $0.052, 4 cues | 14 turns, 8 cues, 60% | 16 turns, 10 cues, $0.137 |

## Limitations and published failure cases

We publish failures. Each has evidence, a root cause and a status in [`issues-found/`](issues-found/README.md), and the raw traces are in [`blog-assets/`](blog-assets/).

- **Continuous speech means no safe gaps.** The lecture clip gets **0 cues, by design**. Narrate refuses rather than talk over the speaker. Real "extended" description that pauses the video is not implemented.
- **The vision model hallucinates**, especially motion and on-screen text. On Tears of Steel, Super VL (video mode) claimed the on-screen texts "40 YEARS LATER" and "SIMULATION READY". The frame verifier contradicted both (`blog-assets/11_*`). The verifier is fallible too: it also rejected "PLAYBACK READY", text it had just reported itself. Verification reduces errors; it does not prove correctness.
- **Verification has gaps.**
  - "MEMORY PLAYBACK GLOBAL" was marked supported although the verifier's own evidence read "REPLAY ATTACK - GLOBAL".
  - On the kitchen clip, a supported claim ("STEP 1 - chop onions, then Stir and serve") was committed as only its first half, so the cue is stale for most of its window.
  - The first kitchen card's title was described as "yellow vertical rectangle" instead of being read.

  On-screen text accuracy is the weakest point.
- **The orchestrator can loop, invent, or retry blindly.** Each of the following was fixed, and each has an issue file:
  - Ultra re-inspected 10 slots three times after history compaction and wrote invented cue text ("a window showing Earth's blue curve").
  - It hand-trimmed one sentence for about 20 turns.
  - It retried 13–21 times after opaque tool errors.

  The guards are an evidence board, repeat refusal, one shared word limit, tool-side redrafting and explicit errors. Ultra still decides how many turns to spend, and 14–16 turns is typical for a 100 s clip.
- **The speech detector is not ASR.** Silero misses some robotic or quiet speech, and music can mask gaps. On Tears of Steel, narration overlapped subtitled dialogue by **0.39 s** in one run (`blog-assets/12_*`), so "0 detected overlaps" does not mean 0 real overlaps.
- **Coverage is a temporal proxy**, not a measure of semantic usefulness. Events during dialogue are listed as `events_in_speech_regions` and cannot be narrated without extended AD.
- **Cost and latency.** A 100–110 s clip takes about 3–6 min and $0.14–0.17 on the dev endpoint with Ultra orchestrating (86–96% of cost). Free-tier errors and queueing added up to 139 s to a single call. `--orchestrator super` should cut orchestration cost about 3× on Token Factory, but that is untested.
- **Voices.** espeak-ng sounds robotic. Piper's `en_US-ljspeech` is public domain. Piper's `hi_IN-priyamvada` is **CC BY-NC-SA, non-commercial**, so use espeak for commercial use. Hindi has not had native-speaker review.
- **Licensing.** The Tears of Steel soundtrack is listed under CC BY-ND 3.0. Narrate only ducks it, but check before redistributing narrated outputs.
- Only clips of 2 minutes or less, and English or Hindi.

## Web UI

`python -m app.app` serves Gradio on 127.0.0.1:7860. It does not share by default.

- **Samples tab (zero cost):** cached **real** runs (NVIDIA DEV badge) with the original vs narrated video, an EN/HI toggle, an **Eyes closed** toggle (audio only), the agent trace with model chips (Ultra purple, VL blue, Nano green, tools grey) and corrections highlighted, VTT cues, the results card and downloads. Each cache shows a MOCK, DEV ONLY or NEBIUS badge.
- **Run tab:** upload a clip of up to 120 s and 50 MB, and watch the trace stream live.
  - Hard limits per live run: $0.25, 24 orchestrator turns and 300 s. When a limit is hit, the fallback finisher ships what is already committed. Set them with `NARRATE_UI_RUN_CAP`, `NARRATE_UI_MAX_TURNS` and `NARRATE_UI_TIMEOUT_S`.
  - Spending caps: $0.25 per session and $3.00 per IST day (stored in `runs/ui_spend.json`).
  - `nebius` appears only if `NEBIUS_API_KEY` is set on the server. `nvidia-dev` also needs `NARRATE_ENABLE_DEV=1`. Keys never come from the browser.
- To rebuild the caches: `python scripts/build_cached_runs.py --provider mock|nvidia-dev|nebius`. Screenshots: `python scripts/screenshot_ui.py`.

## Samples and licenses

| File | Source | License |
|---|---|---|
| `sample_kitchen.mp4`, `failure_continuous_speech.mp4` | generated by `scripts/make_sample.py` | Apache-2.0 (ours) |
| `tears_of_steel_0015-0155.mp4` + `.en.srt` | *Tears of Steel*, © Blender Foundation, mango.blender.org | CC BY 3.0 (soundtrack caveat above) |
| `nasa_chile_harvest_0000-0150.mp4` | NASA Image and Video Library, `Plant_Habitat-04_Harvest` | NASA media guidelines; no endorsement implied |

Details: [`samples/SOURCES.md`](samples/SOURCES.md). Silero VAD (MIT): [`narrate/assets/`](narrate/assets/README.md). espeak-ng and Piper (GPL-3.0) are run as external CLIs and are not vendored.

## Repository map

```text
narrate/agent/   agent loop, tools, orchestrator client, VAD
narrate/         provider client + SpendGuard, media/ffmpeg, TTS, baseline pipeline
app/             Gradio UI          scripts/   samples, smoke tests, caches, eval_against_subs
tests/           offline pytest      issues-found/   published failures and fixes
blog-assets/     dated evidence + BLOG_NOTES.md      DEMO_SCRIPT.md   demo recording guide
```

Development notes: the coding was delegated to Codex and Claude CLIs under human direction (see `_agent_logs/`). Every real-run number above was measured, not estimated.

## License

Apache-2.0. See [LICENSE](LICENSE). Copyright 2026 Nandigam Hari Krishna.
