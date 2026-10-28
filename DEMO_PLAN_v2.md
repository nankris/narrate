# Narrate demo plan v2

## LEAD: extended audio description (Round 8c, English)

Open with extended mode, the headline. Use the files in `runs/ext/final/`. Every cue text and time below is copied from
`runs/ext/final/roti/ad_extended_en.vtt`.

| Time | Screen | Action | Voice-over |
|---|---|---|---|
| 0:00-0:12 | `runs/ext/final/roti/extended_en.mp4`, picture hidden | Play from 0:00; the first freeze lands at 0:00.8 | "Close your eyes." Let the cue play: "A wooden mixing bowl holds flour on a white countertop..." |
| 0:12-0:30 | Picture revealed, jump to 1:23.7 | Video freezes on the cut dough balls; the cue plays; the video resumes | "At every scene change the video pauses, explains, and resumes. Nobody is talked over." |
| 0:30-0:45 | `runs/ext/final/lecture/extended_en.mp4` | Play from 0:25 | "In-gap mode refuses this lecture because there is no gap. Extended mode pauses at sentence breaks and reads the slide." |
| 0:45-1:00 | `ad_extended_en.vtt` + score.md | Show the ground truth vs the score | "An independent Nemotron ground truth and a frame audit score every cue." |

Then continue with the in-gap storyline below as "the default mode".


Target: **2:45**, hard stop **2:50**. Record only after the new director-mode roti cache exists. Every spoken cue, timestamp, step number, cost, and result must be copied from that cache; placeholders below are intentional.

## Storyline

Open on the real roti clip with the picture hidden: “Close your eyes.” Play an original speech-free moment, then replay the same moment with Narrate. Reveal the picture by **0:25** so the audience immediately hears and sees the value. Explain that the director first builds a scene bible, Ultra writes one coherent whole-track script, still frames verify risky claims, failed claims are repaired, and Hindi is authored and timed natively. Show this as one stage strip, not a wall of raw logs.

Use the verified correction as the agentic proof: at `<<fill from new cache: step N>>` the verifier rejects a wrong claim; at `<<fill from new cache: step N>>` the repaired cue is accepted. Do not quote either cue until it is copied verbatim from the new cache. Switch to Hindi without losing the playhead. Then show the honest continuous-speech refusal: speech-free AD cannot safely fit, so extended AD—pausing the source—is needed. Close on the hosted URL and invite judges to use the zero-cost Samples tab.

## Shot list

| Time | Screen | Click/action | Voice-over | On-screen caption / credit |
|---|---|---|---|---|
| 0:00–0:07 | Roti sample, **Eyes closed** on | Play original at `<<cache timestamp>>` | “Close your eyes. What just happened?” | `Original audio · picture hidden` |
| 0:07–0:20 | Same hidden frame | Replay narrated English at the identical time | “Now listen again.” Let the cached Nemotron cue play; do not speak over it. | `Narration: verbatim from new cache` |
| 0:20–0:25 | Roti video revealed | Toggle Eyes closed off | “Narrate placed that description inside a gap where nobody was speaking.” | `English audio description · speech preserved` |
| 0:25–0:38 | Player plus cue timeline | Click the cue just heard; it seeks to its start | “It finds safe gaps, but it also has to tell the cooking story as one coherent sequence.” | Maple Kitchen credit, abbreviated |
| 0:38–0:59 | Director stage strip | Advance/highlight Bible → Script | “Super VL watches the whole clip window by window; Nemotron Ultra builds a scene bible and then directs the whole track, choosing what matters and what can stay silent.” | `Scene bible → whole-track script` |
| 0:59–1:18 | Stage strip and trace | Highlight Verify → Repair | “Still frames challenge risky claims. Here, verification caught a wrong claim before it reached the final track.” | `Rejected: <<fill from new cache: step N>>` then `Repaired: <<fill from new cache: step N>>` |
| 1:18–1:31 | Before/after cue timeline | Toggle old vs v2, same playhead | “The new director sees the whole story, so it can reduce repetition and place each line in the right moment.” | Use cache-derived comparison only; no invented metrics |
| 1:31–1:47 | Hindi mode, same playhead | Switch English → Hindi; play one cached cue | “Hindi is authored and measured for the Hindi voice, not pasted into English timings.” | `हिंदी · native timed track`; cue verbatim from cache |
| 1:47–2:00 | Results / provenance card | Show provider badge and real cache summary | “These are cached results from Nebius Token Factory. The sample costs judges nothing to replay.” | `Nebius Token Factory · cached run`; only cache-derived numbers |
| 2:00–2:17 | Continuous-speech failure sample | Open limitation card | “Narrate refuses when speech leaves no safe room. It will not talk over the speaker. That case needs extended audio description, which pauses the video and is future work.” | `Honest limitation · extended AD not implemented` |
| 2:17–2:29 | NASA sample thumbnail / short muted visual | Select NASA; do not play a claimed cue unless newly verified | “A second, very different sample tests people, plants and action in microgravity.” | NASA credit and no-endorsement line |
| 2:29–2:39 | Brief muted Tears of Steel still, optional | No soundtrack; no narration claim | “We also keep a brief licensed stress test, shown here silent.” | Blender Foundation credit; `Muted in this demo` |
| 2:39–2:50 | Hosted Space landing page and URL | Focus URL; show Samples tab | “Try the zero-cost samples at this URL. Narrate: audio description in English and Hindi.” | `https://huggingface.co/spaces/<<owner>>/narrate` |

