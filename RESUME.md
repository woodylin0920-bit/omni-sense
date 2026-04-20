# 重開 / 接續工作

下次打開 Cursor 在這個 repo，把 `## Resume Prompt` 整段貼給 Claude 即可。

---

## Resume Prompt

> 我在繼續 omni-sense 這個專案（視障者離線導航 pipeline）。週末要 demo 給投資人看「技術可行性 + 速度」。
>
> **專案 context：**
> - 位置：`~/Desktop/omni-sense/`
> - GitHub：private repo @ woodylin0920-bit/omni-sense
> - 硬體：M1 MacBook Air 8GB（記憶體緊）
> - 差異化定位：全離線 = 成本 + 延遲優勢（對標 Biped.ai / Seeing AI / OrCam）
> - 投資人想要：AI 眼鏡 + 骨傳導，但先 demo Mac prototype 看技術可不可行
>
> **技術堆疊：**
> - Layer 1：YOLO26s + `say` 本地 TTS（<300ms 緊急播報）
> - Layer 2：Gemini 2.0 Flash 雲端描述（需 `GEMINI_API_KEY`）
> - Layer 3：Ollama + **Gemma 3 1B**（離線 fallback，multi-lingual zh/en/ja）
> - DepthAnything V2 Small 深度估算
> - pipeline.py 單檔，process_frame / process_stream / set_language 三個入口
>
> **已完成（見 git log）：**
> - pipeline.py 重寫：Layer 3 + camera loop + cooldown 分級 (near 0.5 / mid 1.5 / far 3s) + HIGH_PRIORITY 過濾 + runtime 語言切換 + Gemini endpoint 離線偵測 + warm up 全部三個模型
> - test_pipeline.py 7 個 test（offline_fallback, near_bypass_cooldown, no_speak_edge_offline regression, cooldown_gradient, ollama_describe_happy, is_online_gemini_endpoint, set_language_runtime）
> - docs/DESIGN.md（office-hours + plan-eng-review 完整記錄）
> - README.md
>
> **還沒做：**
> - [x] ~~確認 `pytest` 裝到 venv~~ → **已裝**（pytest-9.0.3）
> - [x] ~~跑 test~~ → **7/7 PASSED** ✅
> - [x] ~~寫 benchmark.py~~ → **已建** `benchmark.py`（YOLO/Depth/Ollama/Gemini 四段延遲）
> - [ ] 確認 `ollama pull gemma3:1b` 下載完成（`ollama list` 檢查 — 仍在下載中）
> - [ ] 跑 benchmark：`./venv/bin/python benchmark.py`（需 gemma3:1b 下載完）
> - [ ] 端到端手動測試：`python pipeline.py --source 0`（camera）+ 切飛航模式驗證 Layer 3 接手
> - [ ] 投資人 demo 的敘事腳本（3 分鐘 pitch：「看這個、看這個延遲、看我切飛航、本地 LLM 接手」）
>
> **已知 blocker / 風險：**
> 1. M1 8GB 記憶體緊，Gemma 3 4B 會 swap，已降到 1B — 若 1B 描述品質不夠，可能要改 prompt 加 few-shot
> 2. edge-tts 在 Layer 2 時要網路 — 線上切離線瞬間可能卡頓
> 3. **需求驗證 = 0**：還沒訪談真實視障者，這是 post-demo 必做
>
> **現在請幫我：**
> （這邊你接下去講你當下想做的事，例如「跑 benchmark.py」、「補完端到端測試」、「修 test 跑失敗的那個」等）

---

## 背景任務追蹤

開 session 前可能這些還在 pending：

```bash
# 1. 確認 Gemma 3 1B 下載完
ollama list | grep gemma3

# 如果沒看到 gemma3:1b，重 pull
ollama pull gemma3:1b

# 2. 確認 pytest 裝到 venv
./venv/bin/python -m pytest --version || ./venv/bin/python -m pip install pytest

# 3. 確認 Ollama service 跑著
brew services list | grep ollama   # 應該 started

# 4. 確認 GEMINI_API_KEY 在環境
echo $GEMINI_API_KEY | head -c 10   # 不為空代表有
```

---

## Demo 前 checklist

- [ ] Gemma 3 1B 已 warm up（首次推論完 ~3s）
- [ ] YOLO + DepthAnything 已 warm up（已在 `__init__` 裡）
- [ ] camera 權限授權 Cursor / Terminal 用攝影機
- [ ] 飛航模式切換順暢（直接關 WiFi 測）
- [ ] benchmark 數字背好（YOLO 幾 ms、Depth 幾 ms、Layer 3 幾 s）
- [ ] 準備影片檔 fallback — 現場 camera 不穩時切到預錄影片
