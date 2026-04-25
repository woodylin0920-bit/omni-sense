"""chat.py unit tests — mock omni_sense_ocr + ollama, no model load."""
from __future__ import annotations
import sys
import types

import numpy as np
import pytest


@pytest.fixture(autouse=True)
def _mock_deps(monkeypatch):
    fake_ocr = types.SimpleNamespace()
    fake_ocr.ocr_full_frame = lambda frame, **kw: [
        ((0, 0, 10, 10), "便利商店", 0.9),
        ((10, 0, 20, 10), "FamilyMart", 0.8),
    ]
    monkeypatch.setitem(sys.modules, "omni_sense_ocr", fake_ocr)

    fake_ollama = types.SimpleNamespace()
    fake_ollama.chat = lambda *a, **kw: {"message": {"content": "  前方有便利商店。  "}}
    monkeypatch.setitem(sys.modules, "ollama", fake_ollama)

    monkeypatch.delitem(sys.modules, "chat", raising=False)


def _frame():
    return np.zeros((100, 100, 3), dtype=np.uint8)


def _dets():
    return [("person", "near", 0.9, 0.3), ("car", "mid", 0.8, 0.5)]


def test_answer_query_returns_answer():
    import chat
    ans = chat.answer_query("前面是什麼？", _frame(), _dets(), lang="zh")
    assert "便利商店" in ans


def test_answer_query_empty_question_returns_empty():
    import chat
    assert chat.answer_query("", _frame(), _dets()) == ""
    assert chat.answer_query("   ", _frame(), _dets()) == ""


def test_answer_query_strips_whitespace():
    import chat
    ans = chat.answer_query("test", _frame(), _dets(), lang="zh")
    assert ans == ans.strip()


def test_build_context_zh_includes_objects_and_text():
    import chat
    ctx = chat._build_context(
        [("person", "near", 0.9, 0.3), ("car", "mid", 0.8, 0.5)],
        [((0, 0, 10, 10), "出口", 0.9)],
        lang="zh",
    )
    assert "person" in ctx
    assert "出口" in ctx


def test_build_context_empty_returns_no_detect():
    import chat
    ctx = chat._build_context([], [], lang="zh")
    assert ctx == "（無偵測結果）"


def test_filter_ocr_removes_timestamps():
    import chat
    raw = [
        ((0, 0, 10, 10), "2019/11/08 04:29:31", 0.9),
        ((10, 0, 20, 10), "出口", 0.8),
        ((20, 0, 30, 10), "2024-03-15", 0.7),
    ]
    clean = chat._filter_ocr(raw)
    texts = [r[1] for r in clean]
    assert "出口" in texts
    assert not any("2019" in t or "2024" in t for t in texts)


def test_no_detection_no_ocr_skips_ollama(monkeypatch):
    """When both detections and clean OCR are empty, return fixed string without calling Ollama."""
    called = []
    fake_ollama = types.SimpleNamespace()
    fake_ollama.chat = lambda *a, **kw: called.append(1) or {"message": {"content": "x"}}
    monkeypatch.setitem(sys.modules, "ollama", fake_ollama)

    fake_ocr = types.SimpleNamespace()
    fake_ocr.ocr_full_frame = lambda *a, **kw: []
    monkeypatch.setitem(sys.modules, "omni_sense_ocr", fake_ocr)
    monkeypatch.delitem(sys.modules, "chat", raising=False)

    import chat
    ans = chat.answer_query("前面有什麼？", _frame(), [], lang="zh")
    assert called == []  # Ollama not called
    assert ans  # returns a non-empty fallback string


def test_sign_question_with_empty_ocr_skips_ollama(monkeypatch):
    """Asking '招牌寫什麼' with empty OCR returns fixed reply, no Ollama call."""
    called = []
    fake_ollama = types.SimpleNamespace()
    fake_ollama.chat = lambda *a, **kw: called.append(1) or {"message": {"content": "x"}}
    monkeypatch.setitem(sys.modules, "ollama", fake_ollama)

    fake_ocr = types.SimpleNamespace()
    fake_ocr.ocr_full_frame = lambda *a, **kw: []
    monkeypatch.setitem(sys.modules, "omni_sense_ocr", fake_ocr)
    monkeypatch.delitem(sys.modules, "chat", raising=False)

    import chat
    ans = chat.answer_query("前面那個招牌寫什麼？", _frame(), _dets(), lang="zh")
    assert called == []
    assert "沒有可辨識的文字" in ans


def test_sign_question_with_ocr_calls_ollama(monkeypatch):
    """Sign question with OCR text present should still call Ollama (not skip)."""
    called = []
    fake_ollama = types.SimpleNamespace()
    fake_ollama.chat = lambda *a, **kw: called.append(1) or {"message": {"content": "前方招牌寫著「某商店」。"}}
    monkeypatch.setitem(sys.modules, "ollama", fake_ollama)
    monkeypatch.delitem(sys.modules, "chat", raising=False)
    import chat
    ans = chat.answer_query("前面那個招牌寫什麼？", _frame(), _dets(), lang="zh")
    assert called == [1]
    assert "某商店" in ans


def test_answer_query_ollama_failure_returns_empty(monkeypatch):
    failing_ollama = types.SimpleNamespace()
    failing_ollama.chat = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("ollama down"))
    monkeypatch.setitem(sys.modules, "ollama", failing_ollama)
    monkeypatch.delitem(sys.modules, "chat", raising=False)
    import chat
    ans = chat.answer_query("test", _frame(), _dets(), lang="zh")
    assert ans == ""
