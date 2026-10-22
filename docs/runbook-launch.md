# Launch day runbook (Saturday)

The exact sequence for releasing the final release candidate to the live site and watching it through launch day. Do the steps in
order; each one says what "good" looks like and what to do when it is not. Written October 22, 2026, for the release after
`v1.0.0-rc.13` (live today: commit `e6aced4`).

Who does what: **owner** = Saif (anything with a password, a key, money or the phone); **coordinator** = the managing session, which
can run the commands that need no secret. Nothing here needs a secret typed into chat or a file.

| Thing | Value |
|---|---|
| Live site | https://uaply.net (Cloudflare, proxied, SSL/TLS **Full (strict)**) → Render service `uaply` (`srv-db9i3i6q1p3s738b5b4g`, https://uaply.onrender.com), branch `dev` |
| Release before this one | `v1.0.0-rc.13` = `e6aced4d950d7b83f5c1c803462205c32e55b227` |
| Repository | `saifsiddiqueep-sketch/uaply`, private (no GitHub Pages; the only workflow that matters is **Check the code**) |
| Live settings (Render, Environment) | `OWNER_PASSWORD`, `UAPLY_CONFIG_JSON`, `UAPLY_PUBLIC_URL=https://uaply.net`, `UAPLY_USAJOBS_KEY`, `UAPLY_USAJOBS_EMAIL`, `UAPLY_DATA_DIR=/var/data`, `MALLOC_ARENA_MAX=2`, `UAPLY_FEEDS`, Stripe test keys |

## 0. Before you start (Friday night or Saturday morning, 15 minutes)
1. **Freeze.** Nothing new merges into `sandbox` after the release candidate is chosen. The full suite is green on it
   (`bash tools/run-all-tests.sh` on the laptop) and the three reviewer passes are done.
2. **A backup of the live disk** (owner, 2 minutes): Render → `uaply` → **Shell** → `python tools/backup-data.py --keep 4`. Good: it
   prints the file name under `/var/data/backups/`. This is what a rollback falls back on if data ever went wrong (DEPLOY.md, Backups).
3. **Cloudflare** (owner, read only): DNS shows `uaply.net` and `www` as CNAMEs to `uaply.onrender.com`, **Proxied** (orange cloud);
   SSL/TLS → Overview says **Full (strict)**. Change nothing on Cloudflare today unless step 9 says so.
4. **The outside uptime check** (`docs/uptime.md`) is set up and green, so you hear about an outage by email.
5. **Render API key for the rollback command** (owner, once): Render → your picture → **Account Settings** → **API Keys** → **Create
   API Key**, name `launch rollback`. Keep it in your password manager. Only ever type it into the one terminal window that needs it
   (step 9), never into chat or a file.

## 1. Release to dev (coordinator, 10 minutes)
1. One pull request from `sandbox` into `dev`:
   `gh pr create --base dev --head sandbox --title "Release candidate 14: <the headline>" --body-file <notes>`
   in the CONTRIBUTING.md shape (what users get, how it was tested, what could go wrong, not done, deploy). Hiring mode and the
   emailed-code sign-up stay sandbox-only by themselves (the code checks the instance name), so nothing needs to be cut out.
2. Wait for **Check the code** to pass on the PR, then **Merge pull request** (a merge commit, not squash, so `dev` keeps the history).
3. Tag it: `git fetch origin && git tag -a v1.0.0-rc.14 origin/dev -m "Release candidate 14" && git push origin v1.0.0-rc.14`, and move
   the CHANGELOG's "Unreleased (sandbox)" heading under a new `## 1.0.0-rc.14 (dev, <date>)` in the next small PR.
4. Write down the new commit: `git rev-parse --short origin/dev` (7 letters). Every check below compares against it.

## 2. Deploy (owner or coordinator, 3 minutes)
1. Render → `uaply` → **Events**. If a deploy for the new commit started on its own within 2 minutes of the merge, wait for it. If not
   (auto-deploy has not fired for this service since it was made), **Manual Deploy** → **Deploy latest commit**. The coordinator can
   do the same through the Render connector (trigger a deploy of `srv-db9i3i6q1p3s738b5b4g`).
2. Good: Events says **Deploy live** for the new commit within about 3 minutes. A few seconds of 502 during the switch is normal (a
   service with a disk stops the old copy first).
3. Render → **Logs**, search `[uaply] dev on`. The newest start-up line must say all of: `data: /var/data (persistent disk)`, `email:
   on`, `Google sign-in: on`, `payments: on` (TEST mode until the live Stripe keys exist), `UAPLY_CONFIG_JSON: valid`, `feeds:` with
   `usajobs` in the list, and `commit: <the 7 letters>`. Anything else: stop and fix it before going on (a typo in Environment is the
   usual cause; each save restarts the service, so batch the changes).

## 3. Live check from outside (coordinator, 3 minutes)
`python tools/live-check.py --base https://uaply.net --expect all`
Good: no FAIL line, and "the site runs the latest push" names the new commit. `--expect all` turns email, Google, payments and the
persistent disk from SKIP into FAIL when one is off, so a missing setting cannot pass quietly. A FAIL on "latest push": the deploy did
not happen; go back to step 2.

## 4. A stranger's first visit in a browser (coordinator, 5 minutes)
`node tools/cdp.js tools/ui-live.js --base https://uaply.net --out ui-live-shots`
Good: every line PASS at phone size (390x844) and computer size (1280x800): the agreement box, tips, a swipe, the Account wording,
Continue with Google leading to Google's page (it never signs in), Plan and billing, the help assistant.

