═══════════════════════════════════════════════════════════════
PRE-FLIGHT（執行端開工前確認）
═══════════════════════════════════════════════════════════════
- 已在 Cursor / Terminal 跑 `/remote-control` + `/config` 開 push（可選）
- 在 omni-sense repo cwd？(`pwd` = ~/Desktop/repo/public/omni-sense)
- gh CLI 已登入？（`gh auth status` 應 OK）
- ⚠️ **本 prompt 跨 repo 操作**：會在 ~/Desktop/repo/public/woody-harness/ 建立**新 repo**，然後回 omni-sense archive 本 prompt
═══════════════════════════════════════════════════════════════

你正在從 omni-sense 的開發經驗抽取出 reusable framework — **woody-harness**。這是 phase 1（核心 bootstrap 層）。

═══════════════════════════════════════════════════════════════
任務：建 woody-harness Phase 1 — 核心 bootstrap + memory + inbox
═══════════════════════════════════════════════════════════════

背景（不要再開戰場）：
- woody-harness 是給 Woody 自己用的個人 dev framework，public on GitHub
- 抽取 omni-sense 過去 1 週證明有效的 patterns：plan/execute split、inbox handoff、memory 系統、phase-based commits
- 路線：bootstrap 模式（每新 project clone harness + 跑 init script）；symlink 是 Phase 3 的事
- 共 4 phases，本任務是 Phase 1（13 個檔案）：核心讓 bootstrap 跑得起來、memory 載得進來、inbox 能傳 prompt
- Phase 2 加 codex audit + safety audit + smoke test templates
- Phase 3 加 CI / hooks / push notifications
- Phase 4 加 ethos docs + 範例 project + user research framework

工作風格：
- 環境：~/Desktop/repo/public/woody-harness（**新建**，不在 omni-sense 內）
- 完成後 push 到 GitHub public repo (woodylin0920-bit/woody-harness)
- bash + markdown only，無 build dependency
- commit message 第一行 imperative，<72 字
- 完成後**回到 omni-sense**，把本份 prompt 從 docs/prompts/_inbox.md 搬到 docs/prompts/2026-04-27-woody-harness-phase1.md，清空 _inbox.md
- 全跑完 → 兩個 repo 都 push（woody-harness + omni-sense 的 archive commit）

═══════════════════════════════════════════════════════════════
COMMIT 1: 建 woody-harness repo + 13 個檔案
═══════════════════════════════════════════════════════════════

1. 建立目錄 + git init：

```bash
mkdir -p ~/Desktop/repo/public/woody-harness
cd ~/Desktop/repo/public/woody-harness
git init
mkdir -p .claude/commands templates/prompts templates/memory docs scripts
```

2. 建 13 個檔案，內容如下：

#### 2-A. README.md（harness 使用入口）

```markdown
# woody-harness

Solo developer framework for fast-shipping AI-augmented projects with Claude Code (Opus + Sonnet split).

Extracted from real-world omni-sense development (2026-04-21 → 2026-04-27): 4 ship-able phases + safety audit in 1 week.

## What you get

- **Plan / Execute session split** — Opus terminal plans + writes prompts, Sonnet executes via `/inbox` slash command
- **Inbox handoff** — `docs/prompts/_inbox.md` is the cross-session mailbox
- **Memory system** — auto-loaded preferences, workflow rules, project state
- **Phase-based atomic commits** — every change ship-ready, revertable
- **Pre-flight checks** — every executor prompt starts with environment verification

## Quick start

```bash
# Clone harness once
git clone https://github.com/woodylin0920-bit/woody-harness ~/woody-harness

# Bootstrap new project
cd ~/Desktop/repo
bash ~/woody-harness/bootstrap.sh my-new-project
cd my-new-project

# Open two Claude Code sessions:
# Terminal 1 (planning):  claude  # Opus
# Terminal 2 (executor):  claude --model sonnet  # Sonnet, /effort medium
```

## Roadmap

- [x] Phase 1: bootstrap + inbox + memory templates (this commit)
- [ ] Phase 2: codex audit + safety audit + smoke test templates
- [ ] Phase 3: CI / hooks / push notifications
- [ ] Phase 4: philosophy docs + example project + user research framework

## Lineage

Born from [omni-sense](https://github.com/woodylin0920-bit/omni-sense), a fully-offline blind-navigation pipeline shipped solo in a week.

## License

MIT (see LICENSE).
```

#### 2-B. bootstrap.sh（建新 project 的腳本）

