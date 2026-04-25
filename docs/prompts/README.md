# Phase Prompts

把每個 phase 的 Claude Code prompt 存在這，未來接手者（不論是你自己 3 個月後、
另一個 Claude / Cursor / Codex）打開 repo 就知道專案的計畫線。

| Phase | 檔案 | 狀態 |
|---|---|---|
| 1 | phase1-ocr.md | ✅ 完工（見 git log）|
| 2 | phase2-whisper.md | ✅ 完工（見 git log）|
| 3 | phase3-chat.md | ⏳ 待寫 |

## 怎麼用

1. 開新 Claude Code session
2. cd 到 repo 根目錄
3. cat docs/prompts/phaseN-XXX.md | pbcopy（複製到剪貼簿）
4. 貼進 Claude Code 開工

每個 prompt 都是自包含的 — 包含環境路徑、commit 規則、驗證步驟。
