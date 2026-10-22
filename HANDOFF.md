# Handoff: where UAply stands and how we work (updated October 22, 2026)

Read this first when continuing the work in a new session. It carries what the earlier sessions knew: the owner's rules, the state of
every instance, what is waiting to be released, and what only the owner can do. Launch day itself is `docs/runbook-launch.md`; the
work of each release is in `CHANGELOG.md`. The live record of tasks is the Trello board "UAply Team Board"
(https://trello.com/b/TUiuK5fz/uaply-team-board).

## The owner's rules (standing)
- Ask before any purchase. Say so before anything above the $7.50 a month already authorized on Render (Starter plus the 1 GB disk).
- Never type the owner's secrets (keys, passwords) into chat, commits or files. The owner pastes them into Render's Environment page
  himself, or a session on his own laptop does it with his sign-ins.
- The managing session (Fable) plans, reviews, merges, deploys and reports; the Opus bots write the code, in worktrees, with a
  3-attempt cap per finish line. Every change gets three reviewer passes before its PR (lost or doubled data; security and races;
  broken behaviour or tests that test nothing). Mohammed's bots and Saif's side split the work as the board's "Who works on what" card
  says: server, hosting, email, domain, backups, releases and anything needing Saif's keys are Saif's side.
- Detailed pull requests in the CONTRIBUTING.md shape (what changed, why, how tested, what could go wrong, what is not done, where it
  is going). Show proof: test counts, log lines, screenshots.
- Work moves sandbox, then dev (the release build), always through a pull request. Hiring mode (employer side) and the emailed-code
  sign-up stay sandbox-only (the code checks the instance name) until the owner says otherwise.
- After a merge to dev: trigger the deploy if it did not start, run the live checks, tag `v1.0.0-rc.N`, add the CHANGELOG entry.
- Never automate a job board's apply flow (LinkedIn, Indeed, ZipRecruiter, Handshake). Never submit into a hiring system without a
  key the employer created. Never answer a question the profile cannot. Never send voluntary self-identification. Never get past a
  bot wall or a human check.

## Instances and where they run
| Instance | Branch | Where | State (October 22) |
|---|---|---|---|
| Live site | `dev` | https://uaply.net through Cloudflare (CNAMEs `@` and `www` to `uaply.onrender.com`, **Proxied**, SSL/TLS **Full (strict)**) → Render service `uaply` (`srv-db9i3i6q1p3s738b5b4g`, workspace `tea-db9duku1egvs73et93k0`, Starter, Virginia, https://uaply.onrender.com) | Runs **rc.13** (`e6aced4`, PR #45). `/api/status`: persistent disk, email (Brevo) on, Google sign-in on, payments on in Stripe **test** mode, AI answers off, owner pages on. Health check `/healthz`. |
| Sandbox | `sandbox` | the owner's computer only (`python serve.py 8766 sandbox --api`); no sandbox service on Render | Everything past rc.13: the next release candidate (below). |
| Hosted previews | | retired October 21 | The repository is private, so GitHub Pages cannot publish; run sandbox and dev locally instead. `.github/workflows/check.yml` ("Check the code") is the workflow that matters. |
| Owner's computer | all | 8765 prod (`main`), 8766 sandbox, 8767 dev (`start-uaply.bat`) | The full suite (`bash tools/run-all-tests.sh`) and the Galaxy phone walk (`node tools/phone-walk.js`) run here. |

Render's Environment for `uaply` (names only; the values are the owner's): `OWNER_PASSWORD`, `UAPLY_CONFIG_JSON` (Brevo SMTP, Google
client, `public_url`), `UAPLY_PUBLIC_URL=https://uaply.net` (its own variable since October 21: other addresses get a 301 to it, never
`/api/` or `/healthz`), `UAPLY_USAJOBS_KEY` and `UAPLY_USAJOBS_EMAIL` (the USAJOBS key, issued October 21), `UAPLY_DATA_DIR=/var/data`
(the 1 GB disk), `MALLOC_ARENA_MAX=2`, `UAPLY_FEEDS`, the Stripe test keys and prices. The service was made by hand, so `render.yaml` is a
reference for a fresh setup, not what runs. Deploys: if Events shows none within 2 minutes of a merge into `dev`, use **Manual Deploy**
(or the Render connector's trigger deploy); `tools/live-check.py` fails when the site does not run the head of `dev`.

Behind Cloudflare, `serve.client_ip` takes the visitor's address from `CF-Connecting-IP` only when the last hop is one of Cloudflare's
published ranges (read at start and every 24 hours), and from the host's own last hop otherwise.

## What the next release (rc.14) carries
In plain words, from `CHANGELOG.md` "Unreleased (sandbox)": job feeds rounds 1 to 3 (about 20,000 jobs across every state, employers'
own careers sites and Workday, per-source health, a human-check scan), readiness (a swipe right only sends a complete application; the
minimum to apply is checked on the server too), the Job Tracker name and its rows kept, phone fit on the Galaxy (44 px targets, the
agreement in sight), the Google Play listing pack and installable site, assisted apply in the phone app (questions first, then the
employer's own form; only the hiring systems' hosts; never the whole profile), sign-in hardening (no lockout by strangers, one answer
for every wrong code, the real visitor's address, a site-wide cap on code emails, Google asks the owner's tick), answers kept per
employer, collision-free job ids, the employer outreach kit and "Test this connection" on `/setup`, and the owner's self-check in
`/api/status`. Launch day: `docs/runbook-launch.md` (release, deploy, live checks, the phone walk, a real code and a real Google sign-in,
the 2-hourly watch, and the one-command rollback to rc.13).

## What the owner must do himself (nobody else can)
1. Launch day steps marked "owner" in the runbook (the backup, the Render API key for a rollback, the phone, the real sign-ups).
2. The outside uptime check (UptimeRobot, free; `docs/uptime.md`).
3. Render: link the Render GitHub app to the repository so a merge into `dev` deploys by itself (DEPLOY.md, Auto-deploy).
4. Stripe live mode: needs the C corporation and Stripe's business verification; then the live keys and prices in Render, and the
   lawyer's paid-plan wording in `legal/terms.html` first. Until then payments stay in test mode (or `UAPLY_PLANS_HIDDEN=1` for a
   free-only launch).
5. Brevo's bounce webhook and `email_events_secret` in `UAPLY_CONFIG_JSON` (DEPLOY.md section 5); the AI key if answers should use AI.
6. Phone apps: the Android SDK licences on the laptop and the Play Console (docs/play-store.md); the Apple Developer Program.
7. Attorney review of the legal pages and of the hiring systems' terms (LEGAL-REVIEW.md, docs/assisted-apply.md section 7); trademark
   clearance ("APLY" overlaps "UAply").

## Where things are
- How to run and deploy: `DEPLOY.md` (Render, Running the live site: health check, auto-deploy, rollback, backups, logs, capacity, the
  self-check; Google; Stripe; email). Accounts and sign-in limits: `docs/ACCOUNTS.md`. Job sources: `docs/job-sources.md`. Employers
  connecting their hiring system: `EMPLOYERS.md`, `docs/employers/`. Assisted apply: `docs/assisted-apply.md`. Reviews: `docs/reviews/`.
- Checks: `node check.js` (static), `bash tools/run-all-tests.sh` (everything, local servers only), `python tools/live-check.py --base
  https://uaply.net --expect all` and `node tools/cdp.js tools/ui-live.js --base https://uaply.net` (the live site, after every deploy).
