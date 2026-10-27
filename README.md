# Narrate

Audio description for blind and low-vision viewers: upload a short video through the CLI and receive English and Hindi narration, WebVTT captions, transcripts, and narrated MP4s with original sound ducked during descriptions. This core pipeline supports the accessibility goal of WCAG 1.2.5 (prerecorded audio description); it is not a compliance certification. No web UI is included.

Built during the submission period for the Nebius x NVIDIA Global AI Hackathon, Best Apps & Agents track, 27 October 2026. Copyright 2026 Nandigam Hari Krishna. Apache-2.0.

## 30-second quickstart

Requires Python 3.13, ffmpeg/ffprobe and espeak-ng with `en` and `hi` voices. Python dependencies install from pip; everything after installation runs offline in mock mode.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m narrate run samples/sample_kitchen.mp4 --out runs/demo --mock
.venv/bin/python -m pytest -q
```

Open `runs/demo/narrated_en.mp4` or `narrated_hi.mp4`. The same directory contains `ad_en.vtt`, `ad_hi.vtt`, `transcript_en.txt`, `transcript_hi.txt`, and `report.json`. Checked-in mock artifacts are in `samples/outputs_mock/`. Regenerate the synthetic sample using `.venv/bin/python scripts/make_sample.py`.

**Mock means synthetic descriptions, not visual understanding.** Events come from sampling timestamps, with a fixed shape description and built-in Hindi phrase. Missing `NEBIUS_API_KEY` automatically selects mock with a warning. Zero mock cost and latency do not predict real quality, provider cost, or provider latency.

## Real mode (not exercised in this build)

```bash
export NEBIUS_API_KEY='YOUR_RUNTIME_KEY'
.venv/bin/python -m narrate run your_video.mp4 --out runs/real --lang en,hi --budget-usd 0.25
```

Use only a runtime environment variable for the key; no dotenv loading, saved credentials, or request logging. Real mode sends media to Token Factory and incurs charges. No provider calls were made during development. Catalog/model availability and all provider behavior below are **to verify** with an authorized real key.

`config.yaml` controls models, prices, budget, silence detection, maximum duration (120 seconds), sample interval, perception strategy, speech rates, voices and ducking. `NARRATE_CONFIG` selects another YAML file. Each model may set `base_url` (for example `https://api.tokenfactory.us-central1.nebius.com/v1/`) and `json_mode: false` if JSON mode is unsupported. To select Lightning, replace `models.fit` with the configured `models.lightning` mapping. `auto` tries video, then frame grids on API errors; explicit `video` surfaces video errors, and `frames` skips video. Budget errors always stop, without fallback spending.

`espeak` is the default backend. `silent` makes silent test narration. Optional `piper` requires separately installed `piper-tts`, local voice models and `tts.piper_models: {en: /path/en_US.onnx, hi: /path/hi_IN.onnx}`; companion model config files must be present. Piper is not installed or verified here.

## Pipeline

```text
ffprobe duration check
    -> Super VL: compressed video / timestamped frame contact sheets
    -> ffmpeg silence detection (NumPy energy fallback)
    -> Nano: batched, gap-budgeted English cues, one shorter retry
    -> Ultra: one editorial call + Hindi translation
    -> deterministic validation + espeak/Piper/silent TTS
    -> atempo <=1.35x, trim and flag if still too long
    -> ffmpeg delay + original-audio ducking -> MP4 / VTT / text / report
```

Cue timestamps come exclusively from detected gaps, with 80 ms inset at both ends. Models cannot move cues. Budgets are `max(0, floor(gap_seconds * words_per_second - margin))`. English defaults to 2.3 words/sec, Hindi 2.0. Overlong Nano text gets one shorter-budget retry, then truncation with a report entry. Invalid Ultra output falls back to fitted English; Hindi files are still produced but contain no Hindi descriptions, explicitly reported as unavailable. Continuous sound produces empty cue tracks, not narration over dialogue.

The callable API is `narrate.pipeline.run(path, out_dir, langs, client, budget, progress=callback, config=None)`. The callback receives `{stage, status}` events. It runs synchronously and can be placed in a UI worker later. Pass a reusable `SpendGuard` as `budget` for a session cap. Provider retries reserve cost separately; failed attempts retain their reservation because billing is uncertain. A conservative UTF-8 byte bound (including media payload) estimates input tokens before requests; actual usage reconciles successful calls. This may reject affordable media requests. Provider billing/tokenization is not locally guaranteed; reported usage above the estimate stops the run. No automatic calls continue after budget exhaustion. `report.json` is saved on failure.