## Clip choices, licences, and exact credits

- **Hero — `cooking_roti_0028-0148.mp4`:** real, visually layered hand action; natural English speech gaps; strong cultural fit for Hindi; under two minutes. Burned-in subtitles and the channel logo remain visible and should be acknowledged rather than cropped. Credit: **“How To Make Soft Layered Roti - Paratha” by Maple Kitchen, CC BY 3.0, source: https://www.youtube.com/watch?v=FX3KAGdnKQk. Trimmed/re-encoded; audio description added. No endorsement implied.**
- **Second — `nasa_chile_harvest_0000-0150.mp4`:** a distinct setting with a clear harvest-to-reaction arc and ambient-only source audio. Credit: **“Astronauts harvest, eat first chile pepper crop on space station,” NASA Image and Video Library, NASA ID Plant_Habitat-04_Harvest. Courtesy NASA. No endorsement implied.** NASA media guidance should be rechecked before publishing the final video.
- **Brief stress test — `tears_of_steel_0015-0155.mp4`:** show only a short silent/muted excerpt; do not use its soundtrack in the public demo video. Credit: **“Tears of Steel” © Blender Foundation, CC BY 3.0, mango.blender.org. Excerpt modified by trimming/re-encoding; muted in this demo.** The separately distributed soundtrack has a CC BY-ND caveat, so excluding it is the cleanest choice.
- **Exclude:** the synthetic kitchen slides from all judge-facing footage. Keep the continuous-speech synthetic clip only as an explicitly labelled failure case.

## Recording checklist

- [ ] 1920×1080; browser zoom checked; notifications, bookmarks, personal tabs, and credentials absent.
- [ ] Final runtime ≤2:50; key reveal complete by 0:25; hosted URL readable at the close.
- [ ] No music. Roti voice-over may be heard only where necessary to establish speech preservation.
- [ ] All cue text, step IDs, timestamps, costs, and metrics copied verbatim from the new director cache.
- [ ] Record system audio cleanly; do not speak over English or Hindi cached cues.
- [ ] Public-video narration voice disclosed in the description: **“Demo voice: ElevenLabs/Magnific [select the service actually used], synthetic voice.”** If neither is used, replace with the actual tool.
- [ ] Hosted-app disclosure: **“Interactive app playback uses espeak-ng or Piper, depending on installed voices; it does not use the polished promotional voice.”** Verify the deployed backend before publishing.
- [ ] Roti, NASA, and optional Blender credits visible on screen and repeated in the video description.
- [ ] Tears of Steel is brief and muted; synthetic kitchen slides do not appear.
- [ ] Captions burned in or uploaded; check English/Hindi names and accessibility terminology.

## Hosted demo plan

