# omni-sense

視障者即時導航 pipeline — YOLO 偵測 + 深度估算 + 雲端/本地 LLM 場景描述 + 多語言 TTS + **push-to-talk 問答**。

**差異化定位：全離線 = 成本 + 延遲優勢**（相對 Biped.ai、Seeing AI、OrCam）。

---

## 架構

```
攝影機 / 影片檔
    ↓
YOLO26s 偵測  (HIGH_PRIORITY 過濾：人/車/機車/腳踏車/狗...)
    ↓
DepthAnything V2 深度估算 (near/mid/far 分級)
    ↓
距離排序 → 最近危險物
    ↓
┌─ Layer 1: 本地 TTS (macOS say)     <300ms 緊急播報（一定執行）
│      ↓
│  背景 thread
│      ↓
├─ Layer 2: Gemini 2.0 Flash         <500ms 自然中文描述（線上）
└─ Layer 3: Ollama + Gemma 3 1B      <4s 離線 fallback（純本地）

按 SPACE → push-to-talk 問答（Chat MVP）
    ↓
mlx-whisper ASR（warm ~137ms）
    ↓
RapidOCR 全幀掃描 + YOLO 偵測 cache
    ↓
Gemma 3 1B 回答（離線，~1-4s）
    ↓
macOS say 播報
```

**Cooldown 分級：** near 0.5s / mid 1.5s / far 3s — 近距離車輛不被抑制。
**多語言：** 中 / 英 / 日，runtime 切換（demo 時按 `1` `2` `3`）。

---

## 跑

### 首次設定

> ⚠️ **macOS 警告**：**不要**把 venv 建在 `~/Desktop/` 或 `~/Documents/`。這些路徑若有開 iCloud Drive 的「桌面與文件檔案夾」同步，`fileproviderd` 會攔截每次 `.pyc` 讀取，`import torch` 可能從 1 秒變 23+ 分鐘（~1200x）。把 venv 建在 `~/venvs/` 然後 symlink 回來。詳見 [docs/macos-icloud-venv-trap.md](docs/macos-icloud-venv-trap.md)。

```bash
# 1. Python 環境（macOS：venv 放 iCloud 外）
mkdir -p ~/venvs
python3 -m venv ~/venvs/omni-sense-venv
ln -s ~/venvs/omni-sense-venv venv   # 在 repo 內留 symlink，所有既有指令不變
source venv/bin/activate
pip install ultralytics transformers torch opencv-python edge-tts google-genai ollama pytest
pip install sounddevice mlx-whisper rapidocr-onnxruntime scipy

# 2. portaudio（sounddevice 需要）
brew install portaudio

# 3. Ollama + Gemma 3 1B
brew install ollama
brew services start ollama
ollama pull gemma3:1b

# 4. Gemini API key（Layer 2 要用）
export GEMINI_API_KEY="your-key"
```

### 跑 demo

```bash
# 攝影機即時（含 push-to-talk）
python pipeline.py --source 0 --lang zh

# 影片檔
python pipeline.py --source samples/test_street.mp4 --lang zh

# 單張圖片（測試）
python pipeline.py --source bus.jpg
```

Demo 中鍵盤：
- `SPACE` — push-to-talk 問問題（錄音 3 秒後自動轉錄 + 回答）
- `1` `2` `3` — 切語言（中 / 英 / 日）
- `q` / `ESC` — 結束

**問題範例：**「前面有什麼？」「前面那個招牌寫什麼？」「現在安全嗎？」

### Chat headless 測試（不需攝影機）

```bash
# 從影片抽 3 幀跑 YOLO + OCR + chat Q&A
~/venvs/omni-sense-venv/bin/python scripts/test_chat_video.py
```

### Demo 加速（選用）

把 YOLO 轉 CoreML，M1 上 inference 從 ~71ms → ~14ms（約 5x）：

```bash
./venv/bin/python scripts/export_coreml.py
```

pipeline.py 啟動時會自動偵測 `yolo26s.mlpackage`，存在就用、沒有就 fallback 到 `.pt`。
`yolo26s.mlpackage` 已 gitignored（可重新產生），不會進 repo。

### 跑測試

```bash
./venv/bin/pytest -v   # 53 tests
```

### 跑 benchmark

```bash
./venv/bin/python benchmark.py   # YOLO / Depth / Ollama / OCR / ASR 全測
```

---

## 效能基準（M1 Air 8GB，warm 狀態）

| 元件 | 延遲 |
|---|---|
| YOLO26s (CoreML) | ~14ms |
| YOLO26s (.pt) | ~70ms |
| DepthAnything V2 Small | ~326ms |
| Layer 1 say 觸發 | ~50ms |
| Layer 2 Gemini Flash | ~500ms |
| Layer 3 Gemma 3 1B | ~1–4s |
| ASR mlx-whisper base (warm) | ~137ms |
| OCR RapidOCR (warm) | ~443ms |

---

## 硬體

- Mac M1 8GB 以上（本 repo 預設）
- Gemma 3 1B Q4 ~800MB（M1 8GB 安全）
- 想升 4B 換大模型：改 `OLLAMA_MODEL = "gemma3:4b"` + 建議 16GB 以上

---

## 狀態

- ✅ Layer 1 YOLO + 本地 TTS
- ✅ Layer 2 Gemini Flash
- ✅ Layer 3 Ollama + Gemma 3 1B 離線 fallback
- ✅ 攝影機即時 + 影片檔輸入
- ✅ 多語言 runtime 切換
- ✅ 距離分級 cooldown
- ✅ HIGH_PRIORITY 物件過濾
- ✅ Chat MVP — push-to-talk ASR + OCR + Gemma 問答（SPACE 鍵）
- 🔲 手機 / 胸前硬體 port
- 🔲 視障者 user research（10 人訪談目標）
- 🔲 haptic 回饋

---

## 設計文件

詳細設計決策、競品分析、Premise challenge 見 `docs/DESIGN.md`（office-hours + plan-eng-review 產出）。
Chat MVP 設計決策見 `docs/CHAT_DESIGN.md`。
