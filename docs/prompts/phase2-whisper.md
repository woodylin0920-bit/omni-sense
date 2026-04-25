你正在接手 omni-sense（視障導航 pipeline）。先讀這幾個檔案 60 秒進入狀況：

1. README.md — 架構 + 跑法
2. RESUME.md — Phase 0 + Phase 1 已完工
3. docs/CHAT_DESIGN.md — 為什麼 Phase 2 = ASR
4. docs/prompts/phase1-ocr.md — 上一輪怎麼做（風格依樣畫葫蘆）
5. omni_sense_ocr.py + test_ocr.py — module / test 風格參考
6. git log --oneline -10

讀完直接開工。

═══════════════════════════════════════════════════════════════
任務：Chat MVP — Phase 2 push-to-talk ASR
═══════════════════════════════════════════════════════════════

背景（已決策，不要再開戰場）：
- 路徑 = 路徑 B（Scene Q&A + OCR + ASR），CHAT_DESIGN.md 已鎖
- ASR 用 mlx-whisper + whisper-base MLX（~150MB），不用 tiny（中文 WER 太高）/ openai-whisper / faster-whisper
- Phase 2 只做獨立模組，不整合進 pipeline.py，不碰 chat 邏輯
- 整合進 chat 是 Phase 3

目標：
- 把 ASR 模組獨立寫好、測好、benchmark 好
- 失敗的話（M1 跑不起來 / mlx-whisper 中文 WER 太高 / sounddevice 抓不到 mic），停下來重新評估，不要硬上 Phase 3

工作風格：
- 環境：~/Desktop/repo/public/omni-sense（main branch）
- Python：~/venvs/omni-sense-venv/bin/python（在 iCloud 外，**別自己重建 venv**）
- 5 個 atomic commit，每個都能獨立 revert
- 每次 commit 前跑 ~/venvs/omni-sense-venv/bin/pytest -v 確認綠（Phase 1 完工後是 40 個）
- commit message 第一行 imperative，<72 字
- 全部跑完 → push origin main

═══════════════════════════════════════════════════════════════
COMMIT 1: 安裝依賴 + omni_sense_asr.py 模組
═══════════════════════════════════════════════════════════════

1. 安裝

   brew install portaudio
   ~/venvs/omni-sense-venv/bin/pip install sounddevice mlx-whisper

   驗證 import + mic 列舉（不錄音）：
   ~/venvs/omni-sense-venv/bin/python -c "import sounddevice as sd; import mlx_whisper; print('ok'); print(sd.query_devices(kind='input'))"
   應印 'ok' 跟系統 default mic 名稱。

2. 新增 omni_sense_asr.py（lazy load mlx_whisper / sounddevice）：
   - warmup_once() — 預熱，double-checked lock，thread-safe
   - record_fixed(duration_s) — 固定秒數錄音
   - record_until(stop_event, max_s) — push-to-talk，stop_event.set() 停錄
   - transcribe(audio_np, lang) — numpy array → text
   - transcribe_path(path, lang) — wav/mp3 路徑 → text（benchmark 用）
   常數：SAMPLE_RATE=16000, MODEL_REPO="mlx-community/whisper-base-mlx"

3. 更新 .gitignore 加 .mlx_cache/

Commit message:
feat: add mlx-whisper (base) ASR module for push-to-talk transcription

═══════════════════════════════════════════════════════════════
COMMIT 2: omni_sense_asr 單元測試
═══════════════════════════════════════════════════════════════

新增 test_asr.py，autouse fixture mock sounddevice + mlx_whisper 進 sys.modules。

5 個 tests：
- test_warmup_only_once — warmup 只載一次，第二次 noop
- test_record_until_respects_stop_event — stop_event 在 50ms 觸發，結果 << max_s
- test_record_until_caps_at_max_s — max_s=0.3s，回傳量 <= 1s
- test_transcribe_strips_whitespace — mock 回 "  [mock] hello  " → "[mock] hello"
- test_transcribe_empty_audio_returns_empty — size=0 → ""

跑：~/venvs/omni-sense-venv/bin/pytest -v（Phase 1: 40 → Phase 2: 45 全綠）

Commit message:
test: unit tests for omni_sense_asr (mock sounddevice + mlx_whisper)

═══════════════════════════════════════════════════════════════
COMMIT 3: 測試音檔 + bench_asr() benchmark
═══════════════════════════════════════════════════════════════

1. scripts/make_test_audio.sh — macOS TTS say + afconvert，產生：
   - samples/test_zh.wav（Mei-Jia：「前面那個招牌寫什麼」）
   - samples/test_en.wav（Samantha："what does the sign say"）
   跑：bash scripts/make_test_audio.sh

2. benchmark.py 加 bench_asr()：
   - cold：第一次跑 test_zh.wav
   - warm：n_warm=3 輪跑所有 wav，回報 avg ms + 轉錄文字
   - 找不到 sample wav 時印提示並 return
   - 在 if __name__ == "__main__" 的 bench_ocr() 後加 bench_asr()

