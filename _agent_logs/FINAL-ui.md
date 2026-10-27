# Task 5 — Narrate Web UI

Implemented offline-first Gradio 5 UI in app/app.py, cache builder, browser
screenshot/smoke script, four compact mock cached runs, UI unit tests and README.
No real provider calls, publishing, remotes, pushes or subagents used.

## Behavior

Samples default to the kitchen; EN/HI playback, eyes-closed pictures with audio,
VTT captions, escaped trace rows, correction links, verdict chips, results,
limitations, downloads and public documentation/license links are available.
Live uploads validate type, size and duration; stream from a worker/queue;
provider choices depend on server-side environment presence, never browser keys.
One global run at a time, with three Gradio worker slots and one agent worker.
Default session/daily/run caps: $0.25/$3.00/$0.25. Daily ledger uses locked,
atomic reservation/settlement keyed by IST date; unknown usage retains reservation.
Disconnect cleanup waits for the worker before releasing the run lock.
Mock-only screenshot process blocks external browser requests.

## Validation

- Full offline suite: 64 passed (31.20 seconds).
- Focused UI tests: 4 passed; caps, session/global exhaustion, IST rollover,
  prior-day settlement, upload limits/type, XSS escaping and cache discovery.
- Browser smoke: samples load, eyes-closed toggle, 1280x720 trace visibility,
  mock upload/run completion, output video, README and sources HTTP 200.
- All four mock caches generated, total 11.93 MiB, narrated videos 640px / CRF30.
- Real provider integration and billing were not exercised.

## Screenshot inspection

Opened and inspected Samples and trace PNGs. Initial screenshots 01/02 revealed
low contrast on summary numbers and too much height before the trace. Fixed the
summary text to white, reduced preview height to 125px and put model costs inline.
03/04 and final 07/08 show readable white-on-navy metrics, two compact previews,
a wider trace column and a right-hand results card. The trace detail shows amber
“fixes step 8” and red “contradicted” with the public action note prominent.
Screenshots are 1280x900; browser smoke also checks 1280x720. The full trace is
keyboard-scrollable; captions/downloads are below the first viewport.
A first toggle assertion raced the server update; the screenshot script now
waits for the resulting CSS class before checking it.

## Practical limits

Session budgets reset with a new Gradio session; the persisted global cap remains.
Provider usage can exceed estimates, as documented by the existing SpendGuard.
A crash conservatively retains its reservation; no automatic reconciliation.
Mock costs remain zero, not fabricated estimates of real TF usage. Existing
speech/event-coverage limitations are surfaced beside every report. Cache media
retain SOURCES.md attribution and its Tears of Steel soundtrack licensing caveat.
