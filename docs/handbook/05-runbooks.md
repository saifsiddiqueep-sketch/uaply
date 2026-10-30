# 05 Runbooks

Each entry: **Symptom**, **Check**, **Fix**, **Source** (the file, log line or commit it comes from). Anything marked "owner" needs Saif (keys, money, Render settings, DNS). If a fix needs a step you are not allowed to take (page 06), stop and hand it to the owner with what you found.

General first moves for any live problem:

1. https://uaply.net/healthz (should be `{"ok": true}`).
2. Render, `uaply`, **Events** (deploys, restarts) and **Logs** (search terms on page 04).
3. `/api/status` and, as owner, its `selfCheck`.
4. `python tools/live-check.py --base https://uaply.net --expect all` (read only).

---

## 1. The site is down

**Symptom:** UptimeRobot "down" email; uaply.net does not load; visitors see a 502 or the "Starting UAply" screen.

**Check:**
- Was there a deploy in the last minute? A few seconds of 502 during a deploy is normal (a service with a disk stops the old copy first; October 17 metrics: 1 to 6 per deploy, never between deploys). A "down" and an "up" email 5 minutes apart around a deploy need nothing.
- Render Events: a failed deploy, a restart, "out of memory"?
- Logs: last `[uaply] dev on` line; `Traceback`; `failed:`.
- https://uaply.onrender.com/healthz directly. If that works but uaply.net does not, the problem is Cloudflare or DNS (owner).

**Fix:**
- Failed deploy: read the build log; fix forward on `sandbox`, or roll back (page 04).
- Crash after a deploy and not fixable in 10 minutes: roll back (page 04).
- Out of memory: runbook 2.
- Cloudflare or DNS: owner only. SSL/TLS must be **Full (strict)**; Flexible loops on Render's https redirect.

**Source:** `docs/uptime.md`, `DEPLOY.md` "How deploys behave" and step 6 (Cloudflare), `docs/runbook-launch.md` sections 8 and 9.

## 2. Memory near the 512 MB limit, or an out-of-memory restart

**Symptom:** Metrics memory above 400 MB; Events shows an out-of-memory restart; the site restarts during a job board refresh.

**Check:**
- Metrics, Memory. On October 17 one copy reached 491 MB of 512 MB when a second board read overlapped the first.
- Logs: `[uaply] daily` line, `memory` now and peak.
- Environment has `MALLOC_ARENA_MAX=2`.

**Fix:**
- If `MALLOC_ARENA_MAX` is missing: owner adds `MALLOC_ARENA_MAX` = `2`, Save, rebuild, and deploy.
- The code already reads at most 3 boards at once, never one twice, and hands memory back (commit `aba3963`; later `e1d5b34` read postings one at a time). If a new feed change raised memory, measure with `python tools/test-feed-memory.py` and fix on `sandbox`.
- If it holds for a day (memory above 400 MB, OOM restart, CPU above 0.4 for 10 minutes outside a refresh, or `p95_ms` above 1500): ask the owner about the Standard plan. Never change the plan yourself (it costs money).

**Source:** `DEPLOY.md` "Capacity" and "Environment"; commits `aba3963`, `e1d5b34`; `docs/runbook-launch.md` section 8.

## 3. No jobs, or far fewer jobs than usual

**Symptom:** the deck is empty; Pass is disabled; the self-check warns "no good board read in 2 hours"; `/api/feed-health` shows many sources off.

**Check:**
- Signed out? Then an empty deck is the sign-in gate, not a feed problem: the card is the whole screen and no job card is drawn, and
  `/api/jobs` answers `401` `{"code": "signin"}` without a session (runbook 5). Check the feeds signed in, or with the owner checks
  below.