```bash
#!/usr/bin/env bash
# woody-harness bootstrap — create new project from harness templates.
# Usage: bash bootstrap.sh <project-name>
set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: bash bootstrap.sh <project-name>"
    exit 1
fi

PROJECT_NAME="$1"
HARNESS_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(pwd)/$PROJECT_NAME"

if [ -e "$PROJECT_DIR" ]; then
    echo "ERROR: $PROJECT_DIR already exists"
    exit 1
fi

echo "[bootstrap] Creating $PROJECT_DIR..."
mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"

# Copy templates
mkdir -p .claude/commands docs/prompts
cp "$HARNESS_DIR/.claude/commands/inbox.md" .claude/commands/
cp "$HARNESS_DIR/templates/CLAUDE.md" CLAUDE.md
cp "$HARNESS_DIR/templates/RESUME.md" RESUME.md
cp "$HARNESS_DIR/templates/.gitignore" .gitignore
cp "$HARNESS_DIR/templates/prompts/_inbox.md" docs/prompts/_inbox.md
cp "$HARNESS_DIR/templates/prompts/README.md" docs/prompts/README.md

# Substitute project name placeholder
sed -i '' "s/{{PROJECT_NAME}}/$PROJECT_NAME/g" CLAUDE.md RESUME.md 2>/dev/null || true

# Setup memory directory
SLUG=$(echo "$PROJECT_DIR" | sed 's|/|-|g')
MEM_DIR="$HOME/.claude-work/projects/$SLUG/memory"
mkdir -p "$MEM_DIR"
cp "$HARNESS_DIR/templates/memory/MEMORY.md" "$MEM_DIR/MEMORY.md"
cp "$HARNESS_DIR/templates/memory/feedback_terse_zh.md" "$MEM_DIR/"
cp "$HARNESS_DIR/templates/memory/feedback_workflow_split.md" "$MEM_DIR/"
cp "$HARNESS_DIR/templates/memory/feedback_model_split.md" "$MEM_DIR/"
cp "$HARNESS_DIR/templates/memory/env_paths.md" "$MEM_DIR/"

# git init
git init -q
git add .
git commit -q -m "chore: bootstrap from woody-harness"

echo "[bootstrap] Done."
echo ""
echo "Next steps:"
echo "  cd $PROJECT_NAME"
echo "  # Terminal 1 (planning):"
echo "  claude   # Opus"
echo "  # Terminal 2 (execution):"
echo "  claude --model sonnet"
echo "  # In Sonnet session: /inbox after Opus writes a prompt"
echo ""
echo "Memory dir: $MEM_DIR"
```

讓它可執行：`chmod +x bootstrap.sh`

#### 2-C. .claude/commands/inbox.md（slash command — 跟 omni-sense 那份一樣）

```markdown
---
description: 讀 docs/prompts/_inbox.md 的 prompt 開工
---

讀取 `docs/prompts/_inbox.md` 的完整內容，把它當作這次對話的 prompt 開始執行。

執行流程：
1. cat docs/prompts/_inbox.md 看完整 prompt
2. 完全照 prompt 開工（不要二次推理 prompt 的決策，那些已由規劃端鎖定）
3. 全部 commit 完成後，把 docs/prompts/_inbox.md 的內容**搬移**到 docs/prompts/<descriptive-name>.md（檔名跟內容對齊），然後清空 _inbox.md
4. 在最後一個 commit 把搬移也納入

如果 _inbox.md 是空的或內容看起來不像 prompt，跟使用者確認。
```

#### 2-D. templates/CLAUDE.md（給新 project 用的 routing 規則）

```markdown
# {{PROJECT_NAME}}

This project uses [woody-harness](https://github.com/woodylin0920-bit/woody-harness) workflow conventions.

## Skill routing

When the user's request matches a slash command, invoke it via the Skill tool as your FIRST action:

- `/inbox` → read `docs/prompts/_inbox.md` and execute as your prompt

## Workflow

This repo uses **plan / execute session split**:

- **Planning session (terminal Opus 4.7)**: strategy, decisions, prompt authoring. Writes prompts to `docs/prompts/_inbox.md`.
- **Execution session (Sonnet via `/inbox`)**: commits, pytest, push. Reads `_inbox.md` and executes literally.

After execution, the prompt is archived to `docs/prompts/<descriptive-name>.md`.

## Memory

Persistent memory at `~/.claude-work/projects/-Users-{user}-{repo-path}/memory/`. Auto-loaded each session.

See [woody-harness docs](https://github.com/woodylin0920-bit/woody-harness/tree/main/docs) for full conventions.
```

#### 2-E. templates/RESUME.md（每個 project 的 reverse-chronological log）

