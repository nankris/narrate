# Narrate demo plan v2

The final shot list and spoken copy are in `DEMO_SCRIPT.md`. Extended audio description is the opening and headline feature.

Use the two local cached outputs in `runs/ext/final/`. The roti sample demonstrates a visual tutorial; the synthetic lecture
demonstrates why in-gap narration alone is insufficient. The intended timing contract is “pause after the event ends; cues
describe only already-happened events.” Do not record until the chronology repair from `codex/ad-timing` is merged and every cue
has been reviewed against the source.

For the interactive segment, run `scripts/serve_cached_demo.py`. It exposes cached samples only, needs no API key, disables
Gradio analytics, binds to localhost, and must not create a public share link.

Human tasks remain: review cue accuracy, listen for music/licensing concerns, record and caption the video, verify any hosted
URL if one is later created, and submit the project manually.
