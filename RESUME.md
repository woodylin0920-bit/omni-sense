# 重開 / 接續工作

下次打開 Cursor 在這個 repo，把 `## Resume Prompt` 整段貼給 Claude 即可。

---

## 🟢 2026-04-21 Phase 0 已驗證通過

**重大變更**：`venv` 已從 iCloud-synced Desktop 搬到 `~/venvs/omni-sense-venv`，專案內留 symlink（`~/Desktop/omni-sense/venv` → `~/venvs/omni-sense-venv`）。**專案路徑不變，所有既有指令繼續可用。**

**為什麼搬**：原本 `./venv/bin/python -c "import torch"` 要 23+ 分鐘。真凶是 macOS iCloud Desktop sync 讓 `fileproviderd` 攔截每個 `.pyc` 讀取。搬離後 **1.15s warm**（~1200x 加速）。Codex 二次診斷確認。

**Phase 0 實測數據（samples/test_street.mp4，11 個 Layer 3 事件）**:
- Layer 3 Ollama warm: mean 968ms，範圍 712-1506ms（目標 3-8s，**遠超 SLO**）
- Frame→播報 總計 warm: mean ~1170ms
- Stale drop rate: **0/11 = 0%**（目標 <20%）
- Cold start Ollama: 2057ms

**下一個 blocker = prompt 品質不是延遲**：Layer 3 輸出 "請您提供更多上下文" / "車子會帶您到目的地" 這種 AI boilerplate。需要調 system prompt 讓 gemma3:1b 做場景描述而不是 chat。

若重開機後 `import torch` 仍慢：檢查 `readlink ~/Desktop/omni-sense/venv` 應指向 `~/venvs/omni-sense-venv`。若 symlink 壞掉：
```bash
rm ~/Desktop/omni-sense/venv
ln -s ~/venvs/omni-sense-venv ~/Desktop/omni-sense/venv
```

pipeline.py + test_pipeline.py 的 Phase 0 改動已在 commit `c49d481` 等先前 commits 內。

---

## Resume Prompt

> 我在繼續 omni-sense 這個專案（視障者離線導航 pipeline）。週末要 demo 給投資人看「技術可行性 + 速度」。
>
> **專案 context：**
> - 位置：`~/Desktop/omni-sense/`
> - GitHub：public repo @ woodylin0920-bit/omni-sense
> - 硬體：M1 MacBook Air 8GB（記憶體緊）
> - 差異化定位：全離線 = 成本 + 延遲優勢（對標 Biped.ai / Seeing AI / OrCam）
> - 投資人想要：AI 眼鏡 + 骨傳導，但先 demo Mac prototype 看技術可不可行
>
> **技術堆疊：**
> - Layer 1：YOLO26s + `say` 本地 TTS（<400ms 緊急播報）
> - Layer 2：Gemini 2.0 Flash 雲端描述（需 `GEMINI_API_KEY`）
> - Layer 3：Ollama + **Gemma 3 1B**（離線 fallback，multi-lingual zh/en/ja）
> - DepthAnything V2 Small 深度估算
> - pipeline.py 單檔，process_frame / process_stream / set_language 三個入口
>
> **已完成（見 git log）：**
> - pipeline.py：Layer 1/2/3 + camera loop + cooldown 分級 (near 0.5s / mid 1.5s / far 3s) + HIGH_PRIORITY 過濾 + runtime 語言切換 + Gemini endpoint 離線偵測 + 三個模型 warm up
> - pipeline.py（穩定性修正）：ultralytics lazy import（`import pipeline` 不觸發 torch）、絕對路徑（`Path(__file__).parent`）、bg worker 單工化（drop-if-busy 策略）、edge-tts 唯一暫存檔（`tempfile`）
> - test_pipeline.py：**12 tests，12/12 PASSED，0.33s**（含 lazy import、路徑、tempfile、bg worker 驗證）
> - benchmark.py：動態摘要（實測值），絕對路徑
> - docs/DESIGN.md + docs/PITCH.md + README.md
> - samples/：7 張街景圖片 + test_street.mp4（14 秒測試影片）
> - bounding box 視覺化：距離色（near=紅/mid=橙/far=綠）+ ★ 標記第一個播報物件
> - per-layer timing 輸出：偵測→播報 ms、Gemini ms、Ollama ms、TTS 觸發 ms
>
> **效能基準（M1 Air，warm 狀態）：**
> - YOLO26s：avg 70ms
> - DepthAnything V2 Small：avg 326ms
> - YOLO + Depth 合計：avg 549ms
> - Layer 1 say：~50ms
> - Layer 3 Ollama（gemma3:1b，warm）：avg ~1.2-5s
> - Layer 2 Gemini Flash：avg ~500ms
>
> **還沒做 / 下次繼續：**
> - [ ] 端到端攝影機測試：`python pipeline.py --source 0 --lang zh`（需 camera 權限）
> - [ ] 切飛航模式驗證 Layer 3 自動接手
> - [ ] 投資人 demo 現場排練（3 分鐘）
> - [ ] 視障者用戶訪談（post-demo，30 天內找 10 人）
>
> **已知 blocker / 風險：**
> 1. M1 8GB 記憶體緊，三個模型同時載入約 1.1GB RAM — 冷啟動慢（30-60s）、warm 後快
> 2. edge-tts 需網路 — 切離線瞬間有短暫 TTS 空窗，已有 tempfile 防並發，但 gap 仍存在
> 3. **需求驗證 = 0**：還沒訪談真實視障者，這是 post-demo 必做
>
> **現在請幫我：**
> （這邊接下去講你當下想做的事，例如「跑攝影機測試」、「做 demo 排練」等）

---

## 快速啟動指令

```bash
# 單元測試（不載入模型，~0.3s）
./venv/bin/pytest -q test_pipeline.py

# 影片測試
python -u pipeline.py --source samples/test_street.mp4 --lang zh

# 攝影機即時測試（鍵盤 1/2/3 切語言，q 結束）
python pipeline.py --source 0 --lang zh

# 離線 Layer 3 測試（先切飛航模式再跑）
python pipeline.py --source 0 --lang zh

# benchmark
./venv/bin/python benchmark.py
```

---

## Demo checklist

- [ ] Gemma 3 1B warm up 完成（`ollama list | grep gemma3`）
- [ ] camera 權限授權（Terminal / VS Code 可用攝影機）
- [ ] 飛航模式切換順暢（直接關 WiFi）
- [ ] benchmark 數字背好：YOLO ~70ms、Depth ~326ms、Layer 3 ~1-5s
- [ ] 準備 samples/test_street.mp4 作 camera 不穩時的 fallback
- [ ] GitHub public repo 可對外展示