## Nemotron model-by-model

Illustrative token/cost estimates below are planning assumptions, **not measured usage**. Rates are configured USD per million input/output tokens. Batched fitting minimizes requests.

| Stage | Model id | Why this model | Calls/video | Illustrative input/output tokens; cost |
|---|---|---|---|---|
| Perceive | `nvidia/Nemotron-3.5-Super-VL` | Visual events and readable text | 1; fallback may add 1 logical call | 8,000/1,000; $0.00330 at 0.30/0.90 |
| Fit | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | Cheap constrained gap writing | 1 batched; up to 1 shorter retry | 2,000/500; $0.00024 at 0.06/0.24 |
| Alternate fit | `nvidia/Nemotron-3_5-Lightning` | Configurable low-cost alternative | Replaces Nano | 2,000/500; $0.00024 at 0.06/0.24 |
| Edit | `nvidia/Nemotron-3-Ultra-550b-a55b` | Global consistency and bilingual editing | 1 when there are cues | 2,000/1,000; $0.00500 at 1.00/3.00 |

Each logical SDK call permits two transport retries with backoff; Ultra has one logical editorial call. Empty-gap videos skip fit and edit. Reports include configured models, actual/mock call records, token counts, reserved/estimated cost, strategy, fallback, per-stage latency, scheduling coverage, dropped slots and TTS trim flags.

## Where Token Factory helped

The integration is designed around one OpenAI-compatible endpoint for three Nemotron sizes: expensive visual perception and global editing surround cheap Nano fitting. Per-stage model selection allocates cost according to the task; Nano's configured rate also supports future per-gap calls. JSON mode and regional per-model endpoints are configurable. These integration advantages are **to verify** in real mode: video_url acceptance, image-grid interpretation, JSON mode across each model, Hindi quality, regional availability, actual tokenization and pricing. Offline tests verify our request construction paths and deterministic pipeline, not these service claims.

`scripts/list_models.py` prints configured public-catalog IDs when no key exists and lists live Nemotron IDs when a key is present. Catalog provenance supplied for this task: public catalog, fetched 27 Oct 2026. `scripts/smoke_video_input.py --allow-paid` is an explicitly opted-in real smoke test for a tiny video and frame grid; results save to `runs/smoke/`. It was not run with a key.

## Results card — MOCK

Synthetic 30-second kitchen-title clip; espeak English and Hindi; no real visual analysis or human accessibility evaluation.

| Metric | MOCK result |
|---|---|
| Scheduled gap coverage | 91.77% English / 91.77% Hindi |
| Overlaps with dialogue | 0 detected-gap boundary violations (not a speech-recognition assessment) |
| Cues dropped | 1 gap too short after inset/budget |
| TTS cues trimmed | 0 |
| Cost/minute | $0.00, offline mock |
| Pipeline latency | Approximately 3 seconds on this shared CPU host; see cached report |

For a real results card replace these fields with measured values, model/region, clip cohort, accessibility review findings, and date. Gap coverage measures allocated cue windows divided by detected silent seconds, not useful information coverage or audible narration occupancy.

## Limitations & published failure cases

- Fast cuts and sparse frame sampling miss actions; timestamp mock events do not detect visual scenes.
- Sub-second gaps may be skipped; aggressive word truncation and speech trimming can hurt comprehension.
- Continuous speech/music can leave no safe gaps: extended AD with paused video is needed and not implemented.
- Energy/silence detection is not speech recognition. Quiet speech can be mistaken for silence; music can hide safe speech-free intervals. Zero scheduled violations cannot establish zero real dialogue overlap.
- On-screen Hindi text and translations need native-reader review. Ultra failure leaves Hindi descriptions unavailable.
- espeak voices sound robotic; Piper and its Hindi voices remain unverified.
- VL hallucinations and stale event selection are possible. Human review is required before relying on descriptions.
- The synthetic sample uses captions and shapes, not a filmed kitchen. Mock-mode numbers are not quality numbers.
- Video_url schema, model JSON support, regional routing and cost estimates are not yet verified against Token Factory.

See [issues-found](issues-found/README.md) for evidence, causes and status. Tests run entirely offline, including full-pipeline tests marked `slow` but included by default. Output video streams are copied; input formats/codecs must be compatible with MP4. This prototype does not run OCR, diarization or safety-critical scene interpretation.
