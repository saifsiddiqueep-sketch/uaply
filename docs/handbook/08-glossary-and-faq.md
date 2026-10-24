# 08 Glossary and FAQ

## Glossary

| Term | Meaning |
|---|---|
| **UAply** | The product. A job-swiping app. Always spelled with capital U and A. |
| **prod** | The original single-page app, `prod/index.html`, on branch `main`. Local port 8765. Only the owner changes it. Not the live site. |
| **sandbox** | The test bench branch and instance. Every experiment, switchable. Local port 8766. |
| **dev** | The release build branch and instance. **The live site runs `dev`.** Local port 8767. |
| **Live site** | https://uaply.net, Render service `uaply`, branch `dev`. |
| **Preview** | Static copies with no server: the Render site `uaply-sandbox-preview` (from `sandbox`; it embeds every shared script, the sign-up card included, PR #63) and GitHub Pages copies, which exist only while the repository is public. |
| **Experiment** | A file in `shared/uaply-*.js` that patches a copy of `prod/index.html` in memory. |
| **`once()`** | The patch helper in each experiment: replace the first exact match, or throw "patch target not found". |
| **Promoted** | An experiment listed in `PROMOTED` in `dev/index.html`, so it is on in the release build. |
| **Release candidate (rc.N)** | A numbered release merged into `dev`, tagged `v1.0.0-rc.N` (tags `v1.0.0-rc.1` to `v1.0.0-rc.13` exist). The live site runs `9b76822`, the sign-in gate v2 release of October 23 (rc.14, not tagged yet). |
| **Owner** | In the launch docs, Saif: anything with a password, key, money or the phone (`docs/runbook-launch.md`). |
| **Coordinator / managing session** | The AI coding session that plans, reviews and runs commands that need no secret (`HANDOFF.md`, `docs/runbook-launch.md`). |
| **Bots** | AI coding sessions that write code in separate worktrees, each on one task (`HANDOFF.md`). |
| **Owner pages** | `/setup`, `/outbox`, `/feedback`. Open on a laptop; need `OWNER_PASSWORD` on a public server. |
| **Test inbox / outbox** | `/outbox`: where emails go in test mode instead of real inboxes. |
| **Gate / sign-in gate** | Signed out, the sign-up card is the whole screen and data routes answer 401 `signin`. |
| **403 verify** | The answer when an action needs a verified email and the address is not verified yet. |
| **Test mode (sign-up)** | `UAPLY_SIGNUP_TEST=1` on a non-public server: sign-up verified at once, no email. Ignored on a public server. |
| **`delivery`** | Setting in `UAPLY_CONFIG_JSON`. `test` means nothing is emailed to employers. |
| **Feeds** | Public job sources read by `jobs_api.py` (Greenhouse, Lever, Ashby, SmartRecruiters, USAJOBS, The Muse, Jobicy, Workable, careers sites). |
| **ATS / hiring system** | An employer's applicant tracking system. UAply submits into one only with a key the employer created. |
| **Connected employer** | An employer who gave UAply a key for their hiring system (`/setup`, `docs/employers/`). |
| **Route** | How a job's application travels: connected, email, one-tap, assisted, ready. The card's wording follows it. |
| **Assisted apply** | In the Android app, UAply fills the employer's own form and the person taps Submit (`docs/assisted-apply.md`). |
| **Question box** | The one-time box that asks what the profile cannot answer for an employer's form. Answers are remembered. |
| **`READY_MIN`** | The minimum to apply: a name, an email, and a phone number or a resume (`shared/uaply-nav.js`; also checked on the server). |
| **Job Tracker** | The middle tab (formerly Dashboard): applied, not sent yet, passed. |
| **Hiring mode** | The employer side (post a job). Sandbox only. |
| **Self-check** | The owner-only `selfCheck` block in `/api/status`: last board read, last email, disk space, warnings. |
| **Start-up line** | The `[uaply] dev on ...` log line that says what is switched on and the commit. |
| **Daily line** | The `[uaply] daily {...}` log line at midnight UTC and each stop. |
| **Bounce list** | `mail-suppressed.json`: addresses UAply will not email, fed by Brevo's webhook. |
| **Held mail** | Mail waiting until after midnight UTC because the daily quota is near (`mail-held.json`). |
| **Stand-in** | A local fake of an outside service for tests (`tools/mock-*.py`, `tools/fake-smtp.py`). |
| **Heads-up columns** | The Trello lists "Mohammed is working on" and "Saif is working on". Information only, not locks. |
| **Galaxy walk / phone walk** | `tools/phone-walk.js` driving a real Samsung Galaxy over USB. |
| **TWA** | Trusted Web Activity: the Play Store app that opens uaply.net full screen (`mobile/twa/`). |

## FAQ

**Which branch do I start from?**
`origin/sandbox`, always the newest. See page 02.

**I merged into dev. Is it live?**
Not by itself today. Auto-deploy has not fired since October 17. Check Render Events and start a manual deploy if needed (page 04, runbook 10).

**Why does the live site run a branch called "dev"?**
History: `dev` became the release build. A rename (`dev` to `release` or `prod`) is an open owner decision in the October 17 handoff. Status: **TO CONFIRM with Saif/Mohammed**.

**Is `render.yaml` what runs?**
No. The live service was made by hand. `render.yaml` is a reference for a fresh setup (`HANDOFF.md`).

**Why are there no real jobs on the preview?**
The preview has no server. Run `python serve.py 8766 sandbox --api` locally.

**Can I test payments?**
Locally with `tools/mock-stripe.py` and `python tools/test-billing.py`. Never touch the Stripe dashboard. The live site is in Stripe test mode today; only Saif changes that.

**Can I send a real email from my laptop?**
Only with your own test mail account in your own git-ignored `uaply-config.json`, and only if your task needs it. By default email goes to `/outbox`.

**Where do I find what changed in a release?**
`CHANGELOG.md`. The sandbox copy lacks rc.12 and rc.13 headings; the PR titles for #44 and #45 on GitHub describe them.

**What do I do if the full suite fails on groups I did not touch?**
Check whether they need the public job boards (network) or Chrome. Rerun that one test alone. If it still fails on a clean `sandbox`, say so in your PR and on the Trello card.

**Who decides what goes into a release?**
Saif (releases are his area). Product questions about the card UI or mobile go to Mohammed.

**Can I turn on an experiment in dev?**
Only with the owner's decision. Adding to `PROMOTED` ships it to users.

**Where are the legal pages and who changes them?**
`legal/`. Wording changes need the owner and the attorney. They say "draft, not reviewed by a lawyer" until reviewed.

**How do I reach the founders?**
Trello card comments first. Direct contact details and urgent contact: **TO CONFIRM with Saif/Mohammed**.

**What if a doc and the code disagree?**
The code and the newest `sandbox` docs win. Fix the doc in your PR and update this space.
