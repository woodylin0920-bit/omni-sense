# AI Agent 協作開發流程：從人工 Router 到 A2A

**這份文件的目的**：整理我在 omni-sense 專案中實際使用的 AI agent 協作模式，以及我對「邊做專案邊把流程升級成 A2A (Agent-to-Agent)」的看法。寫給自己也寫給 CTO/工程夥伴，避免重新發明輪子。

---

## TL;DR

1. 我今天的開發流程**已經是一個非正式 agent harness**，只是 router 是我自己
2. 從「人工 router」進化到「A2A 自主協作」有明確 5 個 level，**不要跳級**
3. Agent 可以加速「做正確的事」，但不能代替你判斷「做的是不是對的事」（用戶訪談 / taste / domain 判斷這些永遠人自己做）
4. 實作上最大的風險是 **token cost 指數成長** 和 **chain 越長 debug 越難**

---

## 今天的實戰證據（omni-sense 專案 Debug）

今天花了一個 session 從「pipeline 卡住無法跑」debug 到「Phase 0 SLO 達標」。用到的 agent 和角色：

| Agent | 角色 | 今天做的事 |
|---|---|---|
| 人（我） | Orchestrator | 決定用哪個 agent、什麼時機、approve 動作 |
| Claude Opus 4.7 | Primary worker | 讀 log、寫程式、寫文件、做假設 |
| Codex CLI (gpt-5.1-codex) | Reviewer / 二意見 | 挑戰我的診斷「是相關，不是因果」，逼我做乾淨 A/B test |
| Claude Sub-agent (Explore) | Parallel surveyor | 並行 audit repo 整體狀態（git + tests + docs + gaps） |
| Persistent memory | Shared state | 跨 session 存 user role、feedback、project state |

**關鍵時刻**：我原本以為 pipeline 卡住是 swap thrashing，搬記憶體後沒解。我寫了一份診斷文丟 Codex 審，它回「你的證據是 strong correlation 不是 causal test」，要求我跑乾淨的 A/B benchmark。那個挑戰直接讓我找到真因（iCloud `fileproviderd`）。**兩個模型不同意彼此 > 一個模型自我確認**。

這整個流程完成後最終產出：

- `c49d481` 提交 Phase 0 程式碼
- `33fa3c4` 搬 venv 出 iCloud + 驗證 SLO
- `4309a7e` docs + README warning
- 公開 gist 分享 debug 過程：https://gist.github.com/woodylin0920-bit/0bf6b8fba2f85ceb9e9d1a606b7b4284
- Phase 0 實測：Layer 3 Ollama warm 968ms、stale drop 0%、import torch 1200x 加速

---

## Harness 對照表：我有什麼、正式框架是什麼

| Harness 元件 | 今天的實例 | 正式框架對應 |
|---|---|---|
| Orchestrator | 人（我） | LangGraph supervisor / CrewAI manager / Anthropic Agent SDK |
| Worker agent | Claude Opus 4.7 | LLM node with tool-use |
| Reviewer agent | Codex CLI | Critic node |
| Explorer agent | Claude sub-agent (Task tool) | Retrieval / research node |
| Memory | `~/.claude-work/memory/*.md` | Vector store / state graph |
| Skills | gstack, codex skills | Prompt templates / pre-registered tools |
| Shared state | Git repo + RESUME.md | Blackboard |
| Hooks | Claude Code hooks (SessionStart, post-commit) | Event triggers |

**差距 = 我現在是人工 router**。A2A 的終點是 router 本身也是 agent，看 task 自己決定叫誰。

---

## 5-Level 進化路徑（邊做專案邊升）

不要跳級。每升一級才有資格上下一級。

### L1 — 模式記錄
**做什麼**：每次完成 task 後問自己「剛才這流程是不是 pattern？」。寫進 memory 或 `/docs/patterns/`。

