# Your Python venv on macOS Desktop is ~1200x slower than it should be

**TL;DR**: If your Python virtualenv lives inside `~/Desktop` or `~/Documents` on a Mac with iCloud Drive's "Desktop & Documents Folders" enabled, every file open is mediated by `fileproviderd`. A venv has thousands of `.pyc` files. I measured `import torch` taking **23+ minutes** on an iCloud-synced path vs **1.15 seconds** after moving the venv out. Same machine, same Python, same packages.

Fix at the bottom.

## How I noticed

I was building an offline navigation pipeline for visually impaired users on an M1 MacBook Air 8GB. Three ML models — YOLO, DepthAnything V2, Ollama — all loaded on cold start. One day the pipeline just... stopped progressing past `loading YOLO26s...`. For 23+ minutes.

I blamed, in order:

1. **Swap thrashing** — there was some (22GB swap). Rebooted. No change.
2. **macOS App Nap / QoS throttling** — tried `caffeinate -i -s`, `taskpolicy -B -t 0 -p <pid>`. No effect.
3. **Corrupted venv** — partially true, had a broken `-ertifi` install from an earlier OOM. Not the main issue.
4. **Cursor + Claude Code fighting for CPU** — closed both. No change.

Then I ran a minimal test outside the project:

```bash
/usr/bin/time -lp ./venv/bin/python -c "import torch"
# real: 23m+  (yes, minutes)
# user: 4.26s
# sys:  0.70s
```

**User + sys time is ~5 seconds. Wall time is 23+ minutes.** That's not CPU. That's not swap. That's I/O blocked on something that doesn't need CPU.

## The hidden cause: `fileproviderd`

macOS's "Desktop & Documents Folders" iCloud sync turns `~/Desktop` and `~/Documents` into **iCloud-managed paths**. Every file open on them goes through a daemon called `fileproviderd` that:

- Checks if the file is materialized locally or just a placeholder
- Updates access metadata for cloud sync
- Arbitrates between local writes and cloud pulls

A Python venv has **~2000 `.pyc` files**. Importing `torch` reads hundreds of them. Each read hits `fileproviderd`. In my case, `fileproviderd` was burning 100-125% CPU for the entire 23 minutes, while the Python process sat blocked in a syscall at 0% CPU.

Evidence I pulled during the stall:

```
$ ps -o pid,%cpu,time,command -p $(pgrep fileproviderd)
  PID  %CPU      TIME COMMAND
  654 110.9  93:11.71 /System/Library/PrivateFrameworks/FileProvider.framework/Support/fileproviderd

$ ps -o pid,stat,%cpu,time -p 26722  # the stuck python process
  PID STAT  %CPU      TIME
26722 S     0.0   0:00.00
```

93 minutes of cumulative CPU just from the daemon, ~110% active draw. The Python process: 0% CPU, blocked in syscall.

## The numbers

Same machine (M1 Air 8GB, macOS 15), same Python 3.10.8, same package set (`torch 2.11`, `ultralytics 8.4`, `edge-tts 7.2`, `transformers 5.5`), same command:

| Location | `import torch; import ultralytics; import edge_tts` warm |
|---|---|
| `~/Desktop/omni-sense/venv/` (iCloud-synced) | **23+ minutes** |
| `~/venvs/omni-sense-venv/` (non-iCloud) | **1.15 seconds** |

Ratio: **~1200x**. That's not "slow" or "suboptimal". That's "unusable vs instant".

## The fix

```bash
# 1. Move your venv out of iCloud-synced paths
mkdir -p ~/venvs
mv ~/PROJECT/venv ~/venvs/PROJECT-venv

# 2. Symlink back so all existing commands keep working
ln -s ~/venvs/PROJECT-venv ~/PROJECT/venv

# 3. Tell Spotlight to leave it alone (minor contributor)
touch ~/PROJECT/.metadata_never_index
touch ~/venvs/PROJECT-venv/.metadata_never_index
```

**Gotcha**: `mv` itself may hang forever if iCloud decides to "rearrange" the files before releasing them. I had a `mv` block for 4+ minutes with **zero files moved**, fileproviderd at 100% CPU trying to materialize 624MB of `.pyc` before allowing the rename. I killed it and rebuilt the venv fresh at the new location — took 2 minutes total.

```bash
# Nuclear rebuild — often faster than waiting for mv
rm -rf ~/PROJECT/venv &                              # may also be slow on iCloud, run in bg
/opt/homebrew/bin/python3.10 -m venv ~/venvs/PROJECT-venv
ln -s ~/venvs/PROJECT-venv ~/PROJECT/venv
./venv/bin/pip install -U pip setuptools wheel
./venv/bin/pip install -r requirements.txt
```

## Why this matters

Every ML dev on a new Mac hits this. The default macOS setup has "Desktop & Documents Folders" sync **on** if you signed into iCloud during setup. Most tutorials say `cd ~/Desktop && git clone && python -m venv venv`. That puts your venv in a sync-mediated path from day one.

The damage is invisible. You don't get an error. You get a slow that looks like a hang. Then you blame Python / PyTorch / M1 / your machine. I nearly did.

If you're seeing any of these on a Mac and can't explain it, **check your venv location first**:

- `import torch` takes minutes but `user` + `sys` time is under 10 seconds
- Fresh `python -m venv` inside `~/Desktop/anything` takes 30+ seconds to create
- `fileproviderd` shows >50% CPU when you're not actively using iCloud
- Pipelines that used to work get stuck loading the first model

Check with:

```bash
# Is this folder iCloud-managed?
xattr -l ~/Desktop/YOUR_PROJECT | grep -i 'cloud\|fileprovider'
# Any output = yes, it's synced
```

## Debugging note

I was using Claude Code (Opus 4.7) + Codex CLI as a second opinion. Claude spent a few hours chasing swap/QoS/App Nap before proposing the iCloud hypothesis. I asked Codex to challenge the diagnosis — it called the evidence "plausible but not proven, strong correlation not causal test" and demanded a cleaner A/B test. That pushed me to run the isolated `time -lp python -c "import torch"` outside the project, which is when the 23-minute wall / 5-second CPU number became impossible to explain any other way.

Two models disagreeing productively beat one model self-confirming.

---

Project: [omni-sense](https://github.com/woodylin0920-bit/omni-sense) — offline navigation pipeline for visually impaired users, M1 Air, all-local inference.