- Signed in and still empty: the deck reads the job list a page at a time. `GET /api/jobs?size=200&page=1` is the first page (then
  `?cursor=<the next of the page before>`, and `&type=internship,coop` for a stack's own pages); `GET /api/jobs` with no query is the
  whole list as before; `GET /api/jobs/<id>` is one job (a shared job opens this way; `404` `gone` when it is no longer listed).
  Compare the first page's jobs with the whole list (`serve.py`, `jobs_api.get_page`, `jobs_api.job_full`).
- First start on an empty disk takes about a minute to fill. After that, saved jobs show at once while boards refresh.
- Logs: search `job feed` (a board that could not be read).
- `selfCheck.feeds.lastOk` and `minutesAgo` in `/api/status` (owner).
- Settings: `UAPLY_FEEDS` in Environment; the `feeds` list and `feeds_off` in `UAPLY_CONFIG_JSON`; `UAPLY_FEEDS_OFF`. A `feeds` list in `UAPLY_CONFIG_JSON` keeps feeds on even after `UAPLY_FEEDS` is removed.
- USAJOBS shows status "no key" until `UAPLY_USAJOBS_KEY` is set, and is on only when the `feeds` list names `usajobs`.

**Fix:**
- One board failing: nothing urgent; it is skipped. Many failing: look for a shared cause in the log lines (network, a format change) and fix on `sandbox` with a test in `tools/test-feeds.py` or `tools/test-jobs.py`.
- Postings silently dropped: one past bug read dates in seconds as January 1970 and the 60-day rule dropped them (commit `460c4e3`). Check date handling first when a whole source vanishes.
- Settings wrong: owner edits Environment.

**Source:** `DEPLOY.md` step 5 and "Before real users" item 5; `docs/runbook-launch.md` sections 2 and 8; `CHANGELOG.md` "A student's first visit" (epoch ms); commit `9a5b25e` (cold start: no card, Pass disabled).

## 4. Sign-in broken: Google errors

**Symptom:** Google shows an error page, or the Google button is missing.

**Check and fix** (from the table in `DEPLOY.md` section 3; all fixes are in Google Cloud or `UAPLY_CONFIG_JSON`, so owner only):

| You see | Fix |
|---|---|
| `Error 400: redirect_uri_mismatch` | Add the exact address + `/api/auth/google/callback` under Authorized redirect URIs (Google's error details show the one it got). Wait 5 minutes. |
| `origin_mismatch`, "origin is not allowed" | Add the exact origin (scheme, www, port, no trailing slash) under Authorized JavaScript origins. |
| `Error 401: invalid_client` or log `Google refused to swap the sign-in code (invalid_client)` | Client ID or secret in `UAPLY_CONFIG_JSON` is wrong, has a space, or the client was deleted. |
| `Error 403: access_denied` for everyone but the owner | Audience is still Testing: Publish app. |
| `Error 403: disallowed_useragent` | Sign-in was tried inside an app's web view. Use Safari or Chrome. (The phone apps hide the Google button for this reason.) |
| "That Google sign-in expired or could not be checked" every time | Site opened at one address, Google returned to another. List both; `public_url` should be `https://uaply.net`. |
| No Google button | Start-up line says `Google sign-in: off` or `OFF: ...`. Fix `UAPLY_CONFIG_JSON` until the log says `valid`. |

**Source:** `DEPLOY.md` section 3, "If you see X, do Y"; `docs/runbook-launch.md` section 7.

## 5. Sign-in broken: people cannot sign up or get "Sign in first"

**Symptom:** after sign-up the app shows nothing; data routes answer 401 `signin` or 403 `verify`; people say they are locked out.

**Check:**
- The gate is on the live site since the October 23 release (`9b76822`; on `sandbox` since October 22): signed out, data routes
  answer `401` `{"code": "signin"}`. An unverified address gets `403` `verify` where a verified email is needed. That is expected; the app should show the sign-up card or the code step.
- Is email working (runbook 6)? A sign-up needs its 6-digit code to verify. On a live server without email, sign-up still works but
  no code can arrive, so every account stays unverified and every data route answers `403` `verify` for everyone: nobody gets past the
  gate. `/api/status` says `"email": false`, and `tools/live-check.py --expect email` fails.
- Limits: 40 sign-ups an hour per address, codes 3 an hour per account and 80 per address, a site-wide cap of 500 code emails an hour (`UAPLY_CODE_SENDS_PER_HOUR`). The refusal text says what to do.
- `node tools/cdp.js tools/ui-gate-live.js` against the site (read only) checks the gate.

**Fix:**
- No email on the live server (owner): set the email keys (the Brevo SMTP settings in `UAPLY_CONFIG_JSON`, runbook 6 and `DEPLOY.md`
  step 4 and section 5), redeploy, and check `"email": true` in `/api/status`; then people use Resend code or Email me a code.
- Front end not showing the code step: test with `tools/ui-gate.js` locally and fix on `sandbox`.
- A campus behind one address hitting limits: the limits were raised for this in October; any further change is a server change (Saif's area).
- Real visitor address wrong behind Cloudflare: `serve.client_ip` trusts `CF-Connecting-IP` only from Cloudflare's ranges (`UAPLY_CF_RANGES=0` keeps the built-in copy).

**Source:** `CHANGELOG.md` "Sign-in, server side (Saif, October 22)", "Sign-in, server side (PR #49 review)", "Five fixes from the October 22 audit"; `docs/ACCOUNTS.md`; `HANDOFF.md` (Cloudflare and `client_ip`).

## 6. Emails not arriving (codes, resets, receipts)

**Symptom:** no 6-digit code; no receipt; the sign-up says "the problem is on our side, try again in a few minutes".

**Check:**
- Start-up line says `email: on` and `UAPLY_CONFIG_JSON: valid`.
- Logs: `email not sent` lines name the reason, for example `quota (421 ...); held until ... UTC`.
- The daily limit: Brevo free plan is 300 a day. From 250, only codes, resets and applications go; receipts and copies are held until after midnight UTC. At 300 nothing more is tried that day.
- `selfCheck.email.lastSent` / `minutesAgo` (owner).
- Brevo, Statistics and Logs for that address. Spam folder.
- The address may be on the bounce list (runbook 7).

**Fix:**
- Quota: wait for midnight UTC, or the owner moves to a paid Brevo plan and sets `mail_daily_quota` and `mail_priority_at` in `UAPLY_CONFIG_JSON` (costs money: owner approves).
- Refused login (revoked SMTP key): receipts are retried every 15 minutes up to 8 times; codes fail. Owner replaces the SMTP key in `UAPLY_CONFIG_JSON`.
- Close to 250 by afternoon: tell the owner before the evening.

**Source:** `DEPLOY.md` section 5 "The daily limit"; `docs/runbook-launch.md` sections 6 and 8; commit `a15b43a`.

## 7. One person never gets email: the bounce list

**Symptom:** sign-up says the address bounces; one user never receives anything.

**Check:** the Brevo webhook puts hard bounces, blocks, invalid addresses, complaints and unsubscribes on `mail-suppressed.json` for a year; five soft bounces in a week for a week. The start-up line says `email: on (bounce events: on)` when the webhook secret is set.

**Fix (owner, needs `email_events_secret`):** take the address off with the `uaply_unblock` call in `DEPLOY.md` section 5 step 4, and remove it in Brevo, Contacts, Blocklisted. Never type the secret into chat or a file.

**Source:** `DEPLOY.md` section 5 "Bounces and complaints".

## 8. Accounts disappear after a deploy

**Symptom:** people are signed out and their accounts are gone after each deploy.

**Check:** start-up line says `NOT a persistent disk` instead of `data: /var/data (persistent disk)`. The self-check warns about a data folder that is not a persistent disk. This was the live state on October 17 before the disk was attached ("accounts vanish at each deploy").

**Fix (owner):** Render, Disks: a disk mounted at `/var/data`, and `UAPLY_DATA_DIR=/var/data`. Stop sign-ups until fixed (`docs/runbook-launch.md`: "data not persistent (stop: fix before anyone signs up)").

**Source:** `HANDOFF.md` (dev branch, October 17, instances table); `DEPLOY.md` step 5; `docs/runbook-launch.md` section 8.

## 9. A setting was saved but nothing changed

**Symptom:** after editing Environment, email, Google or payments are still off.

**Check:** start-up line says `NOT VALID JSON`: `UAPLY_CONFIG_JSON` has a typo and was ignored. `UAPLY_PUBLIC_URL` that is not a bare `https://` address is ignored and the log says so.

**Fix (owner):** correct the one-line JSON (`tools/render-config-line.py` helps build it on the owner's computer), Save, rebuild, and deploy. Batch edits: each save restarts.

**Source:** `DEPLOY.md` step 3 and step 5; `docs/runbook-launch.md` section 2.3.

## 10. A merge into dev did not reach the live site

**Symptom:** `live-check.py` fails "the site runs the latest push"; `/api/status` shows an older commit.

**Check:** Render Events: no deploy for the new commit. Auto-deploy has not fired since October 17.

**Fix:** Render, `uaply`, **Manual Deploy**, **Deploy latest commit** (or the Render API). Lasting fix (owner): install Render's GitHub app for the repository, add the GitHub credential in Render, and confirm Build and Deploy shows the repository, branch `dev`, Auto-Deploy On Commit (`DEPLOY.md` "Auto-deploy" steps 1 to 4).

If the deploy fails with "repository not found" after the repository went private: GitHub, Settings, Applications, Render, Configure, give it access to `uaply`, deploy again.

**Source:** `DEPLOY.md` "Auto-deploy"; `HANDOFF.md` "Deploys"; `docs/runbook-launch.md` sections 1.5 and 2; commit message of the live-check fix (it now reads dev's head from GitHub, not a stale local checkout).

## 11. The preview site is not updating

**Symptom:** a change merged into `sandbox` does not show on the preview.

**Check:**
- Which preview? The Render static site `uaply-sandbox-preview` builds from `sandbox` on every commit. GitHub Pages copies build from `.github/workflows/pages.yml` only while the repository is public; they were retired on October 21 when it went private, came back on October 22, and go away again when the repository is made private at launch.
- `/dev.html` on the preview is the dev page **as it is on `sandbox`**, not the live site.
- GitHub, Actions, "Publish hosted sandbox and dev": did it run? It is disabled on purpose once the repository is private.
- `node check.js` builds the hosted copies too (`share/build-share.js --full`); a build failure shows there.
- Browser cache: scripts are cached a year under hashed names; pages are `no-store`. Hard reload.

**Fix:** a failed build: fix on `sandbox`. A Render static site that did not build: Render, `uaply-sandbox-preview`, Events (owner access). Pages after the repository went private: expected, use the Render preview.

**Source:** `.github/workflows/pages.yml` header; `HANDOFF.md` instances table; `docs/runbook-launch.md` step 1.5; `CHANGELOG.md` "Apply wording ... caching".

## 12. Payments: a plan did not unlock, or a test card unlocked nothing

**Symptom:** a person paid but still shows Free; or the test card does nothing on the live site.

**Check:**
- Live site payments are in Stripe **test** mode today (`HANDOFF.md`). A live server ignores test-mode events, so test cards cannot unlock a plan once live keys are set. That is intended.
- A plan changes only from a signed webhook, and UAply re-reads the subscription from Stripe. Stripe, Developers, Webhooks, the endpoint: every delivery should be 200. A failed delivery shows the reason; Stripe retries for up to three days.
- Start-up line: `payments: on, LIVE mode` (or TEST mode) and nothing in capitals after it; `NO WEBHOOK SECRET` or `OFF:` names what is missing.
- Only the exact Plus and Pro prices count. A wrong `STRIPE_PRICE_PLUS` / `STRIPE_PRICE_PRO` means no plan.
- `UAPLY_PLANS_HIDDEN=1` hides paid plans and `/api/billing/checkout` answers 403.

**Fix:** all Stripe and Environment changes are owner only. Never refund, cancel or change a subscription yourself. Code bugs: reproduce with `tools/mock-stripe.py` and `python tools/test-billing.py`, fix on `sandbox`.

**Source:** `DEPLOY.md` section 4 (steps 5, 6 and 8); `HANDOFF.md` October 17 Bot 4 notes; `billing_api.py` header.

## 13. Disk filling up

**Symptom:** self-check warns under 100 MB free; `could not save` in logs.

**Check:** `selfCheck.disk.freeMB`, `usedPercent`; Render, Disks. Old backups in `/var/data/backups/` (the tool keeps the newest 4 with `--keep 4`).

**Fix:** owner only. Remove old backups after copying them off Render, or ask the owner about a bigger disk (costs money).

**Source:** `DEPLOY.md` "The owner's self-check" and "Backups"; `docs/runbook-launch.md` section 8.

## 14. "Could not reach the server" on a laptop

**Symptom:** the local app at localhost:8766 or 8767 says "Could not reach the server".

**Check:** are the servers running? A computer restart stops them.

**Fix:** double-click `start-uaply.bat` (Windows) or run the `serve.py` commands (page 03). If ports are taken, close the old "UAply ..." windows first: a second prod would not get its port.

**Source:** `README.md`; `start-uaply.bat`; `docs/runbook-launch.md` section 10.

## 15. A new file in shared/ answers 404 locally, or old code keeps running

**Symptom:** a script newly added to `shared/` answers 404 on a local server; behaviour does not match the code on disk.

**Check:** log line `code changed on disk, restart me`; response header `X-UAply-Stale: restart`. Servers started before a file was added used to 404 it until restarted (Mohammed hit this on October 22).

**Fix:** restart the local servers. Servers started after the stale-server fix serve new `shared/` files without a restart.

**Source:** commit "Local servers: files added to shared/ are served without a restart" (merged as `3482db1`); `tools/test-stale-server.py`.

## 16. Browser tests cannot start

**Symptom:** `tools/cdp.js` fails to find Chrome; many `ui-*` groups fail at once.

**Check:** is Chrome, Chromium or (on Windows) Microsoft Edge installed in a usual place (on Windows, Chrome per-user or in Program Files)? Edge is used only when no Chrome is found.

**Fix:** set `UAPLY_CHROME=/path/to/chrome` (in PowerShell `$env:UAPLY_CHROME = "C:\path\to\chrome.exe"`).

**Source:** `CONTRIBUTING.md`; `HANDOFF.md` (dev branch, October 17, Bot 1: `tools/cdp.js` finds Chrome through `UAPLY_CHROME`, the Windows path, Playwright's Chromium or the Mac app).

## 17. People on an old address see "UAply has moved"

**Symptom:** visitors at `uaply.onrender.com` or `www.uaply.net` get a 301 or a "moved" page and are signed out once.

**Check:** `UAPLY_PUBLIC_URL=https://uaply.net` is set. Pages on other addresses get a 301; `/api/` and `/healthz` are never moved (so webhooks and Google's callback keep working). The home page of an old address offers "Save a backup" when that browser holds a profile.

**Fix:** none needed; it is intended. People sign in again at uaply.net and their account is on the server.

**Source:** `DEPLOY.md` step 3, `UAPLY_PUBLIC_URL`.

## 18. Broken release: decide between fixing and rolling back

**Symptom:** something important broke right after a release.

**Check:** is it a setting (fix in Environment, owner) or code? How long has it been broken?

**Fix:** site down or sign-up broken for 10 minutes and not a setting, or 5xx for 15 minutes: roll back (page 04). Then fix forward on `sandbox` and release again. Data damage: restore a backup (page 04).

**Source:** `docs/runbook-launch.md` section 9; `DEPLOY.md` "Rolling back".
