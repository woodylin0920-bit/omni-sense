"""
pipeline.py 的 7 個必要 test。

不載入 YOLO / DepthAnything / Ollama（重） — 直接測邏輯層。
跑法: cd ~/Desktop/omni-sense && ./venv/bin/pytest test_pipeline.py -v
"""

import os
import time
import socket
import threading
from pathlib import Path
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
    p._bg_thread = None
    p._bg_lock = threading.Lock()
    p.model = MagicMock()
    p.depth_pipe = MagicMock()
    p._frame_lock = threading.Lock()
    p._latest_frame = None
    p._stop_event = threading.Event()
    return p


# === Test 1: 離線時 Layer 3 接手（核心 regression） ===
def test_offline_fallback_to_layer3():
    """離線 → Gemini 不通 → Layer 3 ollama_describe_stream 被呼叫 → 播報用 speak_local。"""
    p = make_pipeline()

    with patch("pipeline.is_online", return_value=False), \
         patch("pipeline.gemini_describe", return_value="") as mock_gemini, \
         patch("pipeline.ollama_describe_stream", return_value=iter(["前方有車輛。"])) as mock_stream, \
         patch("pipeline.speak_local") as mock_say, \
         patch("pipeline.speak_edge") as mock_edge:

        p._background_describe(["car", "person"])

        mock_gemini.assert_not_called()  # 離線不該打 Gemini
        mock_stream.assert_called_once_with(["car", "person"], lang="zh")
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
    p._last_alert[("car", "near")] = p._last_alert[("car", "near")] - 2.6
    assert p._should_alert("car", "near") is True


# === Test 3: Regression — Layer 3 絕對不用 speak_edge（舊 bug 的護身符） ===
def test_layer3_never_calls_speak_edge():
    """Gemini 失敗（線上但 API error） → Layer 3 接手 → 不可用 speak_edge。"""
    p = make_pipeline()

    with patch("pipeline.is_online", return_value=True), \
         patch("pipeline.gemini_describe", return_value="") as _mock_gemini, \
         patch("pipeline.ollama_describe_stream", return_value=iter(["安全提醒。"])), \
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


# === Test 5: ollama_describe 正常路徑（chat API）===
def test_ollama_describe_happy_path():
    """sys.modules mock — ollama.chat stream 版本。"""
    fake_stream = iter([
        {"message": {"content": "前方有車。"}},
    ])
    mock_ollama = MagicMock()
    mock_ollama.chat.return_value = fake_stream

    with patch.dict("sys.modules", {"ollama": mock_ollama}):
        result = pipeline.ollama_describe(["car"], lang="zh")

    assert result == "前方有車。"
    mock_ollama.chat.assert_called_once()
    _, kwargs = mock_ollama.chat.call_args
    assert kwargs["model"] == pipeline.OLLAMA_MODEL
    assert kwargs.get("stream") is True
    messages = kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert "car" in messages[-1]["content"]


# === Test 26: _looks_like_boilerplate 偵測中文 patterns ===
def test_looks_like_boilerplate_detects_zh_patterns():
    assert pipeline._looks_like_boilerplate("請您提供更多上下文", "zh") is True
    assert pipeline._looks_like_boilerplate("您是我的助手", "zh") is True
    assert pipeline._looks_like_boilerplate("", "zh") is True
    assert pipeline._looks_like_boilerplate("  ", "zh") is True
    assert pipeline._looks_like_boilerplate("前方有車輛和行人", "zh") is False
    assert pipeline._looks_like_boilerplate("前方有狗", "zh") is False


# === Test 27: template_fallback zh — 兩個物件 ===
def test_template_fallback_zh_two_objects():
    result = pipeline.template_fallback(["car", "person"], "zh")
    assert result == "前方有車輛和行人"


# === Test 28: template_fallback en ===
def test_template_fallback_en():
    result = pipeline.template_fallback(["bus", "bicycle"], "en")
    assert result == "Ahead: a bus and a bicycle"


# === Test 29: template_fallback ja ===
def test_template_fallback_ja():
    result = pipeline.template_fallback(["dog", "person"], "ja")
    assert result == "前方に犬と人"


# === Test 30: template_fallback 未知 label → default ===
def test_template_fallback_unknown_label():
    result = pipeline.template_fallback(["banana"], "zh")
    assert result == "前方有障礙物"


