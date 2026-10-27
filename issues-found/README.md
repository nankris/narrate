# Issues found

| Group | Evidence / status |
|---|---|
| [Provider compatibility](provider.md) | No authorized real calls; schema, JSON mode, regions and billing to verify |
| [Speech and scheduling](speech.md) | Short gap skipped; detector is not VAD; espeak quality limitations |
| [Mock fidelity](mock.md) | Timestamp-driven mock is deterministic, not perception quality evidence |

## Real-provider behaviour not yet verified - see smoke scripts

All provider tests use fake clients; no real network requests were made. Video schema support, JSON rejection handling, reasoning controls, Hindi quality, model availability, rates and token estimates need authorized smoke runs. Use `scripts/smoke_video_input.py`, `scripts/smoke_text.py`, and `scripts/list_models.py` with `--provider`. Final/demo measurements must use Nebius.
