# FINAL: opus-v2 (director mode)

Branch `opus-v2`, worktree `narrate_opus`. All work is offline, using mock and fake clients only. No real LLM calls were made, so **v2 has not been run on Token Factory yet**.

## What changed

**Diagnosis.** The 30–42 turn Ultra tool loop was both the cost bottleneck (roti: $0.33, 95 % of it Ultra) and the quality bottleneck: it was story-blind, worked gap by gap, and let Nano write the prose. v2 ("director") inverts that:

- **Look at the whole clip.** ffmpeg shot cuts plus Super VL `video_url` windows of about 24 s, snapped to cuts, cover the *whole* clip (not only gaps).
  - Events get **absolute** times. Relative times are shifted, and the `event`/`action` keys are accepted.
  - Burned-in **subtitles** go to `subtitle_text` and are never read aloud. This fixes `Title: "to 35 minutes"`.
- **Scene bible: one Ultra call.** Setting, cast descriptors (no names, no guessed gender), objects, story goal, beats with times, and real on-screen text versus subtitles.
- **Event→gap assignment.** By midpoint or ≥ 50 % overlap; ongoing long events also serve the gaps they mostly cover. Edge brushes never count, which fixes the NASA cue 6/7 timing bug. Refuted events are excluded everywhere.
- **Script: one Ultra call writes the whole English track.**
  - Inputs: bible, full timeline (including speech regions), and all gaps with word budgets **measured from the actual TTS voice**, their evidence ids, and what is said around each gap (subtitles or an `.en.srt` sidecar).
  - The writer may skip gaps (silence is allowed).
  - **Deterministic post-checks:**
    - word budget, plus measured TTS seconds via `check_fit`;
    - `lint` plus director lint ("Person …" opener, "continues", jargon, quoting a subtitle);
    - similarity to the previous cue and to any cue;
    - every cited evidence id must lie inside the gap.
- **Verify, repair, drop.**
  - Super VL checks each cue on 2 stills from *inside its own gap*, batching 4 cues per call.
  - Contradicted: the evidence the false phrase came from is refuted, then a targeted Ultra repair runs on the failed cues only, with the rejection reasons.
  - At most 2 rounds; anything still failing is dropped. A missing verdict means the cue is dropped, so nothing is committed unverified.
  - "Uncertain" is accepted only for cues with no quotes, numbers or names.
- **Hindi.** One Ultra call writes native spoken Hindi from the bible and the English meaning, within Hindi budgets. Each line is measured with Hindi TTS; over-long lines get one batched refit, and anything still failing is omitted (and reported).
- **Bounded.** A hard cap of 6 Ultra calls (bible, script, ≤ 2 repairs, Hindi, refit) and a SpendGuard cap of $0.15 (target ≤ $0.10 per 2-min clip).
- **Trace.** Per stage: model ids, calls, tokens, cost, latency, input and output summaries (`trace.json["stages"]`).
  - `trace.md` is written for judges: a stage table, the bible, the timeline (refuted events struck through), the script with evidence, verdicts and Hindi, and a per-cue history (script → verify → repair → drop).
  - Ultra calls use role `orchestrator` and verdicts appear as `verify_claim` rows, so the existing UI shows Turns and the supported/contradicted chips.
- **Report.** `report.json` keeps every field the app and the cache builder read, and adds `mode`, `bible`, `timeline`, `shots`, `windows`, `stages`, `cue_history`, `director_stats` and `tts_wps_measured`.

## Files

| File | Change |
|---|---|
| `DESIGN_v2.md` | New. The design, including hosted-demo constraints, failure modes and the test plan. |
| `narrate/director.py` | New. `Director(Agent)` and `run_director()`; reuses VAD, slots, the scene pass, `check_fit`/TTS, render and save. |
| `narrate/director_prompts.py` | New. Prompts for timeline, bible, script, verify, repair, Hindi and Hindi refit, plus TTS calibration sentences (not narration). |
| `narrate/agent/core.py` | `submodel(..., system=None)` accepts an explicit system prompt. |
| `narrate/llm.py` | `Client.call` no longer repeats `_system` inside the user JSON. Real token saving, which also benefits the agent. |
| `narrate/__main__.py` | `--mode director\|agent\|pipeline`. Director is the default for `agent`/`run`; `pipeline` keeps the legacy one-shot. |
| `config.yaml` | New `director:` block; `ui.mode: director`. |
| `app/app.py` | Live runs use the director when `ui.mode` (or `NARRATE_UI_MODE`) is `director`. Budget = min(per-run reservation, `director.budget_usd`). |
| `scripts/build_cached_runs.py` | `--mode director` (default) or `agent`; `meta.json` records the mode. |
| `scripts/compare_runs.py` | New. Old and new cue tables side by side, aligned by time, plus cost, Ultra-call, fallback and silence totals. |
| `tests/test_director.py` | New. 21 tests (fake clients). |
| `.secretscan-allow` | Untracked. Allowlists a verified false positive (env-var names) in `DEMO_PLAN_v2.md`. That file and `deploy/` were created in this worktree by another step and were **not** committed by me. |

