# 03 Local setup and tests

## What you need

| Tool | Version | Why |
|---|---|---|
| Git | any recent | the repository |
| Python 3 | 3.12 (Render runs 3.12.7, CI runs 3.12; `render.yaml`, `.github/workflows/check.yml`) | the server and the Python tests |
| Node | 20 (CI) | `check.js` and the browser tests |
| Google Chrome or Chromium | any recent | browser tests through `tools/cdp.js` (it finds Chrome on Windows, Mac, Linux or a Playwright Chromium; set `UAPLY_CHROME=/path/to/chrome` to choose) |
| Bash | Git Bash on Windows | `tools/run-all-tests.sh` |

The server needs no packages. Optional packages are in `requirements.txt`: `pypdf` (reads PDF resumes) and `anthropic` (AI help answers). The linters CI uses: `pyflakes`, `ruff`, `pyyaml` (for `tools/audit-files.py`).

## Get the code

```
git clone https://github.com/saifsiddiqueep-sketch/uaply.git
cd uaply
git checkout sandbox
```

The repository is private outside launch week; you need to be added as a collaborator (page 06). Always work from the newest `sandbox`. An old checkout has old docs (for example `HANDOFF.md` on `dev` is from October 17).

## Install

**Windows (PowerShell):**

```
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install pyflakes ruff pyyaml
```

On Windows `python` is sometimes only a Microsoft Store shortcut. `check.js` falls back to the `py` launcher by itself.

**Mac or Linux:**

```
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install pyflakes ruff pyyaml
```

## Run the app

The three local instances (`README.md`):

| Instance | Command | Address |
|---|---|---|
| prod (`main` page) | `python serve.py 8765 prod` | http://localhost:8765 |
| sandbox | `python serve.py 8766 sandbox --api` | http://localhost:8766 |
| dev (release build) | `python serve.py 8767 dev --api` | http://localhost:8767 |

**Windows shortcut:** double-click `start-uaply.bat`. It starts all three in minimized windows. Close a window to stop that server. After every computer restart, run it again, or the app says "Could not reach the server".

**Mac or Linux:** run the three commands above, each in its own terminal (or add `&`).

What `--api` does: turns on the back end (real job feeds, accounts, applications). By default applications go to a simulated inbox at `/outbox` and **nothing leaves your computer**.

### Useful local settings (environment variables)

| Setting | Effect | Source |
|---|---|---|
| `UAPLY_DATA_DIR=/some/folder` | keep data somewhere other than `./data` | `serve.py` |
| `UAPLY_SIGNUP_TEST=1` | sign-up is verified at once with no email, on a server that is not public only | `CHANGELOG.md`, Sign-in server side |
| `UAPLY_CONFIG_FILE=none` | ignore `uaply-config.json` | `tools/run-all-tests.sh` |
| `UAPLY_CONFIG_JSON='{...}'` | settings as one line of JSON instead of the file | `DEPLOY.md` |
| `UAPLY_FEEDS=greenhouse,lever,ashby` | which job feeds to read | `render.yaml` |
| `UAPLY_CHROME=/path/to/chrome` | which browser the tests drive | `CONTRIBUTING.md` |

### Owner pages on your computer

`/setup`, `/outbox` and `/feedback` are open on your own computer without a password (on a public server they need `OWNER_PASSWORD`). `/setup` shows what is on and has "Send test email".

### Real email or Google on your computer (only if your task needs it)

Run `python tools/setup-config.py`. It asks for the values (hidden typing) and saves them into the git-ignored `uaply-config.json`. Use **your own test accounts**, never the company's live values (page 06). For Google there is a stand-in: `python tools/mock-google.py` with `python tools/test-google.py`.

### A server running old code

A local server keeps running the code it started with. Since the stale-server fix, a local server that sees `serve.py` or an `*_api.py` newer than itself logs `code changed on disk, restart me` and answers with the header `X-UAply-Stale: restart`. Restart it.

## Run the tests

### Before every push (fast, 1 to 2 minutes)

```
node check.js
python tools/audit-files.py
```