# === Test 31: Layer 3 boilerplate → template fallback ===
def test_layer3_boilerplate_triggers_fallback():
    """When Layer 3 returns boilerplate, template_fallback is substituted."""
    p = make_pipeline()

    with patch("pipeline.is_online", return_value=False), \
         patch("pipeline.ollama_describe_stream",
               return_value=iter(["請您提供更多上下文"])), \
         patch("pipeline.speak_local") as mock_say, \
         patch("builtins.print"):
        p._background_describe(["car", "person"])

    mock_say.assert_called_once()
    spoken = mock_say.call_args[0][0]
    assert "請您" not in spoken
    assert "前方有" in spoken


# === Test 25: ollama_describe_stream uses chat API + few-shot ===
def test_ollama_describe_stream_uses_chat_api():
    """ollama_describe_stream yields raw chunks and uses chat API with system + few-shot."""
    fake_chunks = [
        {"message": {"content": "前方"}},
        {"message": {"content": "有車"}},
        {"message": {"content": "。"}},
    ]
    mock_ollama = MagicMock()
    mock_ollama.chat.return_value = iter(fake_chunks)

    with patch.dict("sys.modules", {"ollama": mock_ollama}):
        result = list(pipeline.ollama_describe_stream(["car"], "zh"))

    assert result == ["前方", "有車", "。"]
    mock_ollama.chat.assert_called_once()
    _, kwargs = mock_ollama.chat.call_args
    assert kwargs["model"] == pipeline.OLLAMA_MODEL
    assert kwargs.get("stream") is True
    messages = kwargs["messages"]
    # system role at index 0
    assert messages[0]["role"] == "system"
    # 3 few-shot pairs (6 msgs) + 1 final user = 7 non-system messages
    user_msgs = [m for m in messages if m["role"] == "user"]
    asst_msgs = [m for m in messages if m["role"] == "assistant"]
    assert len(user_msgs) == 4   # 3 few-shot + 1 final
    assert len(asst_msgs) == 3   # 3 few-shot
    assert "car" in messages[-1]["content"]


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


# === Test 8: 背景 worker 單工化（drop-if-busy 策略）===
def test_bg_worker_single_thread():
    """bg thread 正在跑時，新 alert 不啟動第二個 worker（忽略策略）。"""
    p = make_pipeline()

    # 模擬一個正在執行中的 bg thread
    running_event = threading.Event()
    block_event = threading.Event()

    def slow_bg():
        running_event.set()
        block_event.wait(timeout=5)

    p._bg_thread = threading.Thread(target=slow_bg, daemon=True)
    p._bg_thread.start()
    running_event.wait()  # 確保 thread 已在跑

    with patch.object(p, "_detect", return_value=[("car", "near", 0.9, 0.2)]), \
         patch("pipeline.speak_local"), \
         patch("pipeline.gemini_describe") as mock_gemini, \
         patch("pipeline.ollama_describe") as mock_ollama:

        p.process_frame(MagicMock())

    # bg worker 在跑 → 忽略新請求，LLM 不被呼叫
    mock_gemini.assert_not_called()
    mock_ollama.assert_not_called()

    block_event.set()
    p._bg_thread.join(timeout=1)


# === Test 9: 資源路徑是絕對路徑（相對 pipeline.py 目錄）===
def test_absolute_paths():
    """_PTFILE, _resolve_yolo_path, _WARMUP_IMG 均是以 pipeline.py 目錄為基準的絕對路徑。"""
    pipeline_dir = os.path.dirname(os.path.abspath(pipeline.__file__))

    assert str(pipeline._PTFILE).startswith(pipeline_dir)
    assert str(pipeline._PTFILE).endswith("yolo26s.pt")

    yolo_path = pipeline._resolve_yolo_path()
    assert os.path.isabs(yolo_path), "_resolve_yolo_path() 應回傳絕對路徑"

    warmup = str(pipeline._WARMUP_IMG)
    assert os.path.isabs(warmup), "_WARMUP_IMG 應為絕對路徑"
    assert warmup.startswith(pipeline_dir)
    assert warmup.endswith("bus.jpg")


