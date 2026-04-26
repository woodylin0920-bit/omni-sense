═══════════════════════════════════════════════════════════════
PRE-FLIGHT（執行端開工前確認）
═══════════════════════════════════════════════════════════════
- 已在 Cursor 跑 `/remote-control` 並在 `/config` 開 push notifications？
  → 長任務（>10 min）跑完會推到 iPhone Claude app
  → 若 `/remote-control` 連不上，跳過，不影響本任務執行
- pytest baseline 綠？（~/venvs/omni-sense-venv/bin/pytest -v 應 55 passed）
- 在 omni-sense repo cwd？(`pwd` 確認 = ~/Desktop/repo/public/omni-sense)
═══════════════════════════════════════════════════════════════

你正在接手 omni-sense（視障導航 pipeline）。先讀 RESUME.md + git log -5 進入狀況。

═══════════════════════════════════════════════════════════════
任務：修「影片跑完聲音才出來」bug
═══════════════════════════════════════════════════════════════

已診斷的根因（不要再開戰場）：
- pipeline.py __init__ 有用 _WARMUP_IMG 做 YOLO + Depth warm up
- 但 _WARMUP_IMG 跟使用者的 video 解析度不同
- MPS / CoreML 在新 shape 第一次 inference 會 JIT 重編譯，~2-5s
- 期間 capture loop 已經按 fps 把整支短影片（如 14s）讀完並結束
- analyze loop 跑完第一 tick 時 stream 已停 → 只剩末端 1-2 個 say 在影片結束後播

使用者 2026-04-27 實機驗證症狀符合 H1（影片播放期間完全靜音、結束後才連串 say）。

修法：在 process_stream 開頭、起 capture/analyze thread 之前，**用第一幀做 _detect 預熱**（編譯真正解析度的 MPS/CoreML kernel），然後 rewind 影片回 frame 0。

2 個 atomic commit。

工作風格：
- 環境：~/Desktop/repo/public/omni-sense（main branch）
- Python：~/venvs/omni-sense-venv/bin/python
- 每次 commit 前跑 ~/venvs/omni-sense-venv/bin/pytest -v 確認綠（baseline 55 個）
- commit message 第一行 imperative，<72 字
- 全部跑完 → push origin main
- 完成後把本份 prompt 搬到 docs/prompts/phase3-fix-stream-warmup.md，清空 _inbox.md

═══════════════════════════════════════════════════════════════
COMMIT 1: process_stream 開頭 real-shape warmup + 結束時清掉殘留 audio
═══════════════════════════════════════════════════════════════

修改 pipeline.py 的 process_stream（目前在約 line 828）：

1. 開 VideoCapture 後、起 capture/analyze thread 前，**讀第一幀做 2 次 _detect 預熱**（第 1 次編 kernel，第 2 次驗證 warm）。然後 rewind 回 frame 0（攝影機 rewind 失敗無妨，代價只有跳過 1 幀）。

2. finally 區塊（join thread 之後、destroyAllWindows 之前）加上殺殘留 audio：

```python
# 影片結束後若還有 say 在播，preempt 掉避免「stream 結束後音訊還在響」
with _audio_lock:
    _stop_current_audio_unlocked()
```

完整修改後的 process_stream 結構（節錄關鍵段，不要逐字 copy 取代，請對應現有程式整合）：

```python
def process_stream(self, source):
    """攝影機或影片檔連續流。3 lanes：capture / analyze / display。"""
    import cv2

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise RuntimeError(f"無法開啟 video source: {source}")

    print(f"開始串流 (source={source}, 分析 stride={FRAME_STRIDE})")

    # Real-shape warmup：用第一幀預編 MPS/CoreML kernel，避免 analyze 第一 tick 卡 2-5s
    # 把整支短影片放完還沒處理到任何事件
    ok, first_frame = cap.read()
    if ok:
        print(f"  warm up at video resolution {first_frame.shape[1]}x{first_frame.shape[0]}...")
        t0 = time.perf_counter()
        for _ in range(2):
            self._detect(first_frame)
        print(f"  warm 完成 ({(time.perf_counter()-t0)*1000:.0f}ms)")
        # rewind 影片到 frame 0；攝影機 rewind 失敗無妨
        try:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        except Exception:
            pass

    print("按 q 或 ESC 結束｜SPACE 問問題（錄音 3 秒）")

    self._stop_event.clear()
    capture_t = threading.Thread(target=self._capture_loop, args=(cap,), daemon=True)
    analyze_t = threading.Thread(target=self._analyze_loop, daemon=True)
    capture_t.start()
    analyze_t.start()

    try:
        while not self._stop_event.is_set():
            # ... (現有 display + key handling 邏輯保留不動)
            ...
    finally:
        self._stop_event.set()
        capture_t.join(timeout=2)
        analyze_t.join(timeout=2)
        # stream 結束後殺殘留 say/afplay 避免「影片停了還在響」
        with _audio_lock:
            _stop_current_audio_unlocked()
        cap.release()
        cv2.destroyAllWindows()
```

