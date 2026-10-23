# 06 Security and money guardrails

Read this page fully before your first task. These rules let the founders step back without taking on security or financial risk. When a rule and a deadline conflict, the rule wins; ask.

## The five rules that never bend

1. **Never commit, paste or type a secret value** into code, a commit, a pull request, Trello, Confluence, a chat or a log. Refer to secrets by their setting name only (`HANDOFF.md`: "Never type the owner's secrets (keys, passwords) into chat, commits or files").
2. **Nothing that spends money without Saif's yes first.** That includes Render plan or disk changes, Brevo, Stripe products, app store fees, paid tools (`HANDOFF.md`: "Ask before any purchase").
3. **A merge into `dev` is a production release.** Only through a reviewed PR, and only with Saif's approval (page 02).
4. **No production user data leaves production.** No copying accounts, applications or backups to a laptop, a chat or a ticket.
5. **No automation against job boards or hiring systems beyond what the rules allow** (below).

## Where secrets live

| Secret (name only) | Where it lives | Who holds it |
|---|---|---|
| `OWNER_PASSWORD` (owner pages `/setup`, `/outbox`, `/feedback`) | Render, `uaply`, Environment | Saif |
| `UAPLY_CONFIG_JSON` (Brevo SMTP login and key, Google client ID and secret, `email_events_secret`, `public_url`, `delivery`, feed keys) | Render Environment | Saif |
| `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_PLUS`, `STRIPE_PRICE_PRO` | Render Environment; Stripe dashboard | Saif |
| `UAPLY_USAJOBS_KEY`, `UAPLY_USAJOBS_EMAIL`, `UAPLY_COS_USER_ID`, `UAPLY_COS_TOKEN` | Render Environment | Saif |
| `ANTHROPIC_API_KEY` (AI help answers; off today) | Render Environment | Saif |
| Render API key (rollback command) | Saif's password manager; typed only into one terminal window | Saif |
| `UAPLY_BACKUP_PASSPHRASE`, `GITHUB_BACKUP_TOKEN` (off-site backups) | Saif's password manager; typed only into the Render Shell session | Saif |
| Employers' hiring system keys (Greenhouse, Lever, Ashby, SmartRecruiters, Workable) | Saved on the server through `/setup` (owner only); never shown again | Saif |
| Local laptop settings | `uaply-config.json`, `uaply-partners.json` (git-ignored) | Whoever runs that laptop |
| Android upload key `mobile/android/uaply-upload-key.jks` and its password | Git-ignored file; backed up privately | Does not exist yet (Saif, October 23) |
| App Store Connect API key ("UAply ASC key") | Codemagic | Does not exist yet: there is no Apple developer account (Saif, October 23) |
| Cloudflare, GitHub owner, Google Cloud, Brevo, Stripe, Render, Trello, UptimeRobot logins | The founders' own accounts | Saif (Trello: both) |

Sources: `HANDOFF.md` ("Render's Environment for uaply (names only)"), `DEPLOY.md`, `render.yaml`, `docs/runbook-launch.md`, `.gitignore`.

### Guards already in the repository

- `.gitignore` excludes `uaply-config.json`, `uaply-partners.json`, `data/`, `uaply-backup-*`, `*.bak`.
- `tools/audit-files.py` (in CI) fails if those files or a data backup are committed, and scans for secret patterns (AI provider keys, AWS keys, Google client secrets, private keys).
- `check.js` never reads the owner's secret files (an error message could quote them).
- `render.yaml` marks every secret `sync: false`: typed into Render, never stored in the repository.
- `/setup` and `/api/status` show only whether a secret is set, never its value.
- Request log lines never contain an IP address, query string, cookie or email address.

### If a secret leaks

1. Tell Saif at once, by phone if needed. Say which setting, where it appeared, and when.
2. Do not try to "clean" history yourself and do not force-push.
3. Saif rotates the value at its source (Stripe, Google, Brevo, Render) and updates Render Environment.
4. Write down what happened on the Trello card (names only).

How to reach Saif urgently: **TO CONFIRM with Saif/Mohammed**.

## Stripe and live money

- Live keys go **only** into Render Environment for `uaply`, typed by Saif. "Never put a live key in a file, a chat or the sandbox; sandbox stays on test keys" (`DEPLOY.md` section 4).
- Today the live site runs Stripe in **test** mode. Going live needs the company formation, Stripe business verification, live prices and webhook, and the lawyer's paid-plan wording in `legal/terms.html` first (`HANDOFF.md` item 4; `DEPLOY.md` section 4 "Going live").
- A plan unlocks only from a signed, re-read webhook. Do not add any other way to set a plan.
- UAply never sees card numbers (Stripe Checkout). Do not build anything that collects card details.
- Contractors never refund, cancel, change prices, change Radar rules or touch payouts. Report the issue to Saif.

