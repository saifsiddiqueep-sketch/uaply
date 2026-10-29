# Handoff: where UAply stands and how we work (updated October 23, 2026)

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
- Work moves sandbox, then dev (the release build), always through a pull request. GitHub enforces it on `dev` and `main`: the
  ruleset "Live branches: owner only" (id 25654532, since October 22) asks for a pull request with 1 approval, no force-push and no
  deletion, with only the repository's admin role (Saif) able to bypass it; `sandbox` has no rule. Hiring mode (employer side) stays
  sandbox-only (the code checks the instance name) until the owner says otherwise; the sign-in gate and the sign-up card are on every
  front end since the October 23 release.
- Pro Mode (CLAUDE.md, Saif's side): off by default; "go pro" switches it on (GOAL / DONE WHEN / BUDGET on every order, Sonnet for
  test runs and log reading, a fresh session per milestone with a handoff, this file and the handbook updated after every merge,
  two reviewers for changes under 100 lines). One task per chat on Saif's side starts with it, Monday October 26.
- After a merge to dev: trigger the deploy if it did not start, run the live checks, tag `v1.0.0-rc.N`, add the CHANGELOG entry.
- Never automate a job board's apply flow (LinkedIn, Indeed, ZipRecruiter, Handshake). Never submit into a hiring system without a
  key the employer created or a public apply endpoint the system provides for that posting (Recruitee's), and never where terms forbid
  automation (SmartRecruiters). Never answer a question the profile cannot. Never send voluntary self-identification. Never get past a
  bot wall or a human check.

## Instances and where they run
| Instance | Branch | Where | State (October 23) |
|---|---|---|---|
| Live site | `dev` | https://uaply.net through Cloudflare (CNAMEs `@` and `www` to `uaply.onrender.com`, **Proxied**, SSL/TLS **Full (strict)**) → Render service `uaply` (`srv-db9i3i6q1p3s738b5b4g`, workspace `tea-db9duku1egvs73et93k0`, Starter, Virginia, https://uaply.onrender.com) | Runs **`9b76822`** (rc.14: the sign-in gate v2, deployed October 23; not tagged yet, the tags are `v1.0.0-rc.1` to `v1.0.0-rc.13`). Next: `17105d4` (proposed rc.15, below). `/api/status`: persistent disk, email (Brevo) on, Google sign-in on, payments on in Stripe **test** mode, AI answers off, owner pages on. Health check `/healthz`. |
| Sandbox | `sandbox` | the owner's computer only (`python serve.py 8766 sandbox --api`); no sandbox service on Render | Tip `17105d4` (October 23), the next release's candidate: swipe phase A (de96435) and its test fixes, the paged and ranked deck (282adbf, deck-paged), the Recruitee reader (feeds-recruitee), the 14 px pass (text-14), the handbook and joint CLAUDE.md, runbooks 3 and 5, Mohammed's PRs #61 and #63, and the ui-gate wording fix (2612f1a). |
| Hosted previews | `sandbox`, `dev` | https://saifsiddiqueep-sketch.github.io/uaply/sandbox.html and /dev.html (GitHub Pages); second copy: https://uaply-sandbox-preview.onrender.com/sandbox.html | Back on October 22 while the repository is public until launch: `.github/workflows/pages.yml` builds them with `node share/build-share.js --full` on each push. Static copies with example jobs and no server; they say so (preview wording). The GitHub Pages copies exist only while the repository is public. Since PR #63 the build embeds every shared script the pages list, the sign-up card included; with no server the card is not used and Account says it is a preview. |
| Owner's computer | all | 8765 prod (`main`), 8766 sandbox, 8767 dev (`start-uaply.bat`) | The full suite (`bash tools/run-all-tests.sh`) and the Galaxy phone walk (`node tools/phone-walk.js`) run here. |

Render's Environment for `uaply` (names only; the values are the owner's): `OWNER_PASSWORD`, `UAPLY_CONFIG_JSON` (Brevo SMTP, Google
client, `public_url`), `UAPLY_PUBLIC_URL=https://uaply.net` (its own variable since October 21: other addresses get a 301 to it, never
`/api/` or `/healthz`), `UAPLY_USAJOBS_KEY` and `UAPLY_USAJOBS_EMAIL` (the USAJOBS key, issued October 21), `UAPLY_DATA_DIR=/var/data`
(the 1 GB disk), `MALLOC_ARENA_MAX=2`, `UAPLY_FEEDS` (gets `recruitee` added with the `17105d4` release), the Stripe test keys and prices. The service was made by hand, so `render.yaml` is a
reference for a fresh setup, not what runs. Deploys: if Events shows none within 2 minutes of a merge into `dev`, use **Manual Deploy**
(or the Render connector's trigger deploy); `tools/live-check.py` fails when the site does not run the head of `dev`.

Behind Cloudflare, `serve.client_ip` takes the visitor's address from `CF-Connecting-IP` only when the last hop is one of Cloudflare's
published ranges (read at start and every 24 hours), and from the host's own last hop otherwise.

## What rc.14 carried (live since October 23, `9b76822`)
In plain words, from `CHANGELOG.md` "Unreleased (sandbox)": job feeds rounds 1 to 3 (about 20,000 jobs across every state, employers'
own careers sites and Workday, per-source health, a human-check scan), readiness (a swipe right only sends a complete application; the
minimum to apply is checked on the server too), the Job Tracker name and its rows kept, phone fit on the Galaxy (44 px targets, the
agreement in sight), the Google Play listing pack and installable site, assisted apply in the phone app (questions first, then the
employer's own form; only the hiring systems' hosts; never the whole profile), sign-in hardening (no lockout by strangers, one answer
for every wrong code, the real visitor's address, a site-wide cap on code emails, Google asks the owner's tick), answers kept per
employer, collision-free job ids, the employer outreach kit and "Test this connection" on `/setup`, and the owner's self-check in
`/api/status`. Launch day: `docs/runbook-launch.md` (release, deploy, live checks, the phone walk, a real code and a real Google sign-in,
the 2-hourly watch, and the one-command rollback to rc.13).

## What the next release carries (candidate `17105d4` over the live `9b76822`)
In plain words; the detail, with what was checked, is the CHANGELOG section "The next release: candidate 17105d4 over the live
9b76822". The deck draws its first card from one page of 200 jobs and ranks the whole list once it has it, in the background. Swipe
phase A: the first-swipe agreement (box version 4, so everyone agrees once more) kept on the account and required for every send;
apply by email where a posting asks for it; one tap in the phone app; the outreach queue (a tool); Send applications for me.
Automatic submit (rc.17): on by the agreement only where a system is approved and no human check was measured (Ashby);
Greenhouse, Lever and Workable are approved but stay assisted while their forms carry a check; SmartRecruiters (terms) and other stay assisted.
Recruitee's public apply endpoint is on by default. Test accounts (UAPLY_TEST_EMAILS, or /setup) never send, and the first live send of each
session needs the server's own confirmation. Also: Recruitee careers sites as a new job source (off until
`recruitee` is in `UAPLY_FEEDS`), text at 14 px or more everywhere, pay as the posting gives it, and the phase A test fixes. For the
team: the handbook as a reference, the joint CLAUDE.md, this file, and the no-attribution repository setting. Rolling back to
`9b76822` keeps every account: this release only adds to the accounts database (the `consents` table, the `send_for_me` columns).