注意：`_audio_lock` + `_stop_current_audio_unlocked` 已經是 module-level（pipeline.py 上半部已定義），直接用即可。

驗證：
1. 跑 ~/venvs/omni-sense-venv/bin/pytest -v 確認 55/55 綠（純結構修改不該動到既有測試）
2. 跑 ~/venvs/omni-sense-venv/bin/python pipeline.py --source samples/test_street.mp4 --lang zh
   - 期望：印出 "warm up at video resolution... 完成 XXms"（第一次跑可能 2000-5000ms，正常）
   - 期望：影片**播放期間**就有 Layer 1 say 出聲音（不是結束後才一次來一串）
   - 期望：影片結束時殘留 audio 被砍掉，不延伸到 stream 結束後

如果跑完還是「影片跑完才有聲音」，回報 warm 完成的 ms 數字。若 warm 跑了 ~3000ms 還是症狀依舊，代表不是 shape JIT 問題，停下來回報，不要硬上 commit 2。

Commit message:
fix: warm up YOLO+Depth at real video resolution before streaming

═══════════════════════════════════════════════════════════════
COMMIT 2: regression test — process_stream 必須在 spawn thread 前跑過 _detect
═══════════════════════════════════════════════════════════════

更新 test_pipeline.py，新增 test 鎖住「process_stream 開頭呼叫 _detect」這個 invariant，避免未來 refactor 把它拿掉又踩回 bug。

加在 test_pipeline.py 末尾：

```python
def test_process_stream_warms_up_before_threads(monkeypatch):
    """Regression：process_stream 必須在 spawn capture/analyze 前用第一幀跑 _detect 預熱，
    否則短影片會在 MPS/CoreML JIT 重編譯時錯過整段 stream。"""
    import pipeline
    import numpy as np
    import cv2 as _cv2

    # 假 cv2.VideoCapture：第一次 read() 回 frame，後續回 EOF
    class _FakeCap:
        def __init__(self):
            self._reads = 0
        def isOpened(self): return True
        def read(self):
            self._reads += 1
            if self._reads <= 1:
                return True, np.zeros((720, 1280, 3), dtype=np.uint8)
            return False, None
        def get(self, key): return 0
        def set(self, key, val): return True
        def release(self): pass

    fake_cap = _FakeCap()
    monkeypatch.setattr(_cv2, "VideoCapture", lambda src: fake_cap)
    monkeypatch.setattr(_cv2, "imshow", lambda *a, **k: None)
    monkeypatch.setattr(_cv2, "waitKey", lambda *a, **k: 0)
    monkeypatch.setattr(_cv2, "destroyAllWindows", lambda: None)

    pipe = pipeline.OmniSensePipeline.__new__(pipeline.OmniSensePipeline)
    pipe.lang = "zh"
    pipe._stop_event = __import__("threading").Event()
    pipe._stop_event.set()  # 立刻退出主 loop
    pipe._frame_lock = __import__("threading").Lock()
    pipe._latest_frame = None
    pipe._capture_thread = None
    pipe._analyze_thread = None
    pipe._bg_thread = None
    pipe._bg_lock = __import__("threading").Lock()

    detect_calls = []

    def _fake_detect(frame):
        detect_calls.append(frame.shape)
        return []

    pipe._detect = _fake_detect

    pipe.process_stream("dummy.mp4")

    assert len(detect_calls) >= 1, "process_stream 沒做 real-shape warmup！"
    assert detect_calls[0] == (720, 1280, 3)
```

如果這個 test 因為 OmniSensePipeline attribute 結構變更跑不起來，用 monkeypatch 補齊缺的 attribute，**不要**為了讓 test 過而砍掉 commit 1 的 warmup 行為。

跑：
- ~/venvs/omni-sense-venv/bin/pytest test_pipeline.py::test_process_stream_warms_up_before_threads -v
- ~/venvs/omni-sense-venv/bin/pytest -v 確認 56/56 全綠

Commit message:
test: regression — process_stream warms at video resolution before threads

═══════════════════════════════════════════════════════════════
最後步驟
═══════════════════════════════════════════════════════════════

1. git log --oneline -2 確認 2 個 commit 都在 main
2. ~/venvs/omni-sense-venv/bin/pytest -v 確認 56 個全綠
3. ~/venvs/omni-sense-venv/bin/python pipeline.py --source samples/test_street.mp4 --lang zh
   實機跑一次，記下：
   - "warm 完成" 用幾 ms？（第一次冷跑可能 2000-5000ms）
   - 影片播放期間有沒有聽見 Layer 1 say？
   - 影片結束後 audio 是否乾淨切斷？
4. 把本份 prompt 從 docs/prompts/_inbox.md 搬到 docs/prompts/phase3-fix-stream-warmup.md，清空 _inbox.md
5. push：git push origin main

回報模板：
- ✅ 2 commits SHA
- ✅ pytest 數字（應 56 passed）
- ⚠️ 實機觀察：warm 用了 XXms / 影片中有沒有 say / 結束後 audio 是否乾淨
- 🤔 主觀判斷：bug 是否解掉？
