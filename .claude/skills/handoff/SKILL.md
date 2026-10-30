---
name: handoff
description: Save where an area stands so the next chat — on either founder's laptop — can continue cheaply. Use before /clear, before switching model, after a >1h break, when context passes ~150k, when the other founder will pick this area up, or when the user types /handoff.
---

# Handoff (must reach Trello — both founders read it there)

The area = this chat's title minus anything after " — " (e.g. "Job Feeds — Rumman" → Job Feeds). Never ask the user
for a card number; cards are found by name in the "📍 Areas" list on board "UAply Team Board" (trello.com/b/TUiuK5fz).

1. Write the note (under 200 words, facts only, no secrets/user data):
```
AREA: <name>   BY: <Mohammed|Saif>   DATE: <local time>
GOAL:
DONE (with evidence): commits/PRs/test output lines
NEXT: next 3 steps, in order
OPEN DECISIONS: who decides
FILES THAT MATTER: paths only
LOCKS HELD: (queue.py status) — release before leaving unless mid-merge
```
2. Post it — try A, then B:
   - **A. Trello connector.** If tools are deferred, `ToolSearch` for "trello". Use the read tools to find the
     "📍 Areas" list on board TUiuK5fz and the card whose name matches the area; add the note as a comment with the
     write-card tool; then READ the card's comments back and confirm your note is there. Only then is it posted.
   - **B. Script.** Save the note to a temp file (e.g. `.handoff-note.md`, delete after), then run
     `bash tools/lite/run.sh trello.py handoff "<chat title or area>" --file .handoff-note.md`.
     It is posted only if the output contains `POSTED ✓`. Exit 2 = area name not recognised: pick from the list it
     prints and rerun. `python tools/lite/trello.py areas` lists the cards.
3. Success → tell the user: "Posted to <card> <url>. Next time in this area (either laptop): /clear, then: Read the
   latest comment on the <area> card and nothing else. Confirm the next step in one line."
4. ONLY if A and B both failed: save the note as `HANDOFF-<area>.md` in the repo root (gitignored, never commit —
   the repo is public) and tell the user, in bold:
   **⚠ HANDOFF NOT SHARED — Saif/Mohammed can't see it.** Then give the one-line reason from the tool/script
   (missing keys, token revoked, offline…) and its fix, and ask them to run `python tools/lite/doctor.py`.

Never say "posted", "shared" or "saved to Trello" without the read-back confirmation (A) or the `POSTED ✓` line (B).
