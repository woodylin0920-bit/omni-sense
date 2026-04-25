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
