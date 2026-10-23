# 00 Start here

## What UAply is

UAply is a job-swiping app. A person sees one job card at a time. Swipe right to start an application, swipe left to pass (`README.md`).

What a swipe right really does depends on the employer (`HANDOFF.md`, `CHANGELOG.md`):

1. **Straight into the employer's hiring system** when that employer connected its own key (Greenhouse, Lever, Ashby, SmartRecruiters, Workable; `ats_api.py`).
2. **By email or signed webhook** to an employer who agreed to receive applications that way (`uaply_api.py`, `EMPLOYERS.md`).
3. **Otherwise: saved, with a receipt and every answer ready**, and the person finishes on the employer's own page. In the Android app, "assisted apply" fills the employer's form and the person taps Submit themselves (`docs/assisted-apply.md`).

Jobs come from public employer job boards and careers pages (`jobs_api.py`, `docs/job-sources.md`). There are plans: Free, Plus ($9.99 a month) and Pro ($19.99 a month), paid through Stripe (`billing_api.py`, `DEPLOY.md` section 4). As of October 22, payments run in Stripe **test** mode on the live site (`HANDOFF.md`).

The live site is **https://uaply.net** (Cloudflare in front of Render). There is an Android app and an iPhone project under `mobile/`.

## The 10-minute orientation

Do these in order. You need read access to the GitHub repository (see page 06 for access levels).

1. **Minute 0 to 2. Read `HANDOFF.md` on the `sandbox` branch.** It is the single page that says what runs where today and the owner's rules. Older copies on other branches are out of date (the copy on `dev` is from October 17).
2. **Minute 2 to 4. Look at the three branches.**
   - `sandbox`: the test bench. Every experiment, each one switchable.
   - `dev`: the release build. **This is the live site.** A merge into `dev` is a production release.
   - `main`: the original page (`prod/index.html`). Only the owner changes it.
3. **Minute 4 to 6. Open the live site and its status.** Visit https://uaply.net. Then open https://uaply.net/healthz (should say `{"ok": true}`) and https://uaply.net/api/status (yes/no facts about what is switched on, plus the deployed commit).
4. **Minute 6 to 8. Skim the code map.** Python standard library server in the repository root: `serve.py` (the web server and router), `auth_api.py` (accounts), `jobs_api.py` (job feeds), `uaply_api.py` (applications), `billing_api.py` (Stripe), `mailer.py` and `emails.py` (email), `google_auth.py` (Google sign-in), `chat_api.py` (help assistant), `ats_api.py` and `autofill.py` (hiring systems). The front end is `prod/index.html`, patched in memory by experiments in `shared/uaply-*.js`. See page 01.
5. **Minute 8 to 10. Run the static check.** In a clone: `node check.js`. It should end with no `FAIL` lines. See page 03.

## Who owns what

From the brief for this handbook and `HANDOFF.md` ("server, hosting, email, domain, backups, releases and anything needing Saif's keys are Saif's side"):

| Area | Owner | Examples in the repository |
|---|---|---|
| Server side (Python back end) | Saif | `serve.py`, `auth_api.py`, `uaply_api.py`, `billing_api.py`, `ats_api.py` |
| Job feeds | Saif | `jobs_api.py`, `job-boards.json`, `docs/job-sources.md` |
| Hosting, deploys, domain, backups, releases | Saif | Render service `uaply`, Cloudflare, `render.yaml`, `DEPLOY.md`, `tools/backup-data.py` |
| Email sending | Saif | `mailer.py`, `emails.py`, Brevo |
| The app frame (outer pages that load the app) | Saif | `dev/index.html`, `sandbox/index.html`, `shared/uaply-envs.js` (TO CONFIRM with Saif/Mohammed: exact file list for "app frame") |
| Anything that needs Saif's keys or money | Saif | Render Environment, Stripe, Google Cloud, Brevo |
| Card UI and front end | Mohammed | `shared/uaply-nav.js`, `shared/uaply-signup.js`, `shared/uaply-share.js`, swipe card design |
| Mobile | Mohammed | `mobile/`, `codemagic.yaml`, `mobile/store/play/` |
| Docs | Mohammed | `docs/`, this handbook |

In the launch documents "owner" means Saif (`docs/runbook-launch.md`: "owner = Saif (anything with a password, a key, money or the phone)").

The Trello board has two "heads-up" lists, "Mohammed is working on" and "Saif is working on", one card per branch in progress. Glance at them before you touch a branch (page 02).

## How to get help

1. **Search first:** this space, then `HANDOFF.md`, `DEPLOY.md`, `docs/`, and `CHANGELOG.md` (search for the symptom words). Most past problems are written up there.
2. **Runbooks:** page 05 lists symptom, check and fix for the common failures.
3. **Ask on the card:** comment on the Trello card for your task on the "UAply Team Board" (https://trello.com/b/TUiuK5fz/uaply-team-board).
4. **Ask the area owner** (table above). How to reach Mohammed and Saif (chat tool, phone, response times): **TO CONFIRM with Saif/Mohammed**.
5. **Never** put a password, key or user's personal data in a question. Describe it by name.

The support mailbox for users is uaplytechnologies@gmail.com (`DEPLOY.md`, `SUPPORT_EMAIL`). It is for users, not engineering questions.

## Your first week

- Day 1: this page, page 01, page 06.
- Day 2: page 03; get `node check.js` and `bash tools/run-all-tests.sh` green on your machine.
- Day 3: pick a small Trello card, follow page 02 to a pull request into `sandbox`.
- Later: shadow one release (page 04) before you run one.
