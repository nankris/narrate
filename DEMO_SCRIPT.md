# Narrate: demo recording guide (target 2:40, hard limit 3:00)

You record this yourself: a screen recording with your own voice-over. Each step says what to click, what to say (as a rough guide), and how long it should take. **The key moment, hearing the difference, lands by 0:30.**

---

## 0. Before you record (about 10 min, not filmed)

The repo already ships **real cached runs**: NVIDIA dev endpoint, final code, badged **NVIDIA DEV · development only**. Nothing has to run live on camera.

1. Open a terminal in the repo:
   ```bash
   cd narrate && source .venv/bin/activate      # or: python -m venv .venv && pip install -r requirements.txt
   python -m pytest -q                           # 131 passed, fully offline
   ```
2. *(Optional, recommended once your Token Factory key exists.)* Check the key, then rebuild the caches on Nebius so the badge reads **Nebius Token Factory**:
   ```bash
   export NEBIUS_API_KEY=...                     # type it into an off-screen terminal, never into a file
   python scripts/smoke_provider.py              # must end with READY (~$0.01)
   python scripts/build_cached_runs.py --provider nebius    # ~4 clips, ~$0.40, ~12 min
   ```
   If you rebuild, re-read the numbers in steps 5 and 7 from the new Results cards. A fresh run can differ.
3. Start the UI with `python -m app.app`, then open http://127.0.0.1:7860.
4. On the **Samples · zero cost** tab, check that:
   - the badge never says MOCK;
   - *Tears of Steel* shows **8 cues** and the trace has a **red "contradicted"** chip (step 29 with the shipped cache).
5. Recording setup: 1920×1080, browser zoom 110%, close other tabs, mute notifications, headphones on, system audio captured.

Numbers in the shipped caches, which you will say in step 7 (*Tears of Steel*, 100 s):
- $0.171 per run, about $0.10 per minute at Token Factory list prices;
- 14 Ultra turns;
- 8 of 8 gaps described, 60% EN coverage;
- 0 overlaps with detected speech, and 0.39 s against the film's subtitles.

---

## 1. 0:00–0:10: Eyes closed (original audio)
- **Screen:** Samples tab, *Tears of Steel* selected, **Eyes closed** toggle ON (the video is hidden). Seek the **Original video** player to **0:45** and play about 9 s. You hear one line ("This is pretty freaky."), then music only. The scene is a cyborg leaning over a brain, then the film's title card.
- **Say:** "Close your eyes. Something just happened on screen. Can you tell what?"

## 2. 0:10–0:28: Same seconds with Narrate ← KEY MOMENT
- **Click:** with language **English** selected, seek the **Narrated video** player to **0:45** and play. The dialogue line stays untouched; right after it, under the ducked music, you hear: *"A cyborg examines a brain under an arc lamp; title card displays 'Tears of Steel'."*
- Toggle **Eyes closed** OFF at about 0:22 so viewers see that the description matched.
- **Say:** "That's Narrate. An AI agent built on NVIDIA Nemotron watched the video and wrote audio description that fits only into the gaps where nobody is talking."

## 3. 0:28–0:40: The problem in one line
- **Screen:** stay on the player, or show the README title.
- **Say:** "Audio description is how blind and low-vision people follow video. It's a WCAG requirement, and almost no small creator or teacher can afford a human describer. Narrate does it for a two-minute clip in English and Hindi."

## 4. 0:40–1:20: It's an agent, and here's which model does what
- **Screen:** scroll to **Agent trace** for the same run. Point at the model chips while you speak:
  - **purple · Nemotron 3 Ultra**: the orchestrator. It plans, calls tools and reads the results ("observe"), and decides what to fix.
  - **blue · Nemotron 3.5 Super VL**: watches each short segment (video input) and later re-checks claims on still frames.
  - **green · Nemotron 3 Nano** (Lightning on the dev endpoint): drafts every gap in one batched call, each to an exact word limit.
  - **grey tools**: speech-gap detection (Silero VAD), TTS duration measurement, fit check, render, finalize.
