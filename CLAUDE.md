# UAply: read this first

UAply is a job-swiping app (a swipe right starts an application). Founders: Mohammed Hussain and Saif Siddiquee. Repo:
saifsiddiqueep-sketch/uaply. This file is the joint version (October 23, 2026): where the two founders' sides work differently, each
rule says which side it is for. Mohammed's side is his cards (card UI, front end, mobile, docs); Saif's side is everything else (below).

## Start of every chat
1. One task per chat. The task is a numbered card on the UAply Team Board (https://trello.com/b/TUiuK5fz). Read that card first.
   (Mohammed's side now; Saif's side from Pro Mode on, Monday October 26.)
2. Read `HANDOFF.md` on the `sandbox` branch for the current state of every instance.
3. How the system works: the handbook in `docs/handbook/` (start with `docs/handbook/index.md`). The same pages are in the Confluence
   space "UAply Engineering Handbook" (https://uaplytechnologies.atlassian.net/wiki/spaces/UENG).
4. If something is missing, ask one question, then record the answer (memory or the card) so the next chat has it.

## End of every chat ("write the handoff")
Update the Trello card (what changed, links, what is next), move it, and leave a one-line starter for the next chat:
`Task: card NNN, <title>. Read the card first. Done when <outcome>.` (Mohammed's side now; Saif's side from Pro Mode on.)

## Who owns what
- Saif: server side (`serve.py`, `auth_api.py`, `google_auth.py`, `*_api.py`), job feeds, hosting (Render, Cloudflare), email sending,
  the app frame, releases, anything with keys or money.
- Mohammed: card UI and front end (`shared/uaply-*.js`), mobile (`mobile/`, `codemagic.yaml`), docs.
- Do not edit the other founder's area without asking. Check the heads-up lists "Mohammed is working on" / "Saif is working on" before
  touching a branch; they are a heads-up only, never a lock.

## Branches
work branch -> PR into `sandbox` -> review -> merge (the rules below) -> preview at https://uaply-sandbox-preview.onrender.com ->
PR `sandbox` into `dev`. **`dev` is the live site** (Render deploys it). `main` changes only when the owner decides. Never push straight
to `dev` or `main`: GitHub's ruleset "Live branches: owner only" (id 25654532) requires a pull request with one approval and allows no
force-push on both; `sandbox` has no rule.

## What has to happen before a merge
- **Mohammed's cards:** show every change as plain bullets and get a founder's OK before any commit lands on `sandbox`. One fresh
  reviewer per change.
- **Saif's side:** a change merges to `sandbox` after three green review lenses: correctness, security and server, behaviour and docs
  (two reviewers for changes under 100 lines once Pro Mode is on).
- **Both sides:** `dev` and `main` need Saif's word. Anything that touches the live site, money, settings, accounts or emails that go
  out needs Saif's word.
- Every PR has plain-English notes: what changed, why, where, how it was checked.

## Rules that are never skipped
- Nothing outward-facing without a founder's yes: emails, posts, merges to live, money, deleting data. Emails go draft -> test to the
  founder -> OK -> send.
- Never put a secret value in code, docs, chat or Trello. Name the setting instead.
- UI copy never promises what the code cannot do. Spell it "UAply".
- No Claude or Anthropic attribution in commits or pull requests on either side; the repository setting in .claude/settings.json
  enforces it. Credit the founder who asked.

## Proof, not claims
Before any push: `node check.js` and `python tools/audit-files.py`. Before review: `bash tools/run-all-tests.sh` (ends
`ALL TESTS PASSED`). Show the command and its output. Stop and report after failed fix attempts: two on Mohammed's side, three on
Saif's side.

## Working cheaply
- Text checks, not screenshots. Trello and Confluence: in-page API calls from their own tab. Gmail emails: Gmail's own compose window
  (the Gmail connector strips button styling and rewrites links).
- Mohammed's side: one fresh reviewer per change; cheap models for test runs and log reading.
- Saif's side: Opus bots do the code and the tests, Fable manages. The model mix is set by Saif ("go pro" / "pro off"), not by this file.
- Check sign-ins (Trello, Gmail, Atlassian, Render) at the start of a task, not halfway through.
- Long dictated requests: restate them as a numbered list, do the reversible items, ask once for the outward ones.

## Pro Mode (Saif's side)
Off by default. Saif says "go pro" to switch it on and "pro off" to switch it off. While it is on:
- Every order carries GOAL, DONE WHEN and BUDGET.
- Sonnet runs the test suites and reads the logs.
- A fresh session per milestone, started from a written handoff.
- `HANDOFF.md` and the handbook are updated after every merge.
- Done Trello cards are cleared automatically.
- Monday: backlog review. Friday: leak review (what cost time or money for nothing).
- Two reviewers instead of three for changes under 100 lines.
