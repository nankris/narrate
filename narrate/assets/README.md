Silero VAD is by Silero Team, licensed under MIT (see SILERO_LICENSE.txt).
Install the upstream ONNX asset with `pip install silero-vad --no-deps`.
Narrate loads `silero_vad/data/silero_vad.onnx` directly using onnxruntime;
it does not import silero_vad, torch, or torchaudio. Model weights remain in
the installed package, avoiding a second binary in this repository.
The package source is https://github.com/snakers4/silero-vad.
