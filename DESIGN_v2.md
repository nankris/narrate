# Narrate v2: the "director" pipeline

Status: design + implementation on branch `opus-v2` (`narrate/director.py`, `--mode director`).
The tool-calling agent stays available as `--mode agent`.

## 1. Why v2: what the review and the real runs show

The judge review (`REVIEW_opus.md`, overall ≈ 6/10, narration 4/10) and the Token Factory caches point to the same root cause.

| Symptom (real Token Factory runs) | Root cause |
|---|---|
| Roti clip: **42 Ultra turns, $0.33, Ultra = 95 % of cost**, fallback finish. Tears clip: 30/30 turns, fallback. | Ultra re-reads a growing tool history every turn (≈ 7 k input tokens × 40 turns). Most turns are bookkeeping: propose, fail, redraft, verify. |
| Flat, repetitive cues: "Person continues kneading dough until it forms cohesive ball." NASA cues 1–5 all say "a man tends plants". | Each gap is drafted alone by Nano from 1–3 events. No stage ever sees the whole story, so nothing can say "what is new", "the result", or "why it matters". |
| `Title: "to 35 minutes".` | A burned-in **subtitle** fragment was perceived as on-screen text and read aloud. |
| NASA cues 6–7 describe shots from 10–15 s later. | Events leaked across gaps (edge overlap), and segment-relative VL times were taken as absolute (P0-3). |
| Tears: about 12 turns spent re-drafting "40 YEARS LATER", which the verifier had already contradicted twice. | Refuted evidence stayed on the board (P0-2). The HEAD snapshot fixed this in the agent; v2 builds the fix in from the start. |
| "Camera moves…", the literal word "TITLE". | Rules were stated in prompts but not enforced (the HEAD snapshot added `lint()`; v2 reuses it). |

**Diagnosis.** The 30–40 turn Ultra loop is both the cost bottleneck and the quality bottleneck. It works gap by gap, so it is story-blind. Ultra is the most capable writer in the Nemotron family, yet it spends its tokens on tool plumbing while a 30 B model writes the actual prose.

**v2 idea.** Invert the roles. Cheap models *look* at the whole clip. Ultra *writes the whole track at once*, like a human describer with a shot list. Deterministic code and a different modality then *check* the result. Ultra is called only where judgement is needed: ≤ 6 calls instead of 30–42.

## 2. Pipeline

```
probe ─► gaps (Silero VAD, slots, TTS-calibrated budgets)
      ─► shots (ffmpeg scene-change)            ┐ cheap, whole clip
      ─► scene (Super VL, 6 stills)             │
      ─► timeline (Super VL video windows)      ┘
      ─► bible (Ultra, 1 call)
      ─► assign events → gaps (midpoint / ≥50 % overlap; refuted excluded)
      ─► script (Ultra, 1 call, whole English track)  ─► post-checks (deterministic)
      ─► verify (Super VL on stills inside each gap)
            └─ failures ─► repair (Ultra, failed cues only) ─► post-check ─► verify   (≤ 2 rounds, then drop)
      ─► hindi (Ultra, 1 call, native Hindi) ─► measured with Hindi TTS ─► refit (≤ 1 call)
      ─► render (TTS, ducking mix, VTT, transcripts) ─► report.json / trace.json / trace.md
```

It is still an **agent**: a planner (script), tools (perception, TTS measurement, frame checks), a verifier, and a repair loop that acts on observations. The difference is that the loop is **bounded and structured**: plan the whole track once, then repair only what failed.

Targets per 2-minute clip: **≤ 6 Ultra calls, ≤ $0.10**, about 2–3 minutes wall time. Hard caps are set in `config.yaml → director`: `max_ultra_calls: 6` and `budget_usd: 0.15` (a SpendGuard cap).

### 2a. Shot and event timeline (whole clip, absolute times)