- `check.js`: syntax of every script, every Python module compiles, JSON files parse, legal page markers, every experiment still applies to `prod/index.html`, the release flags in `dev/index.html`, the hosted builds. **Green looks like:** a list of `ok` lines and the last line `All checks passed.` Any `FAIL` line is a problem; the exit code is 1.
- `audit-files.py`: every file (JSON, Python, JS, HTML, links, XML, images), secret patterns, line endings, git hygiene. It fails if `uaply-config.json`, `uaply-partners.json` or a data backup is committed. Errors fail; warnings are for a human to read.

### What CI runs on every push and PR

`.github/workflows/check.yml` ("Check the code") on Ubuntu with Node 20 and Python 3.12:

```
node check.js
python -m ruff check --select E9,F63,F7,F82 .
python tools/test-pages.py
python tools/audit-files.py
python tools/test-jobs.py
python tools/test-verify.py
python tools/test-delivery.py
python tools/test-setup.py
python tools/test-emails.py
python tools/test-support.py
python tools/test-signin-contract.py
python tools/test-chat.py
python tools/test-ats.py
python tools/test-ats-ashby.py
python tools/test-ats-smartrecruiters.py
python tools/test-ats-flow.py
python tools/test-billing.py
python tools/test-autofill.py
python tools/test-resume.py
python tools/test-render.py
python tools/test-self-check.py
```

You can run any of these alone. Each prints a `passed / total` line such as `42 / 42`.

### Everything (before review, 10 minutes or more)

```
bash tools/run-all-tests.sh
```

On Windows run it in Git Bash. It starts its own throwaway servers on ports 18766, 18767, 18775, 18810 to 18814 and others, uses temporary data folders, ignores your `uaply-config.json`, never touches the live site, and stops everything at the end. No single check may run longer than 600 seconds.

It runs, in order: static checks; servers; job feed rules; email codes; delivery to employers; swipe-right emails; accounts, applying, reset and setup; screens in a real browser at iPhone size; Google sign-in against a stand-in; a public server behind HTTPS; real email against a stand-in mail server (`tools/fake-smtp.py`); a burst of 300 visitors; hostile input (`tools/fuzz-api.py`); and the after-deploy checks against local servers.

**Green looks like:** every line `PASS <label> (n / n)`, and the last line `ALL TESTS PASSED`. Otherwise it prints `FAIL <label>` with the last 15 lines of that test, and ends with `N test group(s) FAILED`.

Some groups need the real public job boards (network). In a network-restricted environment they can fail for that reason alone (`HANDOFF.md` October 17: "41 of 48 groups pass in the cloud (the rest need the live job feeds)").

### One browser test alone

Browser tests are `tools/ui-*.js`, run through `tools/cdp.js`, against a server you started. Examples from `README.md`:

```
W=390 H=844 PORT=8767 node tools/cdp.js tools/ui-release.js
REL=1 PORT=8767 node tools/cdp.js tools/ui-sweep.js
node tools/cdp.js tools/ui-reset.js
```

In PowerShell set the variables first: `$env:W=390; $env:H=844; $env:PORT=8767; node tools/cdp.js tools/ui-release.js`.

### Stand-ins (never call real services in tests)

| Stand-in | Pretends to be |
|---|---|
| `tools/mock-google.py` | Google sign-in |
| `tools/mock-stripe.py` | Stripe |
| `tools/fake-smtp.py` | the mail server |
| `tools/mock-ats.py` | Greenhouse, Lever, Ashby, SmartRecruiters, Workable |

### Checks of a running site (read only)

| Command | What |
|---|---|
| `python tools/live-check.py --base https://uaply.net --expect all` | health, headers, gate, owner pages closed, email, Google, payments, disk, and "the site runs the latest push". Never signs up or sends email. |
| `node tools/cdp.js tools/ui-live.js --base https://uaply.net --read-only` | a stranger's first visit in a browser |
| `bash tools/launch-smoke.sh https://uaply.net` (or `powershell -File tools\launch-smoke.ps1 https://uaply.net`) | both of the above plus a timed `/healthz`, with one summary file |
| `node tools/phone-walk.js live` | the Galaxy phone walk over USB (needs `ADB`); see `docs/runbook-launch.md` step 5 |

Run these against the live site only when your task or a release calls for it. They are read only, but they still count as traffic.
