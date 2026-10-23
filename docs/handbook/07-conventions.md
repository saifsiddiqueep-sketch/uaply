# 07 Conventions

## Code style

### Python (server)

- **Standard library only** for the server. `requirements.txt` lists only optional packages (`pypdf`, `anthropic`), and the server must still run without them (a PDF then gets "use a Word or text file for now").
- Python 3.12 (Render and CI).
- CI runs Ruff with the "this will crash" rules only: `python -m ruff check --select E9,F63,F7,F82 .` (syntax errors, undefined names, invalid comparisons). Keep it clean.
- Each module starts with a docstring that says, in plain words, what it does and where it keeps things. Follow that pattern in new modules.
- Every route that changes data checks sign-in and limits on the server, even if the front end already does (example: the minimum to apply is checked in `uaply_api._validate` as well as in the app).
- Log lines start with `[uaply]` and never contain an IP address, query string, cookie, email address or secret.

### JavaScript and HTML (front end)

- Do not edit `prod/index.html` for sandbox or dev features. Write an experiment in `shared/`.
- Pages must work at the phone and computer sizes the tests use: 390x844, 375x667, 440x956 and 1280x800, plus turned phones 667x375, 844x390, 832x384 (`HANDOFF.md`, `CHANGELOG.md`).
- Tap targets at least 44 px; text at least 14 px on tracker figures (`CHANGELOG.md`, Galaxy walk fixes).
- The tap and focus style is one rule, `shared/uaply-focus.css`, copied word for word into every page; `python tools/test-focus.py --sync` rewrites the copies after a change.
- Line endings are LF (`.gitattributes`).

## The experiment pattern and `once()`

The sandbox and dev pages never change `prod/index.html` on disk. `shared/uaply-envs.js` reads it, each experiment patches a copy in memory, and the result runs in a frame with its own browser storage key.

Every experiment file defines the same helper:

```
function once(src,a,b){if(src.indexOf(a)<0)throw new Error("patch target not found: "+a.slice(0,40));return src.replace(a,function(){return b})}
```

What it means for you:

- `once(src, target, replacement)` replaces the **first** exact match of `target`. If the target text is not there, it **throws**. That is on purpose: a patch that silently does nothing is worse than a loud failure.
- Pick a target string that is unique and unlikely to change. The function form of `replace` means `$` signs in the replacement are taken literally.
- When you change `prod/index.html` or an earlier experiment, a later patch may lose its target. `node check.js` applies the core experiments to `prod/index.html` ("Every experiment still applies to the production page") and fails with the missing target.
- Some features add hooks into `shared/uaply-nav.js` (for example `shareJob`, and the four guarded hooks for the sign-up card); `check.js` fails if a hook goes missing.

### Switching an experiment on

- **Sandbox:** `sandbox/index.html` shows a chip per experiment (from `UAplyEnv.FEATURES`), with "All" and "Reset".
- **Dev (the release build):** `dev/index.html` lists the experiments that are on in the `PROMOTED` array and sets `release:true` in `window.UAplyOpts`. Adding a name to `PROMOTED` **ships it to the live site** at the next release. That is a product decision for the owner, not a code tidy-up.
- Features that must stay sandbox-only (Hiring mode, the emailed-code sign-up) check the instance name in the server code.

## Branches, commits and pull requests

- Branch from `origin/sandbox`; PR into `sandbox`; release PR `sandbox` into `dev` (page 02).
- **Commit and PR titles:** `<area>: <what changed, in plain words>`. Example from `CONTRIBUTING.md`: `Emails: right swipe now sends a clear, labelled receipt`. History examples: `Sign-in gate: ...`, `Feeds: ...`, `Hosting: ...`.
- Commit bodies explain why, list what changed by area, and end with the tests and their counts (see any recent commit on `sandbox`).
- Merge with a merge commit, not squash, so `dev` keeps the history (`docs/runbook-launch.md` section 1.2).
- **PR description:** the template in `.github/pull_request_template.md`: Summary, Where it is going, What changed, What users or teammates will notice, How it was tested (the three check boxes), Risks, Not done. Plus plain-English bullets: what, why, where, how checked. No pasted code.
- Credit the person who asked for or designed the change in the CHANGELOG (the repository does this: "Mohammed's design", "Saif, October 22"). Recent commits on `sandbox` carry an AI tool co-author line; whether new contributors should add or omit such lines: **TO CONFIRM with Saif/Mohammed**.
- Never commit secrets or data (page 06). Never force-push a shared branch.

## Tests

- New behaviour comes with a test. A bug fix comes with a test that **fails on the old code** and passes on the new one; say so in the CHANGELOG (for example "each fails on 512bf84").
- Python tests are `tools/test-*.py`; browser tests are `tools/ui-*.js` run through `tools/cdp.js`. Each prints `passed / total`.
- Add a new test to `tools/run-all-tests.sh`, and to `.github/workflows/check.yml` if it needs no browser, network or open port.
- Tests use stand-ins (`mock-google.py`, `mock-stripe.py`, `fake-smtp.py`, `mock-ats.py`) and throwaway data folders. Never real services, never the live site (except the read-only live checks).

## Changelog

- Every change adds an entry under `## Unreleased (sandbox)` at the top of `CHANGELOG.md`.
- Entry shape: a `###` heading naming the change (and who designed or asked for it, with the date), then bullets with a bold lead phrase, then a `Tests:` bullet with file names and counts.
- At release, the Unreleased items move under `## 1.0.0-rc.N (dev, <date>)` and the tag `v1.0.0-rc.N` is pushed (page 04).
- After launch day, add a short note of what was seen in the first day (`docs/runbook-launch.md` section 11).

## The honesty rule in words people see

UAply never tells a person something happened when it did not. The repository applies this everywhere; keep doing it:

- **Outcomes are exact.** A swipe right says sent, saved, finish on their site, or failed. "Never a plain 'Applied' for an application nothing was sent for" (`CHANGELOG.md`). A Job Tracker row says Sent only when it was sent (or the employer's confirmation page appeared, in assisted apply).
- **The card tells the truth before the swipe:** "Ready" or "N answers needed", from the same plan the swipe would use (`CHANGELOG.md`, Apply journey fixes).
- **Wording follows the route:** "Apply instantly" and "Opens employer site" were removed because they were not always true (`CHANGELOG.md`, Apply wording).
- **No promises the server cannot keep:** the Account screen does not promise a receipt where email is off; sign-up on a hosted site without email does not promise receipts (`HANDOFF.md` October 17).
- **No job counts anywhere a person sees** (the owner's rule, `CHANGELOG.md`).
- **Previews say what they are.** Hosted copies with no server use preview wording.
- **The release build never says "test version", "test inbox", "sandbox", "simulated", or names the coding tools.** `check.js` fails if a release help answer does.
- **Never invent an answer** for an employer's form. Ask once and remember.
- **Legal pages say "draft, not reviewed by a lawyer"** until the attorney reviews them.
- A "starting up" or outage screen must not promise a time to come back; it says it checks by itself (team rule from Mohammed; the screen retries `/healthz`).

## Words and names

- The product is spelled **UAply** (capital U, capital A, lower-case ply).
- The middle tab is **Job Tracker** (it used to be Dashboard; internal ids did not change).
- Plain English, short sentences, no jargon in anything a user reads. The PR template asks the same for engineering text.
