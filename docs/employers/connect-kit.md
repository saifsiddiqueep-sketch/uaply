# Employer outreach: the email, the one-page kit, and who to ask first

October 22, 2026. For the owner. Nothing here has been sent to anyone. The one-page kit below is also rendered as
[connect-kit.pdf](connect-kit.pdf) by `node tools/cdp.js tools/render-connect-kit.js` (it must stay one page; the tool checks that), and
the employer list at the end is written by `python tools/employer-targets.py --write`.

**How we say it now.** Not "swipe right = apply". A swipe right *starts* an application. It is *sent* only where the employer has
connected (or agreed to take applications by email); everywhere else the person finishes on the employer's own page. Every sentence
below follows that.

## 1. The outreach email

Fill in the brackets from the table in section 3. Send it from the company address to the recruiting contact you found on their careers
site, one employer at a time. Attach connect-kit.pdf.

> **Subject:** Applicants for your [System] jobs, straight into [System]
>
> Hello [first name],
>
> I run UAply, a job app for students and early-career people. Your [N] open roles on [System] appear in UAply from your public job
> board. Today, when someone in UAply chooses one of your jobs, we send them to your careers page to apply there, and some never
> finish.
>
> If you connect a [System] key, those applications arrive directly in [System] instead: the person's details, their resume as a file
> and the answers to your own screening questions, as one new candidate on the right job. It takes about ten minutes and you can switch
> it off at any time by revoking the key. The attached page has the exact steps for [System].
>
> Two things we never do: we never send voluntary self-identification answers (gender, race, veteran or disability status), and we never
> use your key for anything but reading your application form and submitting applications people chose to send you.
>
> If you would like to try it, reply to this email and I will send the one-page consent letter. Happy to talk it through on a call.
>
> [Your name], UAply
> [support address] · uaply.net

## 2. The one-page kit (connect-kit.pdf)

<!-- PAGE: rendered to connect-kit.pdf by tools/render-connect-kit.js -->
# Get UAply applicants directly in your hiring system

**What changes when you connect.** People find your jobs in UAply (from your own public job board) and choose to apply. Without a
connection, UAply sends them to your careers page to finish. With one, their application arrives in your system as a new candidate on
that job: name, email, phone, city, links, school and degree, the resume as a file, and answers to your screening questions where their
profile has them. If your form asks something their profile cannot answer, UAply asks them first; if it still cannot be answered, nothing
is sent and they finish on your page.

**Ten minutes, three steps.** (1) Reply to our email to agree to the one-page consent letter (2 minutes). (2) Create the key below (5
minutes). (3) Send it to us through a one-time secure link from your password manager, or read it to us on a call; never paste it into an
email. We connect it and test it the same day; you can revoke it at any time.

| You use | Where you create the key | Give it only these rights | Also tell us |
|---|---|---|---|
| **Greenhouse** | Configure, Dev Center, API Credential Management: new credential, type **Job Board API** | Job Board API (submits applications to your published jobs) | Your board name (after `boards.greenhouse.io/`) |
| **Lever** | Settings, Integrations and API, API Credentials: **Generate new key** under Postings API (a Super Admin) | Postings API | Your site name (after `jobs.lever.co/`) |
| **Ashby** | Admin, Integrations, API Keys: create a key | **Candidates write** and **Jobs read** only | Your board name (after `jobs.ashbyhq.com/`) |
| **SmartRecruiters** | Settings, Administration, Apps & Integrations, Credentials: **New Credential, API Key** (an Administrator) | An API key (SmartRecruiters has no narrower kind); UAply uses only its Application API calls | Your company identifier (after `jobs.smartrecruiters.com/`) |
| **Workable** | Profile icon, Settings, Integrations, Apps, API Access Tokens: **Generate API token** (an Admin) | **r_jobs** and **w_candidates** only | Your subdomain (`yourcompany` in `yourcompany.workable.com`) |

