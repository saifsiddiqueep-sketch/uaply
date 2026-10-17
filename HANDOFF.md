# Handoff: where UAply stands and how we work (written October 17, 2026)

Read this first when continuing the work in a new session. It carries what the earlier sessions knew: the owner's rules, the state
of every instance, the last two weeks of work, what the bots did on October 17, and what is still open. The live record of links and
owner to-dos is the launch board (https://claude.ai/artifact/EEEa9pfxBa1z4zjPJWDdP3); the research behind "truly apply" is the apply
plan (https://claude.ai/artifact/WwkzTD3ZE9aYeVRRKa5iRP).

## The owner's rules (standing)
- Ask before any purchase. Say so before anything above the $7.50 a month already authorized on Render (the 1 GB disk, about $0.25 a
  month more, is already flagged and approved in principle).
- Never type the owner's secrets (keys, passwords) into chat, commits or files. The owner pastes them into Render's Environment page
  himself, or a session on his own laptop does it with his sign-ins.
- No more than the nine bots (Bot 1 code audit, Bot 2 swipe/buttons/profile, Bot 3 apply and email, Bot 4 sign-in and payments,
  Bot 5 hosting / resume, Bot 6 phone apps, Bot 7 launch readiness, Bot 8 swipe learning, Bot 9 job feeds and keys).
- Detailed pull requests in the CONTRIBUTING.md shape (what changed, why, how tested, what could go wrong, what is not done, where it
  is going). Show proof: test counts, log lines, screenshots.
- Work moves sandbox, then dev (the release build), then main, always through a pull request. Hiring mode (employer side) stays
  sandbox-only until the owner says otherwise.
- After a merge to dev: add the CHANGELOG entry and tag `v1.0.0-rc.N`.
- Never automate a job board's apply flow (LinkedIn, Indeed, ZipRecruiter, Handshake). Never submit into a hiring system without a
  key the employer created. Never answer a question the profile cannot. Never send voluntary self-identification.

## Instances and where they run
| Instance | Branch | Where | Notes |
|---|---|---|---|
| Live site | `dev` | https://uaply.onrender.com (Render service `srv-db9i3i6q1p3s738b5b4g`, workspace `tea-db9duku1egvs73et93k0`, Starter plan, Virginia) | Runs release candidate 9 (commit 522f2e5, PR #34 merged 07:54 UTC Oct 17, deployed 07:57). `UAPLY_DATA_DIR` points at a temporary folder because no disk is attached yet: accounts vanish at each deploy. Email, owner pages, AI answers and payments are off (no secrets set). Job feeds on: ashby, greenhouse, jobicy, lever, muse, smartrecruiters, usajobs. |
| Hosted previews | `dev`, `sandbox` | https://saifsiddiqueep-sketch.github.io/uaply/dev/ and /sandbox/ | GitHub Pages copies with no server; they say so (preview wording). |
| Owner's computer | all three | 8765 prod (`main`), 8766 sandbox, 8767 dev | `start-uaply.bat`. The full test suite (`bash tools/run-all-tests.sh`, 48+ groups) runs there; the cloud ran everything that needs no Chrome. |
| Domain | | uaply.net (Cloudflare) | Not connected yet: Render Custom Domains + CNAME `@` and `www` to uaply.onrender.com, DNS only, SSL Full. Each DNS save only after the owner's "yes". |

Tags: `v1.0.0-rc.8` is the last tag on GitHub. `v1.0.0-rc.9` should point at 522f2e5; the cloud session could not push tags (its proxy
allows branch pushes only), so add it from a laptop session or GitHub Releases.

## What the owner must do himself (nobody else can)
All with exact values on the launch board. 1) Render → Disks: add `uaply-data` at `/var/data`, 1 GB; then set `UAPLY_DATA_DIR=/var/data`
and confirm the startup log says `data: /var/data (persistent disk)`. 2) Render → Environment: `OWNER_PASSWORD` and `UAPLY_CONFIG_JSON`
(one line; Brevo relay is already set up: host smtp-relay.brevo.com, port 587, login be5bc2001@smtp-brevo.com, verified sender
uaplytechnologies@uaply.net; only the SMTP key from Brevo → SMTP & API is missing). The log must then say `email: on` and
`UAPLY_CONFIG_JSON: valid`. 3) Google Auth Platform: a Web client "UAply web" with origins https://uaply.onrender.com, https://uaply.net,
https://www.uaply.net and the same three + `/api/auth/google/callback` as redirect URIs; client ID and secret go in the `google` block of
`UAPLY_CONFIG_JSON`. 4) Stripe: activate the account, prices Plus $9.99 and Pro $19.99 a month, webhook https://uaply.onrender.com/api/billing/webhook
(events checkout.session.completed, customer.subscription.created/updated/deleted), then `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`,
`STRIPE_PRICE_PLUS`, `STRIPE_PRICE_PRO` in Render. Test keys first, then live. 5) Allow `uaply.onrender.com` in the cloud environment's network
settings if bots in the cloud should test the live site. 6) The domain (above). 7) Decide the branch rename (`dev` → `release`/`prod`), accept
the Android SDK licences on the laptop, get the attorney review of the legal pages and of the public boards' terms.