* **Shots.** `media.scene_cuts()` (ffmpeg `select='gt(scene,0.3)'` at 5 fps, 320 px) gives cut times at no model cost. The shot list goes into the bible and the script, and is used to place window boundaries.
* **Windows.** The *whole* clip is covered with windows of about `window_s = 24` s, not just the gaps. Each interior boundary snaps to a shot cut within ±3 s, so a shot is rarely split. A 2-minute clip gets 5 windows, so 5 Super VL `video_url` calls (640×360, 4 fps).
* **Prompt.** The prompt asks for events with `t_start/t_end` (absolute), `what` (who does what to what, and the visible result), `on_screen_text` (titles, labels, signs only), `subtitle_text` (burned-in subtitles: what is *said*), `importance` and `confidence`.
* **Normalisation** (`normalise_events`), which never trusts the model's time base or key names:
  * accepts `what | action | event | description`;
  * runs `absolute_times()` to detect segment-relative times and shift them;
  * clamps events into the window and drops impossible ones.
* **Subtitle demotion.** On-screen text is moved to `subtitle_text` when it looks like a subtitle fragment (starts lower-case, e.g. "to 35 minutes", "and add it") or when the scene pass reported `burned_in_subtitles` and the text is a sentence fragment. That one rule removes the roti `Title: "to 35 minutes"` bug class.
* **Ids and fallback.** Events are deduplicated across windows and given stable ids `e1…eN` in time order. If a window's video call fails, the same window is perceived from 4 stills (`separate_frames`). If that also fails, the window simply has no events, and the gaps inside it are skipped.

Because the timeline covers speech regions too, the writer knows what happened while people were talking. For example, the dough was divided at 0:38 under the voice-over, so the next gap can say "the dough balls now…" instead of re-establishing.

### 2b. Scene bible (one Ultra call)

**Inputs.** The Super VL scene pass (6 stills, existing `establish_scene`), the shot list and the full timeline.

**Output.**

```json
{"setting": "a bright home kitchen with a white wooden table",
 "cast": [{"id": "c1", "descriptor": "the cook", "first_seen": 0.0, "notes": "striped sleeves, bangles; only hands and torso visible"}],
 "objects": ["wooden bowl", "flour", "rolling pin", "baking mat"],
 "story": "making layered roti: knead, rest, divide, roll, oil, coil, roll flat",
 "beats": [{"t": 6.0, "beat": "water goes into the flour"}],
 "on_screen_text": [{"t": 2.0, "text": "...", "kind": "title|label|sign"}],
 "subtitles_present": true, "tone": "calm cooking tutorial"}
```

**Why Ultra rather than Super.** The bible is the only place where *story understanding* happens: what the goal is, which events are beats and which are repetition, and how to refer to people. Every cue inherits its quality. It is one text-only call of about 5 k input and 0.8 k output tokens (≈ $0.007), roughly 2 % of the old run's cost. Super VL already contributes the visual facts (scene pass and timeline), so the bible call needs no images. `director.bible_stage` can switch it to Super (`orchestrate_alt`) if cost matters more than quality. If the bible call fails, a deterministic bible is assembled from the scene pass, so the run continues.

**Rules:**
* Cast entries are short descriptors and never names, unless a name is written on screen.
* `subtitles_present` and subtitle texts are context. **Subtitles transcribe speech and are never read aloud.**

### 2c. Event→gap assignment (P0-3) and refuted evidence (P0-2)

Each event gets one **home** gap. The rule (`assign_events`):

1. Use the gap containing the event **midpoint**.
2. Otherwise use the gap that covers **≥ 50 % of the event**.
3. Otherwise the event is "in speech". It is story context only and cannot be cited as evidence.

A long, ongoing event (for example a 20 s kneading shot) is also evidence for any *other* gap it covers ≥ 50 % of. An event that only brushes a gap edge, like the NASA pepper shot that overlapped gap 6 by 0.1 s, is never assigned there.

A refuted event (`refuted: true`, set after a contradicted verification) is excluded from assignment, from the script and repair inputs, and from coverage metrics.

### 2d. Script writer (one Ultra call for the whole English track)

**Input:**
* the bible;
* the full timeline (ids, times, `what`, gap or "in speech");
* every narratable gap with:
  * `start/end`;
  * `max_words` **measured from the actual TTS voice**: the engine renders a calibration sentence once per language, which gives words per second and so `floor(min(0.9·dur, max_cue_s) · wps) − margin`;
  * its `evidence` ids;
  * `said_before` / `said_after`: subtitle text near the gap, plus an optional `<clip>.en.srt` sidecar;
* the rules.