```markdown
# {{PROJECT_NAME}} — RESUME

Reverse-chronological work log. Latest at the top. Each ship-able milestone gets its own block.

---

## 🟢 [DATE] [Phase / Milestone Name]

**Commits**:
- abc1234 short imperative summary
- def5678 ...

**What shipped**:
- bullet 1
- bullet 2

**Next**:
1. ...
2. ...

**Known issues / caveats**:
- ...

**Verify health (X seconds)**:
\`\`\`bash
~/venvs/{{PROJECT_NAME}}-venv/bin/pytest -v   # should be N passed
\`\`\`

---

(older milestones below)
```

#### 2-F. templates/.gitignore

```
# Python
__pycache__/
*.py[cod]
*.so
.Python
*.egg-info/
.pytest_cache/

# Virtualenv
venv
.venv
env/

# IDE
.vscode/
.idea/
.cursor/

# Claude Code local overrides
.claude/settings.local.json
.claude/scheduled_tasks.lock

# macOS
.DS_Store

# Local logs
*.log
logs/*.jsonl

# Env / secrets
.env
.env.local
*.key

# Inbox handoff (gitignored — only archived prompts go in git)
docs/prompts/_inbox.md
```

#### 2-G. templates/prompts/_inbox.md

空檔即可（`echo "" > _inbox.md`），但留一行佔位避免 zero-byte：

```
# (empty inbox — planning session writes here, executor session reads via /inbox)
```

#### 2-H. templates/prompts/README.md（inbox flow 說明）

```markdown
# docs/prompts/

Cross-session prompt mailbox + archive.

## Files

- `_inbox.md` — current prompt (gitignored, transient)
- `<descriptive-name>.md` — archived prompts (committed, self-handoff for future sessions)

## Inbox handoff flow

1. **Planning session** (terminal Opus) writes a self-contained prompt to `_inbox.md`
2. **Execution session** (Sonnet) types `/inbox`
3. Slash command reads `_inbox.md`, executes literally
4. After commits, archives `_inbox.md` content to `<descriptive-name>.md`, clears `_inbox.md`

## Why

- Eliminates copy-paste friction between two Claude sessions
- Archived prompts = self-documenting project history
- Each prompt is atomic + self-contained = future-you can re-read and understand intent
```

#### 2-I. templates/memory/MEMORY.md

```markdown
- [terse Mandarin updates](feedback_terse_zh.md) — reply in 繁中, 1-2 sentences, mid-task pings = status check not stop
- [planning-here, execute-elsewhere workflow](feedback_workflow_split.md) — this window plans + writes prompts; user pastes into Cursor/other Claude to execute. Don't run code unless asked.
- [model split: Opus plans, Sonnet executes](feedback_model_split.md) — terminal=Opus 4.7 (planning), Cursor/terminal=Sonnet (executor). Make execution prompts very explicit (Sonnet is more literal).
- [environment paths](env_paths.md) — Python venv location, hardcoded tooling paths, OS-specific gotchas
```

#### 2-J. templates/memory/feedback_terse_zh.md

```markdown
---
name: terse Mandarin updates, no progress narration
description: user prefers very short Mandarin replies and dislikes mid-task "are you done yet" prompts; mid-task pings mean "give a short status," not "stop"
type: feedback
---

User communicates in 繁體中文 and prefers terse, no-fluff replies. Mid-task they may ping with things like 「好了嗎」 — that is a status check, not an instruction to stop. Continue working but acknowledge the question with a one-line update before resuming tool calls.

**Why:** Quick communication is the user's working style. Long progress recaps slow them down.

**How to apply:** Reply in 繁體中文 by default, keep updates to 1-2 sentences, never write multi-paragraph progress summaries unless the user explicitly asks. Resume the queued work in the same turn.
```

#### 2-K. templates/memory/feedback_workflow_split.md