Use a public Hugging Face Space with the **Gradio SDK** on the free **CPU Basic** tier. Judges land on **Samples · zero cost** and can replay cached English/Hindi outputs without API calls. The live tab is director-mode only, accepts clips of **≤60 seconds**, uses the server-side `NEBIUS_API_KEY` Space secret, queues one run at a time, and never exposes the credential.

Production limits: `NARRATE_DAILY_CAP_USD=1.5` initially (raise only to at most `$2/day` after observing use), session cap `$0.25`, per-run cap `$0.20–0.25`, maximum turns/time bounded, and queue concurrency `1`. Disable the live provider when the daily cap is exhausted; preserve samples. Reject unsupported/oversized media before inference. Keep Gradio analytics off, avoid request-body logging, retain only minimal aggregate spend state, periodically remove generated uploads/outputs, and document that abusive or repeated requests may be rate-limited or the live tab disabled. The present process lock and spend ledger are useful safeguards, but a public deployment should also add per-IP/request throttling at the hosting edge if available.

If the Space sleeps, the landing page may cold-start: put “Waking up—cached samples will appear shortly” in the project description, test the URL before judging, and keep the cache inside the Space repository. If free hosting is unreliable, use a small **Nebius VM** as fallback with the same caps, one worker, TLS/reverse proxy, and server-side secret; do not switch during judging without updating the submitted URL.

### Deployment commands — do not run now

**Requires user approval: creates a public Space.** Replace placeholders, review copied files for size, and authenticate interactively; never place a token in a command, file, or shell history.

```bash
python -m pip install --upgrade huggingface_hub
huggingface-cli login
huggingface-cli repo create narrate --type space --space_sdk gradio
git clone https://huggingface.co/spaces/<<owner>>/narrate narrate-space
rsync -a --exclude '.git' deploy/hf_space/ narrate-space/
rsync -a app narrate config.yaml narrate-space/
rsync -a samples/SOURCES.md samples/cached_runs samples/*.mp4 narrate-space/samples/
cp README.md LICENSE narrate-space/
cd narrate-space
git add .
git commit -m "Deploy Narrate director demo"
git push
```

Set `NEBIUS_API_KEY` only in **Space Settings → Variables and secrets → New secret**. Set non-secret variables there: `NARRATE_DAILY_CAP_USD=1.5`, `NARRATE_MAX_CLIP_S=60`, `NARRATE_UI_SESSION_CAP=0.25`, `NARRATE_UI_RUN_CAP=0.25`, `NARRATE_UI_MAX_TURNS=<<director limit>>`, and `NARRATE_UI_TIMEOUT_S=<<director timeout>>`. See `deploy/hf_space/DEPLOY.md` for the required duration-hook patch and director-only verification.

## Interactive UI improvements

| Priority | Improvement | Effort | Acceptance criteria |
|---|---|---:|---|
| P0 | Director stage strip: Bible → Script → Verify → Repair → Hindi, with per-stage cost | 1 day | Each stage links to its trace range; status, latency, and cache-derived cost sum to the run total; failures are visibly distinct and keyboard reachable. |
| P0 | Scene-bible card | 0.5 day | Shows setting, people/hands, ingredients, tools, continuity facts, and uncertainty from the trace; no generated field is presented as verified without evidence. |
| P0 | Cue timeline below player with click-to-seek | 1 day | Every cue renders at its actual interval; mouse/keyboard activation seeks both players to cue start; active cue follows playback. |
| P0 | “Eyes closed” default on for hero hook | 0.25 day | Roti opens visually blacked out with an explicit accessible state label; toggle restores video without resetting time. |
| P1 | Old vs v2 narration toggle | 0.75 day | Both cached tracks use one player/playhead; toggling preserves time, language, pause/play state, and clearly labels provenance. |
| P1 | English/Hindi switch preserving position | 0.5 day | Switch changes audio, VTT, and active cue while retaining time within 250 ms; unavailable tracks are disabled, not broken. |
| P1 | Accessible live cue captions | 0.5 day | Current cue text is exposed in a polite `aria-live` region without repeatedly announcing unchanged text; decorative trace content is hidden from screen readers. |
| P1 | Keyboard shortcuts | 0.5 day | Documented shortcuts control play/pause, seek ±5 s, language, eyes-closed mode, and next/previous cue; they do not fire while typing. |
| P2 | Hosted-demo guardrail panel | 0.5 day | Shows ≤60 s, one-at-a-time queue, remaining availability without exposing global spend details, and actionable cap/sleep errors; live controls disable safely at exhaustion. |