# === Test 10: speak_edge 每次產生唯一暫存檔路徑 ===
def test_speak_edge_unique_tempfile():
    """連續兩次 speak_edge 使用不同暫存檔路徑，不互相覆蓋。"""
    paths_used = []

    def capture_popen(cmd, **kwargs):
        if isinstance(cmd, list) and cmd[0] == "afplay":
            paths_used.append(cmd[1])
        m = MagicMock()
        m.wait.return_value = 0
        return m

    with patch("asyncio.run"), \
         patch("subprocess.Popen", side_effect=capture_popen):
        pipeline.speak_edge("first", lang="zh")
        pipeline.speak_edge("second", lang="en")

    assert len(paths_used) == 2
    assert paths_used[0] != paths_used[1], "兩次呼叫應使用不同暫存檔"
    assert all(p.endswith(".mp3") for p in paths_used)
    assert all("omni_tts.mp3" not in p for p in paths_used), "不應使用硬編碼路徑"

    # 清理 asyncio.run 被 mock 時留下的空檔
    for p in paths_used:
        try:
            os.unlink(p)
        except OSError:
            pass


# === Test 17: mark_network_down resets cache ===
def test_mark_network_down_resets_cache():
    """mark_network_down() sets _network_ok=False and _last_check=0.0."""
    pipeline._network_ok = True
    pipeline._last_check = time.time()

    pipeline.mark_network_down()

    assert pipeline._network_ok is False
    assert pipeline._last_check == 0.0


# === Test 18: Gemini failure calls mark_network_down ===
def test_gemini_failure_marks_network_down():
    """Any Gemini exception → mark_network_down() → _network_ok reset."""
    pipeline._network_ok = True
    pipeline._last_check = time.time()

    mock_genai = MagicMock()
    mock_genai.Client.side_effect = RuntimeError("quota exceeded")

    with patch.dict("os.environ", {"GEMINI_API_KEY": "fake-key"}), \
         patch.dict("sys.modules", {
             "google": MagicMock(genai=mock_genai),
             "google.genai": mock_genai,
         }):
        result = pipeline.gemini_describe(["car"], "zh")

    assert result == ""
    assert pipeline._network_ok is False
    assert pipeline._last_check == 0.0


# === Test 16: speak_local 語速依 priority 分級 ===
def test_speak_local_rate_per_priority():
    """L1 speak_local uses rate 220; L3 uses rate 175."""
    with patch("subprocess.Popen") as mock_popen:
        mock_popen.return_value.poll.return_value = None

        pipeline._current_audio_proc = None
        pipeline._current_audio_priority = 99
        pipeline.speak_local("緊急", "zh", priority=pipeline.PRIORITY_L1)
        l1_cmd = mock_popen.call_args_list[0][0][0]

        pipeline._current_audio_proc = None
        pipeline._current_audio_priority = 99
        pipeline.speak_local("描述", "zh", priority=pipeline.PRIORITY_L3)
        l3_cmd = mock_popen.call_args_list[1][0][0]

    pipeline._current_audio_proc = None
    pipeline._current_audio_priority = 99
    pipeline._current_audio_started = 0.0

    assert "-r" in l1_cmd
    assert l1_cmd[l1_cmd.index("-r") + 1] == "220"
    assert "-r" in l3_cmd
    assert l3_cmd[l3_cmd.index("-r") + 1] == "175"


# === Test 13: bg_busy 時跳過 Depth（Phase 0 止血修改）===
def test_bg_busy_skips_depth():
    """bg worker 在跑時，_detect 跳過 depth_pipe，改用 bbox heuristic。"""
    import numpy as np

    p = make_pipeline()

    running_event = threading.Event()
    block_event = threading.Event()
    p._bg_thread = threading.Thread(
        target=lambda: (running_event.set(), block_event.wait(5)),
        daemon=True,
    )
    p._bg_thread.start()
    running_event.wait()

    fake_frame = np.zeros((480, 640, 3), dtype=np.uint8)

    mock_box = MagicMock()
    mock_box.conf = 0.9
    mock_box.cls = 0
    mock_box.xyxy = [MagicMock()]
    mock_box.xyxy[0].tolist.return_value = [100.0, 100.0, 300.0, 400.0]

    mock_r0 = MagicMock()
    mock_r0.speed = {"preprocess": 1.0, "inference": 100.0, "postprocess": 0.5}
    mock_r0.names = {0: "person"}
    mock_r0.boxes = [mock_box]
    mock_r0.plot.return_value = fake_frame.copy()

    p.model.return_value = [mock_r0]

    with patch("builtins.print"):
        p._detect(fake_frame)

    p.depth_pipe.assert_not_called()

    block_event.set()
    p._bg_thread.join(timeout=1)


