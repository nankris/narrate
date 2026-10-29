# Narrate final output (English only) - review sheet

Generated 2026-10-29. All description text was written by NVIDIA Nemotron models on Nebius Token Factory
(`provider: nebius`, `mock: false` in every report). Speech is the local Piper voice `en_US-ljspeech-medium`
(public domain); speech detection (Silero VAD) and audio/video mixing (ffmpeg) also run locally.

Each folder has, per sample:
- `extended_en.mp4`: the video pauses on a frozen frame while the description is spoken, then resumes.
- `narrated_en.mp4`: in-gap mode, description only inside natural silences, original audio ducked underneath.
- `ad_extended_en.vtt` / `ad_en.vtt` captions, `transcript_*.txt`, and `extended_report.json` / `ingap_report.json`.

| Sample | In-gap cues | Extended pauses | Extended length | Cost (both modes) | Known issue |
|---|---|---|---|---|---|
| cooking_roti_0028-0148 | 12 | 7 | 119.9 s -> 203.6 s | $0.079 | one 37 s stretch has no extended description |
| failure_continuous_speech | 0 (refuses by design) | 3 | 30.0 s -> 64.7 s | $0.013 | none; shows why extended mode exists |
| nasa_chile_harvest_0000-0150 | 10 | 6 | 110.0 s -> 205.7 s | $0.086 | one 46 s stretch has no extended description |
| sample_kitchen (synthetic) | 4 | 3 | 30.0 s -> 68.5 s | $0.024 | none |
| tears_of_steel_0015-0155 | 8 | 2 | 100.0 s -> 128.2 s | $0.095 | extended is thin: only 2 of 7 planned pauses survived verification; use in-gap for this clip |

Every run: 0 narration/speech overlaps, status complete, no fallback finisher. Extended output durations equal
source length plus the inserted freezes.

Not yet done by a person: listening to the audio, checking each cue against the video, recording and captioning
the demo. Descriptions are model-written and can contain errors; the verifier reduces but does not remove them.
