# How we work on UAply

## Branches
- `sandbox`: the test bench. Try things here first.
- `dev`: the release build. This is what the hosted site and the phone apps run.
- `main`: production. It changes only when the owner decides.

Work moves **sandbox, then dev, then main**, always through a pull request. Nothing is pushed straight to `dev` or `main` for a
change someone else should review.

## Pull requests (every one, no exceptions)
1. **Title:** `<area>: <what changed, in plain words>`. Example: `Emails: right swipe now sends a clear, labelled receipt`.
2. **Description:** fill in the template that opens automatically. Write for someone who joins in a year: what changed, why, how
   it was tested, what could go wrong, and what is still not done. Do not paste code; the diff shows it.
3. **Say where it is going** (sandbox to dev, or dev to main) and which instance it affects.
4. **Checks must pass** before merging: `node check.js`, `python tools/audit-files.py`, and ideally `bash tools/run-all-tests.sh`.
5. After merging to `dev`, add an entry to `CHANGELOG.md` and tag the release (`v1.0.0-rc.N`, later `v1.0.0`).

## Before you push
    node check.js                   # syntax of every script, Python lint, JSON, legal pages, release flags, hosted builds
    python tools/audit-files.py     # every file: JSON, Python, JS, HTML, links, XML, images, secrets, line endings, git hygiene
    bash tools/run-all-tests.sh     # servers, accounts, emails, jobs, Google, public server, and every screen at iPhone size

The browser tests find Chrome by themselves (Windows, Mac, Linux, a Playwright Chromium); set `UAPLY_CHROME=/path/to/chrome` to pick another one.

## Things that must never be committed
`uaply-config.json` (keys, passwords), `uaply-partners.json`, and the `data/` folder. `tools/audit-files.py` fails if they are.
