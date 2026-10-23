# UAply Engineering Handbook

**Confluence space name:** UAply Engineering Handbook
**Space key:** UENG
**Why this name:** it says who the space is for (engineers) and what it is (the handbook), and the short key is free of the brand's odd capital so it is easy to type in links.

This space is the handover pack for engineers who join UAply without having met the founders, Mohammed Hussain and Saif Siddiquee. It explains how the app is built, how work moves from an idea to the live site, how to test and deploy, how to fix the common problems on your own, and where the hard limits are for security and money.

Every fact here comes from the repository (`saifsiddiqueep-sketch/uaply`, read on the `sandbox` branch as of October 23, 2026, and the `dev` branch). Where the repository does not say, the page says **TO CONFIRM with Saif/Mohammed**.

## Pages

| # | Page | Read it when |
|---|---|---|
| 00 | [Start here](00-start-here.md) | Your first day. What UAply is, a 10-minute orientation, who owns what, how to get help. |
| 01 | [Architecture](01-architecture.md) | Before you change any code. Components, request flow, where data lives, outside services. |
| 02 | [Workflow and stages](02-workflow-and-stages.md) | Before you start a task. Idea to Trello card to branch to sandbox to review to live. |
| 03 | [Local setup and tests](03-local-setup-and-tests.md) | Setting up your computer and before every pull request. |
| 04 | [Deploy and rollback](04-deploy-and-rollback.md) | Releasing to the live site, undoing a bad release, reading logs. |
| 05 | [Runbooks](05-runbooks.md) | Something is broken. Symptom, check, fix. |
| 06 | [Security and money guardrails](06-security-and-money-guardrails.md) | Before you touch secrets, payments, user data or access. Read it fully once. |
| 07 | [Conventions](07-conventions.md) | Writing code, commits, pull requests, changelog entries and words people see. |
| 08 | [Glossary and FAQ](08-glossary-and-faq.md) | Any time a word or name is unclear. |

## Source documents in the repository

These are the originals this handbook summarises. When they disagree with this space, the repository wins; update this space.

- `HANDOFF.md`: current state of every instance and the owner's standing rules.
- `README.md`, `CONTRIBUTING.md`, `.github/pull_request_template.md`: how to run and contribute.
- `DEPLOY.md`: hosting on Render, Google sign-in, Stripe, email.
- `docs/runbook-launch.md`: the launch day sequence and the rollback command.
- `docs/uptime.md`, `docs/ACCOUNTS.md`, `docs/job-sources.md`, `docs/assisted-apply.md`, `EMPLOYERS.md`, `docs/employers/`.
- `CHANGELOG.md`: what each release changed.
- `render.yaml`, `check.js`, `tools/run-all-tests.sh`, `.github/workflows/`.

## Keeping this space true

- When a pull request changes how something works, update the matching page here in the same week.
- Never paste a secret value into this space. Name the setting instead (for example `STRIPE_SECRET_KEY`).
