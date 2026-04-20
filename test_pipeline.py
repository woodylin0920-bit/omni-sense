"""
pipeline.py 的 7 個必要 test。

不載入 YOLO / DepthAnything / Ollama（重） — 直接測邏輯層。
跑法: cd ~/Desktop/omni-sense && ./venv/bin/pytest test_pipeline.py -v
"""

import socket
from unittest.mock import MagicMock, patch

import pytest

import pipeline


# --- Helper: 繞過 __init__ 造 pipeline instance ---
def make_pipeline(lang: str = "zh", ollama_ready: bool = True) -> pipeline.OmniSensePipeline:
    """不載入重模型，純測邏輯。"""
    p = pipeline.OmniSensePipeline.__new__(pipeline.OmniSensePipeline)
    p.lang = lang
    p._last_alert = {}
    p._ollama_ready = ollama_ready
    p.model = MagicMock()
    p.depth_pipe = MagicMock()
    return p


# === Test 1: 離線時 Layer 3 接手（核心 regression） ===
def test_offline_fallback_to_layer3():
    """離線 → Gemini 不通 → Layer 3 ollama_describe 被呼叫 → 播報用 speak_local。"""
    p = make_pipeline()

    with patch("pipeline.is_online", return_value=False), \
         patch("pipeline.gemini_describe", return_value="") as mock_gemini, \
         patch("pipeline.ollama_describe", return_value="前方有車輛，請注意") as mock_ollama, \
         patch("pipeline.speak_local") as mock_say, \
         patch("pipeline.speak_edge") as mock_edge:

        p._background_describe(["car", "person"])

        mock_gemini.assert_not_called()  # 離線不該打 Gemini
        mock_ollama.assert_called_once_with(["car", "person"], lang="zh")
        mock_say.assert_called_once()  # Layer 3 必須用 speak_local
        mock_edge.assert_not_called()  # Layer 3 絕不能用 edge-tts


# === Test 2: 近距離車輛不被 cooldown 抑制（核心 regression） ===
def test_near_distance_bypass_cooldown():
    """第一次播報 car/near 後 0.6s 再播報 → 因 near cooldown 0.5s，應該允許。"""
    p = make_pipeline()

    # 第一次：允許
    assert p._should_alert("car", "near") is True
    p._mark_alerted("car", "near")

    # 0.6 秒後（模擬）：near cooldown 是 0.5s，該允許
    p._last_alert[("car", "near")] = p._last_alert[("car", "near")] - 0.6
    assert p._should_alert("car", "near") is True


# === Test 3: Regression — Layer 3 絕對不用 speak_edge（舊 bug 的護身符） ===
def test_layer3_never_calls_speak_edge():
    """Gemini 失敗（線上但 API error） → Layer 3 接手 → 不可用 speak_edge。"""
    p = make_pipeline()

    with patch("pipeline.is_online", return_value=True), \
         patch("pipeline.gemini_describe", return_value="") as _mock_gemini, \
         patch("pipeline.ollama_describe", return_value="安全提醒"), \
         patch("pipeline.speak_local") as mock_say, \
         patch("pipeline.speak_edge") as mock_edge:

        p._background_describe(["truck"])

        mock_say.assert_called_once()
        mock_edge.assert_not_called()  # 就算線上，Layer 3 也必須用 speak_local


# === Test 4: Cooldown 分級 near/mid/far 各自的時間對 ===
def test_cooldown_gradient():
    """驗證 COOLDOWN_BY_DIST 的分級正確。"""
    p = make_pipeline()
    assert p._cooldown("near") == 0.5
    assert p._cooldown("mid") == 1.5
    assert p._cooldown("far") == 3.0
    assert p._cooldown("unknown") == 3.0  # 未知距離用保守值


# === Test 5: ollama_describe 正常路徑 ===
def test_ollama_describe_happy_path():
    """mock ollama.generate 回 response，驗證函式正確剝出文字。"""
    fake_response = {"response": "前方有車，請小心  "}

    with patch("ollama.generate", return_value=fake_response) as mock_gen:
        result = pipeline.ollama_describe(["car"], lang="zh")

    assert result == "前方有車，請小心"  # strip 後
    mock_gen.assert_called_once()
    args, kwargs = mock_gen.call_args
    assert kwargs["model"] == pipeline.OLLAMA_MODEL
    assert "繁體中文" in kwargs["prompt"]
    assert "car" in kwargs["prompt"]


# === Test 6: is_online 測的是 Gemini endpoint，不是 google.com ===
def test_is_online_targets_gemini_endpoint():
    """驗證 check_network 打的是 generativelanguage.googleapis.com:443。"""
    # 重置全域狀態
    pipeline._network_ok = False
    pipeline._last_check = 0

    # Mock socket.create_connection 成功
    with patch("socket.create_connection") as mock_sock:
        mock_sock.return_value.__enter__ = MagicMock()
        mock_sock.return_value.__exit__ = MagicMock()
        pipeline.check_network()

        # 檢查打對 host:port
        args, kwargs = mock_sock.call_args
        host, port = args[0]
        assert host == "generativelanguage.googleapis.com"
        assert port == 443
        assert pipeline._network_ok is True

    # 模擬 timeout → offline
    with patch("socket.create_connection", side_effect=socket.timeout):
        pipeline.check_network()
        assert pipeline._network_ok is False


# === Test 7: set_language runtime 切換生效 ===
def test_set_language_runtime():
    """切到 ja 後 _templates() 回日文模板。"""
    p = make_pipeline(lang="zh")
    assert p._templates()["car"] == "注意，前方有車輛"

    p.set_language("ja")
    assert p.lang == "ja"
    assert p._templates()["car"] == "注意、前方に車"

    p.set_language("en")
    assert p._templates()["car"] == "Warning, car ahead"

    # 不支援的語言應 raise
    with pytest.raises(ValueError):
        p.set_language("kr")
