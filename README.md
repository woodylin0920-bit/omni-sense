# omni-sense

視障者即時導航 pipeline — YOLO 偵測 + 深度估算 + 雲端/本地 LLM 場景描述 + 多語言 TTS。

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
```

**Cooldown 分級：** near 0.5s / mid 1.5s / far 3s — 近距離車輛不被抑制。
**多語言：** 中 / 英 / 日，runtime 切換（demo 時按 `1` `2` `3`）。

---

## 跑

### 首次設定

```bash
# 1. Python 環境
python3 -m venv venv
source venv/bin/activate
pip install ultralytics transformers torch opencv-python edge-tts google-genai ollama pytest

# 2. Ollama + Gemma 3 1B
brew install ollama
brew services start ollama
ollama pull gemma3:1b

# 3. Gemini API key（Layer 2 要用）
export GEMINI_API_KEY="your-key"
```

### 跑 demo

```bash
# 攝影機即時
python pipeline.py --source 0 --lang zh

# 影片檔
python pipeline.py --source demo.mp4 --lang en

# 單張圖片（測試）
python pipeline.py --source bus.jpg
```

Demo 中鍵盤：`1` 中文 `2` 英文 `3` 日文 `q` / `ESC` 結束。

### 跑 test

```bash
./venv/bin/pytest test_pipeline.py -v
```

### 跑 benchmark

```bash
./venv/bin/python benchmark.py
```

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
- 🔲 手機 / 胸前硬體 port
- 🔲 視障者 user research（10 人訪談目標）
- 🔲 haptic 回饋

---

## 設計文件

詳細設計決策、競品分析、Premise challenge 見 `docs/DESIGN.md`（office-hours + plan-eng-review 產出）。
