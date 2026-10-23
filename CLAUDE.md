# UAply: read this first

UAply is a job-swiping app (swipe right = start an application). Founders: Mohammed Hussain and Saif Siddiquee. Repo: saifsiddiqueep-sketch/uaply.

## Start of every chat
1. One task per chat. The task is a numbered card on the UAply Team Board (https://trello.com/b/TUiuK5fz). Read that card first.
2. Read `HANDOFF.md` on the `sandbox` branch for the current state of every instance.
3. How the system works: the handbook in `docs/handbook/` (start with `docs/handbook/index.md`). The same pages are in the Confluence space "UAply Engineering Handbook" (https://uaplytechnologies.atlassian.net/wiki/spaces/UENG).
4. If something is missing, ask one question, then record the answer (memory or the card) so the next chat has it.

## End of every chat ("write the handoff")
Update the Trello card (what changed, links, what is next), move it, and leave a one-line starter for the next chat: `Task: card NNN, <title>. Read the card first. Done when <outcome>.`

## Who owns what
- Saif: server side (`serve.py`, `auth_api.py`, `google_auth.py`, `*_api.py`), job feeds, hosting (Render, Cloudflare), email sending, the app frame, anything with keys or money.
- Mohammed: card UI and front end (`shared/uaply-*.js`), mobile (`mobile/`, `codemagic.yaml`), docs.
- Do not edit the other founder's area without asking. Check the heads-up lists "Mohammed is working on" / "Saif is working on" before touching a branch; they are a heads-up only, never a lock.

## Branches
work branch -> PR into `sandbox` -> review -> founder OK -> merge -> preview at https://uaply-sandbox-preview.onrender.com -> PR `sandbox` into `dev`. **`dev` is the live site** (Render auto-deploys it). `main` changes only when the owner decides. Never push straight to `dev` or `main`.

## Rules that are never skipped
- Show every change as plain bullets and get a founder's OK before any commit lands on `sandbox` or `dev`.
- Every PR has plain-English notes: what changed, why, where, how it was checked.
- No Claude or Anthropic attribution anywhere (no co-author trailer, no "generated with" footer). Credit the founder who asked.
- Nothing outward-facing without a founder's yes: emails, posts, merges to live, money, deleting data. Emails go draft -> test to the founder -> OK -> send.
- Never put a secret value in code, docs, chat or Trello. Name the setting instead.
- UI copy never promises what the code cannot do. Spell it "UAply".

## Proof, not claims
Before any push: `node check.js` and `python tools/audit-files.py`. Before review: `bash tools/run-all-tests.sh` (ends `ALL TESTS PASSED`). Show the command and its output. Two failed fix attempts = stop and report.

## Working cheaply
- Text checks, not screenshots. Trello and Confluence: in-page API calls from their own tab. Gmail emails: Gmail's own compose window (the Gmail connector strips button styling and rewrites links).
- Bots only for noisy or parallel work; one fresh reviewer per change; cheap models for test runs and log reading.
- Check sign-ins (Trello, Gmail, Atlassian, Render) at the start of a task, not halfway through.
- Long dictated requests: restate them as a numbered list, do the reversible items, ask once for the outward ones.
