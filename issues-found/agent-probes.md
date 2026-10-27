# Findings supplied by live NVIDIA development probes, 27 October 2026

Source: ../blog-assets-staging/BLOG_NOTES.md, supplied by the lead. This agent
implementation made no provider calls. Token Factory remains untested.

* Reasoning consumed all 400 output tokens with empty content. `/no_think`
  did not fix it; `chat_template_kwargs.enable_thinking=false` did. This is
  now the default; empty content is retried and never parsed as reasoning.
* Nano `nvidia/nemotron-nano-3-30b-a3b` and Super
  `nvidia/nemotron-3-super-120b-a12b` returned account-specific 404s despite
  catalog listing. NVIDIA development fitting now uses Lightning.
* Ultra returned a correct OpenAI tool call. Super VL accepted video_url and
  multiple image_url parts. Video used about 600 prompt tokens/second at
  10 fps / 640x360. JSON fences must be accepted.
* Video-mode VL hallucinated fading text and a blue dot. Still frames were
  accurate. Agent verification always uses sampled frames, never video.
* Continuous music hid all gaps from silencedetect. Silero found six gaps
  totalling 74.7 seconds in the 100-second film excerpt, about 24% speech.
  It missed a robotic line: VAD is not ground truth. Evaluate against subtitle
  dialogue with scripts/eval_against_subs.py; detected overlap is only a proxy.

## Published synthetic failure case

`samples/failure_continuous_speech.mp4`, produced with `--kind lecture`, has
30 seconds of continuous espeak over slides. The offline agent found no usable
gaps and emitted empty narration tracks with an explicit extended AD
(pause-the-video) recommendation. Reproduce with:

```
python -m narrate agent samples/failure_continuous_speech.mp4 --out runs/agent_failure --provider mock
```

Silero is loaded from the MIT upstream package using ONNX Runtime. Missing
runtime/model falls back to silencedetect/energy, explicitly reported.