**Privacy.** UAply never sends gender, race or ethnicity, veteran status, disability status or any other voluntary self-identification,
even when your form asks. Your key stays on UAply's server: it is never shown in the app, written to a log or put in an error message, and
it is used only to read your job's application form and submit applications people chose to send you. Each application is one person
who reviewed what would be sent and agreed. Hiring decisions stay yours; UAply does not rank or screen applicants for you.

**Stopping.** Revoke the key in the same screen where you made it: applications stop at once. Tell us and we delete our copy and take
you off our list within 2 business days.

**Questions:** [support address] · uaply.net. Ask us for the full page for your system: what is sent, what the key can do, how to revoke it.
<!-- /PAGE -->

## 3. Who to ask first: the top 50 employers in the feed

<!-- TARGETS: written by tools/employer-targets.py -->
Ranked by US jobs in UAply's feed (job-boards.json, counted 2026-10-21). The careers site is the employer's own public job board; their recruiting contact is usually linked from it or from the company's main site. Nothing has been sent to any of them.

| # | Employer | System | US jobs | All jobs | Careers site |
|---|---|---|---|---|---|
| 1 | Domino's | SmartRecruiters | 24810 | 24810 | https://careers.smartrecruiters.com/dominos |
| 2 | CROSSMARK | SmartRecruiters | 21158 | 21158 | https://careers.smartrecruiters.com/crossmark1 |
| 3 | Prolific Academic Ltd | Greenhouse | 3926 | 3939 | https://job-boards.greenhouse.io/prolificacademicltd |
| 4 | AECOM | SmartRecruiters | 3767 | 5382 | https://careers.smartrecruiters.com/aecom2 |
| 5 | EōS Fitness | Greenhouse | 2498 | 2787 | https://job-boards.greenhouse.io/eosfitness |
| 6 | Anduril Industries | Greenhouse | 2387 | 2498 | https://job-boards.greenhouse.io/andurilindustries |
| 7 | Turner & Townsend | SmartRecruiters | 2043 | 3523 | https://careers.smartrecruiters.com/turnertownsend |
| 8 | Pilot Company | SmartRecruiters | 1936 | 1936 | https://careers.smartrecruiters.com/pilotcompany |
| 9 | USM | SmartRecruiters | 1483 | 1483 | https://careers.smartrecruiters.com/usm2 |
| 10 | CGS Federal (Contact Government Services) | Lever | 1428 | 1429 | https://jobs.lever.co/cgsfederal |
| 11 | Northwestern Memorial Healthcare | SmartRecruiters | 1409 | 1409 | https://careers.smartrecruiters.com/northwesternmedicine |
| 12 | AbbVie | SmartRecruiters | 1402 | 1948 | https://careers.smartrecruiters.com/abbvie |
| 13 | LifeStance Health | Lever | 1348 | 1378 | https://jobs.lever.co/lifestance |
| 14 | TSMG | Lever | 985 | 4448 | https://jobs.lever.co/tsmg |
| 15 | Boyd Gaming | SmartRecruiters | 836 | 836 | https://careers.smartrecruiters.com/boydgaming |
| 16 | Veolia Environnement SA | SmartRecruiters | 785 | 2806 | https://careers.smartrecruiters.com/veoliaenvironnementsa |
| 17 | Infojini Inc | SmartRecruiters | 773 | 773 | https://careers.smartrecruiters.com/infojiniinc1 |
| 18 | PLS | Greenhouse | 767 | 780 | https://job-boards.greenhouse.io/plscareers |
| 19 | RA | SmartRecruiters | 694 | 789 | https://careers.smartrecruiters.com/ra2 |
| 20 | Accenture Federal Services | Greenhouse | 692 | 694 | https://job-boards.greenhouse.io/accenturefederalservices |
| 21 | IDEALFORCE LLC | SmartRecruiters | 657 | 657 | https://careers.smartrecruiters.com/idealforcellc |
| 22 | Speechify | Greenhouse | 646 | 738 | https://job-boards.greenhouse.io/speechify |
| 23 | OpenAI | Ashby | 645 | 809 | https://jobs.ashbyhq.com/openai |
| 24 | vTech Solution | SmartRecruiters | 628 | 628 | https://careers.smartrecruiters.com/vtechsolution1 |
| 25 | ALO | Greenhouse | 619 | 792 | https://job-boards.greenhouse.io/aloyoga |
| 26 | Eurofins | SmartRecruiters | 618 | 2579 | https://careers.smartrecruiters.com/eurofins |
| 27 | Intuitive | SmartRecruiters | 611 | 764 | https://careers.smartrecruiters.com/intuitive |
| 28 | RR Donnelley | SmartRecruiters | 575 | 575 | https://careers.smartrecruiters.com/rrdonnelley |
| 29 | Bosch Group | SmartRecruiters | 561 | 5100 | https://careers.smartrecruiters.com/boschgroup |
| 30 | Anthropic | Greenhouse | 532 | 674 | https://job-boards.greenhouse.io/anthropic |
| 31 | Shield AI | Lever | 522 | 657 | https://jobs.lever.co/shieldai |
| 32 | KIPP | SmartRecruiters | 513 | 513 | https://careers.smartrecruiters.com/kipp |
| 33 | ServiceNow | SmartRecruiters | 485 | 714 | https://careers.smartrecruiters.com/servicenow |
| 34 | CSC Generation | Lever | 485 | 511 | https://jobs.lever.co/cscgeneration-2 |
| 35 | MedElite Group, LLC. | Greenhouse | 477 | 485 | https://job-boards.greenhouse.io/medelitellc |
| 36 | Veeva Systems | Lever | 454 | 920 | https://jobs.lever.co/veeva |
| 37 | Renesas Electronics | SmartRecruiters | 430 | 936 | https://careers.smartrecruiters.com/renesaselectronics |
| 38 | Lyra Health | Lever | 419 | 475 | https://jobs.lever.co/lyrahealth |
| 39 | SGS | SmartRecruiters | 416 | 4627 | https://careers.smartrecruiters.com/sgs |
| 40 | BCforward | SmartRecruiters | 404 | 404 | https://careers.smartrecruiters.com/bcforward3 |
| 41 | DH Pace | Greenhouse | 404 | 404 | https://job-boards.greenhouse.io/dhpace |
| 42 | Olsson | Greenhouse | 390 | 390 | https://job-boards.greenhouse.io/olsson |
| 43 | Procom Consultants Group | SmartRecruiters | 387 | 387 | https://careers.smartrecruiters.com/procomconsultantsgroup |
| 44 | NBCUniversal | SmartRecruiters | 374 | 457 | https://careers.smartrecruiters.com/nbcuniversal3 |
| 45 | US IT Solutions Inc | SmartRecruiters | 352 | 352 | https://careers.smartrecruiters.com/usitsolutionsinc |
| 46 | Meridial | Greenhouse | 335 | 833 | https://job-boards.greenhouse.io/agency |
| 47 | Egis Group | SmartRecruiters | 333 | 1590 | https://careers.smartrecruiters.com/egisgroup |
| 48 | SA Technologies Inc. | SmartRecruiters | 330 | 355 | https://careers.smartrecruiters.com/satechnologiesinc4 |
| 49 | Crusoe | Ashby | 328 | 343 | https://jobs.ashbyhq.com/crusoe |
| 50 | SOSi | SmartRecruiters | 324 | 335 | https://careers.smartrecruiters.com/sosi1 |
<!-- /TARGETS -->

Before writing to one: check the careers site still lists jobs, find the recruiting or talent contact (a "Contact us" page, the
recruiting team's address in the site's footer, or the company's main site), and note in the owner's tracker the date and the person.
For any of them, once a key arrives, `/setup` checks it at once ("Test this connection": their open postings and whether the key works)
before a single application is sent. Our own first connection is in [first-connection.md](first-connection.md).
