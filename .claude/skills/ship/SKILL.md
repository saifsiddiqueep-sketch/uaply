---
name: ship
description: UAply delivery loop for a Trello card — branch, build, prove, review, merge through the queue, update Trello once. Use for any code change, or when the user types /ship <card#>.
---

# Ship a card (Workflow Lite)

Pick the lane first. **Risky** = touches sign-in, auth, payments, API, database, email sending, deploy,
secrets, or >5 files. Everything else is **Fast**. Unsure → Risky.

## Fast lane (most cards)
1. `python tools/lite/trello.py show <#>` — read the card (only this card). Its first line `AREA: …` says which part of the app this is.
   Before the first edit print: `AREA x · ENV sandbox · BRANCH c<#>-… · TOUCHING <files>`.
2. `git fetch -q origin && git switch -c c<#>-<slug> origin/sandbox` (works inside an area tab folder)
3. TPD writes the builder brief (card goal, files, done-when). Launch `builder` (fast lane) or `builder-deep` (risky lane).
   Tiny one-line fixes: TPD does them itself.
4. Check the builder's proof: `node check.js` + the named test, command + last lines of output. No output = not done.
   **UI GATE** (anything a user can see: pages, components, CSS, copy, icons, layout) — NEVER commit to sandbox until
   Mohammed approves. Show it in the browser preview at phone (390px) and desktop (1280px); if there's a design choice,
   show 2–3 labeled options (A/B/C) side by side; then STOP and ask 'Which option do you approve?'. Only after an explicit
   'approve A/B/C' → commit, PR, merge. Overnight/unattended bots may build UI but stop at the preview — never merge UI.
   Server-only changes are exempt.
5. TPD opens the PR into `sandbox` (`gh pr create --base sandbox --title "c<#>: ..."`).
6. `python tools/lite/queue.py take sandbox "c<#> <slug>"` → merge PR (`gh pr merge --squash`) → `queue.py release sandbox`.
   If taken: `queue.py wait sandbox "c<#> <slug>"`. Never merge without holding the lock.
7. Trello (ONE call): `trello.py update <#> --comment "<what changed, PR link, test evidence>"`, then move the card to
   "Waiting on someone" (connector, signed). Never Completed here.

## Risky lane (adds 3 things, nothing else)
- Before building: a 5-line plan (files, approach, test, rollback) → wait for the area owner's OK.
- After building: one fresh `reviewer` bot gets the diff + the plan (not your conclusions).
  Fix only what it flags as correctness/security/requirement gaps. Max 2 fix rounds, then escalate.
- Cross-area (front+back) → both founders approve in the PR.

## Live release (sandbox → dev) — Saif only
`queue.py take live "release <date>"` → PR sandbox→dev → CI green → Saif merges → verify Render shows the new SHA
→ smoke test sign-up/sign-in/apply → `queue.py release live` → move each released card to "Completed" with a signed comment.

## Roles
Need a specialist lens? Read only that section of `roles.md` in this folder. The main chat wears the hat;
only reviewer / runner / researcher run as separate bots (`.claude/agents/`).