**Rules:**
* The first cue establishes **place and who**.
* Later cues tell the **progression**: what is new, the result, why it matters for the goal.
* Short descriptors or pronouns after the first mention; never "Person …".
* Present tense, specific verbs, concrete nouns from the bible. No "camera", no "we see", no subtitles.
* On-screen text is quoted only for titles, labels and signs.
* Every factual claim must come from **that gap's evidence ids**. No future events.
* Do not repeat what the speaker just said.
* `"skip": true` when there is nothing new (silence is good DCMP practice).

**Output:** `{"cues": [{"gap_id", "text", "evidence": ["e3"]} | {"gap_id", "skip": true, "reason"}]}`.

**Deterministic post-checks** (`check_cue`). Any failure sends the cue to repair, together with the reason:

| Check | Rule |
|---|---|
| Budget | words ≤ `max_words`, **and** `check_fit()` renders the cue with the real TTS engine: seconds ≤ the cue cap, and no speech overlap |
| Lint | the existing `lint()` (we see, camera, bare TITLE, "Screen…", SKIP) plus director rules: a generic `Person …` opener, "continues …" (a no-new-information verb), and quoting a known subtitle |
| Redundancy | token-Jaccard ≥ 0.5 with the previous accepted cue, or ≥ 0.8 with any accepted cue |
| Evidence | ≥ 1 cited id that exists, is not refuted and is **assigned to this gap**; out-of-gap ids are stripped and reported |

### 2e. Verify (Super VL, different modality) → repair → drop

**Verify.**
* Each accepted cue is checked on 2 stills taken **inside its own gap**, at the cited events' midpoints clamped into the gap.
* Up to 4 cues are batched per Super VL call, with frames labelled by cue id.
* The verifier lists the cue's concrete claims and returns `supported | contradicted | uncertain`, plus the wrong phrase when contradicted.
* Motion is judged "consistent", because stills cannot show movement.

**Policy:**
* `contradicted`: the cited events that the quoted wrong phrase overlaps are **refuted**. If the verifier quotes no phrase, the whole cue is wrong, so the events it rests on are refuted. The cue then goes to repair with the verifier's reason.
* `uncertain`: accepted only when the cue has no risky content (quotes, numbers, names, per `risky_text`); otherwise it goes to repair.
* Verification call failed: the cue is **not** committed (`require_verification: true`). The only exception is mock mode.

**Repair.** One Ultra call per round covers **only the failed cues**. It sees each rejection reason, the remaining non-refuted evidence, and the accepted neighbouring cues. Repaired cues go through the post-checks and verification again. After 2 rounds anything still failing is **dropped**, so unverified text is never committed. Every repair round counts toward the 6-call Ultra cap.

### 2f. Hindi (one Ultra call, written natively)

**Inputs:** the bible, each cue's English *meaning*, and a Hindi word budget measured with the Hindi voice.

**Rules:**
* Ultra writes natural spoken Hindi rather than a literal translation.
* Correct gender and number agreement.
* Everyday words (आटा, बेलन, तवा, लोई).
* Devanagari only, no transliteration.

**Check and refit.** Each line is measured with Hindi TTS (`check_fit(…,'hi')`). Failing lines get **one** batched refit call that includes the measured and allowed seconds. A line that still fails is omitted from the Hindi track and reported. English is never blocked by Hindi.

### 2g. Trace and report

**Stage record.** Each stage (`gaps, shots, scene, timeline, bible, assign, script, verify, repair_N, hindi, render`) writes one record with model id(s), calls, tokens in/out, cost, latency, and input and output summaries:
* `trace.json` keeps `steps`, so `app/app.py` renders it unchanged. Ultra calls use role `orchestrator`, so the UI's "Turns" counter means Ultra calls. Per-cue verdicts appear as `verify_claim` rows, so the UI shows supported/contradicted chips.
* `trace.json` also adds `stages`.

**trace.md.** Written for judges: a stage table (model, calls, tokens, $, s), the bible, the timeline, the script with the evidence for each cue, verifier verdicts, repairs, and drops with reasons.

**report.json.** Keeps every field the app and `build_cached_runs.py` read: `status`, `cues`, `tracks`, `gaps`, `speech`, `cues_committed`, `cues_dropped`, `gap_coverage_percent`, `high_importance_covered_percent`, `overlaps_with_speech`, `usage`, `cost_by_role`, `estimated_cost_usd`, `agent_stats`, `latency_s`, `issues`, `fallback_finalize`. It adds `mode: "director"`, `bible`, `timeline`, `shots`, `stages` and `director_stats`.

