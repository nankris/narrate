# Narrate: demo recording guide (target 2:40, hard limit 3:00)

You record this yourself: a screen recording with your own voice-over. Each step says what to click, what to say (as a rough guide), and how long it should take. **The key moment, hearing the difference, lands by 0:30.**

---

## 0. Before you record (about 15 min, not filmed)

1. Open a terminal in the repo:
   ```bash
   cd narrate && source .venv/bin/activate      # or: python -m venv .venv && pip install -r requirements.txt
   python -m pytest -q                           # should be all green
   ```
2. Build the real cached runs so nothing can stall on camera. Use the Token Factory key if you have it, otherwise the dev endpoint:
   ```bash
   export NEBIUS_API_KEY=...        # type it into the terminal, never into a file
   python scripts/build_cached_runs.py --provider nebius
   # dev-only fallback (badged "DEV ONLY" in the UI):
   # export NVIDIA_DEV_API_KEY=...; python scripts/build_cached_runs.py --provider nvidia-dev
   ```
3. Start the UI with `python -m app.app`, then open http://127.0.0.1:7860.
4. On the **Samples · zero cost** tab, pick *Tears of Steel* and check that:
   - the badge says NEBIUS or DEV ONLY (never record a MOCK badge as if it were real);
   - the agent trace has at least one **contradicted** verification (amber or red chip).
   If no run has one, use the documented one in `blog-assets/11_*` and show it in step 6 instead.
5. Write down three real numbers from the Results card: cost per minute, gap coverage, and overlaps. You will say them in step 7.
6. Recording setup: 1920×1080, browser zoom 110%, close other tabs, mute notifications, headphones on, system audio captured.
7. Have the failure clip cached as well (*Failure continuous speech*).

---

## 1. 0:00–0:10: Eyes closed (original audio)
- **Screen:** Samples tab, *Tears of Steel* selected, **Eyes closed** toggle ON (the video is hidden). Play the **original** for about 8 s, starting at 0:00 (music and city ambience, then dialogue).
- **Say:** "Close your eyes. Something just happened on screen. Can you tell what?"

## 2. 0:10–0:28: Same seconds with Narrate ← KEY MOMENT
- **Click:** with language **English** selected, play the **Narrated video** player over the same 0:00–0:10. The ducked narration describes the rocket and the city skyline, with the original audio underneath.
- Toggle **Eyes closed** OFF at about 0:22 so viewers see that the description matched.
- **Say:** "That's Narrate. An AI agent built on NVIDIA Nemotron watched the video and wrote audio description that fits only into the gaps where nobody is talking."

## 3. 0:28–0:40: The problem in one line
- **Screen:** stay on the player, or show the README title.
- **Say:** "Audio description is how blind and low-vision people follow video. It's a WCAG requirement, and almost no small creator or teacher can afford a human describer. Narrate does it for a two-minute clip in English and Hindi."

## 4. 0:40–1:20: It's an agent, and here's which model does what
- **Screen:** scroll to **Agent trace** for the same run. Point at the model chips while you speak:
  - **purple · Nemotron 3 Ultra**: the orchestrator. It plans, calls tools and reads the results ("observe"), and decides what to fix.
  - **blue · Nemotron 3.5 Super VL**: watches each short segment (video input) and later re-checks claims on still frames.
  - **green · Nemotron 3 Nano** (Lightning on the dev endpoint): drafts a description to an exact word budget.
  - **grey tools**: speech-gap detection (Silero VAD), TTS duration measurement, fit check, render, finalize.
- Tick **Only notes & corrections** to make the reasoning readable, then scroll slowly through one *check_fit failed → shorter redraft* correction (amber).
- **Say:** "Ultra runs a plan, act, observe loop. Super VL inspects each gap. Nano drafts a line. A deterministic check measures the actual speech duration. If the line doesn't fit, the agent rewrites it. Every step is logged in this trace."

## 5. 1:20–1:45: Self-verification catches a hallucination
- **Screen:** find the `verify_claim` step with a **contradicted** chip (on Tears of Steel, the VL model claimed on-screen text like "40 YEARS LATER"). Expand the evidence.
- **Say:** "Here the vision model claimed there was on-screen text. Before anything with text, numbers or names gets spoken, the agent has to verify it, using a different modality: still frames instead of video. The claim was contradicted, so the line was dropped and redrafted."

## 6. 1:45–2:00: Hindi
- **Click:** language **Hindi** and play about 6 s of the Hindi narrated track with the Hindi cues visible.
- **Say:** "One click gives Hindi too. Ultra translates, and the timing is re-checked against the Hindi speech, because Hindi runs longer."

## 7. 2:00–2:15: Results card (real numbers only)
- **Screen:** Results card.
- **Say:** "This clip cost [cost/min] per minute of video at Token Factory list prices. Overlaps with detected speech: [n]. [x]% of the silent gaps are described. All the Nemotron models come through one OpenAI-compatible Token Factory API." (Use your numbers from setup step 5. If they came from the dev endpoint, say "estimated at Token Factory prices".)

## 8. 2:15–2:35: Where it fails (be honest)
- **Click:** sample *Failure continuous speech* → Results / trace.
- **Screen:** the issue line "Cannot narrate safely without extended AD (pause-the-video): no usable speech-free gaps."
- **Say:** "Where it fails: a lecture with nonstop speech has no gaps, so Narrate refuses rather than talk over the speaker. That needs extended description that pauses the video, which is next. The vision model also still invents details, and verification catches some of them, not all. They're published in the README."

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
- [ ] Optional 5 s cutaway to a terminal showing `python -m narrate agent ... --provider nebius` with a key-free log line that names the model ID.
