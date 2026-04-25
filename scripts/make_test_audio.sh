#!/usr/bin/env bash
# Generate baseline ASR test audio using macOS built-in TTS.
# WARNING: TTS-clean audio is *easy* for whisper. Real-world WER will be higher.
# Use these only for cold/warm latency baselines, not for accuracy claims.
set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p samples
TMP=$(mktemp -d)
trap "rm -rf $TMP" EXIT

say -v Mei-Jia "前面那個招牌寫什麼" -o "$TMP/zh.aiff"
afconvert -f WAVE -d LEI16@16000 -c 1 "$TMP/zh.aiff" samples/test_zh.wav

say -v Samantha "what does the sign say" -o "$TMP/en.aiff"
afconvert -f WAVE -d LEI16@16000 -c 1 "$TMP/en.aiff" samples/test_en.wav

echo "wrote samples/test_zh.wav and samples/test_en.wav"
ls -la samples/test_*.wav