## Release day for `17105d4` (the runbook's steps that apply, in order)
The runbook (`docs/runbook-launch.md`) was written for rc.14 over rc.13. For this release use the values here where they differ; the
next section lists where it is out of date.
1. Freeze `sandbox` at `17105d4`. The full run (`bash tools/run-all-tests.sh`) is green on it and the three reviews are done (runbook 0.1).
2. Owner: back up the live disk. Render → `uaply` → Shell → `python tools/backup-data.py --keep 4` (0.2). This matters more than
   usual: the new code adds a table and two columns to the accounts database the first time it starts.
3. Owner, read only: Cloudflare DNS and SSL/TLS as in 0.3; the outside uptime check is green (0.4); the Render API key for a
   rollback is in the password manager (0.5).
4. Coordinator: one pull request from `sandbox` into `dev`, titled "Release candidate 15: ..." (1.1). Wait for **Check the code**,
   then merge with a merge commit (1.2).
5. Tag both releases: `git fetch origin && git tag -a v1.0.0-rc.14 9b76822 -m "Release candidate 14" && git tag -a v1.0.0-rc.15
   origin/dev -m "Release candidate 15" && git push origin v1.0.0-rc.14 v1.0.0-rc.15`. Write down `git rev-parse --short origin/dev` (1.3, 1.4).