```markdown
---
name: planning-here, execute-elsewhere workflow
description: this conversation window is for planning + prompt-writing only; user pastes the prompts into a separate Cursor / Claude Code session that executes. Don't run code unless explicitly asked.
type: feedback
---

User uses a two-window split:
- **Planning window**: strategy, phase decisions, model/tradeoff comparisons, decision support, and writing self-contained prompts that another Claude Code can execute. Output prompts as copy-paste-ready code blocks or write directly to `docs/prompts/_inbox.md`.
- **Execution window** (Cursor / separate Claude Code): where the prompts get pasted/loaded and the actual git commits / pytest / pip installs / file edits happen.

**Why:** Separation of concerns. Planning context stays clean; executor sessions are short-lived per task. Avoids context contamination between strategy and tactics.

**How to apply:**
- Default: planning window does NOT run Bash/Edit/Write on project files. Don't run git, pytest, pip, or modify the repo. Save context budget for planning.
- Reading project files (README, RESUME.md, code) for understanding is fine and expected.
- When asked to "do X" on the project, first clarify if they want a prompt or in-window execution. Default assumption is prompt.
- Memory writes (~/.claude-work/.../memory/) are exempt — those are Claude-side, not project-side.
- When the executor reports back, planning window's job is to interpret results (numbers, errors, transcripts) and decide next step — not to re-run the work.

**Pre-flight reminder block (every prompt written to docs/prompts/_inbox.md must start with this):**

\`\`\`
═══════════════════════════════════════════════════════════════
PRE-FLIGHT（執行端開工前確認）
═══════════════════════════════════════════════════════════════
- 已在 Cursor 跑 \`/remote-control\` 並在 \`/config\` 開 push notifications？
- pytest baseline 綠？
- 在 repo cwd？(\`pwd\` 確認)
═══════════════════════════════════════════════════════════════
\`\`\`
```

#### 2-L. templates/memory/feedback_model_split.md

```markdown
---
name: model split — Opus plans, Sonnet executes
description: user pairs Opus 4.7 (planning, prompt-writing, decisions) with Sonnet (execution, commits, pytest). Tune prompts for the receiving model.
type: feedback
---

User runs two parallel Claude sessions:
- **Planning: Opus 4.7** — reasoning-heavy: phase design, model selection, tradeoffs, prompt authoring.
- **Executor: Sonnet** — receives prompts, runs git/pytest/pip, ships commits.

**Why:** Cost/quality split. Opus where reasoning matters, Sonnet where speed + structured execution matters.

**How to apply:**
- When writing prompts for the executor session, optimize for **Sonnet**:
  - Make decisions **explicit** in the prompt. Don't leave room for "use your judgment". Sonnet is more literal than Opus.
  - Inline all code blocks (don't say "write a reasonable test"; show the exact test).
  - Pre-write commit messages.
  - Pre-specify verification commands.
- Recommended `/effort` settings:
  - Planning Opus: `high` (default) — bump to `xhigh` for hard architecture decisions
  - Executor Sonnet: `medium` (or `low` for trivial tasks)
- Do not assume Sonnet has access to the planning conversation's context. Each prompt must be fully self-contained including read-list of files (README, RESUME, related modules).
```

#### 2-M. templates/memory/env_paths.md

```markdown
---
name: environment paths
description: hard-coded paths for Python env, tooling, and OS-specific gotchas
type: reference
---

Fill in for each project on first session:

- Python: `~/venvs/{{PROJECT_NAME}}-venv/bin/python`
- pytest: `~/venvs/{{PROJECT_NAME}}-venv/bin/pytest`
- Repo: `~/Desktop/repo/<public|private>/{{PROJECT_NAME}}`

**macOS iCloud trap (carried from omni-sense lesson):** Never put venv in `~/Desktop/` or `~/Documents/` if iCloud Drive sync is on. fileproviderd intercepts every `.pyc` read; `import torch` can take 20+ minutes instead of 1 second. Always venv in `~/venvs/` outside iCloud, symlink into project if needed.

**Other gotchas to record per-project**:
- macOS cv2 windowing must be on main thread (if using opencv)
- ...
```

#### 2-N. docs/WORKFLOW.md（深度說明 — 給其他人看 woody-harness 怎麼跑）

