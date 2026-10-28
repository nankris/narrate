### Round 8b scoring

Round 8b makes the single temperature-zero Ultra scoring call source-time-aware. Cue 1 is judged against `[0, pause₁]`;
later cues use `(pauseᵢ₋₁, pauseᵢ]`, clamped to the source duration, with two seconds of target-boundary tolerance. The call
receives only the verified key events, timed action steps, and visual ambiguities eligible for each cue. A match requires the
same action and object; vague matches receive half credit. Deterministic normalization rejects cross-window verdicts and
computes key-event/action-step coverage, unsupported claims, chronology errors, visual-ambiguity explanation, fluency, the
longest source span without a pause, speech overlaps, and pause-boundary placement. `score.md` audits every cue's exact
window, text, matched targets, unsupported claims, and chronology errors. Scoring remains capped at $0.05.

Ground-truth consolidation now describes visuals only: speech and subtitles are timing context and are never summarized.
Pause recommendations move forward out of speech and may use locally detected `-30 dB`, 80 ms energy micro-silences when
VAD merges continuous speech. A local low-threshold visual-change pass and Stage A title/label changes add sampling and
timeline boundaries for slide or text transitions.