## The last two weeks, in plain words (October 3 to 17)
About 160 commits on sandbox. Earlier sessions' summary plus the CHANGELOG:

**Code quality and safety.** Email codes deleted after sending (not kept readable in logs); the fake test sign-in removed; crashes from hostile
input (null bytes, empty requests, malformed job data) fixed; script injection and connection bursts blocked; a legal-pages file-read hole
closed; Reply-To that a profile name could hijack fixed; a file audit (control characters, tracked backups, secrets) added; `check.js` compiles
every module, reads every JSON file and checks how the files fit together; 25 audit fixes by Bot 1; stress and fuzz runs (4,500+ requests).

**Accounts and sign-in.** Password accounts with a 6-digit email code; a per-account lock-out that faked addresses cannot dodge; reset links;
delete account; Continue with Google (Google's button on computers and Android, full-page sign-in on iPhone, no account pre-hijack through an
unconfirmed email, Google returns people to the address they started on); the Google Cloud guide on `/setup#google`; the agreement asked once
before the first swipe with "You agreed on <date>" and Show it again.

**Email.** Verification codes and receipts through SMTP (Gmail App Password or Brevo); help tickets emailed to uaplytechnologies@gmail.com with
the person as reply address; receipts that say where the resume and the application really went; the owner's copy of every application;
"Applied on" formatting; a retry path for failed sends.

**Applying.** Swipe right with honest outcomes (sent, saved, finish on their site, failed), retries when the server is down, two quick swipes
both count, links on a card open only on a tap, undo window; employer email with the resume as a real attachment and the signed webhook
(the Indeed way, EMPLOYERS.md); straight into Greenhouse and Lever for employers who connect (ats_api.py, autofill.py reads the posting's own
form and answers it from the profile; a required question the profile cannot answer is asked once and remembered; never a guess); the
instant-apply filter; the Applied list; a browser replay of every apply path.

**Jobs.** Real postings from Greenhouse, Lever, Ashby, SmartRecruiters (City of Philadelphia), USAJOBS (needs the free key), The Muse (key),
Jobicy, Remotive (owner to decide); "via …" credit on every card; `feeds_off`; Jobs near you (location prompt, commute slider, nearby first);
the job list reads about five times faster; learns from your swipes (naive-Bayes per attribute, capped at ±1.5), on in the release build.

**Plan and billing.** Free, Plus $9.99, Pro $19.99 with weekly limits (50, 250, unlimited); Stripe Checkout, portal and signed webhooks; the
plan changes only from a verified webhook; three states decided on the server (real buttons with keys, "free during early access" on a public
server without keys, test Payment Links on the owner's computer); the "Checkout canceled" message bug fixed.

**Hosting and phone apps.** Render: clean stop on SIGTERM, one startup line that says what is on, broken records survive, disk and port checks,
`render.yaml` and DEPLOY.md proven by `tools/test-render.py`; the service created and made live on Oct 17. Android targets Android 16 (Google
Play's rule since Aug 31, 2026), the offline screen wired in, apps open uaply.net, Google hidden inside the apps' web views, a signed release
build script, the iPhone-only project, the Codemagic workflow, store listing docs.

**Pages and help.** Terms, Privacy (covers Google sign-in, codes, resume files, ZIP codes, form answers, plans, the AI chat, data deletion),
AI and matching, Copyright, Support page; legal pages still say "draft, not reviewed by a lawyer"; the help assistant names the real screens
and "Take me there" opens the right Profile setup step; hosted previews say what they are; the Account screen on the live site no longer
points visitors at owner-only pages (fixed Oct 17).

**Hiring mode (sandbox only, with Mohammed's work).** Employers post a job in four steps or from a link or pasted text; one-word bottom tabs on
phones. Company verification and application management are the next build. Marketing demos recorded (autofill, phone swipe, two real-apply
recordings) under `marketing/`.

**Research (Oct 17, apply plan page).** Only hiring systems with an employer-created key accept third-party applications (Greenhouse, Lever,
Ashby, SmartRecruiters, Workable). Indeed Apply, LinkedIn Apply Connect and ZipApply are employer-side products with no job-seeker API and
terms that forbid bots; Handshake has no public API and blocks accounts past 300 applications a day; USAJOBS' terms require sending people to
USAJOBS to apply; Workday and iCIMS are partner-gated. So the three tiers: 1) straight into the connected employer's system, 2) email or
signed webhook to an employer who agreed, 3) save, receipt with every answer ready, open the employer's page.

## October 17 in the cloud session (this handoff's author)
- Resolved PR #34's conflict with dev (dev/index.html options and the nav lift cap), added the hosted Account wording fix, merged PR #34
  into dev, triggered the Render deploy (auto-deploy did not fire), verified the live log line.
- Published the apply plan and the launch board pages.
- Bot 2 → PR #35 merged into sandbox: Profile setup asks relocate, expected pay, country, job title and dates; autofill rules for them;
  Greenhouse hidden fields (`country_short_name`, location + latitude + longitude together, `employments[0][...]`); expected pay sent and
  listed only where a form requires it; receipt, employer email, webhook, Privacy Policy and EMPLOYERS.md updated; test-autofill 67/67.
- Bot 3 → PR #36 merged into sandbox: Ashby (`jobPosting.info` + `applicationForm.submit`, multipart, Basic auth, needs Candidates write and
  Jobs read) and SmartRecruiters (`/postings/{uuid}/configuration` + `/postings/{uuid}/candidates`, `x-smarttoken`, resume as base64 object,
  answers as `[{id, records:[{fields}]}]`) connectors; one shared answer function (`autofill._answer`) for every system; stand-ins and 58 new
  checks; the Connect box offers four systems; SmartRecruiters postings record their uuid. Not yet tried with a real key.
