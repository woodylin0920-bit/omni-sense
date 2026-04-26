# Phase 4a — woody-harness adoption scaffolding (legal + entry layer)

## Context (read before starting)
- Repo: `/Users/woody/Desktop/repo/public/woody-harness/` (NOT omni-sense — switch cwd)
- State: Phase 1+2 shipped, 5 commits on main, public at https://github.com/woodylin0920-bit/woody-harness
- Phase 3 skipped per planner decision; Phase 4 = "make this fork-friendly + adoptable"
- Phase 4 is split into 4a (this prompt) → 4b (onboarding docs) → 4c (example project). DO NOT do 4b/4c here.

## Working directory
**ALL commands below run from `/Users/woody/Desktop/repo/public/woody-harness/`.**
First action: `cd /Users/woody/Desktop/repo/public/woody-harness/ && git status` — must be clean before starting. If not clean, STOP and report.

## Commit convention (from existing log — match exactly)
- Subject only, no body unless meaningful, no Claude/co-author trailer.
- Format: `<type>: <imperative summary>` — types used so far: `feat`, `fix`, `docs`, `chore`.
- Reference commit example: `feat: Phase 2 — codex/safety audit + smoke + phase-gate templates`

## Deliverables — 7 atomic commits, in order

### Commit 1 — `LICENSE` (MIT)
- Standard MIT text. Copyright line: `Copyright (c) 2026 Woody Lin`
- Path: `/LICENSE` (repo root)
- Commit: `chore: add MIT LICENSE for fork legal basis`

### Commit 2 — `CHANGELOG.md`
- Path: `/CHANGELOG.md` (repo root)
- Use Keep-a-Changelog format (https://keepachangelog.com/en/1.1.0/)
- Run `git log --oneline --reverse` first to get accurate commit list
- Two release sections:
  - `## [0.2.0] - 2026-04-27` — Phase 2 entries (codex audit prompt, safety audit prompt, ISSUES batch template, smoke.sh, phase-gate command, codex-audit command, FUTURE.md scaling/CLI ideas, bootstrap.sh PROJECT_NAME fix)
  - `## [0.1.0] - 2026-04-27` — Phase 1 entries (bootstrap.sh, /inbox slash command, CLAUDE.md template, RESUME.md template, memory templates, WORKFLOW.md, README.md)
- Each section: `### Added` (and `### Fixed` where applicable) with concise bullets
- Top of file: `# Changelog` heading + Keep-a-Changelog reference line
- Commit: `docs: add CHANGELOG tracking 0.1.0 + 0.2.0 releases`

### Commit 3 — `.github/ISSUE_TEMPLATE/bug.md`
- Create `.github/ISSUE_TEMPLATE/` directory (verify it doesn't exist first)
- YAML front-matter:
  ```yaml
  ---
  name: Bug report
  about: Report a problem with woody-harness templates, bootstrap, or commands
  labels: bug
  ---
  ```
- Body sections (markdown headings): **Reproduction steps**, **Expected behavior**, **Actual behavior**, **Environment** (with bullets for OS+version, bash version, claude version, woody-harness commit SHA)
- Commit: `chore: add bug report issue template`

### Commit 4 — `.github/ISSUE_TEMPLATE/feature.md`
- Front-matter: name `Feature request`, about `Suggest a workflow improvement`, labels `enhancement`
- Body sections: **Problem this solves**, **Proposed solution**, **Alternatives considered**, **Phase fit** (which roadmap phase / or "FUTURE.md")
- Commit: `chore: add feature request issue template`

### Commit 5 — `.github/ISSUE_TEMPLATE/config.yml`
```yaml
blank_issues_enabled: false
contact_links:
  - name: Workflow questions
    url: https://github.com/woodylin0920-bit/woody-harness/blob/main/docs/WORKFLOW.md
    about: Read the plan/execute split workflow first
  - name: Roadmap & deferred ideas
    url: https://github.com/woodylin0920-bit/woody-harness/blob/main/docs/FUTURE.md
    about: Check whether your idea is already on the roadmap
```
- Commit: `chore: route issues through templates only`

### Commit 6 — README.md rewrite (additive, don't delete existing content)
Read `/README.md` first. Then:
- **Add badges row** under H1 title (one line): `![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)` + `![Bash + Markdown](https://img.shields.io/badge/stack-bash%20%2B%20markdown-blue)` + `![Zero deps](https://img.shields.io/badge/deps-zero-brightgreen)`
- **Update Roadmap section**: mark Phase 2 `[x]`, mark Phase 3 as `~~Phase 3: CI / hooks / push notifications~~ (deferred — see FUTURE.md)`, leave Phase 4 unchecked
- **Add "Why woody-harness?" section** between "What you get" and "Quick start" — 3 short bullets:
  - vs. raw Claude Code: gives you the prompt-handoff + memory + phase-gate scaffolding instead of starting blank every session
  - vs. taskmaster / agent frameworks: pure bash + markdown, zero deps, one-command bootstrap, fork-friendly
  - vs. writing your own: extracted from a real shipped project (omni-sense), not a theoretical framework
- **Keep all existing sections** (What you get, Quick start, Lineage, License) — only modify Roadmap as above
- Commit: `docs: README badges, roadmap update, "why woody-harness" section`

### Commit 7 — woody-harness's own `docs/prompts/_inbox.md`
- Currently woody-harness uses omni-sense's inbox (cross-repo bootstrap pattern). Now self-host.
- Create `docs/prompts/_inbox.md` — single blank line file (`\n`)
- Create `docs/prompts/README.md` — short doc:
  ```markdown
  # docs/prompts/

  Cross-session mailbox for the planning Opus session ↔ executor Sonnet session.

  ## Flow
  1. Planning Opus writes prompt into `_inbox.md`
  2. Executor Sonnet runs `/inbox` slash command, picks up the latest prompt
  3. After execution, prompt is archived as `YYYY-MM-DD-<slug>.md` in this directory
  4. `_inbox.md` is reset to empty for the next handoff

  See `docs/WORKFLOW.md` for full plan/execute split details.
  ```
- Commit: `feat: woody-harness self-hosts its own _inbox.md (Phase 4a)`

## Final step — push + verify
After commit 7:
```bash
git log --oneline -10
git push origin main
git status
```
Expected: 7 new commits ahead of pre-Phase-4a head, push succeeds, working tree clean.

## Hard constraints
1. **DO NOT** add Claude/Anthropic co-author trailers (existing log has none — match the convention).
2. **DO NOT** touch `templates/`, `bootstrap.sh`, `scripts/`, or anything in `.claude/` — those are stable.
3. **DO NOT** start Phase 4b (TUTORIAL.md, HARNESS_ETHOS.md, TROUBLESHOOTING.md, CONTRIBUTING.md) or Phase 4c (examples/hello-cli/). Those are separate prompts.
4. **DO NOT** modify `README.md`'s Lineage or License paragraphs.
5. If `.github/` already exists with conflicting templates — STOP and report; don't auto-merge.
6. If `gh` push requires auth and fails — STOP at the push step and report; commits should still be local.

## After done — reply format
```
✅ Phase 4a shipped — 7 commits + push

<git log --oneline -10 output>

<git status output>

Ready for Phase 4b gate (onboarding docs: TUTORIAL.md, HARNESS_ETHOS.md, TROUBLESHOOTING.md, CONTRIBUTING.md).
```

Then stop. Don't proactively start 4b.