**成熟訊號**：memory 累積 20+ 條 feedback / workflow / reference 條目，新 session 開場能靠 memory 跑起來不用從頭解釋專案。

**今天狀態**：✅ 已經有。memory 有 user_role / project_state / feedback_style / feedback_model_collab 等條目。

---

### L2 — Pattern 打包成 Skill
**做什麼**：重複 3 次以上的流程 → 寫成可叫用的 skill / 腳本。Claude Code 的 `.claude/skills/` 或純 bash 都行。

**範例**：「寫 + Codex review + commit」三步驟 → `/ship` skill 自動執行：
1. 把 diff 丟 Codex review
2. Codex 如果 OK，執行 `git add + commit + push`
3. Codex 如果有意見，回傳 diff 給人看

**成熟訊號**：每週至少用一次自製 skill，不靠 gstack / 官方 skill。

**今天狀態**：⚠️ 用了 gstack / codex 官方 skill，還沒自製過。

---

### L3 — Chain 自動化（移除中間 human checkpoint）
**做什麼**：固定 A→B→C 流程不需要人審中間環節。

**範例**：
- `pytest` 綠 → 自動 commit 並 push（紅就停，等人介入）
- PR 開出 → 自動叫 Codex review → review 回 OK → 自動 merge

**前提條件**：
- 所有 step 都有**乾淨的成敗訊號**（test pass/fail、lint clean/dirty）
- 每個 step 有 rollback 機制
- Logging 完整，事後能追是哪一步 agent 做錯

**成熟訊號**：每天有 10+ 次 commit 是「自動化送出」，人只審異常。

**今天狀態**：❌ 每步都要我點頭。

---

### L4 — Router agent
**做什麼**：一個 meta-agent 看 task description 自己選模型 + 呼叫對應 agent。

**範例**：
```
User: "幫我 debug 這個 import 很慢的問題"
Router: 
  → 診斷類任務 → 叫 Opus
  → Opus 說 "我懷疑是 X" → 叫 Codex 挑戰
  → Codex 要證據 → 叫 Sub-agent 跑 benchmark
  → 蒐齊後給人最後決定
```

**前提條件**：L3 已穩定跑 3+ 個月，累積夠多 pattern 供 router 學習判斷。

**技術**：可用 Anthropic Agent SDK、LangGraph 或自己寫 (幾百行 Python + 模型呼叫)

**今天狀態**：❌ 尚未。

---

### L5 — A2A 雙向
**做什麼**：agent 之間主動互動，不只是 router 單向派發。

**範例**：
- Worker 寫 code 遇到不確定 → 主動發訊問 Reviewer
- Reviewer 看到架構問題 → 主動開 issue 給 Planner
- Explorer 找到新資訊 → 主動更新 Memory

**技術**：需要 shared bus（Redis / Postgres / 純檔案系統都可）+ 每個 agent 有自己的 inbox

**今天狀態**：❌ 尚未。通常 L5 是公司級別 infra，不是個人專案。

---

## 問題定義 → 產出產品：Agent 介入點

```
定義問題
  ├─ 用戶訪談 / 痛點收集  ←  Explorer agent 整理原始資料（逐字稿 → 痛點 tag）
  └─ 競品 / 既有方案掃描  ←  Explorer agent 爬 web + GitHub + Linear
      ↓
探索 & PoC
  ├─ 技術可行性驗證       ←  Worker (Opus) — 最貴階段，人要深度參與，不要省 token
  └─ Constraint 找出      ←  Reviewer (Codex) 挑戰假設（「你確定這是真因嗎？」）
      ↓
規劃
  ├─ 架構設計             ←  Opus + Codex 辯論 2-3 輪
  └─ 風險排序             ←  Opus
      ↓
實作
  ├─ 寫程式碼              ←  Worker (Sonnet 或 Haiku 省錢) — 可大量平行
  └─ Auto-test / hook     ←  CI / Claude Code hooks 自動觸發
      ↓
驗證
  ├─ Benchmark / SLO 測  ←  Worker (Haiku) + 人看結果
  └─ Code review          ←  Reviewer (Codex) — iron rule: code-writer 不 review 自己
      ↓
上線
  ├─ Commit / push        ←  Worker + hook
  └─ 用戶 feedback loop   ←  Explorer 聽 Slack / 訪談逐字稿
      ↓
迭代（回到「定義問題」）
```