- Bot 5 → PR #37 merged into sandbox: `resume_parse.py` (pdf through pypdf in a limited separate process, docx, txt), `POST /api/profile/resume`,
  the sandbox experiment "Fill from your resume" in Profile setup → Background and links (fills empty fields only, Replace per field, source
  line per answer), `pypdf` in requirements.txt, 250 parser checks and 22 browser checks. No OCR for scanned resumes.
- Bot 1 → PR #38 merged into sandbox: `tools/cdp.js` finds Chrome through `UAPLY_CHROME`, the Windows path, Playwright's Chromium or the Mac
  app (the whole browser suite now runs in the cloud and on a Mac); the first-open location button no longer stays greyed out; `/api/auth/me`
  returns the real plan; the help assistant answers "Is my data sold?"; sign-up on a hosted site without email no longer promises receipts;
  the phone test follows the one-word tabs. 41 of 48 groups pass in the cloud (the rest need the live job feeds). Findings not fixed there:
  Pass and Apply under the bottom bar on first open (Bot 2 is on it, branch `bot2-buttons-above-bar`); the legal index's "AI draft" note and
  "Effective [launch date]" (owner and attorney); small items (favicon, robots.txt, the default 404 page, "You want $0k+", the Account subtitle).
- Bot 4 → PR #39 merged into sandbox: "Continue with Google" is Google's full-page sign-in on every device once the client secret is set
  (the app runs in a srcdoc frame where `location.origin` is "null", which can make Google's pop-up button fail; it also always goes through
  FedCM now); token checks with 60 s skew, a one-day maximum life, capped key refetches; Stripe: a plan changes only from a signed webhook and
  the subscription is re-read from Stripe, only the exact Plus and Pro prices count, a live server ignores test-mode events, the API version
  is pinned, `invoice.paid` and `invoice.payment_failed` handled (the plan pauses after the 3rd failed renewal), handled event ids kept 30 days,
  deleting an account cancels the subscription first (the account is kept if Stripe refuses); `/setup#google` and DEPLOY.md sections 3 and 4
  carry the owner's two checklists (Google: Branding with authorized domains uaply.net and uaply.onrender.com, Publish app, the Web client with
  the three origins and redirect URIs; Stripe: terms first, the test-card rehearsal, activation, prices, portal, Smart Retries, the webhook's
  six events, the four Render settings, Radar rules, one real purchase). The start-up log line now shows Google and payments status.
  Before live payments the lawyer must replace "UAply is currently free" in `legal/terms.html` with paid-plan and automatic-renewal terms.
- Still running when this was written: Bot 2 (`bot2-buttons-above-bar`): the swipe buttons always visible above the bottom bar on first open at
  390×844, 375×667, 440×956 and 1280×800, with a browser test that fails before and passes after; the Account subtitle, the "$0k+" line, the
  pricing help answer, the location prompt only after Agree, `/favicon.ico`, `/robots.txt`, the app's own 404 page, "Back to UAply" on legal pages.
- The record PDF: `marketing/UAply-record-2026-10-17.pdf` (the cloud session as a transcript, this handoff, the changelog, every commit).

## What is still open
1. Owner steps above (disk, email, Google, Stripe, domain). Until then: accounts temporary, no codes, no Google, no payments.
2. Merge Bot 2's PR (swipe buttons above the bar) when its check is green; run the full suite with Chrome on the laptop on the merged sandbox
   (`UAPLY_CHROME` is only needed where Chrome is not in the usual place); check the new Profile setup screens, "Fill from your resume", the
   Connect box and the Plan screen's new messages in a browser.
3. A PR sandbox → dev with the above once the suite is green (hiring mode stays out), then tag rc.10 and verify the live site.
4. The one-time question box for a required field the profile cannot answer, on screen (today the swipe becomes "finish on their site" when
   the app cannot ask it); Workable connector; the employer outreach kit (how to connect each hiring system + the consent letter); Hiring mode
   as a small ATS for employers who post on UAply directly.
5. Phone apps: Android SDK licences, Apple Developer Program, store listings; Sign in with Apple once native Google sign-in is added.
6. Attorney review; trademark clearance (APLY filing overlaps "UAply", see LEGAL-REVIEW.md).
