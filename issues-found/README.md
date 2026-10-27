> Updated Task 3 evidence and fixes: [live probe findings](agent-probes.md).
> Historical baseline notes below describe the earlier build.

# Issues found

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
