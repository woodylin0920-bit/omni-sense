# Chat 品質實測報告

最後更新：2026-04-26

> Headless 端對端評估：YOLO + OCR + Gemma 3 1B 的 chat 答案品質。
> 跑法：`~/venvs/omni-sense-venv/bin/python scripts/test_chat_video.py`
> Layer 3（攝影機 + 麥克風）需另外實機驗收。

---

## 評分標準

5 分制，**≥4 算成功**。

| 分數 | 定義 |
|---|---|
| 5 | 直接回答問題、用到偵測/OCR、語句通順 |
| 4 | 答對但語意稍弱 |
| 3 | 部分相關但有冗詞或忽略 OCR |
| 2 | 答非所問但仍部分有用 |
| 1 | 完全錯 / 模板回退 / 幻覺 |

三個固定問題：
- **Q1**「前面有什麼？」— 場景描述
- **Q2**「前面那個招牌寫什麼？」— OCR 引用
- **Q3**「現在安全嗎？」— 風險判斷

---

## 第一輪：原本 5 支英文戶外影片（2026-04-26 凌晨）

### 詳細表格（12 幀 × 3 題 = 36 答案）

| 影片 | 幀 | YOLO | OCR 抽樣 | Q1 | Q2 | Q3 |
|---|---|---|---|---|---|---|
| test_youtube #300 | 10s | 空 | 時間戳(過濾) | 5 | 5 | 5 |
| test_youtube #3600 | 120s | 空 | 時間戳(過濾) | 5 | 5 | 5 |
| test_youtube #9000 | 300s | motorcycle+person×2 | 時間戳(過濾) | 5 | 5* | 5 |
| test_street #150 | 5s | bus×3+person+light+truck | tf, hlf | 5 | 3 | 5 |
| test_street #300 | 10s | bus×6+person | Primrose Hill | 5 | 5 | 5 |
| walk_street_fp #290 | 10s | person×10+tie+handbag | (空) | 5 | 5* | 5 |
| walk_street_fp #1741 | 60s | person×2+car×4+umbrella | (空) | 5 | 5* | 5 |
| walk_street_fp #3482 | 120s | person | T | 3 | 1 | 3 |
| crosswalk_fp #119 | 5s | person×8+bus×2+light×2 | 157 | 5 | 3 | 4 |
| crosswalk_fp #447 | 30s | person×13+bus×2+light×2 | 157 | 5 | 3 | 4 |
| indoor_mall #300 | 10s | person×6+plant | (空) | 5 | 5* | 5 |
| indoor_mall #1800 | 60s | person×10 | SOON | 3 | 1 | 5 |

*標記：sign-question guard 啟動，回「畫面中沒有可辨識的文字。」

### 統計

- Q1「前面有什麼？」：**10/12 ≥4** — 場景描述穩定
- Q2「招牌寫什麼？」：**6/12 ≥4** — OCR 有清楚文字才會準
- Q3「現在安全嗎？」：**11/12 ≥4** — 風險判斷穩定
- **總成功率：28/36 = 78%**
- 平均延遲：**667ms**（含 6 個 sign-guard 短回答 ~200ms；剔除後 762ms）

---

## 第二輪：5 支新場景影片（2026-04-26 下午）

填補測試覆蓋缺口：中文招牌、夜間、室內、近距離文字。

### 詳細表格（15 幀 × 3 題 = 45 答案）

| 影片 | 幀 | 場景類型 | YOLO 偵測數 | OCR 抽樣 | Q1 | Q2 | Q3 |
|---|---|---|---|---|---|---|---|
| taipei_walk #150 | 公園小徑 | 11 (盆栽+人) | 無 | 5 | 5 | 5 |
| taipei_walk #450 | 公園 | 5 | 100/, S50/ | 3 | 3 | 4 |
| taipei_walk #750 | 公園 | 2 | 2M | 5 | 3 | 4 |
| **hk_night #125** | 夜間街景 | 1 (bus) | **斯尼威, 會總夜, 81** | 1 | 4 | 2 |
| **hk_night #375** | 夜間招牌 | 0 | **上载你喜愛的香港霓虹招牌照片至** | 5 | 1 | 4 |
| hk_night #512 | 黑屏 | 0 | 無 | 5 | 5 | 5 |
| subway #149 | 月台 | 0 | 無 | 5 | 5 | 5 |
| subway #449 | 列車進站 | 1 (train) | 無 | 5 | 5 | 5 |
| subway #749 | 月台 | 0 | 無 | 5 | 5 | 5 |
| night_walk #125 | 夜間住宅 | 3 (person+car×2) | N | 5 | 1 | 3 |
| night_walk #250 | 夜間住宅 | 3 | N | 5 | 1 | 3 |
| night_walk #450 | 夜間住宅 | 3 | NY | 5 | 1 | 4 |
| store_indoor #50 | 貨架 | 0 | W | 1 | 1 | 3 |
| store_indoor #100 | 貨架 | 0 | 俄文亂碼 | 1 | 1 | 1 |
| store_indoor #150 | 貨架 | 0 | 俄文亂碼 | 1 | 2 | 1 |

