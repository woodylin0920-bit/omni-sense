你正在接手 omni-sense（視障導航 pipeline）。先讀這幾個檔案 30 秒進入狀況：

1. README.md — 架構 + 跑法
2. RESUME.md — 當前狀態
3. git log --oneline -15 — 最近做了什麼
4. docs/DESIGN.md — 為什麼這樣做（Layer 3 office-hours 產出）

讀完直接開工。

═══════════════════════════════════════════════════════════════
任務：Chat MVP — Phase 1 OCR 基礎
═══════════════════════════════════════════════════════════════

背景（已決策，不要再開戰場）：
- 路徑 = 路徑 B（Scene Q&A + OCR），不做地圖 / GPS / 音訊分類
- OCR 用 RapidOCR-onnxruntime（M1 native，輕量），不用 PaddleOCR / EasyOCR
- Phase 1 只做 OCR 基礎模組，不整合進 pipeline.py，不碰 chat 邏輯
- 整合進 chat 是 Phase 3；Whisper ASR 是 Phase 2

目標：
- 先把 OCR 模組獨立寫好、測好、benchmark 好
- 失敗的話（M1 跑不起來 / 太慢 / 讀不到字），停在這裡重新評估，不要硬上 Phase 2/3

工作風格：
- 環境：~/Desktop/repo/public/omni-sense（已是 git repo，main branch）
- Python：~/venvs/omni-sense-venv/bin/python（venv 在 iCloud 外，別自己重建）
- 6 個 atomic commit，每個 commit 都能獨立 revert
- 每次 commit 前跑 ~/venvs/omni-sense-venv/bin/pytest test_pipeline.py -v 確認綠
- commit message 第一行 imperative，<72 字
- 全部跑完 → push origin main

═══════════════════════════════════════════════════════════════
COMMIT 1: docs/CHAT_DESIGN.md — 鎖定 Chat MVP 設計
═══════════════════════════════════════════════════════════════

新增 docs/CHAT_DESIGN.md，內容如下：

# Chat MVP 設計（路徑 B：Scene Q&A + OCR）

## TL;DR

讓視障使用者**按住空白鍵**問問題，pipeline 用「當下 YOLO/Depth 偵測 + bbox OCR」回答。
完全離線，不上雲。

## 為什麼路徑 B（Office-Hours 產出）

使用者真實 query 範例（5 個典型）：
1. 「前面那個招牌寫什麼？」 ← OCR 解
2. 「我前面是公車還是計程車？」 ← OCR (車身字) + YOLO 解
3. 「附近有便利商店嗎？」 ← OCR (店名) 解
4. 「我是不是走過頭了？」 ← 暫不解（需地圖，刻意排除）
5. 「剛剛那個聲音是什麼？」 ← 暫不解（需音訊分類，刻意排除）

→ OCR 解 3/5，是最高 ROI 的單一新能力。

## 三 Phase 拆解

| Phase | 內容 | 標的 |
|---|---|---|
| 1 | RapidOCR 模組獨立 + benchmark | omni_sense_ocr.py |
| 2 | mlx-whisper push-to-talk ASR | omni_sense_asr.py |
| 3 | Chat orchestrator（YOLO + Depth + OCR + Gemma → say）| chat.py |

每個 phase 結束後**重新評估**繼續或停止。

## 刻意排除（v1 不做）

- 多輪對話 / 記憶（單 turn）
- 地圖 / GPS / 路線
- 音訊事件分類
- 雲端 LLM（Gemini）走 chat 路徑（離線優先）
- Wake word（按空白鍵就好）

## 風險

- M1 8GB 記憶體：YOLO + Depth + Gemma + Whisper + RapidOCR 同時 ≈ 1.5GB，邊緣
- OCR 中文招牌字體 / 模糊 / 角度問題 → Phase 1 benchmark 要驗
- 1 turn chat 體驗夠不夠？→ Phase 3 跑 demo 再決定