## Tests

`../narrate/.venv/bin/python -m pytest -q` gives **158 passed** (137 existing + 21 new) in about 120 s.

The new tests cover:
- midpoint and overlap assignment, including the NASA edge brush;
- relative→absolute times and key variants;
- subtitle demotion;
- SKIP;
- budgets from the measured voice;
- every post-check (budget, measured TTS, lint, subtitle quote, similarity, foreign evidence);
- verify→refute→repair→drop with the reason passed through;
- the uncertain policy;
- a failed verifier committing nothing;
- the Ultra cap;
- script-failure fallback;
- Hindi native call, refit and omission;
- trace stages and `trace.md`;
- app `trace_html`/`results_html` on a director report;
- mock end to end;
- the no-gap path making zero model calls;
- the CLI default;
- `compare_runs`;
- a **provider path through a fake Token Factory client** (real ffmpeg windows, video→stills fallback, stills per cue, usage/cost accounting).

## How to run

```bash
# offline
../narrate/.venv/bin/python -m narrate agent samples/cooking_roti_0028-0148.mp4 --out runs/roti_v2_mock --mock
# real (Nebius Token Factory; NEBIUS_API_KEY in env; hard cap $0.15 unless --budget-usd)
../narrate/.venv/bin/python -m narrate agent samples/cooking_roti_0028-0148.mp4 --out runs/roti_v2 --provider nebius --mode director
../narrate/.venv/bin/python scripts/compare_runs.py samples/cached_runs/cooking_roti_0028-0148 runs/roti_v2
# old agent for comparison
../narrate/.venv/bin/python -m narrate agent samples/cooking_roti_0028-0148.mp4 --out runs/roti_agent --provider nebius --mode agent
# rebuild caches with v2 (another step owns samples/cached_runs)
../narrate/.venv/bin/python scripts/build_cached_runs.py --provider nebius --mode director --samples cooking_roti_0028-0148
```

Read `runs/roti_v2/trace.md` first: the stage table shows Ultra calls and cost, and the cue history shows each cue's repairs.

## Known risks

1. **No real-model validation yet.** Prompt quality, JSON adherence and cost are unmeasured on Token Factory. Cost estimates come from config prices; video-token pricing on Token Factory looked much cheaper than `video_tokens_per_second` assumes.
2. **Super VL timeline quality bounds everything.** If windows return few or wrong events, the writer skips or the verifier rejects, which leads to sparse narration. The frames fallback exists but is coarser.
3. **The verifier can be too strict or too lenient on stills.** Motion claims are judged "consistent"; "uncertain" plus no risky detail is accepted.
4. **The refute heuristic** (false phrase ≥ 75 % contained in the event text) is lexical. A paraphrased hallucination may survive and only fail again at the next verification, then be dropped.
5. **Director lint** ("continues", "Person" opener) may reject a rare legitimate line. The repair loop handles it, at the cost of an Ultra call.
6. **Subtitle detection** (`looks_like_subtitle`) is heuristic. A lower-case on-screen label would be treated as speech and not read.
7. **Latency.** Calls are sequential: about 5 timeline windows, 1 scene call, about 3 verify calls and ≤ 6 Ultra calls. That should fit the 300 s UI cap but is unmeasured; parallel windows would be the next optimisation.
8. **The app's Ultra/Super planner dropdown** has no effect in director mode (by design). The UI text still describes "Nano drafts".

## Round 2 (after the first real Token Factory runs)