- Tick **Only notes & corrections** to make the reasoning readable, then scroll slowly. The top bar shows 14 turns, the tool calls, and the cost per model.
- **Say:** "Ultra runs a plan, act, observe loop. Super VL inspects each gap and writes what it saw on an evidence board. Nano drafts all lines in one call. A deterministic tool speaks each line with the real voice and measures it. If a line doesn't fit, the tool redrafts it, so the big model never counts words. Every step is logged in this trace."

## 5. 1:20–1:45: Self-verification catches a hallucination
- **Screen:** untick the filter and scroll to **step 29 `verify_claim`**, which has a red **contradicted** chip. The vision model had read a title "SIMULATION READY..." that is not in the film. Then show **step 42** (amber correction): the replacement line "A person with dreadlocks examines a realistic brain model". Step 58 verifies it as supported.
- **Say:** "Here the vision model claimed there was on-screen text. Before anything with text, numbers or names gets spoken, the agent has to verify it, using a different modality: still frames instead of video. The claim was contradicted, so the line was pulled and replaced with one that checks out."

## 6. 1:45–2:00: Hindi
- **Click:** language **Hindi** and play about 6 s of the Hindi narrated track with the Hindi cues visible.
- **Say:** "One click gives Hindi too. Ultra translates, and the timing is re-checked against the Hindi speech, because Hindi runs longer."

## 7. 2:00–2:15: Results card (real numbers only)
- **Screen:** Results card.
- **Say** (shipped caches; if you rebuilt on Nebius, read your own card): "This 100-second clip took 14 agent turns. Every silent gap got a description, with zero overlaps with detected speech; against the film's subtitles, the overlap was under half a second. Estimated at Token Factory list prices, it costs about ten cents per minute of video, and almost all of that is the Ultra orchestrator, so the expensive model only plans. All the Nemotron models come through one OpenAI-compatible Token Factory API."

## 8. 2:15–2:35: Where it fails (be honest)
- **Click:** sample *Failure continuous speech* → Results / trace.
- **Screen:** the issue line "Cannot narrate safely without extended AD (pause-the-video): no usable speech-free gaps."
- **Say:** "Where it fails: a lecture with nonstop speech has no gaps, so Narrate refuses rather than talk over the speaker. That takes three turns and one cent. Pausing the video for extended description is next. The vision model also still misreads on-screen text, and verification catches some of that, not all. Every failure we hit, seven rounds of them, is published in the repo with its trace."

## 9. 2:35–2:45: Close
- **Screen:** the GitHub README (Apache-2.0 badge and quickstart visible).
- **Say:** "Narrate is open source under Apache 2.0, and it has a mock mode that runs without a key. Audio description for every video."

---

## Recording checklist
- [ ] Runtime under 3:00, with the key moment (step 2) finished by 0:30.
- [ ] Every number you say is from a real run (NEBIUS or DEV ONLY badge). Never quote MOCK numbers.
- [ ] No key is visible in any terminal, `.env` or browser tab. Export the key in a terminal that's off-screen.
- [ ] Credit Tears of Steel on screen or in the description: "Tears of Steel © Blender Foundation, CC BY 3.0, mango.blender.org".
- [ ] Use no other music. Narration voices: espeak-ng or Piper (`en_US-ljspeech`, public domain). The Hindi Piper voice is CC BY-NC-SA, which is fine for a non-commercial demo.
- [ ] Optional 5 s cutaway to a terminal showing `python scripts/smoke_provider.py` ending in `READY`. It prints model IDs and never the key.
- [ ] Optional live run (only if you have time, never in the first 30 s): **Run · live** tab, upload `samples/sample_kitchen.mp4`. A real provider takes about 65 s and $0.05. It is capped hard at $0.25, 24 turns and 300 s, then the fallback ships what is verified. The `mock` provider is instant and free, but say it is synthetic.
- [ ] If the badge says NVIDIA DEV, say "estimated at Token Factory list prices, measured on NVIDIA's dev endpoint".
