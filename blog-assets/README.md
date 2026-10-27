# Blog evidence (numbered, dated)

Raw evidence for the build write-up. All real-model numbers come from the **NVIDIA dev endpoint (build.nvidia.com free tier, dev testing only)**; dollar amounts are *would-be* Nebius Token Factory list prices computed from reported token usage — nothing was billed. No API keys are stored here (checked with `secret_scan.sh` and a grep for key prefixes).

| # | What |
|---|---|
| 01 | 4 s synthetic probe clip used to test Super VL video input |
| 02 | VAD comparison on Tears of Steel: ffmpeg silencedetect vs WebRTC VAD vs Silero |
| 03–04 | contact sheets for the Tears of Steel and NASA clips |
| 05 | baseline fixed pipeline, real runs (before the agent redesign) |
| 06 | espeak-ng vs Piper TTS samples and durations |
| 07 | agent v1, first real run (kitchen) — trace, report, narrated MP4 |
| 08 | agent v2 (fix1), real runs on 4 clips |
| 09 | Super VL video-input smoke test (video_url vs frame grid vs separate frames) |
| 10 | agent v3 (fix2), real runs on 4 clips |
| 11 | failure case: VL hallucinated on-screen text, caught (and once wrongly flagged) by the frame-based verifier |
| 12 | Tears of Steel narration vs subtitle ground truth (overlap seconds) |
| 13–14 | Web UI screenshots (MOCK cached runs) |
| 15 | agent v4 (fix3: long gaps split into slots), real runs on 4 clips — NASA re-inspection loop |
| 16 | agent v5 (fix4: evidence board), real runs on 4 clips — NASA fixed, kitchen propose loop |
| 17 | agent v6 (fix5: one word limit, self-redrafting tools), real runs on 4 clips — kitchen 7 turns, missing-note lockup |
| 18 | agent v7 (fix6, final; code frozen at 2fb4439), real runs on 4 clips — the runs cached in the UI; ToS vs subtitles; pre-fix continuous-speech trace |
| BLOG_NOTES.md | running decision log with real numbers |

Media licences: Tears of Steel © Blender Foundation, CC BY 3.0 (mango.blender.org); NASA footage per NASA media guidelines (no endorsement); synthetic clips are ours (Apache-2.0). See `samples/SOURCES.md`.
