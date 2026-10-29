# opus-v2 progress (newest last; times IST)
- 16:10 r4 real runs: roti $0.0347 (10/12), nasa $0.0338 (10/10). Fragments gone; monotone "The cook ..." openings, NASA misses tasting.
- 16:22 merged main 78434ed -> b4bcbd0 (conflicts: config.yaml, core.py, SOURCES.md, roti cache = theirs). 189 tests.
- 16:38 Opus round 5 -> 7c98aae (story beats, canonical objects, re-look, opening-variety, sound/camera lint, Hindi active voice + refit fix). 203 tests.
- 16:42 committed DEMO_PLAN_v2.md, deploy/hf_space, .secretscan-allow (verified false positive: env var NAME in a how-to line).
Nebius spend for this job: see ../nebius_spend_opus_v2.md
- 16:47 r5 real runs: roti $0.0420 (9/12, story beats + spiral; fragment 'A ball on the mat'), nasa $0.0365 (6/10: 4 routine skips, no place, 'historic first' context leak).
- 17:15 Codex r6 -> a622262 (max-silence 20 s rescue, establishing place, period/verb lint, Hindi danda, title-claim check). 208 tests.
- 17:20 NOTE: box files restored ~16:51 (all mtimes 16:51); runs/*_v2_r5 outputs lost (spend already logged); ../narrate/.venv missing -> created narrate_opus/.venv (gitignored).
- 17:31 piper deps fixed in .venv (pathvalidate). r6 real (r6b): REGRESSION from over-strict lints: roti 7/12 ($0.047, establishing dropped), nasa 3/10 ($0.040; drops: object-identity alias, over budget, no-verb). r6a wasted $0.058 (TTS missing). Next: Opus r7 = soft checks + TTS preflight.
