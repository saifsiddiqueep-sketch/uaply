# 04 Deploy and rollback

Owner of this whole page: **Saif** (hosting and releases). A contractor runs these steps only when Saif asks, with the access Saif grants (page 06). Full originals: `DEPLOY.md` ("Running the live site") and `docs/runbook-launch.md`.

## Render services

| Service | Type | Branch | Address | Notes |
|---|---|---|---|---|
| `uaply` (`srv-db9i3i6q1p3s738b5b4g`) | Web service, Python, Starter (0.5 CPU, 512 MB), Virginia | `dev` | https://uaply.onrender.com, reached as https://uaply.net through Cloudflare | The live site. 1 GB disk at `/var/data`. Made by hand in the dashboard, so `render.yaml` does **not** change it. |
| `uaply-sandbox-preview` | Static site | `sandbox` | https://uaply-sandbox-preview.onrender.com/sandbox.html and /dev.html | Builds `share/build-share.js --full` on every commit to `sandbox`, which embeds every shared script the pages list, the sign-up card included (PR #63, `share/build-share.js`). No server, example jobs only: the card is not used there and Account says it is a preview. |

Workspace: `tea-db9duku1egvs73et93k0`. There is **no** sandbox web service on Render today; the sandbox with a server runs only on a laptop (`HANDOFF.md`). `render.yaml` describes `uaply-dev` and `uaply-sandbox` services for a fresh setup from a Blueprint; it is a reference, not what runs.

Start command on Render: `python serve.py ${PORT:-10000} dev --api`. Build command: `pip install -r requirements.txt`. Health check path: `/healthz`.

### Live Environment settings (names only)

From `HANDOFF.md` and `docs/runbook-launch.md`. Values live only in Render's dashboard.

- From the Blueprint pattern: `PYTHON_VERSION`, `HOST=0.0.0.0`, `UAPLY_DATA_DIR=/var/data`, `MALLOC_ARENA_MAX=2`, `UAPLY_FEEDS`.
- Set by Saif: `OWNER_PASSWORD`, `SUPPORT_EMAIL`, `UAPLY_CONFIG_JSON` (SMTP, Google client, `public_url`, `delivery`, extra feeds), `UAPLY_PUBLIC_URL=https://uaply.net`, `UAPLY_USAJOBS_KEY`, `UAPLY_USAJOBS_EMAIL`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_PLUS`, `STRIPE_PRICE_PRO` (test mode today).
- Optional: `ANTHROPIC_API_KEY` (off today), `UAPLY_COS_USER_ID` and `UAPLY_COS_TOKEN` (CareerOneStop), `UAPLY_PLANS_HIDDEN=1` (free-only launch), `UAPLY_ASSETLINKS_SHA256` (Play app), `UAPLY_REQUEST_LOG=off`.

Every save in Environment restarts the service. Batch changes.

## How a deploy happens

1. A release PR from `sandbox` into `dev` is merged (page 02).
2. **Auto-deploy does not fire today.** Since October 17 every deploy has been started by hand or through Render's API (`DEPLOY.md`, "Auto-deploy"). The fix is to link Render's GitHub app to the repository; it is on Saif's list (`HANDOFF.md`, item 3). Until then:
   - Render, `uaply`, **Events**. If no deploy for the new commit started within 2 minutes, press **Manual Deploy**, **Deploy latest commit**.
3. Render stops the old copy before starting the new one (a service with a disk cannot do zero-downtime). Expect a few seconds of `502` to visitors. The old copy answers `503` to the health check, finishes requests in progress (at most 15 seconds), logs `[uaply] daily {...}` and `[uaply] stopped`.
4. Good: Events says **Deploy live** for the new commit within about 3 minutes.
5. Logs: search `[uaply] dev on`. The newest start-up line must say `data: /var/data (persistent disk)`, `email: on`, `Google sign-in: on`, `payments: on` (TEST mode until live keys exist), `UAPLY_CONFIG_JSON: valid`, and `commit: <7 letters>` matching `git rev-parse --short origin/dev`.
6. Run the smoke check (read only):
   - Git Bash: `bash tools/launch-smoke.sh https://uaply.net`
   - PowerShell: `powershell -File tools\launch-smoke.ps1 https://uaply.net`
   Good: `result  no FAIL` and `site runs` is the new commit.
7. Tag and changelog: `git fetch origin && git tag -a v1.0.0-rc.N origin/dev -m "Release candidate N" && git push origin v1.0.0-rc.N`; move the CHANGELOG's "Unreleased (sandbox)" items under `## 1.0.0-rc.N (dev, <date>)` in a small follow-up PR.

To skip one deploy on purpose, put `[skip render]` in the commit message (`DEPLOY.md`).

### What is live now

The live site runs commit `9b76822` (the sign-in gate v2 release, deployed October 23; `git log -1 origin/dev`; HANDOFF calls it rc.14). The tags on GitHub are `v1.0.0-rc.1` to `v1.0.0-rc.13` (`git ls-remote --tags origin`, October 23): rc.14 is not tagged yet. The `CHANGELOG.md` on `sandbox` has no rc.12 or rc.13 headings.

## How to roll back

