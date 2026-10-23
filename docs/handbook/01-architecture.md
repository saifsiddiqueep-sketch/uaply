# 01 Architecture

## The short version

One Python process, using only the Python standard library, serves both the web pages and the API (`serve.py`; `requirements.txt` says "The server runs on the Python standard library alone"). It runs on one Render web service with a 1 GB disk. Data is a SQLite file plus JSON and JSONL files on that disk. The front end is one HTML app (`prod/index.html`) that the server patches in memory with "experiments" from `shared/`. Outside services: Cloudflare (domain), Render (hosting), Brevo (email), Google (sign-in), Stripe (payments), public job boards (jobs), employers' hiring systems (applications), and optionally an AI provider for help answers.

## Diagram

```
                         Visitor (browser, Android app, iPhone app)
                                         |
                                         v
                  Cloudflare  (uaply.net, www; proxied, SSL/TLS Full (strict))
                                         |
                                         v
         Render web service "uaply"  (Starter: 0.5 CPU, 512 MB, Virginia; branch dev)
         +-------------------------------------------------------------------+
         |  python serve.py $PORT dev --api                                  |
         |                                                                   |
         |  serve.py  -- static pages: dev/index.html + prod/index.html      |
         |     |         patched by shared/uaply-*.js (experiments)          |
         |     |                                                             |
         |     +-- /api/auth/*      auth_api.py, google_auth.py, jwt_rs256.py|
         |     +-- /api/jobs        jobs_api.py  ----------> public job boards|
         |     +-- /api/apply*      uaply_api.py, autofill.py, ats_api.py ---> employers' hiring systems / email
         |     +-- /api/billing/*   billing_api.py  -------> Stripe           |
         |     +-- /api/chat        chat_api.py  ----------> AI provider (optional, off today)
         |     +-- /api/email/events  mailer.py <---------- Brevo webhook     |
         |     +-- /api/profile/resume  resume_parse.py (pypdf, sandboxed)   |
         |     +-- /setup, /outbox, /feedback  setup_api.py (owner only)     |
         |     +-- /healthz, /api/status                                     |
         |                                                                   |
         |  mailer.py / emails.py  -- SMTP --> Brevo relay --> inboxes       |
         |                                                                   |
         |  Disk /var/data (UAPLY_DATA_DIR): uaply.db (SQLite), *.json,      |
         |       *.jsonl, backups/                                           |
         +-------------------------------------------------------------------+

   GitHub repo saifsiddiqueep-sketch/uaply
     sandbox --> Render static site "uaply-sandbox-preview" (preview pages, no server)
     sandbox, dev --> GitHub Pages copies (only while the repo is public)
     dev --> Render web service "uaply" (the live site)
```

Sources: `HANDOFF.md` (instances table), `DEPLOY.md` section 1 and "Running the live site", `serve.py` header, `render.yaml`, `.github/workflows/pages.yml`.

## Components

### Server modules (repository root)

