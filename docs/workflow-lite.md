# UAply Workflow Lite v1.6 Core — install + daily use

**Core = the token savings and safety, nothing that needs Saif's setup first.** Install it tonight; add the
Full layer (area tabs, memory, backups) after launch. Expected: ~55–60% fewer Claude Code tokens vs the Oct 19 week.

## What v1.6 Core fixes (from the Oct 28 review)
| # | Fix | Why it mattered |
|---|---|---|
| 1 | Each chat keeps its own state file; every write is locked + atomic | Tabs were erasing each other → blocker misfired |
| 2 | All output forced to UTF-8 | Windows crashed on ⚠ → and hid warnings |
| 3 | Hooks run through `tools/lite/run.sh`, which picks a working python / py (skips the Microsoft Store stub) | Hooks failed when the wrong Python was found |
| 4 | Escape word is now `go!` | `!go` triggered Claude Code's shell mode |
| 5 | Reopening an old chat keeps its idle clock | Resumed chats slipped past the blocker |
| 6 | Effort cap raised to xhigh | Security/auth work couldn't use xhigh |
| 7 | Start-up network check capped at 5s, skipped offline | Slow network wiped the start card |
| 8 | `lite.env` read even with a BOM or UTF-16 | Notepad/PowerShell files broke FOUNDER |
| 9 | More ways of pushing to `dev` blocked | `git push origin sandbox:dev` slipped through |
| 10 | `PROGRESS.md`, `.lite-area` added to .gitignore | Could leak into the public repo |

## What's in the box
| File | Job |
|---|---|
| `CLAUDE.md` | Team rules: TPD dispatches, bots work, model table, token rules, ownership |
| `.claude/settings.json` | Ultracode off · workflows small · auto-compact 150k · effort medium (cap xhigh) · bots on Sonnet · max 6 bots · output caps · data files blocked · hooks |
| `.claude/skills/` | `/brief` (big prompts → ordered queue) · `/ship` (card → merge) · `/handoff` |
| `.claude/agents/` | builder · builder-deep · writer · researcher · runner · reviewer |
| `tools/lite/run.sh` | Picks a working Python on Windows or Mac |
| `tools/lite/hook_start.py` | New chat: repo, branch, commit, uncommitted files, new sandbox commits, locks, unfinished bots |
| `tools/lite/hook_prompt.py` | **Big-chat blocker** (0 tokens when it blocks) + one `[lite]` line |
| `tools/lite/statusline.py` | Bottom bar: model · effort · chat size · 5h % · locks · bots |
| `tools/lite/queue.py` | Merge lock for sandbox and live |
| `tools/lite/jobs.py` | Bot ledger (no forgotten bots) |
| `tools/lite/hook_check.py` | Runs `node check.js` after edits; silent when it passes |
| `tools/lite/trello.py` | Optional Trello updates (needs your own key/token) |
| `tools/lite/doctor.py` | Self-test — runs the real hooks the way Claude Code does |

## Install (≈20 min, Mohammed alone)
Git Bash (Windows), inside the uaply repo:
1. `git switch sandbox && git pull && git switch -c c0-workflow-lite`
2. `cp CLAUDE.md CLAUDE.old.md`
3. Copy from the zip into the repo root: `.claude  tools  CLAUDE.md  EXTRAS.md`
4. Open `.claude/settings.json` and add back the repo's existing line right after the first `{`:
   `"attribution": { "commit": "", "pr": "" },`
5. Move the real test/run commands from `CLAUDE.old.md` into a `## Commands` section at the end of `CLAUDE.md`; delete `CLAUDE.old.md`.
6. `cat <zip folder>/.gitignore.add >> .gitignore`
7. Create `~/.uaply/lite.env` (Windows: `C:\Users\rumma\.uaply\lite.env`) containing `FOUNDER=Mohammed`
   (Saif: `FOUNDER=Saif`). Optional: `TRELLO_KEY=` and `TRELLO_TOKEN=`.
8. `python tools/lite/doctor.py` until **ALL GOOD**. The "status line has run" check passes
   after you open Claude Code in the repo once.
9. Commit, push, open a PR into `sandbox`. Merge it with the lock: `python tools/lite/queue.py take sandbox "c0 lite"` → merge → `release sandbox`.
10. Saif: pull sandbox, create his own `lite.env` (`FOUNDER=Saif`), run `python tools/lite/doctor.py` on his Windows laptop.
11. Optional: paste `claude-ai/PROJECT_INSTRUCTIONS.md` into the claude.ai UAply Project.

## Daily use
- Talk normally; big multi-request prompts are fine (the TPD turns them into a QUEUE).
- Message blocked with ⛔? Your chat got big or sat idle. Type `/clear` (free) — or `/handoff` first if this chat
  knows something not yet in git/Trello — or start the message with `go!` to send anyway.
- Heavy parallel mode for one big job: put the word `ultracode` in that one prompt.
- Before merging: Claude takes the lock (`queue.py take sandbox`) and releases it after.
- Status bar shows ⚠ or something looks off → `python tools/lite/doctor.py`.
- Nov 4: `npx ccusage@latest weekly` and compare with the Oct 19 week ($1,687).

## Not in Core (comes in v1.6 Full, after launch + Saif's card #38)
Area tabs + "continue" memory · autosave/backups to the private uaply-brain · Trello auto-sync Action · daily status post.
