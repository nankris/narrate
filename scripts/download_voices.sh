#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p voices
base=https://huggingface.co/rhasspy/piper-voices/resolve/main
for spec in en/en_US/ljspeech hi/hi_IN/priyamvada; do
  IFS=/ read -r lang locale name <<< "$spec"
  for suffix in onnx onnx.json; do
    file="$locale-$name-medium.$suffix"
    curl --fail --location --retry 2 "$base/$spec/medium/$file" -o "voices/$file.part"
    mv "voices/$file.part" "voices/$file"
  done
done
