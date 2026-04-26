# Phase Prompts

把每個 phase 的 Claude Code prompt 存在這，未來接手者（不論是你自己 3 個月後、
另一個 Claude / Cursor / Codex）打開 repo 就知道專案的計畫線。

| Phase | 檔案 | 狀態 |
|---|---|---|
| 1 | phase1-ocr.md | ✅ 完工（見 git log）|
| 2 | phase2-whisper.md | ✅ 完工（見 git log）|
| 3 | phase3-chat.md | ⏳ 待寫 |

## Inbox handoff 流程（規劃端 ↔ 執行端）

雙 session 拆分：
- 規劃端（terminal Opus 4.7）：驗收、設計、寫 prompt
- 執行端（Cursor Sonnet）：commit / pytest / push

流程：
1. 規劃端寫好 prompt → 存到 docs/prompts/_inbox.md（gitignored）
2. 執行端開新 chat 輸入 /inbox
3. Sonnet 讀檔開工，完成後把 _inbox.md 搬到 phaseN-XXX.md

_inbox.md 永遠 gitignored — 只是 cross-session 信箱。

## 怎麼用

1. 開新 Claude Code session
2. cd 到 repo 根目錄
3. cat docs/prompts/phaseN-XXX.md | pbcopy（複製到剪貼簿）
4. 貼進 Claude Code 開工

每個 prompt 都是自包含的 — 包含環境路徑、commit 規則、驗證步驟。
