# Draft feedback for Token Factory

This is a private draft for the Token Factory team, not a claim about behavior
outside the runs named below. Reproduction steps that inspect the repository are
offline. The development-probe observations used a separate OpenAI-compatible
endpoint and are labelled as such; they are included where equivalent Token
Factory behavior or documentation would help.

## 1. Explain when prompt caching is available

**Observation.** All 201 model calls in the five shipped Token Factory reports
record `cached_tokens: 0`. This includes repeated Ultra orchestration calls whose
prompt contains a stable prefix and growing history. We configured cached-input
prices, but these runs received no observable cache discount.

**Reproduce (offline).** Run:

```bash
python - <<'PY'
import json
from pathlib import Path

calls = []
for path in Path("samples/cached_runs").glob("*/report.json"):
    calls.extend(json.loads(path.read_text())["usage"])
print(len(calls), sorted({call.get("cached_tokens") for call in calls}))
PY
```

The result is `201 [0]`.

**Request.** Please document whether chat completions use automatic prefix
caching, any minimum token or repetition threshold, which models support it,
and whether `prompt_tokens_details.cached_tokens` is always populated when a
cache hit occurs. A response field explaining why a request was ineligible
would make cost tuning much easier.

**Evidence.** `samples/cached_runs/*/report.json` (`usage[].cached_tokens`),
`docs/consistency_readme.md` (cached-token audit), and
`issues-found/real-run-orchestrator-input-growth.md` (repeated growing prompts).

## 2. Make the reasoning-off control explicit

**Observation.** In a development-endpoint probe, adding `/no_think` to the
system prompt did not disable reasoning: the whole completion budget was
consumed with empty content. Sending
`chat_template_kwargs.enable_thinking=false` did disable it. Narrate therefore
sends both controls and retries empty content.

**Reproduce.** Send the same small chat-completions request twice with a
reasoning-capable Nemotron model with a small fixed completion budget. Include
`/no_think` in both system messages. In the second request also include:

```json
{"chat_template_kwargs":{"enable_thinking":false}}
```

Compare visible content and reasoning-token usage. This reproduction was run
on the development endpoint, not Token Factory; Token Factory parity remains
to be confirmed.

**Request.** Please document one canonical, API-level way to disable thinking,
the models it applies to, and whether prompt directives such as `/no_think` are
supported. Ideally the API would reject an unsupported control instead of
silently spending the output budget.

**Evidence.** `issues-found/agent-probes.md` (reasoning-control finding) and
`blog-assets/BLOG_NOTES.md` (initial development-probe notes).

## 3. Canonicalize model IDs and casing

**Observation.** The working Token Factory IDs mix separators and case, for
example `nvidia/Nemotron-3.5-Super-VL`,
`nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`, and
`nvidia/Nemotron-3-Ultra-550b-a55b`. Other catalog/development IDs use lowercase
and, for Lightning, an underscore in `3_5`. Treating IDs as normalized names is
therefore unsafe. Availability may also differ from a catalog listing: some
listed IDs returned account-specific not-found errors in development probes.

**Reproduce (offline).** Inspect `providers.nebius.models` in `config.yaml`, then
print the distinct `usage[].model` values from
`samples/cached_runs/*/report.json`. They preserve the mixed-case IDs above.

**Request.** Please expose one canonical, copyable ID per model in the model
list, state whether IDs are case-sensitive, retain aliases for renamed models,
and distinguish "listed" from "callable by this account." Structured family,
version, size, modality, and region fields would avoid parsing display names.

**Evidence.** `config.yaml`, `samples/cached_runs/*/report.json`, and
`issues-found/agent-probes.md` (catalog-listed development IDs returning 404).

## 4. Document `video_url` limits and accounting

**Observation.** A development probe accepted an inline base64 MP4 in an
OpenAI-style `video_url` part. Later fixed-pipeline probes found that prompt
token use changed very little as clip duration increased substantially,
suggesting a fixed or capped frame sample rather than token use proportional to
duration. Short-segment inspection was consequently more dependable than
treating a long video as fully observed. These measurements are not direct
Token Factory measurements.

