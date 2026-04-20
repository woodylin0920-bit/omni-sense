# omni-sense — 3 分鐘 Investor Demo 腳本

## Demo 前準備（5 分鐘）

```bash
# Terminal 1 — 確認 Ollama 起來
ollama list | grep gemma3   # 應看到 gemma3:1b

# Terminal 2 — 啟動 pipeline（先切中文）
cd ~/Desktop/omni-sense
source venv/bin/activate
export GEMINI_API_KEY="your-key"
python pipeline.py --source 0 --lang zh
```

---

## 0:00 — 開場（30 秒）

> 「全球有 2.5 億視障與弱視者。現有方案：Seeing AI 要雲端、OrCam 要 $4,000 硬體、
> Biped 要月租費。我們做的是完全不需要網路、不需要訂閱的本地 AI 導航。」

**指著螢幕：** camera 畫面 + YOLO 偵測框在跑

---

## 0:30 — Layer 1 即時播報（45 秒）

> 「這是 Layer 1：用 YOLO 偵測危險物件，用距離分級——近、中、遠——
> 近距離車輛 0.5 秒就重播，不被抑制。macOS 本地 TTS，完全離線。」

**Demo 動作：**
- 舉起手機或移動，讓 YOLO 偵測到 person / car
- 聽到「注意，前方有行人」播報
- 說：「從按下到播報，**不到 300ms**，都在本地跑。」

---

## 1:15 — Layer 2 雲端補充描述（30 秒）

> 「第一聲播完，背景馬上問 Gemini Flash 生成更豐富的場景描述。」

**Demo 動作：**
- 等 terminal 出現 `[Layer 2]` 那行描述文字
- 說：「Gemini Flash 大概 **500ms**，使用者聽到兩層：
>   先是緊急播報，再來是情境說明。」

---

## 1:45 — 切飛航，Layer 3 接手（45 秒）

> 「現在我切掉網路。」

**Demo 動作：**
1. 關掉 WiFi（System Settings → WiFi off，或打開飛航）
2. 再對著鏡頭晃動
3. 等 terminal 出現 `[Layer 3]` 那行
4. 說：「Gemma 3 1B，完全本地，M1 上跑大概 **3 到 5 秒**。
>    使用者 0 感知切換——只是 Layer 2 變 Layer 3，聲音照出。」

**Key line：**
> 「雲端是加速，不是依賴。這是競品沒有的。」

---

## 2:30 — 多語言（15 秒）

**Demo 動作：** 按鍵盤 `2`（英文）、`3`（日文）

> 「按一個鍵，語言即換，TTS 音色也換。
> 日本市場、英語市場，同一套 code。」

---

## 2:45 — 收尾（15 秒）

> 「這是 Mac prototype，驗的是技術可行性。
> 下一步：AI 眼鏡 + 骨傳導模組，讓硬體跟人一樣自然。
> 我們需要的是…（說你的 ask）」

---

## 備用 QA 問題

| 問題 | 回答 |
|------|------|
| 為什麼本地不用 OpenAI Whisper？ | 這是導航不是語音識別；我們的輸入是 camera，不是麥克風。 |
| 1B 模型夠準確嗎？ | 15 字場景描述足夠；若不夠補 few-shot prompt，不換模型。 |
| 耗電量？ | M1 Neural Engine 跑 1B 約 2W，眼鏡硬體可接受。 |
| 競品壁壘？ | 全離線架構 + 距離分級 cooldown + 多語言是一個完整系統，不是單功能。 |
| 下一輪要幹嘛？ | 10 位視障者訪談 → 找出最高優先痛點 → 硬體 MVP。 |

---

## Demo 當天 checklist

- [ ] `ollama list` 確認 gemma3:1b 在
- [ ] WiFi 環境確認（先測 Layer 2 再切離線）
- [ ] 備用：手機熱點（現場 WiFi 不穩時用）
- [ ] 備用影片：`python pipeline.py --source demo.mp4`（camera 出問題時）
- [ ] `benchmark.py` 數字背好（YOLO avg, Depth avg, Ollama avg）
- [ ] 確認 macOS 攝影機權限給 Terminal