### 2h. Modes

| Mode | Role |
|---|---|
| `--mode director` | v2, default for `python -m narrate agent/run`. |
| `--mode agent` | The tool-calling agent, unchanged. It is the "open-ended agent" story and the baseline for comparison. |
| `pipeline` | The legacy one-shot pipeline, kept for its tests. |

`scripts/compare_runs.py old/report.json new/report.json` prints the two cue tables side by side, aligned by time, plus cost and Ultra-call totals.

## 3. Hosted demo constraints (HF Space)

* **Samples tab:** zero cost. It reads `samples/cached_runs`, so the director's outputs drop in unchanged.
* **Live tab:** `NEBIUS_API_KEY` is a Space secret.
  * The existing `SpendLedger` enforces the **daily cap of $3** and the per-session cap.
  * The director's per-run cap is `min(ui.per_run_cap_usd, director.budget_usd)`, so about 30 live runs per day instead of about 9.
* **Hardware.** Clip ≤ 120 s (UI hint: 60 s) and ≤ 50 MB. There is one run at a time (`RUN_LOCK`). TTS uses the CPU (Piper or espeak) and ffmpeg is limited to 2 threads, which suits the free CPU Space.
* **Wall-clock limit.** The cap is `ui.timeout_s = 300`. The director's sequential calls (about 5 timeline + 1 scene + 3 verify + ≤ 6 Ultra) fit within it. The trace streams stage by stage, so the page never looks frozen.
* **Mode switch.** `ui.mode: director` selects the director for live runs. The Ultra/Super planner dropdown only applies to `agent` mode.

## 4. Failure modes and behaviour

| Failure | Behaviour |
|---|---|
| No usable gaps (continuous speech) | No model calls after the gap stage. The issue "extended AD needed" is reported and the outputs are empty but valid. |
| A timeline window fails (video and stills) | The window has no events. Its gaps are skipped and an issue is recorded. |
| Bible call fails or returns invalid JSON | A deterministic bible is built from the scene pass. |
| Script call fails or returns invalid JSON | One retry (it counts toward the Ultra cap). Then a fallback writes *model-written* timeline `what` text, trimmed to budget, and sends it through the same post-checks and verification. `fallback_finalize: true` is set. |
| Ultra cap or budget reached | No more repairs or refits. Failed cues are dropped and verified cues are rendered. `BudgetExceeded` is reported and never raised to the user mid-render. |
| Verifier call fails | Those cues are dropped (never committed unverified) and an issue is recorded. |
| VL returns relative times or odd keys | Normalised (§2a). Out-of-window events are dropped. |
| Hindi line too long after refit | Omitted from the Hindi track only, and an issue is recorded. |
| Timeout (`agent.timeout_s`) | The client deadline stops new calls, and the run finishes with what has been verified. |

## 5. Test plan (offline, fake clients only: `tests/test_director.py`)

* Assignment: midpoint rule, ≥ 50 % overlap rule, edge-brush rejection, one gap per event, refuted events excluded.
* Times: relative→absolute shift, `event` and `action` keys accepted, out-of-window events dropped, subtitle demotion.
* Script: SKIP handling (gap left silent and recorded as no-new-info), over-budget rejection, lint rejection (camera, "Person…", quoted subtitle), similarity to the previous cue, evidence-outside-gap rejection.
* Verify→repair→drop: a contradicted cue triggers refute plus a repair whose request carries the reason. A repaired cue that is supported gets committed. A cue still contradicted after 2 rounds is dropped. A failed verification call commits nothing.
* Ultra-call cap: never more than 6 Ultra calls, even when everything fails.
* Hindi: native call; over-long lines go to one refit; still over means omitted; non-Devanagari is rejected.
* Trace: every stage is present with model, tokens, cost and latency; `trace.md` has the stage table; Ultra calls carry role `orchestrator`.
* Report compatibility: all fields read by `app/app.py` are present, `trace_html()` and `results_html()` render a director run, and `--mock` end to end produces VTT, MP4, transcripts, report and trace.
* `compare_runs.py` aligns the cues of two reports.