## Changes to `DEMO_SCRIPT.md`

Replace every stale statement below when producing the final script. Templates deliberately avoid unverified facts.

| Stale text (quoted) | Replacement template |
|---|---|
| “target 2:40, hard limit 3:00” | “target 2:45, hard limit 2:50” |
| “The key moment, hearing the difference, lands by 0:30.” | “The roti before/after reveal is complete by 0:25.” |
| “The repo already ships **real cached runs**: NVIDIA dev endpoint, final code, badged **NVIDIA DEV · development only**.” | “The repo ships a new director-mode roti cache from Nebius Token Factory; verify its badge before recording.” |
| The entire optional key-export/cache-rebuild command block | “Caches are already prepared off camera. Do not show, inspect, or enter credentials during recording.” |
| “*Tears of Steel* shows **8 cues** and the trace has a **red \"contradicted\"** chip (step 29 with the shipped cache).” | “The roti director cache shows `<<cache cue count>>` cues and a contradicted claim at `<<fill from new cache: step N>>`.” |
| The four-item “Numbers in the shipped caches” block | “Read only these values from the new roti cache: `<<cost>>`, `<<turns>>`, `<<coverage>>`, `<<speech overlap>>`; omit any unavailable metric.” |
| The complete 0:00–0:28 Tears of Steel hook, including “A cyborg examines…” | Use the 0:00–0:25 roti original/narrated hook above; insert cue text verbatim from the new cache. |
| “It's a WCAG requirement” | “Audio description supports WCAG 1.2.5 for prerecorded video; extended AD relates to WCAG 1.2.7.” |
| “Narrate does it for a two-minute clip in English and Hindi.” | “Narrate writes English and Hindi AD for videos up to the configured limit; the public live demo accepts ≤60 seconds.” |
| The 0:40–1:20 model walkthrough beginning “purple · Nemotron 3 Ultra” | “Show the director strip: scene bible → whole-track Ultra script → still-frame verification → repair → native Hindi; use the deployed model labels verbatim.” |
| “The top bar shows 14 turns” | “The top bar shows `<<turns from new cache>>` turns and `<<cost from new cache>>`.” |
| “Nano drafts all lines in one call.” | “Ultra writes the whole-track script from the scene bible; use the new trace to describe any additional fitting model accurately.” |
| The entire step-29/42/58 “SIMULATION READY” section | “At `<<fill from new cache: step N>>`, still-frame verification rejects `<<verbatim wrong claim from cache>>`; at `<<fill from new cache: step N>>`, it accepts `<<verbatim repaired cue from cache>>`.” |
| “One click gives Hindi too. Ultra translates…” | “Hindi is authored natively in the director pipeline and timed against the Hindi voice; confirm the exact implementation in the new trace.” |
| The entire “This 100-second clip took 14 agent turns…” results line | “This `<<duration>>` roti clip used `<<turns>>`, cost `<<cost>>`, and produced `<<verified cache metrics>>` on Nebius Token Factory.” |
| “That takes three turns and one cent.” | Omit unless a new real cache proves it; retain only the safe refusal and extended-AD limitation. |
| “Every failure we hit, seven rounds of them…” | “Published traces document the failures we encountered.” |
| The GitHub-only close | Show and speak the hosted Space URL, then mention Apache-2.0 and offline mock mode secondarily. |
| “Credit Tears of Steel…” as the only credit item | Use the roti, NASA, and optional muted Tears credit lines in this plan. |
| “Narration voices: espeak-ng or Piper…” | “Public video: disclose the actual ElevenLabs/Magnific synthetic voice used. Hosted app: disclose the actual espeak-ng/Piper backend.” |
| The optional live run using `samples/sample_kitchen.mp4` | “If shown, live-run a ≤60 s permitted real clip in director mode; never use the synthetic kitchen slides in judge-facing footage.” |
| “If the badge says NVIDIA DEV…” | “Do not record until the hero cache and UI show Nebius Token Factory.” |