| File | What it does |
|---|---|
| `serve.py` | The web server. Serves the pages, routes `/api/*` to the modules below when started with `--api`, health check, headers, rate limits, the visitor's real address behind Cloudflare (`client_ip`), canonical-address redirects (`UAPLY_PUBLIC_URL`), the start-up log line and daily summary line. |
| `auth_api.py` | Accounts: sign up, sign in, sign out, delete, verify email with a 6-digit code, password reset, sessions. Keeps accounts in a SQLite file `uaply.db`. Contract: `docs/ACCOUNTS.md`. |
| `google_auth.py`, `jwt_rs256.py` | "Continue with Google" (OAuth code flow with PKCE) and checking Google's signed tokens with the standard library. |
| `jobs_api.py` | Reads job postings from public boards (Greenhouse, Lever, Ashby, SmartRecruiters, USAJOBS, The Muse, Jobicy, Workable, careers sites and others), cleans them, de-duplicates, gives each a stable id (`job-ids.json`), keeps a saved copy (`jobs-cache.json`). |
| `uaply_api.py` | Swipe right (`POST /api/apply`) builds and delivers an application; swipe left (`POST /api/decision`) records a pass. Checks the minimum to apply on the server. |
| `autofill.py` | Reads an employer's public application form and answers it from the profile. Never guesses; a question the profile cannot answer is asked once. |
| `ats_api.py` | Sends an application straight into an employer's hiring system, only with a key that employer created. |
| `billing_api.py` | Plans through Stripe Checkout, the billing portal and signed webhooks. A plan changes only from a verified webhook. |
| `mailer.py` | The one place all email is sent: daily quota guard, held mail, retries, bounce list. |
| `emails.py` | Builds the email bodies (receipts, owner copies). |
| `chat_api.py` | The help assistant. Answers from `help/articles.json`; AI answers only when a key is set and the person agrees. |
| `setup_api.py` | The owner's `/setup` page: what is on, test email, test an employer connection. Never shows a secret. |
| `employers_api.py` | Hiring mode (employers post jobs). **Sandbox only.** |
| `resume_parse.py` | Reads a resume (PDF via `pypdf` in a limited separate process, Word, text) and returns profile fields. Nothing is kept. |
| `ui_rules.py` | The shared tap and focus style for pages the server builds. |

### Front end

- `prod/index.html`: the original single-page app. It is never edited by sandbox or dev.
- `shared/uaply-*.js`: "experiments". Each one patches a copy of `prod/index.html` in memory (see page 07, the `once()` pattern). Examples: `uaply-nav.js` (navigation, readiness rule `READY_MIN`), `uaply-live.js` (real jobs, Job Tracker), `uaply-profile.js`, `uaply-learn.js` (learns from swipes), `uaply-signup.js` (sign-up card and sign-in gate), `uaply-share.js` (Share this job, sandbox only), `uaply-assist.js` (assisted apply), `uaply-chat.js`, `uaply-envs.js` (the engine that reads, patches and runs the app in a frame).
- `sandbox/index.html`: shows experiment chips you can switch on and off; its own browser storage key.
- `dev/index.html`: the release build. It turns on a fixed list of experiments (`PROMOTED` in the file) and sets `release:true` in `window.UAplyOpts`. `check.js` fails if `release:true` is lost or the developer bar is not hidden.
- Other served files: `shared/uaply-sw.js` (service worker, keeps only the offline screen), `shared/uaply-offline.html`, `shared/uaply.webmanifest`, `legal/` pages, `help/articles.json`.

### Mobile

- `mobile/`: a Capacitor wrapper that opens https://uaply.net (`mobile/capacitor.config.json`). Android build script `mobile/build-android.ps1`; native assisted apply in `mobile/android` (`AssistPlugin`, `AssistActivity`).
- `codemagic.yaml`: builds `mobile/ios` on Codemagic's cloud Mac and sends it to TestFlight.
- `mobile/twa/`: a Trusted Web Activity setup for Google Play; `mobile/store/play/`: the Play listing pack; `docs/play-store.md`.

## Request flow: a swipe right

1. The browser loads `https://uaply.net/`. Cloudflare forwards to Render. `serve.py` serves `dev/index.html`, which loads `prod/index.html` and the experiment scripts and runs the patched app in a frame.
2. Signed out, the sign-in gate shows the sign-up card only. Data routes answer `401` with `"code": "signin"`; an unverified address gets `403` `verify` where a verified email is needed (`CHANGELOG.md`, "Sign-in, server side", October 22).
3. Signed in, the app asks `GET /api/jobs`. `jobs_api.py` answers from memory or the saved `jobs-cache.json`, and refreshes boards in the background (at most 3 boards at once).
4. Before the swipe, the card may ask `POST /api/apply/plan` to know whether the employer's form needs more answers ("Ready" or "N answers needed").
5. Swipe right sends `POST /api/apply`. `uaply_api.py` checks the minimum (name, email, a phone or a resume), then delivers by the employer's route: hiring system (`ats_api.py`), email or webhook, or a hand-off to the employer's site. It appends to `applications.jsonl` and `decisions.jsonl`.
6. `mailer.py` sends the receipt through Brevo, unless the daily quota says to hold it.
7. The app shows an honest outcome: sent, saved, finish on their site, or failed.

