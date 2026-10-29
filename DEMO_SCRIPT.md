# Narrate demo script — target 2:40, hard stop 2:50

Use only local files. Do not show credentials, terminals with environment variables, or an unverified hosted URL. Do not speak
over a cached narration cue. All metrics below are copied from `runs/ext/final/*/report.json`.

| Time | Screen and action | Voice-over |
|---|---|---|
| 0:00–0:18 | Play `runs/ext/final/roti/extended_en.mp4` from the start with the picture hidden. Say the first sentence, then let cue 1 play. | “Close your eyes. A cooking tutorial has plenty to show even while the presenter talks.” |
| 0:18–0:34 | Reveal the picture during the first freeze and let the source resume. | “Narrate uses extended audio description: pause at a safe boundary, explain what just happened, then resume without talking over dialogue.” |
| 0:34–0:51 | Jump to a later roti freeze. Show the frozen frame and then the resumed source. | “Its intended contract is strict: the pause comes after the event ends, and the cue describes only already-completed events. We are still repairing and reviewing that chronology.” |
| 0:51–1:09 | Play `runs/ext/final/lecture/extended_en.mp4` around the first pause. | “This synthetic lecture has no usable in-gap space. The original mode refuses it. Extended mode pauses at sentence boundaries so the visual slide can be described.” |
| 1:09–1:29 | Show `trace.md`, then `pause_plan.json`, without scrolling through cue prose. | “Nemotron on Nebius Token Factory analyzes the video, writes the description, and checks claims against still frames. Deterministic code chooses boundaries, measures speech, renders freezes, and records every decision.” |
| 1:29–1:47 | Show the two results cards or a prepared text card. | “The shipped roti cache turns one hundred nineteen point nine seconds into two hundred twenty-nine point one, with eight pauses. The thirty-second lecture becomes sixty-four point five seconds with three.” |
| 1:47–1:58 | Keep the results card visible. | “Both reports show zero overlap with detected speech. That is detector evidence, not an accessibility certification.” |
| 1:58–2:16 | Open the local Samples tab. Switch between roti/NASA and English/Hindi. | “Narrate also keeps its original in-gap agent: English and Hindi tracks, downloadable captions and video, a correction trace, and cached real runs that judges can replay without a key.” |
| 2:16–2:33 | Show the issues index, then the repository root. | “We publish the failures too: hallucinated motion, premature events, verification misses, and orchestration cost. Human editorial and accessibility review remain required.” |
| 2:33–2:42 | End card: name, repository, Apache-2.0. | “Narrate: extended audio description built with Nemotron on Nebius Token Factory. Open source under Apache 2.0.” |

## Recording checklist

- Record at 1920×1080, target 2:40, and stop by 2:50.
- Listen through the source audio before publishing; use no copyrighted music.
- Credit sample sources exactly as listed in `samples/SOURCES.md`.
- Disclose the actual synthetic voice used in the recorded video.
- Recheck the roti cue wording and chronology after the `codex/ad-timing` fix is merged.
- Burn in or upload accurate captions. Have a human check every accessibility claim.
- Show the local cached demo only. A public hosted URL and submission are still unverified.
