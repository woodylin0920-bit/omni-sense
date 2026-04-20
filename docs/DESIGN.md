# omni-sense Layer 3: Offline Local LLM Integration

**Author:** woody
**Date:** 2026-04-20
**Branch:** omni-sense-layer3 (pre-git)
**Status:** Design draft — produced via /office-hours, feeding into /plan-eng-review
**Project:** `~/Desktop/omni-sense/` (視障者導航 pipeline)

---

## TL;DR

在現有 3 層 pipeline 的 Layer 3 插入本地 Ollama + Gemma 3 4B，離線時接手生成多語言場景描述。目標：週末 demo 跑得動 2-3 種語言、延遲 < 4s、無需網路的完整導航體驗。差異化定位：**離線 = 成本 + 延遲優勢**（相對 Biped.ai / Seeing AI）。

---

## Project Context

### 現有架構（pipeline.py）

```
攝影機/圖片 → YOLO26s 偵測 → DepthAnything V2 深度估算 → 排序選出最近障礙
                                     ↓
                    Layer 1: 本地 TTS (macOS say) <300ms 緊急播報
                                     ↓
                         背景 thread 啟動 Layer 2/3
                                     ↓
                          is_online()?
                         ↙           ↘
                       Yes            No
                        ↓              ↓
              Layer 2: Gemini Flash   Layer 3: (尚未實作) ← 本 design doc 目標
              <500ms 自然語言         離線 fallback
                        ↓              ↓
                   edge-tts 播報    (需補) say / 本地 TTS
```

### 問題定義

- **Layer 3 是空的**（`pipeline.py:214` 註解 `# Layer 3 (Ollama/Gemma) 留待下一步整合`）
- 離線時：Layer 1 播「前方有車」但沒有自然語言描述（例如「左前方 2 公尺停了一台計程車」）
- 多語言需求：中/英/日（初期）

---

## Market Landscape（Phase 2.75）

| 產品 | Form Factor | AI 架構 | 價格 | 狀態 |
|------|------------|--------|------|------|
| **Biped.ai** 🎯 | 胸前 wearable | 預測 AI + haptic | ~$2-3K | 直接競品 |
| OrCam MyEye | 眼鏡夾式 | OCR + 人臉 | $4,000 | **2025 退出視障市場** |
| Envision Glasses | Google Glass | GPT + OCR | $3,500 | 活躍 |
| WeWALK | 智能白杖 | 物件 + 語音助理 | ~$600 | 活躍 |
| Seeing AI (MS) | iPhone app | 物件/場景/文字 | **免費** | 下載量最大 |
| Be My Eyes | iPhone app | 真人 + GPT-4V | **免費** | 整合 OpenAI |
| WOAD (學術) | 400g 眼鏡+手機 | cross-modal | 研究原型 | Nature 2025 |

### 關鍵啟示

1. **OrCam 退場**（$4000 產品市場吃不下）是**硬體單價警訊**
2. **Seeing AI + Be My Eyes 免費**：純雲端方案已被手機 app 覆蓋
3. **Biped.ai 是最直接對手**：胸前 form factor + AI 避障 + 瑞士品牌
4. **離線 + 多語是市場空白**：所有現有產品依賴雲端 AI

---

## Demand Validation Status

### ⚠️ 已知風險（誠實記錄）

**需求驗證 = 0**
- 尚未訪談過任何真實視障者
- 投資人想要的願景（AI 眼鏡 + 骨傳導）≠ 視障者已表達的需求
- 產品形態（眼鏡/手機/胸前盒）在用戶研究之前就被討論
- 競品（Biped.ai、Seeing AI）已經在解相近問題

**前提假設（未驗證）：**
- 視障者會因為「離線」而選本產品（vs. 免費的 Seeing AI）
- 中文/多語言場景是未被滿足的需求
- 即時避障需要 < 4s 延遲（依據 Biped 宣稱的 < 300ms 推測）

**緩解計畫（demo 後執行）：**
- 30 天內訪談 10 位視障者（視障協會 / 盲人重建院 / FB 社團）
- 觀察他們現在怎麼走路、用手機、出門買東西
- 不 demo prototype，只觀察