Commit message:
docs: lock chat MVP design — path B (scene Q&A + OCR), 3-phase rollout

═══════════════════════════════════════════════════════════════
COMMIT 2: 加 rapidocr-onnxruntime + omni_sense_ocr.py 模組
═══════════════════════════════════════════════════════════════

1. 安裝（注意：不要用 pip install rapidocr-onnxruntime 直接灌進系統 Python，要進 venv）

   ~/venvs/omni-sense-venv/bin/pip install rapidocr-onnxruntime

   若 M1 上有 onnxruntime arch 問題，試 onnxruntime-silicon 替代：
   ~/venvs/omni-sense-venv/bin/pip install onnxruntime-silicon rapidocr-onnxruntime

   裝完跑：
   ~/venvs/omni-sense-venv/bin/python -c "from rapidocr_onnxruntime import RapidOCR; ocr = RapidOCR(); print('ok')"
   應印 'ok'。失敗就停下來把錯誤訊息貼回來。

2. 新增 omni_sense_ocr.py 在 repo 根目錄：

```python
"""
OCR 模組：在 YOLO bbox 內找文字。On-demand 使用（chat 觸發），
非 _detect 熱路徑，避免拖慢 Layer 1。
"""
from __future__ import annotations
import threading

_ocr_instance = None
_ocr_lock = threading.Lock()


def _get_ocr():
    """Lazy load。第一次呼叫 cold ~3-5s，之後快取在記憶體。"""
    global _ocr_instance
    if _ocr_instance is None:
        with _ocr_lock:
            if _ocr_instance is None:
                from rapidocr_onnxruntime import RapidOCR
                _ocr_instance = RapidOCR()
    return _ocr_instance


def ocr_text_in_box(frame, box_xyxy, min_conf: float = 0.5) -> list[str]:
    """
    在 frame 的 (x1,y1,x2,y2) 範圍內跑 OCR，回傳偵測到的文字 list。
    frame: numpy BGR (cv2 預設)
    box_xyxy: (x1, y1, x2, y2) tuple of int
    min_conf: 信心分數門檻
    """
    x1, y1, x2, y2 = [int(v) for v in box_xyxy]
    h, w = frame.shape[:2]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    if x2 <= x1 or y2 <= y1:
        return []
    crop = frame[y1:y2, x1:x2]
    ocr = _get_ocr()
    result, _ = ocr(crop)
    if not result:
        return []
    return [text for box, text, score in result if score >= min_conf]


def ocr_full_frame(frame, min_conf: float = 0.5) -> list[tuple[tuple[int, int, int, int], str, float]]:
    """整張 frame 跑 OCR，回 [(box_xyxy, text, score), ...]。
    chat 場景下若 YOLO 沒偵測到 sign 類別也能用。"""
    ocr = _get_ocr()
    result, _ = ocr(frame)
    if not result:
        return []
    out = []
    for box, text, score in result:
        if score < min_conf:
            continue
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        xyxy = (int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys)))
        out.append((xyxy, text, float(score)))
    return out
```

3. 更新 .gitignore，加：
   *.onnx
   .rapidocr_cache/

Commit message:
feat: add RapidOCR module for on-demand bbox text recognition

═══════════════════════════════════════════════════════════════
COMMIT 3: omni_sense_ocr 單元測試
═══════════════════════════════════════════════════════════════

新增 test_ocr.py 在 repo 根目錄：

```python
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
```

跑：~/venvs/omni-sense-venv/bin/pytest test_ocr.py -v
應該 5/5 綠。

順便跑 ~/venvs/omni-sense-venv/bin/pytest -v 確認既有 test_pipeline.py 沒被波及（35 個 + 5 個 = 40 個全綠）。

Commit message:
test: unit tests for omni_sense_ocr (mock RapidOCR, no model load)

═══════════════════════════════════════════════════════════════
COMMIT 4: OCR cold/warm benchmark
═══════════════════════════════════════════════════════════════

