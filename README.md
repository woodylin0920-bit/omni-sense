# omni-sense

視障者即時導航 pipeline — YOLO 偵測 + 深度估算 + 雲端/本地 LLM 場景描述 + 多語言 TTS + **push-to-talk 問答**。

**差異化定位：全離線 = 成本 + 延遲優勢**（相對 Biped.ai、Seeing AI、OrCam）。

```
┌────────── 自動播報（每幀觸發）──────────┐    ┌──── 主動問答（SPACE 觸發）────┐
│  YOLO26s → DepthAnything → 距離排序     │    │  ASR (mlx-whisper)             │
│  Layer 1: macOS say        <300ms       │    │  → OCR + YOLO snapshot         │
│  Layer 2: Gemini Flash     ~500ms       │    │  → Gemma 3 1B 回答             │
│  Layer 3: Gemma 3 1B       ~1-4s        │    │  → macOS say 播報               │
└─────────────────────────────────────────┘    └────────────────────────────────┘
                  全部在 M1 Air 上跑，飛航模式可繼續用
```

---

## 目錄

- [架構](#架構)
- [快速開始](#快速開始)
- [使用方式](#使用方式)
- [效能基準](#效能基準)
- [Chat 品質實測](#chat-品質實測)
- [測試](#測試)
- [硬體需求](#硬體需求)
- [狀態與 Roadmap](#狀態與-roadmap)
- [設計文件](#設計文件)

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

按 SPACE → push-to-talk 問答（Chat MVP，路徑 B）
    ↓
mlx-whisper ASR 錄音 3 秒（warm ~137ms 轉錄）
    ↓
RapidOCR 全幀掃描 + YOLO 偵測 cache + sign-question guard
    ↓
Gemma 3 1B 回答（離線，含 few-shot + boilerplate guard）
    ↓
macOS say 播報
```

**Cooldown 分級：** near 0.5s / mid 1.5s / far 3s — 近距離車輛不被抑制。
**多語言：** 中 / 英 / 日，runtime 切換。

---

## 快速開始

### 首次設定

> ⚠️ **macOS iCloud 陷阱**：**不要**把 venv 建在 `~/Desktop/` 或 `~/Documents/`。這些路徑若有開 iCloud Drive 的「桌面與文件檔案夾」同步，`fileproviderd` 會攔截每次 `.pyc` 讀取，`import torch` 可能從 1 秒變 23+ 分鐘（~1200x）。把 venv 建在 `~/venvs/` 然後 symlink 回來。詳見 [docs/macos-icloud-venv-trap.md](docs/macos-icloud-venv-trap.md)。

```bash
# 1. Python 環境（macOS：venv 放 iCloud 外）
mkdir -p ~/venvs
python3 -m venv ~/venvs/omni-sense-venv
ln -s ~/venvs/omni-sense-venv venv   # repo 內留 symlink，所有既有指令不變
source venv/bin/activate

# 2. Python 套件（一次裝齊）
pip install ultralytics transformers torch opencv-python edge-tts \
            google-genai ollama pytest \
            sounddevice mlx-whisper rapidocr-onnxruntime scipy

# 3. portaudio（sounddevice 的 C library）
brew install portaudio

# 4. Ollama + Gemma 3 1B（離線 LLM）
brew install ollama
brew services start ollama
ollama pull gemma3:1b

# 5. Gemini API key（Layer 2 用，可選）
export GEMINI_API_KEY="your-key"
```

### 驗證安裝

```bash
~/venvs/omni-sense-venv/bin/pytest -q   # 應該 55 passed
```

---

## 使用方式

### 攝影機即時 demo

```bash
python pipeline.py --source 0 --lang zh
```

**鍵盤操作：**
| 鍵 | 動作 |
|---|---|
| `SPACE` | push-to-talk 問問題（錄音 3 秒 → 自動轉錄 → 回答） |
| `1` / `2` / `3` | 切語言（中 / 英 / 日） |
| `q` / `ESC` | 結束 |

**問題範例：**
- 「前面有什麼？」→ 描述當下偵測到的物件
- 「前面那個招牌寫什麼？」→ OCR 全幀掃描招牌
- 「現在安全嗎？」→ 根據近距離物件判斷風險

### 影片檔

```bash
python pipeline.py --source samples/test_street.mp4 --lang zh
python pipeline.py --source samples/test_youtube.mp4 --lang zh
```

影片會依原 FPS 播放（內建 capture loop FPS throttle）。

### 單張圖片

```bash
python pipeline.py --source samples/bus.jpg
```

### Chat headless 測試（不需攝影機 / 麥克風）

從 5 支不同情境影片各抽幾幀，跑 YOLO + OCR + Gemma 問答：

```bash
~/venvs/omni-sense-venv/bin/python scripts/test_chat_video.py
```

預設測試影片（缺檔自動 skip）：
- `samples/test_street.mp4` — 倫敦街景 + 巴士
- `samples/test_youtube.mp4` — 開車第一人稱
- `samples/walk_street_fp.mp4` — 步行街景
- `samples/crosswalk_fp.mp4` — 行人穿越
- `samples/indoor_mall.mp4` — 室內商場

### Demo 加速（選用）

把 YOLO 轉 CoreML，M1 上 inference 從 ~71ms → ~14ms（5x）：

```bash
./venv/bin/python scripts/export_coreml.py
```

pipeline.py 啟動時會自動偵測 `yolo26s.mlpackage`，存在就用、不存在 fallback 到 `.pt`。

---

## 效能基準

M1 Air 8GB，warm 狀態：

| 元件 | 延遲 | 來源 |
|---|---|---|
| YOLO26s (CoreML) | ~14ms | benchmark.py |
| YOLO26s (.pt) | ~70ms | benchmark.py |
| DepthAnything V2 Small | ~326ms | benchmark.py |
| Layer 1 say 觸發 | ~50ms | pipeline log |
| Layer 2 Gemini Flash | ~500ms | benchmark.py |
| Layer 3 Gemma 3 1B | ~1-4s | benchmark.py |
| ASR mlx-whisper base | ~137ms warm / ~2.4s cold | scripts/verify_asr.sh |
| OCR RapidOCR | ~443ms warm / ~823ms cold | benchmark.py |
| **Chat 端到端**（含 OCR + Ollama） | **~667ms 平均** | scripts/test_chat_video.py |

跑 `./venv/bin/python benchmark.py` 自己量。

---

## Chat 品質實測

12 幀（5 支不同情境影片）× 3 個問題 = 36 個答案，5 分制評分（≥4 算成功）：

| 問題類型 | 成功率 (≥4) | 觀察 |
|---|---|---|
| 「前面有什麼？」 | **10/12** | 場景描述穩定 |
| 「前面那個招牌寫什麼？」 | **6/12** | OCR 有清楚文字才會準；無文字時走 guard 直接回固定句 |
| 「現在安全嗎？」 | **11/12** | 風險判斷穩定 |
| **整體 ≥4** | **28/36 = 78%** | |

**成功 case：** OCR 完整讀到「Primrose Hill」→ Gemma 正確回「前面招牌寫著『Primrose Hill』」。

**已知瓶頸：** OCR 讀到碎片（如單字母 'T'）時 Gemma 仍會把碎片塞進答案；要解需提高 OCR 信心門檻或換更大模型（Gemma 4B）。

驗收細節跑：

```bash
~/venvs/omni-sense-venv/bin/python scripts/test_chat_video.py | tee logs/eval.log
```

---

## 測試

```bash
./venv/bin/pytest -v             # 55 tests, ~8s（全部 mock，不載模型）
./venv/bin/python benchmark.py   # 含 YOLO / Depth / Ollama / OCR / ASR
```

測試覆蓋：
- pipeline 邏輯（cooldown、HIGH_PRIORITY、boilerplate fallback、bg worker drop-if-busy 等 27 項）
- ASR / OCR / chat 三個獨立模組
- chat sign-question guard、timestamp filter、no-detect skip-Ollama

---

## 硬體需求

- **Mac M1 8GB 以上**（本 repo 預設）
- Gemma 3 1B Q4 ~800MB（8GB 安全）
- 升 4B 換大模型：改 `OLLAMA_MODEL = "gemma3:4b"` + 建議 16GB 以上
- 攝影機（macOS Continuity Camera 或內建均可）
- 麥克風（chat 功能需要；YOLO/Depth 不需要）

---

## 狀態與 Roadmap

- ✅ Layer 1 YOLO + 本地 TTS
- ✅ Layer 2 Gemini Flash
- ✅ Layer 3 Ollama + Gemma 3 1B 離線 fallback
- ✅ 攝影機即時 + 影片檔輸入（含 FPS throttle）
- ✅ 多語言 runtime 切換
- ✅ 距離分級 cooldown / HIGH_PRIORITY 物件過濾
- ✅ **Chat MVP — push-to-talk ASR + OCR + Gemma 問答（SPACE 鍵）**
- ✅ Chat 品質 guard（few-shot 洩漏、timestamp 過濾、sign-question 短路）
- 🔲 手機 / 胸前硬體 port
- 🔲 視障者 user research（10 人訪談目標）— **下一步最高優先**
- 🔲 haptic 回饋
- 🔲 升級 Gemma 4B（待 16GB 機器）

---

## 設計文件

| 文件 | 內容 |
|---|---|
| [docs/DESIGN.md](docs/DESIGN.md) | 系統設計決策、競品分析、premise challenge |
| [docs/CHAT_DESIGN.md](docs/CHAT_DESIGN.md) | Chat MVP 路徑 B 設計（為什麼選 OCR + Gemma 而非地圖/GPS） |
| [docs/macos-icloud-venv-trap.md](docs/macos-icloud-venv-trap.md) | iCloud sync 攔截 .pyc 讀取的 1200x 慢化事件 |
| [docs/PITCH.md](docs/PITCH.md) | 投資人簡報重點 |
| [docs/prompts/](docs/prompts/) | Phase 1/2/3 開發 prompt 存檔（self-handoff 用） |
| [RESUME.md](RESUME.md) | 接手 / 重開工作的 context dump |

---

## 授權

待補。