# === Test 14: estimate_distance_bbox — near (大 bbox 在畫面下方) ===
def test_estimate_distance_bbox_near():
    """Large bbox at bottom of frame → near."""
    mock_box = MagicMock()
    mock_box.xyxy = [MagicMock()]
    # bottom_y_ratio = 450/480 = 0.9375 > 0.75 → near
    mock_box.xyxy[0].tolist.return_value = [100.0, 300.0, 500.0, 450.0]
    dist, depth_val = pipeline.estimate_distance_bbox(mock_box, 480, 640)
    assert dist == "near"
    assert depth_val is None


# === Test 15: estimate_distance_bbox — far (小 bbox 在畫面中間) ===
def test_estimate_distance_bbox_far():
    """Small bbox in middle of frame → far."""
    mock_box = MagicMock()
    mock_box.xyxy = [MagicMock()]
    # bottom_y_ratio = 230/480 ≈ 0.479 < 0.55
    # bbox_area_ratio = 30*30 / (480*640) ≈ 0.003 < 0.05 → far
    mock_box.xyxy[0].tolist.return_value = [300.0, 200.0, 330.0, 230.0]
    dist, depth_val = pipeline.estimate_distance_bbox(mock_box, 480, 640)
    assert dist == "far"
    assert depth_val is None


# === Test 19: log_event 寫出合法 JSONL ===
def test_event_log_writes_jsonl():
    """log_event writes a valid JSONL record with ts, type, and payload fields."""
    import tempfile
    import json as _json

    old_fp = pipeline._event_log_fp
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="a", suffix=".jsonl", delete=False) as f:
            tmp_path = f.name
        with open(tmp_path, "a", buffering=1) as fp:
            pipeline._event_log_fp = fp
            pipeline.log_event("test_event", foo="bar", n=42)

        with open(tmp_path) as f:
            line = f.read().strip()
        record = _json.loads(line)

        assert record["type"] == "test_event"
        assert record["foo"] == "bar"
        assert record["n"] == 42
        assert "ts" in record
    finally:
        pipeline._event_log_fp = old_fp
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)


# === Test 20: log_event noop when _event_log_fp is None ===
def test_log_event_noop_when_uninitialized():
    """log_event must not crash when called before init_event_log."""
    old_fp = pipeline._event_log_fp
    try:
        pipeline._event_log_fp = None
        pipeline.log_event("should_not_crash", x=1)  # no exception expected
    finally:
        pipeline._event_log_fp = old_fp


# === Test 22: _capture_loop 只保留最新一幀 ===
def test_capture_loop_drops_old_frames():
    """_capture_loop overwrites _latest_frame; only the last successfully read frame remains."""
    import numpy as np

    p = make_pipeline()
    frames = [np.full((10, 10, 3), i, dtype=np.uint8) for i in range(3)]
    read_state = {"n": 0}

    def mock_read():
        if read_state["n"] < 3:
            f = frames[read_state["n"]]
            read_state["n"] += 1
            return True, f
        p._stop_event.set()
        return False, None

    mock_cap = MagicMock()
    mock_cap.read.side_effect = mock_read

    with patch("builtins.print"):
        t = threading.Thread(target=p._capture_loop, args=(mock_cap,), daemon=True)
        t.start()
        t.join(timeout=2)

    assert p._latest_frame is not None
    np.testing.assert_array_equal(p._latest_frame, frames[-1])