3. git add samples/test_zh.wav samples/test_en.wav
   跑 ~/venvs/omni-sense-venv/bin/python -c "import benchmark; benchmark.bench_asr()"
   把實測數字記進 commit message

Commit message（填入實測）：
perf: add ASR cold/warm benchmark (mlx-whisper base ~XXXms cold, ~YYYms warm)

═══════════════════════════════════════════════════════════════
COMMIT 4: 驗證 sounddevice 可抓 mic + warmup 實跑
═══════════════════════════════════════════════════════════════

1. 跑 mic 驗證（不錄音）：
   ~/venvs/omni-sense-venv/bin/python -c "
   import sounddevice as sd
   dev = sd.query_devices(kind='input')
   print('default input:', dev['name'])
   print('channels:', dev['max_input_channels'])
   "
   確認拿到 mic 名稱（MacBook Air 內建 mic 或外接）。
   若 sounddevice 拋 PortAudioError：檢查 portaudio 是否 brew link 正確。

2. 跑 warmup 計時：
   ~/venvs/omni-sense-venv/bin/python -c "
   import time, omni_sense_asr
   t0 = time.perf_counter()
   omni_sense_asr.warmup_once()
   print(f'warmup: {(time.perf_counter()-t0)*1000:.0f}ms')
   t0 = time.perf_counter()
   omni_sense_asr.warmup_once()
   print(f'second call (noop): {(time.perf_counter()-t0)*1000:.1f}ms')
   "
   預期：第一次 1000-3000ms（model download + load），第二次 <1ms。

   若 warmup > 5s → 記錄但不阻斷；Phase 3 再評估是否影響 UX。

3. 把 mic 名稱 + warmup 數字更新到 RESUME.md Phase 2 區塊（下一個 commit 統一寫）。

Commit message:
chore: verify sounddevice mic enumeration and warmup_once() timing

═══════════════════════════════════════════════════════════════
COMMIT 5: 更新 RESUME.md + 建 phase3-chat.md handoff
═══════════════════════════════════════════════════════════════

1. 在 RESUME.md 最前面（Phase 1 區塊之前）插入：

## 🟢 2026-04-26 Chat MVP Phase 2 完工（ASR 基礎）

**完成**：
- sounddevice + mlx-whisper (base MLX) 安裝驗證
- omni_sense_asr.py — push-to-talk 錄音 + 轉錄（lazy load，warmup_once）
- test_asr.py — 5 unit tests，全部 mock，hermetic
- benchmark.py — ASR cold / warm 數字（見 commit message）
- samples/test_zh.wav + test_en.wav — TTS baseline 測試音檔

**還沒整合進 pipeline.py**。ASR 是 Phase 3 chat orchestrator 才會接進來。

**下一步**（給未來的我 / 接手的人）：
1. 看 ASR cold / warm benchmark 決定要不要繼續：
   - cold < 3s、warm < 1s、中英文都能讀 → 進 Phase 3
   - 慢 / 讀不到中文 → 評估換 whisper-small（大但準）或砍掉 ASR
2. 若繼續：貼 docs/prompts/phase3-chat.md 給 Claude Code
3. **去訪談視障者**（比 Phase 3 更重要）

**已知決策（防止下個 LLM 重新爭辯）**：
- ASR 用 mlx-whisper whisper-base-mlx（M1 native）
- push-to-talk = 空白鍵，不做 wake word
- 單 turn Q&A，無多輪記憶（Phase 3 設計）

2. 新增 docs/prompts/phase3-chat.md（Phase 3 任務描述 stub）：

# Phase 3: Chat Orchestrator（待寫）

Phase 3 目標：
- chat.py — 整合 YOLO + Depth snapshot + OCR + ASR + Gemma 3 1B → say
- 觸發：push-to-talk（空白鍵）
- 流程：record_until → transcribe → build_prompt(yolo_ctx, ocr_ctx) → ollama.chat → say

TODO: 這份 prompt 在開始 Phase 3 前由當時的 Claude Code 補完。

Commit message:
docs: refresh RESUME.md to reflect Phase 2 completion + handoff context

═══════════════════════════════════════════════════════════════
最後步驟
═══════════════════════════════════════════════════════════════

1. 確認 5 個 commit 都在 main：git log --oneline -5
2. 跑 ~/venvs/omni-sense-venv/bin/pytest -v 確認全綠（45 個）
3. push：git push origin main
4. 跑 ~/venvs/omni-sense-venv/bin/python -c "import benchmark; benchmark.bench_asr()"

回報模板：
- ✅ 5 commits SHA + 第一行
- ✅ pytest 數字（45/45）
- ✅ ASR cold / warm 實測（決定要不要進 Phase 3 的關鍵）
- ⚠️  中英文轉錄結果（WER 感覺？）
- ⚠️  install / runtime 有沒有踩雷
- 🤔 你（Claude Code）的主觀評估：ASR 品質夠 chat 用嗎？

如果 warm > 1.5s 或中文 WER 明顯高 → 不要硬上 Phase 3，停下來回報。
