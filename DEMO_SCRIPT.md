# Narrate: demo recording guide (target 2:40, hard limit 3:00)

You record this yourself: a screen recording with your own voice-over. Each step says what to click, what to say (as a rough guide), and how long it should take. **The key moment, hearing the difference, lands by 0:30.**

---

## 0. Before you record (about 10 min, not filmed)

The repo already ships **real cached Nebius Token Factory runs**, badged **Nebius Token Factory**. Nothing has to run live on camera and opening a cached sample has zero incremental cost.

1. Open a terminal in the repo:
   ```bash
   cd narrate && source .venv/bin/activate      # or: python -m venv .venv && pip install -r requirements.txt
   python -m pytest -q                           # fully offline
   ```
2. Start the UI with `python -m app.app`, then open http://127.0.0.1:7860.
3. On the **Samples · zero cost** tab, choose **Tears of steel 0015-0155** in **Cached sample** and check that:
   - the badge says **Nebius Token Factory**, not MOCK;
   - **Results** shows **8 / 0** for **Cues committed / dropped**;
   - the trace has a red **contradicted** chip at step 42, `verify_claim`.
4. Recording setup: 1920×1080, browser zoom 110%, close other tabs, mute notifications, headphones on, system audio captured.

Do not show or claim a subtitle-overlap metric: that appears in `narrate_opus` but is **not on main**. Main reports only **Overlaps with detected speech · target 0**, and the card warns that this does not prove zero dialogue overlap.

Numbers in the shipped caches, which you will say in step 7 (*Tears of Steel*, 100 s):
<!-- numbers:start -->
- $0.134 per run, about $0.08 per minute at Token Factory list prices;
- 16 Ultra turns;
- 8 of 8 narratable gaps described, 50% EN coverage;
- 0 overlaps with detected speech.
<!-- numbers:end -->

---

## 1. 0:00–0:10: Eyes closed (original audio)
- **Screen:** **Samples · zero cost**, **Tears of steel 0015-0155** selected, **Eyes closed · hear audio only** checked. Seek **Original video** to about **0:47** and play about 9 s. The picture stays black while the original soundtrack plays.
- **Say:** "Close your eyes. Something just happened on screen. Can you tell what?"

## 2. 0:10–0:28: Same seconds with Narrate ← KEY MOMENT
- **Click:** with **Narration language** set to **English**, seek **Narrated video** to about **0:47** and play. The shipped cue says *"Title: 'TEARS OF STEEL'."* Toggle **Eyes closed · hear audio only** off while the cue plays so viewers see the title card.
- **Say:** "That's Narrate. An AI agent built on NVIDIA Nemotron watched the video and wrote audio description that fits only into the gaps where nobody is talking."

## 3. 0:28–0:40: The problem in one line
- **Screen:** stay on the player, or show the README title.
- **Say:** "Audio description helps blind and low-vision people follow video and supports WCAG 2.x success criterion 1.2.5. Narrate drafts it for clips up to two minutes in English and Hindi; human review is still required."

## 4. 0:40–1:20: It's an agent, and here's which model does what
- **Screen:** scroll to **Agent trace** for the same run. Point at the model chips while you speak:
  - **purple · Nemotron 3 Ultra**: the orchestrator. It plans, calls tools and reads the results ("observe"), and decides what to fix.
  - **blue · Nemotron 3.5 Super VL**: watches each short segment (video input) and later re-checks claims on still frames.
  - **green · Nemotron 3 Nano**: drafts descriptions to a word limit.
  - **grey tools**: speech-gap detection (Silero VAD), measured TTS fit, verification and finalization.
- Check **Only notes & corrections** to make the trace easier to scan, then scroll slowly. The summary shows turns, tool calls, corrections, verifications, total list-price cost and latency; the lines below break cost down by model.
- **Say:** "Ultra runs a plan, act, observe loop. Super VL inspects segments and records evidence. Nano drafts to the available word budget. The cue tool synthesizes each line with the configured voice and measures whether it fits. Risky claims are checked on still frames, and every action is logged in this trace."

## 5. 1:20–1:45: Self-verification catches a hallucination
- **Screen:** clear **Only notes & corrections**. At step 29, `propose_cue` contains the invented title *"SIMULATION READY"*. Step 42, `verify_claim`, has the red **contradicted** chip and uncommits that cue. Step 51 is the amber correction linked back to step 42; it commits *"The technician calibrates the sensor as bright light jumps from metal terminals."*
- **Say:** "Here the draft invented on-screen text. Text, numbers, names and other risky claims must be verified on still frames before finalization. The verifier contradicted this title, so the cue was removed and replaced. Verification reduces errors, but it does not prove every cue is correct."

## 6. 1:45–2:00: Hindi
- **Click:** set **Narration language** to **Hindi**, open **VTT cues · timestamps**, and play about 6 s of **Narrated video** with the Hindi cues visible.
- **Say:** "One click gives Hindi too. Ultra translates, and the timing is re-checked against the Hindi speech, because Hindi runs longer."

## 7. 2:00–2:15: Results card (real numbers only)
- **Screen:** Results card.
- **Say:** "This 100-second cached run used 16 orchestrator turns and committed eight cues, with none dropped. English narration covers 50 percent of the narratable gap time. It reports zero overlaps with detected speech and costs about 13.4 cents, or 8 cents per minute, at Token Factory list prices. Most of that estimated cost is Ultra, while the Nemotron models share one OpenAI-compatible Token Factory API."

## 8. 2:15–2:35: Where it fails (be honest)
- **Click:** choose **Failure continuous speech** in **Cached sample** and point to **Limitations for this clip** in **Results**.
- **Screen:** the issue line "Cannot narrate safely without extended AD (pause-the-video): no usable speech-free gaps."
- **Say:** "Where it fails: a lecture with nonstop speech has no usable gap, so Narrate commits zero cues rather than speak over the presenter. Pause-the-video extended description is not implemented. Vision can also misread on-screen text; verification catches some mistakes, not all."

## 9. 2:35–2:45: Close
- **Screen:** the README quickstart and Apache-2.0 license text, either in the repository or through **How it works** in the app footer.
- **Say:** "Narrate is open source under Apache 2.0, and it has a mock mode that runs without a key. Audio-description drafts with the evidence and limits visible."

---

## Recording checklist
- [ ] Runtime under 3:00, with the key moment (step 2) finished by 0:30.
- [ ] Every number you say is from a shipped `report.json` and the selected sample has a **Nebius Token Factory** badge. Never quote MOCK numbers.
- [ ] No key is visible in any terminal, `.env` or browser tab. Export the key in a terminal that's off-screen.
- [ ] Credit Tears of Steel on screen or in the description: "Tears of Steel © Blender Foundation, CC BY 3.0, mango.blender.org".
- [ ] Use no other music. The shipped Tears of Steel cache uses espeak-ng. Its soundtrack has a CC BY-ND 3.0 caveat; check before redistributing the narrated output.
- [ ] Keep the recording on **Samples · zero cost**. **Run · live** exists, but provider availability and timing depend on server credentials; the default **mock** provider is offline and synthetic, not evidence of visual quality or cost.