## 5. The phone walk on the Galaxy (owner plugs it in; coordinator runs it, 10 minutes)
USB debugging on, Chrome on the phone. `node tools/phone-walk.js live` (read only on the live site: screens and fit checks, no swipes, no
sign-up). It opens **one** Chrome tab of its own and leaves the phone's other tabs alone. Never run `adb forward --remove-all` (it
cuts every other tool's connection to the phone); remove only a forward you added yourself. Good: the summary has 0 FAIL; screenshots are in `phone-walk/live-<time>/`. Look
at the first screen, the card, Profile and Job Tracker shots yourself.

## 6. A real sign-up with a real code (owner, 5 minutes)
On the Galaxy, in Chrome: https://uaply.net → Profile → Account → **Create account** with a fresh address of yours (for example
`uaplytechnologies+launch1@gmail.com`) and a password, tick 18+ and Terms. Good: you are signed in at once, the 6-digit code arrives
within a minute (look in Spam too), and typing it marks the address verified on the Account screen. (The no-password sign-up card is
sandbox-only and does not run on the live site.) Then on the laptop open https://uaply.net/setup (owner password), then
https://uaply.net/api/status: `selfCheck.email.minutesAgo` is `0` or `1`. No code within 5 minutes: Brevo → Statistics or Logs for that
address, and DEPLOY.md section 5. (Or let the coordinator run `node tools/cdp.js tools/ui-live.js --base https://uaply.net --email
<that address> --code-file code.txt` and type the code into `code.txt` when it arrives.)

## 7. A real Google sign-in (owner, 5 minutes)
On the laptop in a private window, then on the Galaxy: https://uaply.net → **Continue with Google** → pick a real Google account. Good:
Google's page, then back on `uaply.net` signed in; Account shows that address; **Sign out** works. A Google error page instead
("redirect_uri_mismatch", "origin not allowed"): Google Auth Platform → the "UAply web" client must list `https://uaply.net` as an
origin and `https://uaply.net/api/auth/google/callback` as a redirect URI (DEPLOY.md section 3).

## 8. Watch it: every 2 hours until midnight, then once in the morning (owner, 5 minutes each)
| Where | Look at | Good | If not |
|---|---|---|---|
| Your inbox | UptimeRobot "down" emails | none, or a "down" and an "up" 5 minutes apart around a deploy | a real outage: Render Events and Logs, then step 9 |
| https://uaply.net/api/status (after /setup, owner password) | `selfCheck` | `ok: true`; `feeds.minutesAgo` under 60; `email.minutesAgo` small once people sign up; `disk.freeMB` above 100; `warnings: []` | read the warning: job boards not read (Logs, search `job feed`), disk filling (Render → Disks), data not persistent (stop: fix before anyone signs up) |
| Render → `uaply` → Metrics | Memory, CPU, HTTP 5xx | memory under 400 MB; CPU near 0 outside board refreshes; 5xx only within a minute of a deploy | memory above 400 MB for an hour or an "out of memory" restart in Events: tell the coordinator (Standard plan question, DEPLOY.md Capacity) |
| Render → `uaply` → Logs | search `failed:`, `could not save`, `Traceback` | none, or one-off | the same error again and again: send the line (never a secret) to the coordinator |
| Brevo → Statistics | emails sent today | well under 300 (from 250 only codes, resets and applications go out) | close to 250 by afternoon: tell the coordinator before the evening |
| https://uaply.net/api/feed-health (owner) | `jobs`, sources `off` | jobs in the hundreds; few sources off | many sources off: Logs `job feed` |
| Stripe (test mode) | nothing to do on launch day | | |

At midnight UTC the log has one `[uaply] daily {...}` line: requests, 5xx, sign-ups, logins, applications, p95. Keep it for the next
morning's note.

## 9. Roll back to rc.13 (one command, about 3 minutes)
When: the site is down or sign-up is broken for 10 minutes after a deploy and the cause is not a setting you can fix on the spot, or
5xx answers keep coming for 15 minutes. The data stays: nothing between rc.13 and rc.14 changes the accounts database, and the files
rc.14 adds (`job-ids.json`, the self-check's `last_sent`) are ignored by rc.13. People stay signed in.

In a terminal on the laptop, with the API key from step 0.5 in that window only:

PowerShell:

    $env:RENDER_API_KEY = "<paste the key>"; Invoke-RestMethod -Method Post -Uri https://api.render.com/v1/services/srv-db9i3i6q1p3s738b5b4g/deploys -Headers @{Authorization = "Bearer $env:RENDER_API_KEY"} -ContentType "application/json" -Body '{"commitId": "e6aced4d950d7b83f5c1c803462205c32e55b227"}'

Git Bash:

    curl -s -X POST -H "Authorization: Bearer $RENDER_API_KEY" -H "Content-Type: application/json" -d '{"commitId": "e6aced4d950d7b83f5c1c803462205c32e55b227"}' https://api.render.com/v1/services/srv-db9i3i6q1p3s738b5b4g/deploys

It deploys exactly the rc.13 commit and answers with the new deploy's id and `"status": "created"`. Without a key: Render → `uaply` →
**Events** → the deploy of `e6aced4` → **Rollback** does the same in two clicks. Then:
1. `python tools/live-check.py --base https://uaply.net --expect all --commit e6aced4` passes (the site runs rc.13 again).
2. Close the terminal window (the key goes with it).
3. A deploy of a chosen commit leaves auto-deploy as it was: the next merge into `dev` deploys `dev` again. So fix forward on
   `sandbox`, release that as rc.15 through steps 1 to 4, and do not merge anything else into `dev` meanwhile.
4. If data itself went wrong (not just the code): DEPLOY.md, Backups, "To restore", with the backup from step 0.2.

## 10. After launch day
- A short note in the CHANGELOG entry for rc.14: what was seen in the first day (the daily line, any warning).
- HANDOFF.md: the live commit and anything that changed in Render's Environment.
