# Narrate core — final summary

Built: offline-capable English/Hindi audio-description pipeline, CLI and callback API,
Nemotron routing/client/budget guard, mock, synthetic sample, cached narrated outputs,
19 offline tests, documentation, issue records and Apache-2.0 license. No web UI.

Validation: 19 tests passed in 9.81 seconds. Required mock demo command completed.
Sample: 164,061 bytes; both cached narrated MP4s are below 300 KB.
MOCK results: 91.77% scheduled gap coverage, zero detected-gap boundary violations,
one skipped short gap, no TTS trimming and zero provider spend.

Commands:
```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m narrate run samples/sample_kitchen.mp4 --out runs/demo --mock
```

Open issues: real Token Factory video/JSON/region behavior and costs remain unverified;
silence detection is not VAD; espeak quality, Piper verification and human Hindi/AD
review remain open. No provider calls, remote, push or publishing performed.

Required pre-commit secret scan: CLEAN (33 files scanned). This summary is included
in the local-only core implementation commit; no remote was added or push performed.