```markdown
# woody-harness Workflow

This is the day-to-day flow extracted from omni-sense (1 week, 4 phases, 6 P0 safety fixes).

## The two-session split

```
┌─────────────────────────┐         ┌──────────────────────────┐
│  Planning session       │         │  Execution session       │
│  (terminal Opus 4.7)    │         │  (terminal Sonnet)       │
│                         │         │                          │
│  - strategy, tradeoffs  │ writes  │  - reads /inbox          │
│  - prompt authoring     │ ──────► │  - commits + pytest      │
│  - codex audit results  │ _inbox  │  - pushes to remote      │
│  - decisions            │         │  - archives prompt       │
│                         │ ◄────── │                          │
│  - interprets results   │ pastes  │  - reports back          │
└─────────────────────────┘         └──────────────────────────┘
```

## Cycle per phase

1. **Plan** in Opus session: pick next phase, decide tradeoffs, get user input
2. **Write prompt**: Opus writes to `docs/prompts/_inbox.md`, structure:
   - PRE-FLIGHT block
   - "Do not re-litigate decisions" boilerplate
   - 5-6 atomic commits with inlined code + commit messages
   - Verification commands
   - Reporting template
3. **Execute** in Sonnet session: type `/inbox`, walk away
4. **Report**: Sonnet pushes commits, archives `_inbox.md` to `<descriptive-name>.md`, summarizes
5. **Interpret**: paste report back to Opus, get verdict + next step

## Why this works

- **No context bleed**: Sonnet doesn't carry planning rationale; Opus doesn't carry execution detail
- **Atomic prompts**: each `_inbox.md` is one logical unit, revertable
- **Self-documenting**: `docs/prompts/<phase-name>.md` archive shows project history
- **Cheap iteration**: Sonnet is fast + cheap; Opus only spent on hard thinking

## Rules of thumb

- Every prompt **starts with PRE-FLIGHT** check (env, baseline tests green, cwd)
- Every prompt **ends with a reporting template** (commit SHAs, test counts, smoke observations)
- Sonnet **never makes architecture decisions** — those happen in Opus session
- Pytest is **always green** before / after each commit (no "fix later" tech debt)
- Codex audit before any user-facing ship (not in Phase 1, see Phase 2)
```

3. 第一個 commit：

```bash
cd ~/Desktop/repo/public/woody-harness
git add -A
git commit -m "feat: woody-harness Phase 1 — bootstrap + inbox + memory templates"
```

4. 建 GitHub repo + push：

```bash
gh repo create woodylin0920-bit/woody-harness --public --source=. --remote=origin --description="Solo developer framework for fast-shipping AI-augmented projects with Claude Code (Opus + Sonnet split). Extracted from omni-sense."
git push -u origin main
```

如果 gh 預設不認 woodylin0920-bit owner，自動偵測即可（gh 會問）。

═══════════════════════════════════════════════════════════════
COMMIT 2 (in omni-sense): archive prompt + clear inbox
═══════════════════════════════════════════════════════════════

回到 omni-sense：

```bash
cd ~/Desktop/repo/public/omni-sense
mv docs/prompts/_inbox.md docs/prompts/2026-04-27-woody-harness-phase1.md
echo "" > docs/prompts/_inbox.md
git add docs/prompts/2026-04-27-woody-harness-phase1.md docs/prompts/_inbox.md
git commit -m "docs: archive inbox prompt — woody-harness phase 1 spawned new repo"
git push origin main
```

═══════════════════════════════════════════════════════════════
驗證
═══════════════════════════════════════════════════════════════

1. `ls ~/Desktop/repo/public/woody-harness/` — 應看到 README.md / bootstrap.sh / .claude / templates / docs / scripts
2. `cd /tmp && bash ~/Desktop/repo/public/woody-harness/bootstrap.sh test-bootstrap` — 應在 /tmp/test-bootstrap/ 建好 skeleton 並 git commit。看 stdout 列出的 memory dir，確認 ~/.claude-work/projects/-tmp-test-bootstrap/memory/ 也建好
3. `rm -rf /tmp/test-bootstrap ~/.claude-work/projects/-tmp-test-bootstrap` 清掉測試殘留
4. `gh repo view woodylin0920-bit/woody-harness --web` — 該 public repo 在 GitHub 看得到（或 print URL 即可）
5. `cd ~/Desktop/repo/public/omni-sense && git log --oneline -2` — 應看到 archive commit

═══════════════════════════════════════════════════════════════
最後步驟
═══════════════════════════════════════════════════════════════

回報模板：
- ✅ woody-harness commit SHA + repo URL
- ✅ omni-sense archive commit SHA
- ✅ bootstrap test 結果（在 /tmp 跑成功嗎？）
- ⚠️ 任何踩雷（gh repo create owner 問題、sed -i '' macOS quirk、memory dir 路徑等）
- 🤔 你（Sonnet）覺得 templates 寫得 OK 嗎？哪個檔案最不確定？是否有缺東西該補但沒列在 prompt 內？

特別注意：
- bootstrap.sh 用 `sed -i ''`（macOS BSD sed 的空字串 backup 寫法）— 別寫成 GNU `sed -i`
- gh repo create 若失敗（重名 / owner 不對），把要 push 的 git URL 印出來給 user 手動處理
- 不要為了趕進度跳過 templates 內任何欄位 — 13 個檔案就是 13 個檔案
- woody-harness 的 .gitignore 不該 ignore docs/prompts/_inbox.md（因為 harness 自己沒這檔案，是 templates/）
- 不要在 woody-harness 內建 venv / Python（純 bash + markdown framework）