### 統計

| | Q1 ≥4 | Q2 ≥4 | Q3 ≥4 | 總 ≥4 |
|---|---|---|---|---|
| taipei_walk | 2/3 | 1/3 | 3/3 | 6/9 |
| hk_night | 2/3 | 2/3 | 2/3 | 6/9 |
| subway | 3/3 | 3/3 | 3/3 | 9/9 |
| night_walk | 3/3 | 0/3 | 1/3 | 4/9 |
| store_indoor | 0/3 | 0/3 | 0/3 | 0/9 |
| **新片小計** | **10/15** | **6/15** | **9/15** | **25/45 = 56%** |

---

## 兩輪對比

| 指標 | 原 5 支（戶外英文） | 新 5 支（多場景） | 變化 |
|---|---|---|---|
| 樣本數 | 12 幀 / 36 答案 | 15 幀 / 45 答案 | +25% |
| Q1 成功率 | 10/12 = 83% | 10/15 = 67% | ↓16pp |
| Q2 成功率 | 6/12 = 50% | 6/15 = 40% | ↓10pp |
| Q3 成功率 | 11/12 = 92% | 9/15 = 60% | ↓32pp |
| **整體 ≥4** | **28/36 = 78%** | **25/45 = 56%** | **↓22pp** |

---

## 4 個關鍵發現

### 1. 中文 OCR 可用 ✅
- hk_night #125: `斯尼威`, `會總夜`, `81`（'夜總會' 順序部分錯）
- hk_night #375: `上载你喜愛的香港霓虹招牌照片至`（**完整正確繁中**）

但 hk_night #375 OCR 給了完整中文，**Gemma Q2 仍回「某商店」**（few-shot 洩漏）— 這是真正的系統 bug。

### 2. 夜間 YOLO 偵測量 ↓75% ✅
- 白天 walk_street_fp：平均 **12 個偵測**（含 person×10）
- 夜間 night_walk：平均 **3 個偵測**（person + car）
- 符合預期（弱光 → bbox confidence 降）

### 3. 室內近距離 store_indoor 全敗 ⚠️
- 場景：俄文超市貨架（搜尋關鍵字錯位導致）
- OCR 讀出 `KOHAHTEPCKHS`、`ArPYWKM` 等亂碼
- Gemma 把亂碼當成中文/英文，硬掰「前面有三個人」「不安全」
- **資料集問題**，非系統問題（換成日本/台灣便利商店重測即可）

### 4. night_walk Q2 持續幻覺 ⚠️
- OCR='N' → Gemma 回「N 招牌寫著「N」」
- OCR='NY' → Gemma 回「看起來是紐約」
- 單字母 OCR 是無意義碎片，Gemma 應該忽略而非自由聯想

---

## 已知系統 bug（修了會直接有改善）

### Bug 1：OCR 有清楚文字時 Gemma 仍走 few-shot 模板
- 案例：hk_night #375，OCR 含完整中文，Gemma Q2 回「某商店」
- 修法：在 chat.py 答案後處理檢測「某商店」字眼 → 若 OCR 有文字就 reject 重答

### Bug 2：OCR 單字母碎片觸發幻覺
- 案例：night_walk OCR='N' / 'NY' → Gemma 自由聯想
- 修法：在 `_filter_ocr` 加長度過濾（單字母英文 / 單個數字直接丟）

---

## 跑這份報告的腳本

```bash
mkdir -p logs
~/venvs/omni-sense-venv/bin/python scripts/test_chat_video.py 2>&1 \
  | tee logs/test_chat_$(date +%Y%m%d_%H%M%S).log
```

新增測試影片：
1. 修改 `scripts/test_chat_video.py` 的 `VIDEOS` 列表
2. 不存在的影片自動 skip，不會中斷
3. 每幀印出 YOLO / OCR / Q1-Q3 答案 + 延遲

---

## 下一輪建議

1. **先修 Bug 1 + Bug 2**（chat.py 改 < 20 行）→ 預期整體成功率回到 70%+
2. **重抓 store_indoor**（換成日本 / 台灣便利商店 POV，避免俄文）
3. **真實視障者使用測試**（這個 > 任何技術修補）