**Reproduce.** `scripts/smoke_video_input.py` creates a short synthetic MP4 and
submits the same content as `video_url`, a frame grid, and separate
images. The script is intentionally an explicit paid-provider smoke test; it
was **not** run for this draft. Equivalent long-duration probes can keep
resolution and frame rate fixed while varying duration and recording returned
prompt tokens.

**Request.** Please document supported URL schemes (including data URLs),
containers/codecs, byte and duration limits, frame-sampling policy, fetch
timeouts for remote URLs, and how video tokens are calculated. A response field
with sampled frame count/timestamps would make perceptual coverage auditable.

**Evidence.** `issues-found/agent-probes.md`, `blog-assets/BLOG_NOTES.md`
(development video-probe notes), and `issues-found/provider.md` (Token Factory
compatibility still requiring confirmation).

## 5. Publish regional endpoint and timeout guidance

**Observation.** The supplied model notes place the configured models in
different regions, so Narrate supports a `base_url` override per model. The
shipped reports used the global `api.tokenfactory.nebius.com` host. One
`sample_kitchen` call reports 63.32 seconds of model latency while most calls in
that report are below nine seconds. Separately, a development run recovered
from an API timeout on retry.

**Reproduce (offline).** Inspect the distinct `usage[].base_url_host` values and
maximum `usage[].latency_s` in each `samples/cached_runs/*/report.json`. For the
regional configuration path, see the per-model `base_url` test in
`tests/test_providers.py`. No regional endpoint was called for this draft.

**Request.** Please publish the authoritative model-to-region mapping, regional
base-URL format, cross-region behavior of the global endpoint, connection and
inference timeout recommendations, and whether retrying a timed-out request can
duplicate work or billing. A server-provided retryability signal would be more
reliable than classifying transport exceptions client-side.

**Evidence.** `blog-assets/BLOG_NOTES.md` (model/region list and development
timeout), `samples/cached_runs/sample_kitchen/report.json`,
`issues-found/provider.md`, and `tests/test_providers.py`.

## 6. Use consistent product and billing names

**Observation.** Client-facing concepts currently overlap: provider name,
global or regional endpoint, model publisher/family, model ID, catalog/list
price, and billed service. That makes phrases such as "Nemotron cost" or
"Token Factory model" ambiguous, particularly when a development endpoint is
used to estimate Token Factory list cost.

**Reproduce (offline).** Compare `config.yaml` (`providers`, model IDs, and
prices), `issues-found/real-run-dev-cost-zero.md` (development billing versus
list-cost reporting), and any cached report's `provider`, `billed_to`,
`base_url_host`, `usage[].model`, and `cost_usd` fields.

**Request.** Please provide preferred terminology and stable identifiers for
the service, endpoint/region, publisher, model family/version, price tier, and
billing meter. The model-list and usage responses should use the same names as
the pricing page.

**Evidence.** `config.yaml`, `issues-found/real-run-dev-cost-zero.md`, and
`samples/cached_runs/*/report.json`.

## 7. Return a provider-calculated per-request cost

**Observation.** Narrate records `cost_usd` on every one of the 201 cached calls,
but that field is calculated locally from prompt, cached, and completion tokens
plus a copied price table. The API usage object does not provide the amount
actually billed. This leaves ambiguity around failed requests, retries, media
accounting, cache eligibility, price-tier changes, and rounding.

**Reproduce (offline).** Inspect `usage_cost` and the appended usage record in
`narrate/llm.py`, then compare them with `usage[].cost_usd` in any
`samples/cached_runs/*/report.json`. `issues-found/provider.md` describes the
remaining uncertainty for attempted or failed requests.

**Request.** Please return a per-request billed-cost object alongside token
usage, with currency, total, input/output/cached/media components, price/version
identifier, billable status, and whether the value is final or estimated. For
timeouts and retries, returning the same information from a usage lookup would
let clients reconcile cost without storing sensitive request identifiers in
application logs.

**Evidence.** `narrate/llm.py`, `samples/cached_runs/*/report.json`,
`issues-found/provider.md`, and `issues-found/real-run-dev-cost-zero.md`.