更新 benchmark.py：在現有 benchmark 之外加一個 bench_ocr() 函式。
（不要動既有 YOLO / Depth / Ollama benchmark 的邏輯。）

加在 benchmark.py 適當位置：

```python
def bench_ocr(samples_dir="samples", n_warm=3):
    """OCR cold + warm latency on real sample images."""
    import time
    from pathlib import Path
    import cv2
    import omni_sense_ocr

    imgs = []
    for name in ["people_street.jpg", "bus.jpg", "test_street.mp4"]:
        p = Path(samples_dir) / name
        if not p.exists():
            continue
        if p.suffix == ".mp4":
            cap = cv2.VideoCapture(str(p))
            ok, frame = cap.read()
            cap.release()
            if ok:
                imgs.append((name, frame))
        else:
            frame = cv2.imread(str(p))
            if frame is not None:
                imgs.append((name, frame))

    if not imgs:
        print("[ocr] no sample images found, skipping")
        return

    print("\n=== OCR (RapidOCR-onnxruntime) ===")

    # Cold
    name, frame = imgs[0]
    t0 = time.perf_counter()
    out = omni_sense_ocr.ocr_full_frame(frame)
    cold_ms = (time.perf_counter() - t0) * 1000
    print(f"  cold   {name}: {cold_ms:7.1f}ms  ({len(out)} regions)")

    # Warm
    warm_times = []
    for name, frame in imgs:
        for _ in range(n_warm):
            t0 = time.perf_counter()
            omni_sense_ocr.ocr_full_frame(frame)
            warm_times.append((time.perf_counter() - t0) * 1000)
    if warm_times:
        avg = sum(warm_times) / len(warm_times)
        print(f"  warm  avg over {len(warm_times)} runs: {avg:7.1f}ms")


if __name__ == "__main__":
    # ... 其他 bench
    bench_ocr()
```

注意：不要打斷 if __name__ == "__main__" 既有的呼叫順序，bench_ocr() 加在最後。

跑：~/venvs/omni-sense-venv/bin/python benchmark.py
把實測 cold / warm 數字記下來，commit message 引用。

更新 README.md「跑 benchmark」段落底下加一行：
> benchmark.py 也會跑 OCR cold/warm（RapidOCR）— 為 Phase 3 chat latency budget 提供基準。

Commit message（範例，把實測數字填進去）:
perf: add OCR cold/warm benchmark (RapidOCR ~XXXms cold, ~YYYms warm)

═══════════════════════════════════════════════════════════════
COMMIT 5: 更新 RESUME.md — 鎖定 Phase 1 完工，下次接手不迷路
═══════════════════════════════════════════════════════════════

讀現有 RESUME.md。在「## 🟢 2026-04-21 Phase 0 已驗證通過」**之前**插入新區塊：