## Where data is stored

Server side, in the folder named by `UAPLY_DATA_DIR` (`/var/data` on Render, the 1 GB persistent disk; `./data` on a laptop). From `serve.py`, `auth_api.py`, `DEPLOY.md`, `tools/backup-data.py`:

| File | Holds |
|---|---|
| `uaply.db` | SQLite: accounts (email, password hash, names, verified flag, plan), sessions, handled Stripe event ids. |
| `applications.jsonl`, `decisions.jsonl` | Applications and swipe records. |
| `feedback.jsonl` | Help requests and feedback. |
| `employers.json` | Hiring mode data (sandbox). |
| `jobs-cache.json`, `job-ids.json` | Saved job list and stable job ids. Not in backups (rebuilt from the boards). |
| `mail-count.json`, `mail-suppressed.json` | Emails sent per UTC day; bounce list. |
| `mail-held.json` | Mail waiting for the next day (in the instance folder). |
| `question-stats.json`, `finish-digest.json` | Counts of questions employers asked; the daily "finish your application" reminder queue. |
| `backups/` | Backups made by `tools/backup-data.py`. |

On the person's device (browser storage): the profile (name, work picks, place), the resume file used for applications, and a copy of swipe rows for Job Tracker (`CHANGELOG.md`, "Sign-up, nothing hidden" and "Job Tracker keeps every row").

Locally, never committed: `uaply-config.json` (secrets for a laptop server), `uaply-partners.json`, `data/` (`.gitignore`).

## External services

| Service | Used for | Where configured | Owner |
|---|---|---|---|
| Render | Hosting the live site (`uaply`) and the static preview (`uaply-sandbox-preview`) | Render dashboard; `render.yaml` is only a reference because the live service was made by hand | Saif |
| Cloudflare | DNS and proxy for uaply.net; Email Routing for replies to the uaply.net address | Cloudflare dashboard | Saif |
| GitHub | Code, pull requests, CI ("Check the code"), Pages previews while the repo is public | `.github/workflows/` | Saif (repo owner) |
| Brevo | Sending email (SMTP relay), bounce webhook | `smtp` block in `UAPLY_CONFIG_JSON`; `email_events_secret` | Saif |
| Google Cloud (Google Auth Platform) | "Continue with Google" | `google` block in `UAPLY_CONFIG_JSON`; `DEPLOY.md` section 3 | Saif |
| Stripe | Plus and Pro plans | `STRIPE_*` settings in Render; `DEPLOY.md` section 4 | Saif |
| Job boards | Postings (Greenhouse, Lever, Ashby, SmartRecruiters, USAJOBS, The Muse, Jobicy, Workable, careers sites) | `UAPLY_FEEDS`, `feeds` and `feed_keys` in `UAPLY_CONFIG_JSON`, `UAPLY_USAJOBS_KEY`; `docs/job-sources.md` | Saif |
| Employers' hiring systems | Applications for connected employers | Keys saved through `/setup` (owner only); `docs/employers/` | Saif |
| AI provider | Optional AI answers in the help chat (off today) | `ANTHROPIC_API_KEY` | Saif |
| UptimeRobot | Outside uptime email alerts | `docs/uptime.md` (owner sets up) | Saif |
| Trello | Task board "UAply Team Board" | trello.com | Both |
| Codemagic, Google Play Console, Apple | Phone app builds and stores | `codemagic.yaml`, `docs/play-store.md` | Mohammed (TO CONFIRM with Saif/Mohammed who holds the store accounts) |

## Limits to keep in mind

- One instance only: a Render service with a disk cannot run more than one copy, and each deploy has a few seconds of downtime (`DEPLOY.md`).
- 512 MB memory. Job board reads were the memory problem in October (page 05, runbook 2).
- Brevo free plan: 300 emails a day (`DEPLOY.md` section 5).
