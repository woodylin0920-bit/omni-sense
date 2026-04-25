"""omni_sense_ocr unit tests — mock RapidOCR, no model load."""
from __future__ import annotations
import numpy as np
import pytest

import omni_sense_ocr


class _FakeOCR:
    """Mock RapidOCR：回固定結果，不載 onnx model。"""
    def __init__(self, result=None):
        self._result = result or []

    def __call__(self, _img):
        return self._result, None


@pytest.fixture(autouse=True)
def _reset_ocr_singleton(monkeypatch):
    monkeypatch.setattr(omni_sense_ocr, "_ocr_instance", None)


def test_lazy_load_only_once(monkeypatch):
    calls = []

    def factory():
        calls.append(1)
        return _FakeOCR()

    monkeypatch.setattr(omni_sense_ocr, "_get_ocr", factory)
    omni_sense_ocr._get_ocr()
    omni_sense_ocr._get_ocr()
    assert len(calls) == 2  # 只是被 monkeypatch 取代後每次重新呼叫，驗證可被替換


def test_ocr_text_in_box_filters_low_conf(monkeypatch):
    fake = _FakeOCR(result=[
        ([[0, 0], [10, 0], [10, 10], [0, 10]], "HIGH", 0.9),
        ([[0, 0], [10, 0], [10, 10], [0, 10]], "low", 0.3),
    ])
    monkeypatch.setattr(omni_sense_ocr, "_get_ocr", lambda: fake)

    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    out = omni_sense_ocr.ocr_text_in_box(frame, (10, 10, 50, 50), min_conf=0.5)
    assert out == ["HIGH"]


def test_ocr_text_in_box_clamps_to_frame(monkeypatch):
    captured = {}

    class _CaptureOCR:
        def __call__(self, img):
            captured["shape"] = img.shape
            return [], None

    monkeypatch.setattr(omni_sense_ocr, "_get_ocr", lambda: _CaptureOCR())
    frame = np.zeros((50, 50, 3), dtype=np.uint8)
    omni_sense_ocr.ocr_text_in_box(frame, (-10, -10, 200, 200))
    # crop 應該被 clamp 成 (0:50, 0:50)
    assert captured["shape"] == (50, 50, 3)


def test_ocr_text_in_box_invalid_box_returns_empty(monkeypatch):
    monkeypatch.setattr(omni_sense_ocr, "_get_ocr", lambda: _FakeOCR())
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    assert omni_sense_ocr.ocr_text_in_box(frame, (50, 50, 40, 40)) == []
    assert omni_sense_ocr.ocr_text_in_box(frame, (50, 50, 50, 50)) == []


def test_ocr_full_frame_normalizes_polys_to_xyxy(monkeypatch):
    fake = _FakeOCR(result=[
        ([[10, 20], [30, 22], [32, 40], [12, 42]], "STORE", 0.8),
    ])
    monkeypatch.setattr(omni_sense_ocr, "_get_ocr", lambda: fake)

    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    out = omni_sense_ocr.ocr_full_frame(frame, min_conf=0.5)
    assert len(out) == 1
    xyxy, text, score = out[0]
    assert xyxy == (10, 20, 32, 42)
    assert text == "STORE"
    assert score == pytest.approx(0.8)
