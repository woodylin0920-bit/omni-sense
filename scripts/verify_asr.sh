#!/usr/bin/env bash
# Verify sounddevice mic enumeration and mlx-whisper warmup timing.
# Run once after install to confirm hardware access before Phase 3 integration.
set -euo pipefail

PYTHON=~/venvs/omni-sense-venv/bin/python

echo "=== sounddevice mic check ==="
$PYTHON - <<'EOF'
import sounddevice as sd
dev = sd.query_devices(kind='input')
print(f"  default input : {dev['name']}")
print(f"  channels      : {dev['max_input_channels']}")
print(f"  sample rates  : {dev['default_samplerate']:.0f}Hz")
EOF

echo ""
echo "=== mlx-whisper warmup timing ==="
$PYTHON - <<'EOF'
import time
import omni_sense_asr

t0 = time.perf_counter()
omni_sense_asr.warmup_once()
ms = (time.perf_counter() - t0) * 1000
print(f"  cold warmup   : {ms:.0f}ms")

t0 = time.perf_counter()
omni_sense_asr.warmup_once()
ms2 = (time.perf_counter() - t0) * 1000
print(f"  second call   : {ms2:.1f}ms  (should be ~0)")

if ms > 5000:
    print("  WARNING: cold warmup > 5s — check memory pressure")
EOF

echo ""
echo "OK — sounddevice + mlx-whisper verified on this hardware."