# === Test 23: process_stream 乾淨收尾 ===
def test_process_stream_clean_shutdown():
    """After cap exhausts frames, stop_event fires and both worker threads join."""
    import numpy as np

    p = make_pipeline()
    fake_frame = np.zeros((10, 10, 3), dtype=np.uint8)
    read_state = {"n": 0}

    def mock_read():
        if read_state["n"] < 3:
            read_state["n"] += 1
            return True, fake_frame
        return False, None

    mock_cap = MagicMock()
    mock_cap.read.side_effect = mock_read
    mock_cap.isOpened.return_value = True

    mock_cv2 = MagicMock()
    mock_cv2.VideoCapture.return_value = mock_cap
    mock_cv2.waitKey.return_value = 0

    with patch.dict("sys.modules", {"cv2": mock_cv2}), \
         patch.object(p, "process_frame"), \
         patch("builtins.print"):
        p.process_stream("fake.mp4")

    assert mock_cap.release.called
    assert mock_cv2.destroyAllWindows.called


# === Test 24: _resolve_yolo_path mlpackage 優先 ===
def test_yolo_model_path_prefers_mlpackage(tmp_path):
    """_resolve_yolo_path returns mlpackage path when present, .pt otherwise."""
    fake_mlpkg = tmp_path / "yolo26s.mlpackage"
    fake_pt = tmp_path / "yolo26s.pt"
    fake_pt.touch()  # .pt always present as fallback

    # mlpackage exists → prefer it
    fake_mlpkg.mkdir()
    with patch.object(pipeline, "_MLPACKAGE", fake_mlpkg), \
         patch.object(pipeline, "_PTFILE", fake_pt):
        assert pipeline._resolve_yolo_path().endswith(".mlpackage")

    # mlpackage absent → fall back to .pt
    fake_mlpkg.rmdir()
    with patch.object(pipeline, "_MLPACKAGE", fake_mlpkg), \
         patch.object(pipeline, "_PTFILE", fake_pt):
        assert pipeline._resolve_yolo_path().endswith(".pt")


# === Test 21: autouse fixture 停掉 event log ===
def test_event_log_disabled_in_tests():
    """conftest autouse fixture ensures _event_log_fp stays None during tests."""
    pipeline.log_event("foo", x=1)  # must not raise
    assert pipeline._event_log_fp is None


# === Test 11: ultralytics lazy import — import pipeline 不觸發 torch 載入 ===
def test_ultralytics_not_imported_at_module_level():
    """import pipeline 不應在 module 層觸發 ultralytics/torch。
    YOLO 必須只在 OmniSensePipeline.__init__ 內才被 import。
    """
    import sys
    # ultralytics 不應出現在 sys.modules（除非被其他測試已 import）
    # 直接驗證 pipeline 模組頂層不含 YOLO class reference
    assert not hasattr(pipeline, "YOLO"), (
        "YOLO 不應在 pipeline module 頂層可見；必須是 lazy import"
    )


# === Test 12: __init__ lazy import 可被 sys.modules mock 攔截 ===
def test_init_lazy_import_path():
    """用全 sys.modules mock 驗證 __init__ 的 lazy YOLO import 路徑正確，不觸發真實 torch 載入。"""
    mock_yolo_cls = MagicMock()
    mock_yolo_instance = MagicMock()
    mock_yolo_cls.return_value = mock_yolo_instance  # YOLO(path) returns mock model

    mock_depth_pipe = MagicMock()
    mock_hf_module = MagicMock()
    mock_hf_module.pipeline.return_value = mock_depth_pipe

    mock_pil_image = MagicMock()
    mock_pil_module = MagicMock()
    mock_pil_module.Image.open.return_value = mock_pil_image

    mock_ollama = MagicMock()
    mock_ollama.generate.side_effect = Exception("no daemon")

    sys_mocks = {
        "ultralytics": MagicMock(YOLO=mock_yolo_cls),
        "transformers": mock_hf_module,
        "PIL": mock_pil_module,
        "PIL.Image": mock_pil_module.Image,
        "ollama": mock_ollama,
    }

    with patch.dict("sys.modules", sys_mocks), \
         patch("pipeline._resolve_yolo_path", return_value="/fake/yolo.pt"), \
         patch("pipeline._WARMUP_IMG", Path("/fake/bus.jpg")), \
         patch("pipeline.check_network"), \
         patch("builtins.print"):

        p = pipeline.OmniSensePipeline(lang="zh")

    # YOLO was constructed with the correct path
    mock_yolo_cls.assert_called_once_with("/fake/yolo.pt")
    assert p.lang == "zh"
    # YOLO still not at module level after __init__
    assert not hasattr(pipeline, "YOLO")