### ✅ Demo 目標（投資人技術可行性 gate）

投資人想確認「技術上能不能完成識別 + 本地 AI 串接」。Demo 必須 show：
1. YOLO 即時辨識跑得動（M 系列 Mac 攝影機 30fps）
2. DepthAnything 深度估算準確（距離分級 near/mid/far）
3. Layer 3 本地 Gemma 3 4B 生成多語言場景描述
4. Online → Offline 無縫切換
5. 語音播報延遲 < 4s

---

## Premises（Phase 3 — agreed）

1. ✅ **差異化是「全離線 + 隱私」的成本/延遲優勢**（不是純隱私，不是 B2B 軍醫金融）
2. ✅ **Layer 3 採 Ollama + Gemma 3 4B**（多語言是 Gemma 3 官方強項）
3. ✅ **週末 demo 優先於完整架構**，user research 延後 1 週
4. ✅ **hybrid 架構保留**（Layer 2 Gemini 仍在，Layer 3 只在離線啟用）

---

## Alternatives Considered

### APPROACH A: 最小整合（選中）

只在 `pipeline.py:214` 補上 Ollama 呼叫。其他動最少。

```
Effort:  S（CC+gstack ~30min / human ~3-4h）
Risk:    Medium — 冷啟動延遲未測
Pros:
  - 改動最小，pipeline 結構不動
  - 週末 demo 時程可控
  - 失敗可 fallback 到 Layer 1 模板播報
Cons:
  - prompt 不精緻，中文描述可能生硬
  - 沒多語系切換機制（寫死或靠 prompt 區分）
Reuses:
  - 現有 check_network, speak_edge, gemini_describe 結構
```

### APPROACH B: Prompt Engineering + 多語言架構

抽象出 `Describer` 介面，Gemini / Gemma 各自實作，加 few-shot 中/英/日模板。

```
Effort:  M（CC+gstack ~2h / human ~1 天）
Risk:    Low — 結構清楚
Pros:
  - 未來切別的本地模型成本低
  - 多語言擴充乾淨
  - 方便做 prompt A/B 測試
Cons:
  - 過度工程 for demo
  - 抽象層在需求未驗證前可能作廢
```

### APPROACH C: 多模型比較（暫不選）

同時支援 Qwen 2.5 3B / Gemma 3 4B / Llama 3.2，用 CLI flag 切換。

```
Effort:  L（CC+gstack ~4h / human ~2 天）
Risk:    High — 週末時程來不及
理由: 留作 demo 後決定長期模型時再做
```

### RECOMMENDATION

**Approach A（最小整合）** — 週末 demo 優先，抽象層之後再 refactor。

---

## Layer 3 實作設計

### 新增函式

```python
# pipeline.py
def ollama_describe(labels: list[str], lang: str = "zh") -> str:
    """Layer 3: 本地 Gemma 3 4B 生成場景描述。"""
    import ollama
    prompt_map = {
        "zh": f"視障導航助理。用一句話（15字以內）告訴視障者：{', '.join(labels)}。用繁體中文。",
        "en": f"Visual navigation assistant. One sentence (<15 words): {', '.join(labels)}.",
        "ja": f"視覚障害者ナビ補助。一言（15字以内）：{', '.join(labels)}。日本語で。",
    }
    try:
        resp = ollama.generate(
            model="gemma3:4b",
            prompt=prompt_map.get(lang, prompt_map["zh"]),
            options={"num_predict": 40, "temperature": 0.3},
        )
        return resp["response"].strip()
    except Exception as e:
        print(f"[Layer 3] Ollama 失敗: {e}")
        return ""
```

### 修改 `_background_describe`

```python
def _background_describe(self, labels: list[str]):
    lang = LANGUAGE  # "zh" / "en" / "ja"
    if is_online():
        desc = gemini_describe(labels)
        if desc:
            print(f"[Layer 2] Gemini：{desc}")
            speak_edge(desc, lang=lang)
            return
    # 離線或 Gemini 失敗 → Layer 3
    desc = ollama_describe(labels, lang=lang)
    if desc:
        print(f"[Layer 3] Gemma 3: {desc}")
        # 離線不能用 edge-tts，改用本地 say
        speak_local(desc)
```

