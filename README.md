# UAply

A job-swiping app: swipe right to save a job and start an application, swipe left to pass.

There are three separate instances, each on its own branch:

| Instance | Branch | Local address | What it is |
|---|---|---|---|
| **Prod** | `main` | http://localhost:8765 | The original app (`prod/index.html`). Only the owner changes it. |
| **Dev** | `dev` | http://localhost:8767 | The near-final version. |
| **Sandbox** | `sandbox` | http://localhost:8766 | Every experiment, each switchable on or off. |

Sandbox and dev are the production page plus experiments from `shared/`. They read a copy of `prod/index.html` and
patch it in memory, so prod is never edited by them.

## Run it on your computer

Needs Python 3 and Node.

```bash
python serve.py 8765 prod
python serve.py 8766 sandbox --api
python serve.py 8767 dev --api
```

On Windows, double-click `start-uaply.bat` to start all three. Do this after every restart of the computer: a restart stops the servers, and
the app then says "Could not reach the server".

`--api` turns on the back end: real job postings from public employer feeds (`jobs_api.py`) and application delivery
(`uaply_api.py`). By default applications go to a simulated inbox at `/outbox` and nothing leaves your computer.

To email real recruiters, copy `uaply-config.example.json` to `uaply-config.json` and add your own mail login. That file
and the `data/` folder are ignored by git and must never be committed.

## Make a change from a link (no setup)

Open one of these, sign in to GitHub, edit the files in the browser, and commit. If you are not a collaborator, GitHub
copies the project to your account and sends your change to the owner as a pull request.

- Edit the sandbox: https://github.dev/saifsiddiqueep-sketch/uaply/tree/sandbox
- Edit dev: https://github.dev/saifsiddiqueep-sketch/uaply/tree/dev

The browser editor cannot run the app or the checks. The pull request runs the checks for you, and the hosted page
updates once the owner merges.

## Making a change on your computer

1. Branch from `sandbox` (for example `git checkout -b my-idea sandbox`), or fork the repository.
2. Edit the files in `shared/` (experiments), `sandbox/` or `dev/` (the two pages), or the Python back end.
3. Run `node check.js`. It checks every file for syntax errors and confirms every experiment still applies.
4. Push and open a pull request into `sandbox`. The same checks run automatically on the pull request.
5. The owner reviews and merges. Changes move up one step at a time: `sandbox`, then `dev`, then `main`.

A push to `sandbox` or `dev` also republishes that hosted page (see below). Nothing is published from `main`.

## Hosted copies

The previews are back (October 22, 2026, while the repository is public until launch). `.github/workflows/pages.yml` builds them
with `node share/build-share.js --full` after each push to `sandbox` or `dev` and publishes them on GitHub Pages:
https://saifsiddiqueep-sketch.github.io/uaply/sandbox.html and https://saifsiddiqueep-sketch.github.io/uaply/dev.html (also the
`.full.html` names and the older `/sandbox/` and `/dev/` addresses). The second copy is the Render preview,
https://uaply-sandbox-preview.onrender.com/sandbox.html. A static host cannot run the Python back end, so the hosted copies use the
example jobs only and say they are previews; real jobs and application sending need `serve.py --api` running somewhere.

## One-time repository setup (owner)

1. Create an empty repository on GitHub, then:
   ```bash
   git remote add origin https://github.com/saifsiddiqueep-sketch/uaply.git
   git push -u origin main dev sandbox
   ```
2. Settings, Pages: set the source to **GitHub Actions**. Then Settings, Environments, `github-pages`: under
   deployment branches allow `main`, `dev` and `sandbox` (by default only `main` may deploy, so a push to dev or
   sandbox would fail before it starts).
3. Settings, Branches: protect `main`, `dev` and `sandbox` (require a pull request and a passing "Check the code").
4. Who can change things:
   - **Anyone with the link, by proposal:** make the repository public. Anyone can fork it and open a pull request,
     but only you can merge.
   - **Trusted people, directly:** Settings, Collaborators, invite them. They can push branches and open pull requests.
   - Do not give strangers direct write access. This code can send email and handles applicants' details.


## Sign in with Google (free)

Accounts work with email and password out of the box. To also offer "Continue with Google":

1. In Google Cloud Console, create a project, then APIs and Services, Credentials, Create OAuth client ID, type Web application.
2. Add the redirect URI shown at `/api/auth/providers` (locally `http://localhost:8766/api/auth/google/callback`, on a host `https://your-site/api/auth/google/callback`).
3. Put the client ID and secret under `"google"` in the git-ignored `uaply-config.json` (see `uaply-config.example.json`) and restart.

Without those keys the Google button is hidden. `python tools/mock-google.py` and `python tools/test-google.py` test the whole flow
without a Google account; `node tools/cdp.js tools/ui-sweep.js` walks every screen in a headless browser.

## Setup checklist and password reset

Open `http://localhost:8766/setup` (owner only) to see what is on and what still needs a key: Google sign-in, email sending,
the copy of every application to you, and the optional AI assistant. It also has a "Send test email" button.

To add the keys without typing them anywhere public, run `python tools/setup-config.py`. It asks for the Google client ID and
secret, the Gmail address that sends UAply email and its App Password (typed hidden), and your own email, then saves them in the
git-ignored `uaply-config.json`. Restart the server afterwards.

Password reset works end to end: Log in screen, Forgot password?, a one-hour single-use link by email, then a new password
(which signs out every device). Signed-in people can also change their password. Until email sending is set up, reset emails
land in the test inbox at `/outbox` instead of reaching real people.

Tests: `python tools/test-reset.py`, `python tools/test-google.py` (with `tools/mock-google.py`), `node tools/cdp.js tools/ui-reset.js`
and `node tools/cdp.js tools/ui-sweep.js`.


## Release build (dev)

`dev` is what users get; `sandbox` is the test bench. Details and the owner's launch checklist are in `DEPLOY.md`, version notes in
`CHANGELOG.md`. The hosted GitHub Pages copy of dev is a static preview with no server (no accounts, no real jobs); run
`python serve.py 8767 dev --api` or deploy to Render for the real thing. To test the release build:

    node check.js
    W=390 H=844 PORT=8767 node tools/cdp.js tools/ui-release.js
    REL=1 PORT=8767 node tools/cdp.js tools/ui-sweep.js