## Production data and privacy

- Production data is on the Render disk `/var/data` (accounts database with password hashes and emails, applications, feedback). Only Saif opens the Render Shell.
- Backups contain password hashes, emails and applications. Never in a public place, chat or the repository (`DEPLOY.md` "Backups"; `tools/audit-files.py` refuses a committed one).
- Use stand-ins and throwaway data for every test (`tools/run-all-tests.sh` uses temporary folders and never reads `uaply-config.json`). Never point a test at the live site except the read-only checks (page 03).
- Test sign-ups on the live site use addresses the founders own (for example the plus-address pattern in `docs/runbook-launch.md` step 6), and only when a release step asks for it.
- The server keeps the person's profile mostly on their device; the resume reader keeps nothing (`resume_parse.py`, `CHANGELOG.md`). Keep it that way: any new field stored on the server needs the Privacy Policy updated and the owner's OK.
- The help chat sends a message to the outside AI only after the person agrees, and only when AI answers are on (`CHANGELOG.md`, Reviewer 2 fixes).
- Account deletion must keep working end to end (`/api/auth/delete`, `/legal/delete-account.html`): the stores require it (`DEPLOY.md` section 2).

## Product rules that protect the company

From `HANDOFF.md` "The owner's rules":

- Never automate a job board's apply flow (LinkedIn, Indeed, ZipRecruiter, Handshake).
- Never submit into a hiring system without a key the employer created.
- Never answer a question the profile cannot answer. Never guess.
- Never send voluntary self-identification answers.
- Never get past a bot wall or a human check.
- Hiring mode (employer side) and the emailed-code sign-up stay sandbox-only until the owner says otherwise.
- Assisted apply fills only the hiring systems' own hosts listed in `shared/assist-systems.json`, and the person taps Submit. Switching a system to "automatic" needs the attorney's approval (`CHANGELOG.md`, Assisted apply).

## What a contractor may and may not touch

| May (in a PR into `sandbox`) | May not (owner only) |
|---|---|
| Code in your assigned area (page 00) | Render dashboard: Environment, plan, disk, deploys, Shell, rollback (unless Saif asks and grants access for that step) |
| Tests, stand-ins, docs, this space | Cloudflare DNS and SSL settings |
| Run local servers and the full suite | Stripe dashboard, keys, prices, refunds |
| Read-only checks of the live site when a task asks | Google Cloud OAuth client, Brevo account, USAJOBS keys |
| Open PRs, comment on Trello cards | Merging into `dev` or `main` without Saif's approval |
| | Repository settings: visibility, branch protection (the ruleset "Live branches: owner only", id 25654532, on `dev` and `main`), collaborators, GitHub Pages, Actions secrets |
| | `legal/` wording decisions (owner and attorney) |
| | Anything that costs money or emails real people |

## Access to grant a new coder

| System | Grant | Notes |
|---|---|---|
| GitHub `saifsiddiqueep-sketch/uaply` | Collaborator with **Write** (push branches, open PRs) | `README.md`: "Do not give strangers direct write access. This code can send email and handles applicants' details." Protect `main`, `dev`, `sandbox` (require a PR and a passing "Check the code"). Whether protection is switched on today: **TO CONFIRM with Saif/Mohammed**. |
| Trello "UAply Team Board" | Board member | So they can move their own cards. |
| Confluence (this space) | Edit | |
| Render | None by default. If needed for logs: the most limited workspace role Render offers, read only | Today the workspace has one member, Saif; Mohammed has no Render access (Saif, October 23). |
| Stripe, Google Cloud, Brevo, Cloudflare, UptimeRobot | None | Use the stand-ins. |
| Play Console, App Store Connect, Codemagic | None unless the task is mobile release | No Play or Apple developer account exists yet (Saif, October 23); Codemagic: **TO CONFIRM with Saif/Mohammed**. |

Remove access the day the engagement ends. Rotate any secret the person ever saw.

## Approval rules

| Action | Needs |
|---|---|
| Spending any money (plans, disks, paid email, app store fees, tools) | Saif's explicit yes first. Anything above the $7.50 a month already authorized on Render must be flagged (`HANDOFF.md`). |
| Changing anything in Render, Cloudflare, Stripe, Google Cloud, Brevo | Saif does it himself |
| Merging into `dev` (a release) | Saif |
| Turning on email to real employers (`delivery` out of test mode) | Owner, after partner employers agree (`DEPLOY.md`: "keep `delivery` in test mode until partner employers have agreed") |
| Reading or exporting user data, restoring a backup | Saif |
| New data stored about users, or a new outside service that receives user data | Owner, plus a Privacy Policy update |
| Legal page changes | Owner and attorney (`LEGAL-REVIEW.md`) |
| Repository visibility changes | Saif (`docs/runbook-launch.md` step 1.5) |