### 啟動時 warm up

```python
def __init__(self):
    # ... 現有 YOLO / DepthAnything warm up ...

    print("Warm up Ollama Gemma 3...")
    try:
        import ollama
        ollama.generate(model="gemma3:4b", prompt="OK", options={"num_predict": 1})
        self._ollama_ready = True
    except Exception as e:
        print(f"Ollama warm up 失敗（離線 fallback 不可用）: {e}")
        self._ollama_ready = False
```

---

## Demo 缺件盤點（不只 Layer 3）

以下是 demo 前必須補的項目，會在 `/plan-eng-review` 中逐一審查：

### 🔴 Blocker（沒做 demo 跑不動）
1. **攝影機即時流** — 目前 `process_frame` 吃圖片路徑，demo 需要 `cv2.VideoCapture(0)` loop
2. **ALERT_COOLDOWN_SEC = 3.0** 太長，緊急物體（車）需要 bypass
3. **`speak_edge` 離線失敗** — edge-tts 本身需網路，Layer 3 離線場景會 crash，需用 `say` 替代

### 🟡 High priority
4. **`check_network` 只測 google.com** — 中國網路誤判
5. **冷啟動** — Ollama / DepthAnything 首次推論 5-10s，demo 前必須 warm up
6. **多語言切換** — 目前 `LANGUAGE` 寫死在頂層變數，需 runtime 切換

### 🟢 Nice to have
7. **Layer 3 輸出快取** — 同一組 labels 一分鐘內不重算
8. **YOLO CoreML 加速** — `yolo26s.pt` → `yolo26s.mlpackage`
9. **降噪** — 同時多個物體只講最近的（目前已做，但沒過濾靜態物如 table/chair）

---

## Performance Targets

| 階段 | 目標延遲 | 實測（需測） |
|------|---------|-------------|
| YOLO 偵測（單幀） | < 50ms | ? (M-series) |
| DepthAnything 估算 | < 200ms | ? |
| Layer 1 say 播報 | < 300ms | ✅ 目前 OK |
| Layer 3 Ollama 首 token | < 1s | ? (需 warm up) |
| Layer 3 完整描述（15字） | < 3s | ? |
| Online → Offline 切換 | < 1s（感知無縫） | ? |

---

## NOT in Scope（明確排除）

- ❌ **User research / 視障者訪談**（延後 demo 後做，但是 known blocker）
- ❌ **手機 / 胸前硬體 port**（demo 只在 Mac 上）
- ❌ **haptic 回饋**（Biped 有，我們不做）
- ❌ **室內 SLAM / 地圖導航**（不同產品方向）
- ❌ **人臉辨識 / OCR**（不同用例，OrCam 做這個）
- ❌ **distribution agreement 討論**（需求驗證前不簽）

---

## Open Questions（需 plan-eng-review 釐清）

1. Camera loop 的 frame rate？每幀都跑 YOLO + DepthAnything + Ollama，M1 可能撐不住
2. 多語言切換 UX — 按鍵？語音指令？配置檔？
3. Ollama 服務沒跑時的 fallback strategy
4. Demo 現場的錄製 / 展示方式（真實走路？預錄影片？）
5. 投資人 demo 的敘事結構 — 3 分鐘 pitch 的 storyline？

---

## Completion Summary

- Phase 1 Context: ✅
- Phase 2A (Startup mode Q1/Q2/Q3): ⚠️ Q1 答案是「沒驗證」— 接受風險繼續
- Phase 2.75 Landscape: ✅（7 產品 + 學術）
- Phase 3 Premise Challenge: ✅（差異化定位確認「離線 = 成本/延遲」）
- Phase 3.5 Second Opinion: 跳過（時程壓力）
- Phase 4 Alternatives: ✅（A/B/C，推薦 A）
- Design doc: ✅（本文件）

**下一步：** 回到 `/plan-eng-review`，針對 Approach A 做技術審查（架構、代碼品質、測試、效能 4 section）。
