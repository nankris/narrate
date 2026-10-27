# Narrate: build log for the blog (real numbers only; times in IST)

## 2026-10-27 (Tue)

**22:44, model IDs.** The public Token Factory catalog (`/api/public/models_info`) lists five Nemotron models:
- `nvidia/Nemotron-3.5-Super-VL`, us-north1. Its use cases include **"video"**.
- `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`, eu-north1.
- `nvidia/Nemotron-3_5-Lightning`, eu-north1.
- `nvidia/nemotron-3-super-120b-a12b`, us-central1.
- `nvidia/Nemotron-3-Ultra-550b-a55b`, us-central1.

The models sit in three different regions, so per-model base URLs matter.

**22:52, v0 (fixed pipeline, mock).** Codex built the first offline pipeline: probe, perceive, gaps, fit, edit, TTS, mix. 19 tests pass in about 9 s. The mock output is deliberately dumb: four identical cues ("A shape moves across the coloured scene").

**22:55, first real calls on the NVIDIA dev endpoint** (integrate.api.nvidia.com; a dev key, not Token Factory):
- **Video input works there.** Super VL (`nvidia/nemotron-3.5-super-vl-120b-a12b`) accepted a base64 `video_url` mp4. A 4.2 s, 10 fps, 640x360 clip cost **2,554 prompt tokens** (about 600 tokens per second of video). Two JPEG frames of the same clip cost 622 tokens.
- **Reasoning ate the whole budget.** With `max_tokens=400`, all 400 completion tokens were reasoning tokens and the content was empty, for both video and images. A `/no_think` system message did **not** turn this off. `extra_body={"chat_template_kwargs":{"enable_thinking":false}}` did: reasoning tokens dropped to 0 and the answer took 641 tokens (video, 10.5 s) or 68 tokens (images, 0.8 s).
- **The first published failure case is a hallucination.** The clip shows a red square with "RED SQUARE" for 2 s, then the text "BLUE CIRCLE" on white for 2 s. In video mode the model narrated motion that never happens: text "begins to fade out, starting from the left side", and "a blue dot appears at the bottom center". The two-still-frame version was accurate: "(No circle is visible in this frame.)" This is why the agent needs a second-look verification tool. Asset: `01_*_probe_red_square_blue_circle.mp4`.
- **Model availability differs on the dev endpoint.** `nemotron-nano-3-30b-a3b` and `nemotron-3-super-120b-a12b` return **404 "Function not found for account"**, even though `/v1/models` lists them. Ultra, Super VL, Lightning and nano-omni work. On the dev endpoint, Lightning stands in for Nano.
- **Tool calling works.** Ultra (`nvidia/nemotron-3-ultra-550b-a55b`) correctly called `detect_silence_gaps` with `{}` in about 1.2 s, with thinking on or off.
- Lightning returned Hindi in Devanagari ("औरत प्याज काट रही है।"), wrapped in a ```json fence even when asked for JSON only. The parser has to strip fences.

**22:58, sample clips.**
- Tears of Steel (Blender Foundation, CC-BY 3.0), 0:15-1:55, 100 s, 3.8 MB at 640p.
- NASA "Astronauts harvest, eat first chile pepper crop on space station", the first 110 s, 4.2 MB. The NASA caption file is just "[Ambient sounds]".

**23:00, "silence" is the wrong signal.** On the Tears of Steel clip:
- `ffmpeg silencedetect` (-35 dB, 1 s) found **0 gaps**, because the music and ambience never stop.
- WebRTC VAD treated the music as speech: 97% speech at aggressiveness 2 and 87% at 3, leaving 1-3 tiny gaps.
- **Silero VAD** (ONNX, CPU, about 0.5 s for 100 s of audio) found **6 dialogue-free gaps totalling 74.7 s**, with speech at 24%. That lines up with the subtitle file: dialogue at 8-30 s, 35-38.5 s and 46-48 s of the clip. It missed the robotic "Robot's memory synced and locked!" line at 35-38.5 s. Decision: the gap tool uses Silero VAD on top of silencedetect, and the eval uses the subtitles as ground truth for "talked over dialogue". Asset: `02_*_vad_comparison.txt`.

**22:57, redesign.** The hackathon judges *agents*, so the fixed pipeline becomes the baseline. Narrate becomes a tool-calling agent loop with Ultra as the orchestrator: plan → act → observe → reflect, with self-verification and a full trace.

**23:02, the fixed pipeline v1 makes real calls** (nvidia-dev; fit = Lightning, `enable_thinking=false`). Assets: `05_*`.
- **Synthetic kitchen clip (30 s): 12.6 s end to end.** Super VL, video mode: 2,766 prompt tokens and 331 output tokens, 4.5 s. Lightning fit: 1,705 in, 33 out, 0.6 s. Ultra edit: 1,256 in, 87 out, 3.3 s. Would-be Token Factory list cost is about **$0.0028**. Only 2 of 5 gaps got a cue (3 dropped), so gap coverage is 50%. The model read the on-screen text "STEP 1 - chop onions" correctly.
- **Tears of Steel (100 s): 0 gaps, so 0 narration.** silencedetect again. The fixed pipeline fails completely on real films. This is the before shot for the agent with VAD.
- **NASA harvest clip (110 s, ambient audio): one cue lasting 79 s.** The whole clip is "silent", so the pipeline put a 75-word paragraph at 0:00 that describes events happening up to 80 s later. That is not time-aligned audio description. The agent has to split long gaps around events.
- **Super VL video tokens do not scale with length.** 4 s cost 2,554 tokens, 30 s cost 2,766, 100 s cost 2,870 and 110 s cost 2,889. The endpoint seems to sample a fixed number of frames per video, so a 2-minute clip is seen coarsely. That justifies the agent's `inspect_video_segment(start, end)`: zoom in on short segments for detail.
- Bug: report `estimated_cost_usd` shows 0 for nvidia-dev runs even though the per-call usage has the would-be Token Factory costs. To fix: the total should be the sum of the would-be costs.

**23:10, agent v1 (Codex, commit bf693ad): 50 offline tests pass in 27.6 s.** The tool-calling loop has Ultra as orchestrator plus 10 tools. Silero VAD replaced silencedetect.

**23:14–23:18, first real agent run** (nvidia-dev, synthetic 30 s kitchen clip). Assets: `07_*`.
- **Time and steps.** 3 min 44 s wall clock, 101 trace steps, 40 orchestrator turns, which hit `max_steps=40` and triggered the deterministic fallback finisher.
- **Where the time went.** Orchestrator (Ultra): 40 calls, 128 s, 121,496 input and 2,452 output tokens. Super VL: 14 calls, 78 s, 34,593 in and 3,480 out. Lightning: 5 calls, 2.6 s. Ultra Hindi pass: 1 call, 7 s.
- **Would-be Token Factory list cost is about $0.144**, of which Ultra orchestration is $0.130 (90%). The fixed pipeline cost about $0.003 on the same clip. **The agent costs roughly 50x more.** At about 3k input tokens per turn, the conversation history is the cost driver.
- **The self-correction loop works.** It made 4 corrections. Example: Lightning drafted "A yellow outline glitches on brown background while white text cycles 'STEP 1 - chop onions'." (14 words). `check_fit` rejected it three times for the 9-word budget, then accepted "Yellow outline glitches. Text cycles "STEP 1 chop onions"." `commit_cue` also refused a 6.5 s line for a 4.8 s gap.
- **verify_claim worked as intended.** For "yellow rectangle moves", the frames-only second look answered `uncertain`: "movement cannot be confirmed from stills".
- **What broke:**
  1. The orchestrator wrote **no notes**: content is empty when Ultra emits tool calls, so the trace has no "thinking summary".
  2. The Hindi pass hit the word budget, so only 1 of 4 Hindi cues survived. Hindi gap coverage was 11% against 91% for English.
  3. 13 `inspect_video_segment` calls on a 30 s clip, many of them overlapping, until it hit the inspection cap.
  4. One VL response returned the keys `".verdict"` and `".evidence"` (a leading dot), which failed validation.
  5. Byte-based truncation in the trace split Devanagari characters (mojibake).
  6. `estimated_cost_usd` is still 0 for dev runs.
  7. "High-importance events uncovered" counted title-card events at 0-1 s, before the first gap, which can never be narrated.
- The VL also invented "glitches" and "corrupted fragments" for static drawtext. This is another hallucination of motion in video mode.

**23:25 — agent v2 (Codex, f64f963)**: fixes from the real run — required `note` arg on every tool (Ultra returns empty content with tool calls), parallel tool calls + `propose_cue` (fit+commit), per-gap inspection guidance + overlap cache, compact append-only history (prompt-cache friendly), Hindi fit by TTS duration, key normalisation, char-safe truncation, cost reporting, Piper TTS (en_US-ljspeech public domain; hi_IN-priyamvada CC BY-NC-SA). 60 offline tests pass (30.3 s). Mock agent now 9 orchestrator turns (was 40-turn cap in the real run).

**23:27–23:34 — agent v2 real runs** (nvidia-dev free tier, dev only; Ultra orchestrator, Super VL perceive, Lightning draft; costs = would-be Token Factory list price). Assets: `08_*`.

| clip | orchestrator turns | cues | gap coverage EN/HI | cost | wall time | outcome |
|---|---|---|---|---|---|---|
| kitchen (synthetic, 30 s) — v1 | 40 (cap) | 4 | 91% / 11% | $0.144 | 224 s | fallback finalize |
| kitchen — v2 | 8 | 4 | 60% / 70% | $0.050 | 170 s | complete, 0 speech overlaps |
| Tears of Steel (100 s) | 11 | **0** | 0 / 0 | $0.080 | 168 s | **HTTP 500 from Ultra → fallback emitted nothing** |
| NASA harvest (110 s) | 10 | 2 | 20% / 25% | $0.042 | 88 s | complete (narrator VO: only 2 gaps) |
| continuous speech (failure clip) | 3 | 0 | – | $0.009 | 13 s | **correct refusal**: "Cannot narrate safely without extended AD" |

- v2 fixes worked where intended: turns 40 → 8, cost −65%, Hindi coverage 11% → 70%.
- Where the time goes (kitchen): one Ultra turn planning 4 drafts took 40.6 s, Hindi translation 52 s for 591 in / 111 out tokens — free-tier queueing, not tokens. 4 VL inspections ≈ 15 s.
- New real-world failures (→ fix2, Claude): (1) on ToS the agent measured/checked fit 3× with ok=true but never *committed*; then an HTTP 500 killed the loop and the fallback had nothing to commit. (2) drafts described events from the wrong part of the video (gap at 30 s narrated "rocket ignition" from 0–9 s). (3) VTT cues written in commit order, not time order. (4) `verify_claim` was never called in any of the 4 runs — self-verification has to be enforced, not suggested. (5) a 1.1 s gap got a 1-word budget and burned 3 turns. (6) duplicate cue text across two gaps.
- Codex main hit 85% of its 5-hour window after the UI task (limit 78%) → switched coding to Claude CLI.

**23:37–00:00 — fix2 (Claude CLI, commits 2ac70b1 + 3014109)**: fallback finisher that commits best-fitting candidates, retries on 5xx/429/timeouts, drafts grounded only in events overlapping the gap, VTT sorted by time, gaps < 1.5 s skipped, duplicate-cue rejection, and *enforced* verification (finalize refuses until risky cues — on-screen text, numbers, names, low VL confidence — have a second look). Root cause of the "wrong time" events: a 6 s pre-roll in the inspection window, not a timestamp offset. 89 offline tests (≈42–66 s).

**00:01 — Super VL video input re-checked** (nvidia-dev): base64 `video_url` MP4, 4 s synthetic clip → HTTP 200, JSON parsed, both on-screen texts transcribed ("RED SQUARE", "BLUE CIRCLE"), 1,392 input tokens, 1.8 s. Frame grid (420 tokens) and separate frames (738 tokens) also pass. Asset `09_*`.

**00:01–00:10 — agent v3 real runs (fix2 code)**, nvidia-dev, would-be TF list price. Asset `10_*`.

| clip | turns | cues | gap cov EN/HI | verifications (ok/contradicted) | cost | wall | notes |
|---|---|---|---|---|---|---|---|
| kitchen 30 s | 11 | 4 | 75% / 85% | 2 / 0 | $0.082 | 161 s | was $0.050 / 60% in v2: verification turns cost money |
| Tears of Steel 100 s | 30 (cap) | **4** (was 0) | 34% / 43% | 1 / **4** | $0.198 | 212 s | fallback finisher committed after turn cap |
| NASA harvest 110 s | 9 | 2 | 29% / 42% | 2 / 0 | $0.047 | 156 s | 1 APITimeout retried and recovered |
| continuous speech | 2 | 0 | – | – | $0.006 | 6 s | correct refusal (needs extended AD) |

- **Verification earned its keep on Tears of Steel**: Super VL (video mode) claimed on-screen text "40 YEARS LATER" and "SIMULATION READY"; the frame-based second look contradicted both. The Netherlands Film Fund credit was *supported*. But the verifier also contradicted "PLAYBACK READY", text it had itself just reported — the checker is not ground truth either. Asset `11_*`.
- **Subtitle ground truth (ToS, 100 s)**: dialogue-free time 75 s; narrated 23.7 s of it (31.7%); **0.39 s overlap with subtitled dialogue** (VAD boundary vs SRT timing) — not zero. v2 had narrated 0 s. Asset `12_*`.
- **Cost driver**: Ultra orchestrator = 96% of the ToS run ($0.190 of $0.198). Input grows ~200 tokens/turn (2,857 → 9,002 over 30 turns), 0 cached tokens reported on the dev endpoint. VL perception for 5 segments cost $0.004.
- **NASA failure**: the clip has only ambient audio, VAD returns two huge gaps (79 s, 26 s) and the agent wrote one long 47-word cue per gap → 65 s of visuals undescribed. → fix3: split long gaps into 6–12 s slots at scene cuts, cap cue length, trim orchestrator history.

**00:13–00:28 — fix3 (Claude, f39226e)**: long gaps split into 6–12 s slots (snapped to ffmpeg scene cuts), cue length cap 8 s, orchestrator history compaction (last 6 turns verbatim, older tool results summarised), turn budget scales with slot count. 104 offline tests.

**00:30–00:39 — agent v4 real runs (fix3)**, nvidia-dev, would-be TF list price; built straight into the UI cache (`build_cached_runs.py --provider nvidia-dev`). Asset `15_*`.

| clip | turns | cues / slots | gap cov EN/HI | verified / contradicted | cost | wall |
|---|---|---|---|---|---|---|
| kitchen 30 s | 12 | 4 / 4 | 80% / 88% | 4 / 0 | $0.082 | 151 s |
| Tears of Steel 100 s | 14 | 4 / 9 | 32% / 35% | 1 / 0 | $0.082 | 169 s |
| NASA 110 s | 36 (cap) | **2 / 10** | 13% / 16% | 0 / 1 | **$0.209** | 213 s |
| continuous speech | 3 | 0 | – | – | $0.011 | 12 s |

- ToS got cheaper (30 → 14 turns, $0.198 → $0.082) and stayed at 0 detected overlaps.
- **NASA got worse — a new failure caused by my own fix.** History compaction threw away old inspection results, so Ultra forgot it had looked: it inspected all 10 slots *three times* (31 inspect calls; the cache made the repeats free on the VL side, but each turn re-sent the growing context — orchestration was $0.197 of $0.209). It never called the drafting model; at the turn cap it wrote cue text itself and invented "typing on a laptop" and "a window showing Earth's blue curve" (the frame verifier contradicted the second). The fallback then dropped 7 slots because none had a draft.
- Lesson: compress *conversation*, never *evidence*. → fix4: persistent evidence board in the state message, refuse re-inspection with a pointer to the board, treat orchestrator-written text as unverified, fallback drafts in one batched Nano call.

**00:45–01:07 — fix4 (Claude, af593b1)**: persistent evidence board kept in the state message, re-inspection of an already-covered range refused (`repeat_refusals`), cue text not produced by the drafter flagged as orchestrator-authored and sent to verification, fallback finisher drafts all evidence-only gaps in one batched call. 114 offline tests.

**01:08–01:21 — agent v5 real runs (fix4)**, nvidia-dev, would-be TF list price. Asset `16_*`.

| clip | turns | cues / gaps | gap cov EN/HI | verified / contradicted | cost | wall |
|---|---|---|---|---|---|---|
| kitchen 30 s | 30 | **2 / 4** | 45% / 55% | 0 / 0 | **$0.237** | 196 s |
| Tears of Steel 100 s | 30 | 5 / 8 | 37% / 36% | 1 / 0 | $0.198 | 223 s |
| NASA 110 s | 36 | **7 / 10** | **41% / 51%** | 0 / 2 | $0.322 | 328 s |
| continuous speech | 2 | 0 | – | – | $0.006 | 24 s |

- **NASA fixed what it was meant to fix**: 2 → 7 cues, coverage 13% → 41%, 0 orchestrator-authored cues, only 1 repeat inspection. The verifier contradicted 2 cues and the fallback dropped them instead of shipping them.
- **Kitchen regressed badly — another self-inflicted failure.** 38 `propose_cue` calls for 4 gaps. The batched drafter (Lightning) returned 13–14-word lines for 8–9-word budgets and left out the on-screen text ("STEP 1 - chop onions"), which is the whole point of those shots. Two limits disagreed: the word budget allowed 8 words but the fix3 single-cue cap said "under 3.6 s" and an 8-word line measured 3.74 s. My fix4 prompt told Ultra to "shorten only by deleting words", so it hand-trimmed the same sentence for ~20 turns. Result: 2 cues, 3× the cost of v4.
- ToS: subtitle check 0.39 s overlap, 25.7 s of 75 s dialogue-free time narrated (34.3%); 26 inspect calls for 8 gaps — the frames-fallback path returns empty events, which the coverage refusal does not count.
- Orchestration share: kitchen 97%, ToS 97%, NASA 96%.
- Lesson: every limit the checker enforces must be the same number the drafter is given, and the tool should redraft itself instead of making a 550B model count words. → fix5.
