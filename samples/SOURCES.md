# Sample sources

| File | Source URL | License | Attribution | Notes |
|---|---|---|---|---|
| sample_kitchen.mp4 | Self-generated with scripts/make_sample.py | Apache-2.0 | Narrate contributors | Synthetic shapes, captions, espeak; no filmed kitchen |
| failure_continuous_speech.mp4 | Self-generated with scripts/make_sample.py --kind lecture | Apache-2.0 | Narrate contributors | Published failure case: continuous speech, changing slides, extended AD needed |
| tears_of_steel_0015-0155.mp4 | https://download.blender.org/demo/movies/ToS/tears_of_steel_720p.mov | CC-BY 3.0 | (c) Blender Foundation, mango.blender.org | Clip 0:15–1:55. Soundtrack by Joram Letwory is distributed separately under CC-BY-ND 3.0. Narrate only lowers its volume under narration; licensing caveat to double-check before distribution. Re-encoded to 640 px, H.264 CRF 28, AAC 96k. Dialogue at 8-30 s, 35-38.5 s, 46-48 s; music throughout (ffmpeg silencedetect finds 0 gaps). |
| nasa_chile_harvest_0000-0150.mp4 | https://images.nasa.gov/details/Plant_Habitat-04_Harvest | NASA media generally not copyrighted; see https://www.nasa.gov/nasa-brand-center/images-and-media/ | NASA Image and Video Library; “Astronauts harvest, eat first chile pepper crop on space station”, nasa_id Plant_Habitat-04_Harvest | Clip 0:00–1:50 of the ~mobile.mp4 rendition, re-encoded to 640 px. Audio is ambient only (NASA caption file: "[Ambient sounds]"). No endorsement implied. |
| tears_of_steel_0015-0155.en.srt | https://download.blender.org/demo/movies/ToS/subtitles/TOS-en.srt | CC-BY 3.0 (as part of the Tears of Steel project) | (c) Blender Foundation | Shifted by -15 s to match the clip; used only as ground truth for `scripts/eval_against_subs.py` (dialogue overlap). |
