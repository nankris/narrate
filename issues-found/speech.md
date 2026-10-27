> Updated Task 3 evidence and fixes: [live probe findings](agent-probes.md).
> Historical baseline notes below describe the earlier build.

# Silence, speech duration, and Hindi voice quality

Symptom: one synthetic sample gap is too short to fit useful description after the 80 ms edge insets and word margin. Silence is not identical to absence of dialogue. Hindi espeak is a robotic synthetic voice.

Evidence: cached mock report records one dropped slot, zero detected-gap violations, and no trimmed TTS cues. Tests cover known silence intervals, energy fallback, continuous sine audio and no-audio video. No native-reader listening study was conducted.

Root cause: fixed speaking budgets and energy thresholds cannot recognize semantics or reliably separate quiet dialogue from silence. espeak is lightweight offline synthesis.

Fix/status: enforce timestamps independently of models, inset gap boundaries, cap speedup at 1.35x and trim/flag excess speech. Keep continuous-speech output without added descriptions; extended AD remains future work. Optional Piper backend requires local voice models and is unverified. Ultra failure retains English and explicitly records missing Hindi instead of fabricating a translation.