**Inputs.**
- `runs/roti_v2_r1`: $0.025, 5 Ultra calls, 11 cues. The old agent cost $0.33 over 42 turns.
- `runs/nasa_v2_r1`: $0.026, 5 Ultra calls, 7 cues. The old agent cost $0.20 over 25 turns.

Cost and accuracy were fine. Quality was not: headline-style cues, no establishing *where*, a missed climax (eating and reacting), lint over-reach on "camera", Ultra repairs spent on 1–2-word overages, and masculine Hindi for a cook whose gender is not visible. Evidence and fixes are in `DESIGN_v2.md §6`.

**Changes.** All cue text is still written by Nemotron.
- **Style.** The script and repair prompts now ask for complete present-tense spoken sentences with a subject, story links, and `target_words` (70 % of max) to max_words. They state that max_words is a hard limit and that words must be counted.
  - New lint, each with a `Fix:` hint: `;` fragments, subject-less verb openers, `continue`, "is filmed", "close-up".
- **Establishing.** The bible gains `place` and `goal`. The first gap is flagged `establish`, and a post-check requires a place term in the first narrated cue; if it is missing, the cue goes to repair with a hint.
- **Context.** `--context`, `run_director(context=)`, the app's live textbox "What is this video? (optional title)", and `build_cached_runs.py` (title from the `SOURCES.md` attribution). It is sent as `video_title` with an UNVERIFIED note to the bible, script and repair only. It is recorded in `report.video_title` and in the trace summary.
- **Perception.** Windows are 12 s, snapped to cuts within 2 s, so 10 windows per 2-minute clip. The `shots` stage logs a cost estimate, an upper bound of about $0.03 from config prices.
  - The prompt now covers hands, eating/tasting, facial reactions, interactions, state changes, and what is new.
  - Each window gets the previous window's events, and each event a `change` field.
- **Lint.** `core.BANNED` bans camera direction only. "Sets down the camera" and "films with a camera" are allowed. Lint failures in director repairs carry fix hints.
- **Nano tighten.** Cues that fail only on length are shortened by `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` (stage `fit`), up to 2 batched calls, before any Ultra repair.
  - A rewrite that adds new content words is rejected.
  - Length-only failures never trigger an Ultra repair.
  - `min_words` is now 4.
- **Hindi.** `cast_gender` comes from the bible notes. When the gender is not visible, the prompt requires gender-neutral constructions (passive or noun-focused). It also asks for full sentences and natural kitchen words.
- **Story meaning.** Cast and beats are described by story role ("a crewmate photographs the first pepper"), not by filming mechanics.
- **Trace.** `trace.md` opens with a 5-line Run summary: calls (Ultra, Super VL, Nano), cost split, cues and average budget use, silent by choice, and drops with reasons. The context title is added when one was given. The script table shows words used/max.

**Tests.** `../narrate/.venv/bin/python -m pytest -q` gives **169 passed**: 32 director tests, 11 of them new. The new tests cover:
- camera as an object vs camera direction, with hints;
- fragments;
- the establishing check and payload;
- Nano tighten before Ultra, plus rejecting an inventing tighten without spending Ultra;
- context plumbing (bible/script/report/trace, CLI, the `SOURCES.md` titles);
- 12 s windows and previous events;
- the Hindi gender flag;
- the run summary.

All tests use fake clients only; no real API calls were made.

**Next real run.**
```bash
../narrate/.venv/bin/python -m narrate agent samples/nasa_chile_harvest_0000-0150.mp4 --out runs/nasa_v2_r2 --provider nebius \
  --context "Astronauts harvest, eat first chile pepper crop on space station"
../narrate/.venv/bin/python scripts/compare_runs.py runs/nasa_v2_r1 runs/nasa_v2_r2
```

**Risks.**
- **Perception cost.** 10 windows will cost somewhat more for Super VL; expect about $0.03–0.04 per clip in total.
- **Verb-opener lint heuristic.** It could flag a plural-noun opener followed by a determiner (e.g. "Hands the bowl…"). This is rare, and the repair carries a hint.
- **Establishing check.** It is lexical. A synonym of the place that is missing from bible `place` or `setting` (e.g. "ISS" vs "space station") needs a repair.
- **Under-use of the word budget** is guided by the prompt and reported (budget use %), but not enforced, so as not to spend Ultra calls on it.
- **Hindi gender-neutrality** is enforced only through the prompt; there is no deterministic check.