6. Only if Saif calls this the launch release: make the repository private (1.5, all four parts).
7. Owner (or the coordinator through the Render connector): Render → `uaply` → **Environment** → `UAPLY_FEEDS` → add
   `,recruitee` to the end of its value (keep everything already there) → **Save, rebuild, and deploy**. One save does the setting and the
   deploy of the new commit, so the service restarts once (2.1). If a deploy for the merge had already started, let it finish
   first, then save.
8. Render → Logs, the newest `[uaply] dev on` line: the usual list (2.3) with `recruitee` in `feeds:` and `commit:` the new 7 letters.
9. Coordinator: `bash tools/launch-smoke.sh https://uaply.net` (3 and 4). Good: `result  no FAIL`, `site runs` the new commit.
10. Coordinator, with the Galaxy plugged in by the owner: `node tools/phone-walk.js live` (5).
11. Owner: a real sign-up with a real code (6), then a real Google sign-in (7). New this time: the first swipe right shows the
    agreement box (version 4); after agreeing, `/api/auth/me` shows `consent` with `"v": 4`. **Swipe right only on a job that says
    Finish on their site, or use Pass**: a Ready job may now email the employer for real (apply by email).
12. Within an hour of step 7: `/api/feed-health` (owner) lists 33 sources named `recruitee/...`, most of them with jobs and
    none `off`.
13. Coordinator: the computer's own servers (10). Say so in chat first, `git pull --ff-only`, close the 8765, 8766 and 8767 windows,
    double-click `start-uaply.bat`; good: `/healthz` on 8766 and 8767 answer `{"ok": true}` and each window's first line names the
    new commit.
14. Watch every 2 hours (8). Brevo's count now includes emailed applications: at most 10 a day per employer domain and the site's
    `daily_limit` (20 unless `UAPLY_CONFIG_JSON` sets it) on top of codes and resets.
15. If it goes wrong (9): roll back to **`9b76822`** (full id `9b7682215fa08dc68fb7eb7b4a48216aa3118316`), not `e6aced4`, then
    `python tools/live-check.py --base https://uaply.net --expect all --commit 9b76822`. Taking `recruitee` back out of `UAPLY_FEEDS`
    is optional: `9b76822` does not read Recruitee boards. Then fix forward as rc.16.
16. After launch day (11): the first day's note in the CHANGELOG, and here the live commit and the `UAPLY_FEEDS` change.

## Where the runbook is out of date after the October 23 merges (not yet fixed in `docs/runbook-launch.md`)
- The opening lines, the table's "Release before this one" and all of step 9 name rc.13 (`e6aced4`). The release before this one
  is `9b76822` (rc.14, live, not tagged); a rollback goes there.
- Step 9's reason the data is safe ("nothing between rc.13 and rc.14 changes the accounts database") no longer covers this release:
  `17105d4` adds the `consents` table and the `send_for_me` and `send_for_me_at` columns. It is still safe: `9b76822` reads,
  signs in and deletes those accounts (checked on October 23), and deleting an account also deletes its agreement.
- Steps 1.1 and 1.3 say rc.14; this release is rc.15, and `9b76822` still needs its rc.14 tag.
- Step 2.3 and the table: `UAPLY_FEEDS` is `greenhouse,lever,ashby` in render.yaml. The live value needs `recruitee` added (step 7
  above), and the `feeds:` line should then list it.
- Step 6 asks for a real sign-up but not for the first-swipe agreement, and it does not warn that a swipe right can now email an
  employer (apply by email). Step 8's Brevo row does not count emailed applications.
- Out of date since the October 23 release already: step 6 still says the no-password sign-up card is sandbox-only and does not run
  on the live site. Since the gate the card runs on every front end, with a password.

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
