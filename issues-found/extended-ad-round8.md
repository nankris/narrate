# Extended AD (Round 8 to 8c): issues found on real Nebius runs

| # | Symptom (run) | Cause | Fix |
|---|---|---|---|
| 1 | Lecture got 0 pauses (lecture_e1) | One VAD interval covered 0-30 s, and there were no cuts | Round 8b: -30 dB micro-silences plus a visual-change detector |
| 2 | Run crashed taking the frame at the clip end (roti_e2) | `ffmpeg -ss` returned no frame at the duration | `_frame_at` falls back to `-sseof` and uses the last JPEG |
| 3 | HTTP 400 from Super VL (roti_e3) | 9 images in one call | Calls are batched at 6 images or fewer |
| 4 | Coverage guarantee raised in render (lecture_e3) | The guarantee was a hard exception | It is now reported as an issue (`guarantee_met: false`) |
| 5 | Closing pause rejected as "inside speech" (lecture_e4) | The VAD interval ends at 30.0002 s on a 30.000 s clip | The speech check is skipped for the closing pause |
| 6 | 3 of 8 roti pauses dropped (roti_e4) | 48-63-word cues hit a hard 45-word cap | 45 is now a soft target; the hard cap is 65, since the freeze adapts to the narration length |
| 7 | "The camera pulls back to reveal a child" shipped (roti_e4) | The lint regex missed it | Hard check for camera, zoom, pan, close-up and "the shot" |
| 8 | Judge scored 0% coverage and fluency 1.0 (roti_e5 score) | A single judge call hit the 5000-token output cap, and the JSON was cut off | One judge call per cue window |
| 9 | 25 "hallucinations" and 18 chronology errors (roti_e5) | Mostly judge artifacts: it quoted ground-truth steps as claims and flagged static setting facts | Claims must be quoted from the cue text; Super VL frame audit with `--frame-audit` |
| 10 | Real wrong details: glove on the "left" hand, "twisted" for rolled, plate called a bowl (roti_e5) | The verifier saw 2 stills at the pause only | It now sees 5 stills across the window. This is only partly effective: "twist" and "inverted white bowl" survive in e6 |
| 11 | Lecture narrated OCR flicker ("drops FOR", "- ROOM AD") (lecture_e5) | The video-window pass misread a static slide | New `text_stills` stage re-reads on-screen text from stills (4 readings corrected in e7) |
| 12 | Closing freeze missing from the video stream (final render) | `tpad=stop_mode=clone` emitted no frames; the video ended 15.3 s before the audio | A single frame is looped instead; regression test added |
| 13 | roti_e7 regressed: 7 of 8 cues dropped | Ultra cited event ids outside each pause window, and repair did not recover | Open. Run-to-run variance; e6 is used as the final |
| 14 | Lecture e7 timing claims are wrong ("until ten seconds"; the change is at 15 s) and it invents "left edge cropping" | The timeline window events are wrong, and the frame audit is lenient | Open |
| 15 | roti pauses 2 and 3 are only 2.3 s apart (23.4 s and 25.7 s) | Key-event pauses override `min_pause_spacing_s` | Open |