Real-run validation happens later and is outside this step: rebuild the roti, NASA and Tears caches with `--mode director`, then compare them against the current caches with `compare_runs.py` and a frame audit.

## 6. Round 2 changes from real runs

First real Token Factory runs: `runs/roti_v2_r1` ($0.025, 5 Ultra calls, 11 cues; old agent $0.33, 42 turns) and `runs/nasa_v2_r1` ($0.026, 5 Ultra calls, 7 cues; old agent $0.20, 25 turns). Cost and timing accuracy improved as designed. The remaining problems were quality problems, and every fix keeps all cue text Nemotron-written.

| Evidence (r1) | Change |
|---|---|
| Telegraphic headlines that under-use the budget: roti "Cuts dough into portions; rolls each into a ball.", "Gestures to bowl, touches flour." (9 of 17 words in a 9.6 s gap). | The script prompt asks for complete spoken present-tense sentences with a subject, linked into a story ("Now…", the result, why it matters for the goal), DCMP-plain rather than purple. Each gap carries `target_words` = ⌈0.7·max_words⌉. New director lint, each rule with a fix hint: `;` (headline fragments) and a subject-less verb opener ("Cuts…", "Gestures to…"). `continue` is now caught as well as `continues`. `trace.md` shows words used/max and the average budget use. |
| Cue 1 never says where: NASA never mentions a spacecraft or space station; roti never mentions a home kitchen or roti. | The bible adds `place` (1–3 everyday words) and `goal`. The first scripted gap is flagged `establish: true`. A **post-check** requires the first narrated cue to contain a place term (the bible `place` plus the head of `setting`, minus generic adjectives); otherwise it goes to repair with "Fix: name the place (e.g. "home kitchen"), who is there and the goal". If the establishing cue is later dropped, an issue is reported. |
| No user context. | `--context "<title>"` (CLI), `run_director(context=)`, an optional live-tab textbox "What is this video? (optional title)", and `build_cached_runs.py`, which reads the quoted title from the `SOURCES.md` attribution. It reaches the bible, script and repair as `video_title` with an **UNVERIFIED** note: it may name the goal, place or dish, but it is never evidence. Perception and verification never see it. It is recorded in `report.video_title` and in the trace summary. |
| The NASA climax (the crew eating the pepper and reacting, ~81–110 s) was perceived as "talking and gesturing while holding small objects". | `window_s` 24 → **12** (snap 2 s): 10 windows per 2-minute clip. The shots stage logs a cost estimate (upper bound ≈ $0.03 from config prices; r1 measured $0.008 for 5 windows). The timeline prompt now asks explicitly about what hands hold and do, eating/drinking/tasting, facial reactions, interactions between people, changes of state of objects, and what is new. Each window receives the previous window's last 2 events, and events gain a `change` field. |
| Lint over-reach: "sets down the camera" was banned and burned 2 NASA repairs. | `core.BANNED` now bans only camera **direction** (the camera pans/zooms/cuts/shows/follows, "as the camera", "on camera", "zoom in", a leading "cut to"). A held camera is an object. Every lint failure sent to repair carries `Fix: …` (e.g. "a crewmate films with a camera"). |
| Ultra repairs wasted on 1–2 word overages (NASA gap 0 ×2; roti gap 7 dropped at 4 vs 3 words). | A new **Nano tighten** stage (`tighten_stage: fit`, Nemotron 3 Nano) runs before any Ultra repair, for cues whose *only* problems are length: at most 2 batched Nano calls. A rewrite that adds more than 1 new content word is rejected. Length-only failures never trigger an Ultra repair (dropped if Nano fails). The writer is told max_words is a hard limit and to count words. `min_words` is 3 → **4**, so tiny gaps stay silent by design. |
| Hindi used masculine forms ("रसोइया … रहा है") although the bible said gender not visible; fragments. | `cast_gender` is derived from the bible notes and sent with the Hindi and refit calls. If the gender is not visible, the prompt requires passive or noun-focused neutral constructions; otherwise correct agreement. The prompt also asks for full sentences and natural kitchen words (आटा, लोई, बेलन, चकला/मैट, तेल, परतदार रोटी/लच्छा पराठा). |
| Bible beat "The camera operator films"; cue "then filmed close-up". | The bible describes cast by story role ("a crewmate with a camera") and beats by story meaning ("a crewmate photographs the first harvested pepper"). The script prefers that meaning. "is filmed" and "close-up" are lint (film jargon). |
| trace.md was long before it said what happened. | It now opens with a 5-line **Run summary**: model calls (Ultra / Super VL / Nano), cost split, cues and budget use, silent by choice, and dropped with reasons, plus the context title if one was given. |

