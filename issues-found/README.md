> Updated Task 3 evidence and fixes: [live probe findings](agent-probes.md).
> Historical baseline notes below describe the earlier build.

# Issues found

See the complete one-line catalog in [INDEX.md](INDEX.md).

| Group | Evidence / status |
|---|---|
| [Provider compatibility](provider.md) | No authorized real calls; schema, JSON mode, regions and billing to verify |
| [Speech and scheduling](speech.md) | Short gap skipped; detector is not VAD; espeak quality limitations |
| [Mock fidelity](mock.md) | Timestamp-driven mock is deterministic, not perception quality evidence |

## Real-provider behaviour not yet verified - see smoke scripts

All provider tests use fake clients; no real network requests were made. Video schema support, JSON rejection handling, reasoning controls, Hindi quality, model availability, rates and token estimates need authorized smoke runs. Use `scripts/smoke_video_input.py`, `scripts/smoke_text.py`, and `scripts/list_models.py` with `--provider`. Final/demo measurements must use Nebius.

## First real run follow-up

Individual `real-run-*.md` files record each observed failure and fixed/open status. Static-text motion hallucinations remain open; provider cost improvements require a new authorized run.

## Second real-run fixes

- [never-commit](real-run-never-commit.md): exploration tools never committed; fallback emitted zero cues - fixed.
- [wrong-event-drafts](real-run-wrong-event-drafts.md): drafts described other parts of the video - fixed.
- [verify-unused](real-run-verify-unused.md): verification never used - now enforced.

Also fixed (see `tests/test_fix2.py`): transient 5xx/429/timeout retries, unsorted VTT, tiny-gap skipping, duplicate cues, dialogue events counted as uncovered, Lightning price.

## Third real-run fixes

- [long-gaps-one-cue](real-run-long-gaps-one-cue.md): long gaps got one cue (29% coverage); now split into 6-12 s slots, cues capped at 8 s - fixed offline.
- [orchestrator-input-growth](real-run-orchestrator-input-growth.md): ultra input grew ~200 tokens/turn; old turns now summarised, turn budget scales with slots - mitigated offline.

## Fourth real-run fixes

- [reinspection-loop](real-run-reinspection-loop.md): ultra re-inspected all 10 slots twice (31 inspections, 36 turns, 0 drafts, 2 cues / 13 % coverage), wrote ungrounded cue text, fallback dropped 7 slots - evidence board, repeat refusals, grounded-text check and batched fallback drafting added offline.

## Fourth real-run fixes (after fix4)

- [fix4-propose-loop](real-run-fix4-propose-loop.md): 38 `propose_cue` calls / 30 turns on a 30 s clip (two limits, dropped on-screen text, hand-trimming) - fixed offline.
- [missing-note-validation](real-run-missing-note-validation.md): a missing `note` arg + an opaque "ValidationError" disabled every tool for the last 16–21 calls of two real runs - fixed (fix6).