```markdown
## 🟢 2026-04-26 Chat MVP Phase 1 完工（OCR 基礎）

**完成**：
- docs/CHAT_DESIGN.md — 鎖定路徑 B (Scene Q&A + OCR) + 3 phase 拆解
- omni_sense_ocr.py — RapidOCR 模組（lazy load + bbox / full-frame 兩種介面）
- test_ocr.py — 5 unit tests，全部 mock，hermetic
- benchmark.py — OCR cold / warm 數字（見 commit message）

**還沒整合進 pipeline.py**。OCR 是 Phase 3 chat orchestrator 才會接進來。

**下一步**（給未來的我 / 接手的人）：
1. 看 OCR cold / warm benchmark 數字決定要不要繼續：
   - cold < 5s、warm < 1.5s、且讀得到中文招牌 → 進 Phase 2
   - 慢 / 讀不到 → 評估換模型或砍掉 chat 功能
2. 若繼續：貼 docs/prompts/phase2-whisper.md 給 Claude Code（Phase 1 commit 6 已建）
3. **去訪談視障者**（DESIGN.md 已記錄為 #1 blocker，這比 Phase 2/3 都重要）

**已知決策（防止下個 LLM 重新爭辯）**：
- Layer 3 LLM = pitch deck dressing，Layer 1 才是真產品（60s 實機驗證證實）
- Chat 走路徑 B，不做地圖 / GPS / 音訊分類（CHAT_DESIGN.md）
- OCR 用 RapidOCR-onnxruntime（M1 native），非 PaddleOCR / EasyOCR
- YOLO 走 CoreML mlpackage（14ms vs 71ms .pt）

**環境陷阱（別重蹈覆轍）**：
- venv 必須在 ~/venvs/，不能在 ~/Desktop/（iCloud sync 讓 import 慢 1200x）
- macOS cv2 windowing 必須在 main thread（producer/consumer 架構保證了這點）
- pytest 必走 ~/venvs/omni-sense-venv/bin/pytest，否則沒裝套件

**驗證 repo 健康（30 秒）**：
\`\`\`bash
~/venvs/omni-sense-venv/bin/pytest -v          # 應該 40 個全綠
~/venvs/omni-sense-venv/bin/python pipeline.py --source samples/people_street.jpg --lang zh
# 看到 [Layer 1] + [Layer 3] 即正常
\`\`\`

---
```

Commit message:
docs: refresh RESUME.md to reflect Phase 1 completion + handoff context

═══════════════════════════════════════════════════════════════
COMMIT 6: 把 phase prompts 存進 repo（self-handoff）
═══════════════════════════════════════════════════════════════

新增資料夾 docs/prompts/，加 README + 把這份 prompt 自己存進去：

1. docs/prompts/README.md：

```markdown
# Phase Prompts

把每個 phase 的 Claude Code prompt 存在這，未來接手者（不論是你自己 3 個月後、
另一個 Claude / Cursor / Codex）打開 repo 就知道專案的計畫線。

| Phase | 檔案 | 狀態 |
|---|---|---|
| 1 | phase1-ocr.md | ✅ 完工（見 git log）|
| 2 | phase2-whisper.md | ⏳ 待寫 |
| 3 | phase3-chat.md | ⏳ 待寫 |

## 怎麼用

1. 開新 Claude Code session
2. cd 到 repo 根目錄
3. cat docs/prompts/phaseN-XXX.md | pbcopy（複製到剪貼簿）
4. 貼進 Claude Code 開工

每個 prompt 都是自包含的 — 包含環境路徑、commit 規則、驗證步驟。
```

2. docs/prompts/phase1-ocr.md：把這整份 prompt（從「你正在接手 omni-sense」到 commit 6 結尾，包括 commit 6 自己）原文貼進去。
   ⚠️ 注意：因為這個 prompt 包含 commit 6「把 prompt 存進 repo」這層遞迴，存進檔案時就照原文存，不需要改寫。

Commit message:
docs: archive phase prompts in docs/prompts/ for self-handoff

═══════════════════════════════════════════════════════════════
最後步驟
═══════════════════════════════════════════════════════════════

1. 確認 6 個 commit 都在 main：git log --oneline -6
2. 跑 ~/venvs/omni-sense-venv/bin/pytest -v 確認全綠（40 個）
3. push：git push origin main
4. 跑一次 ~/venvs/omni-sense-venv/bin/python benchmark.py，貼最後輸出（OCR 那段）

回報模板：
- ✅ 6 commits SHA + 第一行
- ✅ pytest 數字
- ✅ OCR cold / warm 實測（這是決定要不要繼 Phase 2 的關鍵）
- ⚠️  OCR 在 3 張 sample 實際讀到什麼字（招牌？店名？路線號？）
- ⚠️  install / runtime 有沒有踩雷（M1 RapidOCR 不一定一帆風順）
- 🤔 你（Claude Code）的主觀評估：OCR 品質夠 chat 用嗎？

如果 OCR 慢到 1.5s+ 或 3 張裡讀錯一堆 → 不要硬上 Phase 2，停下來回報。
