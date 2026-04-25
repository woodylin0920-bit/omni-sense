"""omni_sense_asr unit tests — mock sounddevice + mlx_whisper, no mic / model load."""
from __future__ import annotations
import sys
import threading
import types

import numpy as np
import pytest


@pytest.fixture(autouse=True)
def _mock_audio_modules(monkeypatch):
    """Mock sounddevice + mlx_whisper 進 sys.modules，omni_sense_asr 內部 import 時會拿到 fake。"""
    fake_sd = types.SimpleNamespace()

    def _rec(n_frames, samplerate, channels, dtype):
        return np.zeros((n_frames, channels), dtype=np.float32)

    fake_sd.rec = _rec
    fake_sd.wait = lambda: None

    class _Stream:
        def __init__(self, **kw):
            self.kw = kw

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

        def read(self, n):
            return np.zeros((n, 1), dtype=np.float32), False

    fake_sd.InputStream = _Stream
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sd)

    fake_mlx = types.SimpleNamespace()

    def _transcribe(audio_or_path, **kw):
        return {"text": "  [mock] hello  "}

    fake_mlx.transcribe = _transcribe
    monkeypatch.setitem(sys.modules, "mlx_whisper", fake_mlx)

    import omni_sense_asr
    monkeypatch.setattr(omni_sense_asr, "_model_warmed", False)


def test_warmup_only_once():
    import omni_sense_asr
    omni_sense_asr.warmup_once()
    assert omni_sense_asr._model_warmed is True
    omni_sense_asr.warmup_once()  # 第二次 noop
    assert omni_sense_asr._model_warmed is True


def test_record_until_respects_stop_event():
    import omni_sense_asr
    stop = threading.Event()
    stop.set()  # pre-set: loop exits on first check, before any read
    audio = omni_sense_asr.record_until(stop, max_s=10.0)
    assert audio.size == 0  # no chunks collected when stop already set


def test_record_until_caps_at_max_s():
    import omni_sense_asr
    stop = threading.Event()  # 永不 set
    audio = omni_sense_asr.record_until(stop, max_s=0.3)
    assert audio.size <= omni_sense_asr.SAMPLE_RATE * 1  # 0.3s cap → < 1s 量


def test_transcribe_strips_whitespace():
    import omni_sense_asr
    audio = np.zeros(16000, dtype=np.float32)
    text = omni_sense_asr.transcribe(audio, lang="zh")
    assert text == "[mock] hello"


def test_transcribe_empty_audio_returns_empty():
    import omni_sense_asr
    text = omni_sense_asr.transcribe(np.zeros(0, dtype=np.float32), lang="zh")
    assert text == ""