Ultra budget is unchanged (≤ 6 calls); Nano and the extra Super VL windows cost about $0.01 more per clip.

## 7. Round 3 changes from second real runs

The second roti and NASA runs exposed a coverage regression: Nano sometimes returned a bare JSON object, rambled to its token
cap, or made a cue longer; length-only failures were then dropped without using the remaining Ultra repair budget. NASA also
lost its establishing cue because a lexical place check rejected otherwise verified narration.

Round 3 keeps every narration line model-written and changes the bounded control policy:

- Nano receives one cue per call with its current count, exact maximum and required reduction. Thinking remains disabled, the
  response is capped at 160 tokens, bare-object JSON is accepted, and only a shorter, non-inventing result can advance.
- English budgets assume a conservative 2.6 words/s natural narrator (or a slower measured voice). Measured TTS seconds are
  authoritative: a cue may exceed `max_words` by at most 15% only when it fits with the configured `max_atempo` speed-up.
  Anything Nano cannot fit goes to Ultra repair, within the existing six-call cap, before it is dropped.
- The place check accepts any content word from bible `place` or `setting`. A compact place-and-person opening is requested;
  if repairs still cannot add the place, the best otherwise-valid Nemotron cue is verified and retained with a report issue.
- The writer targets 70-90% of the maximum and returns a `words` self-count. Code independently counts and audits it.
- `report.json` and `trace.md` include narrated/narratable coverage, explicit reasons for every silence, and a 75% guard after
  excluding stated no-new-information silence.
- `scripts/judge_rubric.md` defines the frame-grounded DCMP-style scoring used for later re-evaluation.

## 8. Round 4 targeted quality fixes

The third real runs reached good coverage and cost (`roti_v2_r3`: 10/12 gaps; `nasa_v2_r3`: 9/10 gaps; about $0.037 each),
leaving small prose and verification issues. A conservative deterministic check now rejects clear bare-verb fragments such as
“Unrolls and flattens it” and “Takes one ball,” while exempting likely noun subjects. With exactly one bible cast member, a
second check rejects person nouns that drift from that cast descriptor. Both carry fix hints and therefore go to Ultra repair,
never to Nano tightening. If a batched Super VL response omits a cue verdict, the omitted cues get one smaller retry before the
existing unverified-drop policy applies. Script and repair guidance now prioritises distinctive reactions, results, new objects
and state changes over repeated ongoing activity, requires exact bible cast descriptors or pronouns, and favours idiomatic
establishing phrasing. Hindi guidance favours natural noun-focused speech over stiff passive chains. All narration remains
Nemotron-written; these additions only guide, check, retry, or route it.

## 9. Round 5: from grammatical to professional description

The fourth real runs (`roti_v2_r4` 10/12 gaps, `nasa_v2_r4` 10/10, about $0.034 each) produced grammatical cues that did
not yet read like a professional describer. Every fix below only guides, checks, re-looks or routes; each cue word is still
written by Nemotron.