**每個箭頭都是一個「要不要 agent 化？」的決策點**。我今天走的是：規劃 → 實作 → 驗證 → 上線 → 分享（gist）一整圈。用戶訪談那步還是空的 — 這是目前最大的 gap，agent 幫不了（只有我能下場）。

---

## 這套流程的限制（誠實說）

1. **Agent 不會 push back 投資人想錯方向**
   L5 A2A 可以優化「做正確的事」的速度，但無法代替你判斷「做的是不是對的事」。用戶訪談這步永遠人下場。

2. **Chain 越長，錯誤越難 debug**
   L3 之後一個壞 commit 可能是 3 個 agent 傳下來的。一定要加 logging + 可 checkpoint。

3. **Token cost 指數成長**
   L4 router 一次 decision 可能呼叫 3-5 個 agent 辯論，每個專案一天 $20-$100 很常見。Opus 4.7 特別貴。

4. **Agent 不知道 domain taste**
   「為盲人做的」這種 taste 只有你有。agent 只能執行不能原創。

5. **模型切換有 context 成本**
   每次 `/model` 切換要重新 load 對話歷史，不是免費。自動 router 切換更頻繁，要評估值不值。

6. **Heuristic 推薦不等於實測**
   今天我推薦「prompt 用 Opus 寫，review 用 Codex」是直覺，不是實測 Sonnet 比 Opus 差。新人進來要自己驗證。

---

## 新專案起手式（Starter Template）

下次新專案開 repo 第一天就做這些：

```
project/
├── CLAUDE.md                 ← 專案 context、routing rules（給 Claude Code 讀）
├── README.md                 ← 人讀
├── RESUME.md                 ← 跨 session 接續指南（「下次貼這段給 Claude」）
├── docs/
│   ├── DESIGN.md             ← 架構 + trade-off
│   ├── PITCH.md              ← 如果是要做給人看的產品
│   └── patterns/             ← 累積的 pattern（L2 進度）
├── .claude/
│   └── skills/               ← 自製 skill（L2 進度）
└── memory/                   ← 用 gstack 或 Claude auto-memory
```

**第一個 session 做的事**：
1. 寫 `CLAUDE.md` 告訴 Claude 這是什麼專案、routing rules
2. 跟 Claude 做 `/office-hours`（假設你用 gstack） → 產出 design doc
3. `/plan-eng-review` → 產出實作計劃
4. 實作 → test → ship

**第二個 session 做的事**：
- 貼 RESUME.md 給 Claude → 續做
- 每完成一個 pattern 就記進 memory

**第五個 session 之後**：
- 看 memory 有沒有重複 3 次以上的流程 → 可以進 L2 了

---

## 結論

今天在 omni-sense 跑的流程證明：**L1 + L2 的手動協作 + Codex 當二意見 review，就足以做出投資人級別 demo（13 tests pass、SLO 達標、完整 debug 案例可 share）**。

L3+ 的自動化不是必要，是選擇。選擇前問自己：「我現在的 bottleneck 是不是 human router 的延遲？」。如果 bottleneck 是「不知道要做什麼」或「用戶是誰」，L3+ 自動化只會讓你更快做錯的事。

用戶訪談 → 痛點 → 產品假設 → 驗證 → 迭代。這個 loop 才是核心。Agent 是 accelerator，不是 decider.

---

**Contact / Feedback**：這份文件跟 omni-sense 一起演進，歡迎 PR / issue。
