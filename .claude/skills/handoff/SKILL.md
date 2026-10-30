---
name: handoff
description: Save where an area stands so the next chat — on either founder's laptop — can continue cheaply. Use before /clear, before switching model, after a >1h break, when context passes ~150k, when the other founder will pick this area up, or when the user types /handoff.
---

# Handoff (must reach Trello — both founders read it there)

The area = this chat's title minus anything after " — " (e.g. "Job Feeds — Rumman" → Job Feeds). Never ask the user
for a card number; cards are found by name in the "📍 Areas" list on board "UAply Team Board" (trello.com/b/TUiuK5fz).

0. Before writing — leave nothing stranded on this laptop, and lose no decision:
   - **WIP.** Run `bash tools/lite/run.sh trello.py wip "<area>" <every worktree this area used>` (e.g. `. ../wt-c34`;
     default `.`). For each one it commits uncommitted changes as `WIP: <area> handoff` on that worktree's OWN branch
     and pushes it — never sandbox/dev/main, never force, no PR. It runs `tools/audit-files.py` plus key/.env/user-data
     checks first; anything suspicious is NOT committed or pushed and is named instead. Paste its two lines into the note
     as they are. Never push by hand to get round a block — fix the file or leave it local and say why.
   - **Decisions.** Run `bash tools/lite/run.sh trello.py decisions "<area>"` (with A: read the newest `AREA:` comment
     on the card yourself). Carry forward every OPEN DECISION it lists — i.e. not marked `resolved`, ✅ or `[x]` — plus
     any new ones. Mark one `✅ resolved` only when it was actually settled in this chat.
1. Write the note (under 200 words, facts only, no secrets/user data):
```
AREA: <name>   BY: <Mohammed|Saif>   DATE: <local time>
GOAL:
DONE (with evidence): commits/PRs/test output lines
NEXT: next 3 steps, in order
OPEN DECISIONS: who decides — carried + new; settled ones end "✅ resolved"
FILES THAT MATTER: paths only
LOCKS HELD: (queue.py status) — release before leaving unless mid-merge
WIP BRANCHES: <branch → last commit>                       (from step 0)
UNPUSHED WORK: none (checked) | <what's still local and why> (from step 0)
— <FOUNDER> via Claude
```
2. Post it — try A, then B:
   - **A. Trello connector.** If tools are deferred, `ToolSearch` for "trello". Use the read tools to find the
     "📍 Areas" list on board TUiuK5fz and the card whose name matches the area; add the note as a comment with the
     write-card tool; then READ the card's comments back and confirm your note is there. Only then is it posted.
   - **B. Script.** Save the note to a temp file (e.g. `.handoff-note.md`, delete after), then run
     `bash tools/lite/run.sh trello.py handoff "<chat title or area>" --file .handoff-note.md`.
     It is posted only if the output contains `POSTED ✓`. Exit 2 = area name not recognised: pick from the list it
     prints and rerun. `python tools/lite/trello.py areas` lists the cards.
2b. WORK cards touched this chat (Trello connector, each comment ends `— <FOUNDER> via Claude`):
   unfinished → "Next / queued — retain progress" + a one-line progress comment; merged to sandbox →
   "Waiting on someone" + comment with the PR #. Never move a card to Completed here.
   **NEVER move a card that is in "📍 Areas"** — the area card only gets the handoff comment, it stays in that list
   forever. Before any connector move, read the card's list; if it is "📍 Areas", skip the move. (Script path:
   `trello.py update <#> --list ...` refuses to move area cards by itself.)
2c. Bot ledger: run `bash tools/lite/run.sh jobs.py clear-mine`. It drops this chat's finished bot records (so the next
   chat isn't warned about them) and names any still RUNNING — put those under NEXT.
3. Success → tell the user: "Posted to <card> <url>. Next time in this area (either laptop): /clear, then: Read the
   latest comment on the <area> card and nothing else. Confirm the next step in one line."
4. ONLY if A and B both failed: save the note as `HANDOFF-<area>.md` in the repo root (gitignored, never commit —
   the repo is public) and tell the user, in bold:
   **⚠ HANDOFF NOT SHARED — Saif/Mohammed can't see it.** Then give the one-line reason from the tool/script
   (missing keys, token revoked, offline…) and its fix, and ask them to run `python tools/lite/doctor.py`.

Never say "posted", "shared" or "saved to Trello" without the read-back confirmation (A) or the `POSTED ✓` line (B).