| Evidence (r4) | Change |
|---|---|
| Roti: 9 of 10 cues open "The cook …". | **Track-level opening variety** (`restyle_openings`). After the first verification, if one two-word opening starts more than `openings_max_share` (50 %) of the committed cues, every other later occurrence (the first is kept) goes back to Ultra **in the same batched repair**, with `Style: … Fix: vary the opening` and `other_openings`. A rewrite that still opens the same way fails. **Soft:** if the rewrite fails any check or verification, the verified original is restored (`restyle_kept`). It runs only when an Ultra call is still free with one kept for Hindi. The script prompt asks for pronoun, object-first, "Now …" and participial openings. |
| "The cook rolls." | **Concrete-detail check**: a cue needs ≥ `min_detail_words` (2) content words beyond the cast descriptor, person nouns and pronouns. The fix hint is "add the object and its new state, or skip". |
| The layered-roti story (oil, coil → layers, rest, final roll) is not told; generic "folds dough and rolls a ball". | **Story arc in the bible**: each beat cites the `events` that show it and an optional `why` ("the coil makes the layers"), stated only when the goal makes it plain. `map_beats` gives each gap its beat: the home gap of the cited events, else by time. The gap payload carries `beat`, `key_event` (importance, then a visible reaction or result, then a change) and `routine` (no beat, change or reaction, and ≥ 50 % token overlap with the previous gap's events). The script tells the beat in story terms, leads with `key_event`, adds one new concrete detail per cue, and skips routine gaps that would only repeat. |
| NASA: five consecutive plant-tending cues. | The `routine` flag plus the skip rule above. Silence by choice stays outside the 75 % coverage guard. |
| "the plant" is passed around after the pepper harvest. | **Canonical object names**: the bible gives `names: [{name, aliases, from_t}]`, filled only when the events make the identity clear. From `from_t` on, a cue that uses an alias head noun ("plant") without the canonical head ("pepper") fails with `Fix: call it "…"`. Script and repair see `names`. The verifier gets `object_names`, so the canonical name is not marked as contradicted. |
| "Applause sounds as …", "… with laughter". | **Sound lint**: applause, sound(s), noise, music, audible, hear(d), laughter, voice(s) and beep fail with the hint "describe only what is visible (the crew claps and laughs)". Visible verbs such as laughs and claps are allowed. |
| "The camera lowers from the board." | **Camera-as-subject lint**: "the/a camera" at a clause start followed by *any* -s/-ed verb, or by is/was + verb, is camera direction. "She lowers the camera" and "holds the camera high" stay allowed. |
| The tasting (~94–97 s, r3 `e32` "covers his mouth") is absent from the r4 timeline. | **Focused re-look** (`relook` stage). The bible lists ≤ 2 `look_for` moments that the goal, story or UNVERIFIED title implies but no event shows, each with a window. One Super VL video call per item (4–12 s window, about $0.001) carries a FOCUS addendum: watch mouths, hands and faces, report only what is visible, and return `[]` otherwise. New, non-duplicate events join the timeline (`e{N+1}`, importance ≥ 4, `relook: true`). They are ordinary evidence: assigned, cited and verified on stills. |
| Roti Hindi: 9 of 10 lines are passives ("… जाता है"). | The prompt asks for active voice with a noun subject (the hands "हाथ …", the object, a group), at most one passive per line, and varied starts. It still never uses a gendered person subject when gender is not visible. **Soft deterministic check** (`HI_PASSIVE`: perfective participle + जा-, with compound verbs such as "ले जाता" excluded): a line with > 1 passive, and when > `hi_passive_share` of the lines are passive, every other further passive line, goes into the one refit call. A soft rewrite is accepted only if it passes every hard check **and** has fewer passives; otherwise the fitting original stays. |
| NASA Hindi gap 5 missing: "1 over budget -> 0 refit". | Root cause: the line was **not** over budget. It kept the on-screen label in Latin letters ("HATCH CHILE"), and the refit prompt only asked for shorter lines, so the model returned the same label. Now the Latin check names the words and says "write these words in Devanagari letters". The Hindi prompt asks for on-screen English words in Devanagari. `HINDI_REFIT` fixes each listed `problem` (length, Latin, passive) and receives the bible. The stage output reports failure kinds (`latin 1`, `over budget …`, `passive …`) instead of calling every failure "over budget". |

**Cost and calls.** The Ultra cap is unchanged at ≤ 6: bible, script, ≤ 2 repairs (restyle shares them), Hindi and ≤ 1 refit (hard and soft lines in one call). Super VL adds ≤ 2 re-look calls. The expected cost is about $0.035–0.045 per clip, under the $0.15 SpendGuard cap.

**Tests.** `tests/test_round5.py` has 14 tests, offline with fake models. They cover the camera-subject, sound and concrete-detail lints; bible parsing (beats with why/events, names, look_for); object identity, including the verifier payload; beat/key_event/routine in the script payload; the re-look adding only new events as evidence, and no call without look_for; restyling within the batched repair with the verified original kept; restyle skipped when no Ultra call is free; the passive counter; the targeted Latin refit; and the soft passive refit that rejects a worse rewrite.
