---
description: 讀 docs/prompts/_inbox.md 的 prompt 開工
---

讀取 docs/prompts/_inbox.md 的完整內容，把它當成這次對話的 prompt 開始執行。

執行流程：
1. cat docs/prompts/_inbox.md 看完整 prompt
2. 完全照 prompt 開工（不要二次推理 prompt 的決策，已由規劃端鎖定）
3. 全部 commit 完成後，把 docs/prompts/_inbox.md 的內容搬移到 docs/prompts/phaseN-XXX.md（檔名跟內容對齊），然後清空 _inbox.md
4. 在最後一個 commit 把搬移也納入

如果 _inbox.md 是空的或內容看起來不像 prompt，跟使用者確認。
