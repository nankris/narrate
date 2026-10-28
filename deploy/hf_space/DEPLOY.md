# Hugging Face Space deployment

Do not deploy yet. **Requires user approval: creates a public Space.** These steps make a public, free-to-test Gradio Space; they must be performed by the account owner after reviewing licences, cache contents, and storage size.

## Required app patch before deployment

`app/app.py` already reads `NARRATE_UI_DAILY_CAP`, `NARRATE_UI_SESSION_CAP`, `NARRATE_UI_RUN_CAP`, turn and timeout caps, keeps the credential server-side, and serializes live work with a process lock plus Gradio concurrency `1`. The launcher maps `NARRATE_DAILY_CAP_USD` to its existing daily-cap hook.

It does **not** yet read `NARRATE_MAX_CLIP_S`: `validate_upload()` hard-codes 120 seconds and its UI copy says two minutes. Before publishing, make this small patch in the main app (not in this deployment scaffold): parse `NARRATE_MAX_CLIP_S` as a positive finite number, default `120`; use it in upload validation and both live-tab labels; set it to `60` in Space settings. Add tests for 60.0 accepted, >60 rejected, invalid environment values rejected, and the default remaining 120 locally.

Also verify that the in-flight director implementation exposes only director mode in the public live tab. Remove/disable legacy planner choices for the Space; do not claim director-only until this is true.

## Files to copy

Copy this directory's `README.md`, `app.py`, `requirements.txt`, and `DEPLOY.md` to the Space root. Also copy:

- `app/` and `narrate/`
- `config.yaml`
- `samples/cached_runs/`, the referenced source MP4s, and `samples/SOURCES.md`
- root `README.md` and `LICENSE` for the in-app documentation route
- any runtime voice/model assets whose licences permit redistribution

Do not copy local environments, `runs/`, test outputs, development caches, credential files, or unrelated media. Confirm the cached metadata uses relative paths that exist in the Space.

## Commands

Run only after explicit approval. Authenticate interactively; never put an access token or API credential in a command or committed file.

```bash
python -m pip install --upgrade huggingface_hub
huggingface-cli login
huggingface-cli repo create narrate --type space --space_sdk gradio
git clone https://huggingface.co/spaces/<<owner>>/narrate narrate-space
rsync -a --exclude '.git' deploy/hf_space/ narrate-space/
rsync -a app narrate config.yaml narrate-space/
rsync -a samples/SOURCES.md samples/cached_runs samples/*.mp4 narrate-space/samples/
cp README.md LICENSE narrate-space/
cd narrate-space
git add .
git commit -m "Deploy Narrate director demo"
git push
```

## Space settings

In **Settings → Variables and secrets** add `NEBIUS_API_KEY` as a **Secret**, never a Variable. Never print it, send it to the browser, include it in an error, or commit it.

Add these non-secret Variables:

```text
NARRATE_DAILY_CAP_USD=1.5
NARRATE_MAX_CLIP_S=60
NARRATE_UI_SESSION_CAP=0.25
NARRATE_UI_RUN_CAP=0.25
NARRATE_UI_MAX_TURNS=<<director limit>>
NARRATE_UI_TIMEOUT_S=<<director timeout seconds>>
GRADIO_ANALYTICS_ENABLED=False
```

Start at `$1.50/day`; increase only after observing legitimate demand and never above the approved `$2/day`. The per-run value must remain no greater than the session cap. Queue concurrency must remain `1`.

## Verification and operations

1. Open the public URL in a private browser with no account session.
2. Confirm cached roti and NASA samples play in English and Hindi without causing provider spend.
3. Confirm the hero cache says Nebius Token Factory and every displayed number matches its artifacts.
4. Upload valid clips at and above the 60-second boundary; confirm rejection happens before inference.
5. Confirm only director mode is offered and concurrent live requests queue or receive a clear busy response.
6. Exercise per-run, session, daily, turn, and timeout limits with a non-production test cap.
7. Inspect browser responses and ordinary application logs for secret leakage; do not enable request-body or environment dumps.
8. Confirm generated uploads/outputs have a retention/removal policy and errors reveal no filesystem paths or credentials.
9. Let the Space sleep, then test cold-start behavior and cached-sample recovery.

For abuse, reject invalid/large media early, keep one worker, disable live inference when the cap is exhausted, and leave Samples available. Add hosting-edge per-IP/request throttling if available. If abuse or unexpected spend appears, remove/rotate the secret and run Samples-only while investigating.

If CPU Basic sleep or availability is unacceptable during judging, deploy the same reviewed build to a small Nebius VM: one application worker, TLS reverse proxy, firewall-limited ports, server-side environment secret, identical spend/duration caps, health monitoring, and the cached Samples path. Update the submitted URL only after an external clean-browser test.