**When** (`docs/runbook-launch.md` section 9): the site is down or sign-up is broken for 10 minutes after a deploy and the cause is not a setting you can fix on the spot, or `5xx` answers keep coming for 15 minutes. Tell Saif first if you can reach him.

**Option A, two clicks (no key needed):** Render, `uaply`, **Events**, the deploy of the last good commit, **Rollback**.

**Option B, one command (needs a Render API key that Saif creates and keeps in his password manager; type it only into that one terminal window):**

PowerShell:

```
$env:RENDER_API_KEY = "<paste the key>"
Invoke-RestMethod -Method Post -Uri https://api.render.com/v1/services/srv-db9i3i6q1p3s738b5b4g/deploys -Headers @{Authorization = "Bearer $env:RENDER_API_KEY"} -ContentType "application/json" -Body '{"commitId": "<full commit id>"}'
```

Git Bash:

```
curl -s -X POST -H "Authorization: Bearer $RENDER_API_KEY" -H "Content-Type: application/json" -d '{"commitId": "<full commit id>"}' https://api.render.com/v1/services/srv-db9i3i6q1p3s738b5b4g/deploys
```

Get the full id with `git rev-parse "v1.0.0-rc.13^{commit}"`. rc.13 (the release before today's) is `e6aced4d950d7b83f5c1c803462205c32e55b227`; today's live commit is `9b76822` (`git rev-parse origin/dev` for the full id).

**After a rollback:**

1. `python tools/live-check.py --base https://uaply.net --expect all --commit <7 letters>` passes.
2. Close the terminal window (the key goes with it).
3. A deploy of a chosen commit leaves auto-deploy as it was: the next merge into `dev` deploys `dev` again. So **fix forward on `sandbox`** and release that. Merge nothing else into `dev` meanwhile.
4. A rollback does not touch the disk. If the data itself went wrong, restore a backup (below).

## Backups and restore

- First line: Render's daily disk snapshot (`uaply`, **Disks**, **Snapshots**, kept at least 7 days). Restoring one replaces the whole disk.
- Weekly consistent copy (owner): Render, `uaply`, **Shell**, `python tools/backup-data.py --keep 4`. It writes `/var/data/backups/uaply-backup-<time>.tar.gz` with a SHA-256 manifest. Take it off Render encrypted (`--encrypt`, passphrase from `UAPLY_BACKUP_PASSPHRASE`) by magic-wormhole or to a private GitHub repo (`--upload`). Steps: `DEPLOY.md`, "Backups".
- Restore: put the file on the disk, `python tools/backup-data.py --restore <file> --yes` (it checks the manifest and backs up the current state first), then **Manual Deploy**, **Restart service** at once.
- Backups hold password hashes, emails and applications. Never in a public place, a chat or the repository.

## How to read logs

Render, `uaply`, **Logs**. Search box takes plain text, `*` wildcards or `/regex/`. Time range top right; Live tail to watch. The free workspace keeps logs and metrics 7 days. What to search (`DEPLOY.md`):

| Search | Meaning |
|---|---|
| `[uaply] dev on` | The start-up line: what is on, the disk, the commit. |
| `stopping` / `stopped` | A deploy's stop. |
| `[uaply] daily` | One JSON line per day at midnight UTC (and at each stop): requests, 2xx to 5xx, 429, sign-ups, logins, applications, `p50_ms`, `p95_ms`, slowest paths, memory now and peak. |
| `[uaply] GET /api/` / `[uaply] POST /api/` | One line per API request: method, path, status, milliseconds. Never an IP, query string, cookie or email. |
| `failed:` | A server error and its reason. |
| `job feed` | A board that could not be read. |
| `could not save` | A write to the disk failed. |
| `email not sent` | A mail problem, with the reason and whether it is held. |
| `Traceback` | A Python crash. |

Also:

- **Metrics** (`uaply`, Metrics): CPU, memory, HTTP requests by status code.
- **Self-check**: open https://uaply.net/setup with the owner password, then https://uaply.net/api/status in the same browser. `selfCheck` shows when a board was last read, when an email last went out, disk free space, and plain `warnings`. `ok: true` when there are none.
- **Feed health** (owner): https://uaply.net/api/feed-health.
- **Brevo**: Statistics and Logs for email.
- **Stripe**: Developers, Webhooks, the endpoint's deliveries (should be 200).

## Capacity: when to ask about a bigger plan

`DEPLOY.md` "Capacity": Starter is enough for launch week. Ask Saif about Standard ($25 a month instead of $7; he approves any money) when, for a day: memory above 400 MB, an "out of memory" restart in Events, CPU above 0.4 for 10 minutes outside a board refresh, or `p95_ms` in the daily line above 1500.

## Phone apps (summary)

- Android: `powershell -ExecutionPolicy Bypass -File mobile\build-android.ps1` (test `.apk`), add `-Release` for the signed `.aab`. Raise `versionCode` in `mobile/android/app/build.gradle` before each upload. The upload key file is git-ignored and must never be committed.
- iPhone: `codemagic.yaml` on Codemagic, to TestFlight. Needs the App Store Connect key in Codemagic.
- Store accounts and signing keys: none exist yet (no Google Play developer account, no Apple developer account, no upload or signing key; Saif, October 23). `docs/play-store.md` step 6 is still to do.
