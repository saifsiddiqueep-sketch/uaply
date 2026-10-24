# A swipe right that submits: phase A (October 23, 2026)

Saif's direction: a swipe right submits the application as far as the law and the employers' own channels allow, with the person's
recorded consent. Phase A needs no employer key. It has four parts, plus the consent record they all depend on.

| Part | What a swipe right does | Where |
|---|---|---|
| 0. Consent record | Nothing is sent by UAply itself unless the account has the current agreement on record | `consent_api.py`, `POST /api/consent` |
| a. Apply by email | A posting that asks for applications by email gets the application emailed to its own address | `jobs_api.apply_address`, `uaply_api.submit` |
| b. Automatic submit | Phone app only, with the person's separate tick, on a system the lawyer approved (none today) | `shared/uaply-assist.js` `autoSubmit` |
| c. One tap | Phone app: the employer's form opens right after the swipe, filled; the person completes the check and taps Submit | `shared/uaply-nav.js` `__uaplyOneTap` |
| d. Outreach queue | Who to invite to connect each week (it sends nothing) | `tools/outreach-queue.py` |

## Send applications for me

Profile, Account has a **Send applications for me** switch (`POST /api/auth/send-for-me {on}`, kept on the account; `/api/auth/me` returns
`sendForMe`). It is on unless the person turns it off. Off, `uaply_api.submit` turns every swipe right into a hand-off that only saves the
job to Job Tracker (`why: "send_off"`, `sendForMe: false` in the answer): no email, no hiring system, no simulated send, no employer's form
read; the app skips the countdown, opens no form by itself and never submits automatically.

## 0. The consent record

The first-swipe box is version 4 (`CONSENT_V` in `shared/uaply-live.js`; the same words in `consent_api.py`, checked word for word by
`tools/test-consent.py`). Agreeing posts `{version, text, auto}` to `POST /api/consent` (signed in, address confirmed). The server checks the
words against its own copy (409 `consent_text` or `consent_old` otherwise) and keeps one row on the account: the version, the time on its own
clock, the visitor's address (the last hop, as every limit reads it) and the SHA-256 of the words. `/api/auth/me` returns it as
`consent: {v, at, auto}`. `{withdraw: true}` takes it back (the box shown again from Settings and not agreed). The rows go with the account.

Every application UAply sends itself (an email to an employer, an application into an employer's hiring system) needs the current version on
record: `uaply_api.submit` answers 403 `{code: "consent"}` otherwise. A page that has the agreement on the device but not on the server (agreed
before this server kept it, or the post was lost) sends it once and tries again.

## a. Apply by email

**Which postings.** `jobs_api.apply_address` reads the posting's own text (a `mailto:` link keeps its address in it). An address is taken only
when all of these hold:

- it stands in a sentence that asks for applications by email ("send your resume to", "email your CV to", "applications should be sent to",
  "to apply, email ..."), as the place to send them (right after "to", "at", "email", "here" or a colon);
- the sentence is not about accommodations, questions, agencies, privacy, fraud or "do not";
- the address's domain is the employer's own: the domain's name (the part before `.com`, `.org`, `.co.uk`) is the company's name or the
  board's name (one may start the other, at four letters or more), or the domain of the employer's own careers page. A free mailbox
  (gmail.com and the like), a hiring system's or job board's domain, `noreply@`, `privacy@`, `accommodations@` and the like never count;
- the posting names only one such address.

Such a posting has `contact` set to the address, `apply: "email"` and `instant: true`: the card says Ready, and a swipe right sends it. An
employer that connected its hiring system gets the application there instead, never also by email.

**The send.** The existing email route (`uaply_api._deliver`): the person must be signed in with a confirmed address that is the profile's
email, have the consent record, and the live countdown with Undo runs first. The address is always the one this server read from the
posting (`jobs_api.known_contact`), never the one the browser sends. The message has the person's details and resume, `Reply-To` the
person's own address, and a last line that says why it came, with a stop link. The person gets the confirmation email, and Job Tracker says
Sent.

**Limits.** One application per person per job (a second swipe is "duplicate"). At most `email_domain_daily` (10) applications a day to one
employer's domain, from everyone together, and UAply's own `daily_limit`: past either, the swipe is a hand-off (Finish on their site) and
nothing is emailed. The Brevo plan is unchanged.

**Bounces and stops.** An address that hard-bounces (Brevo's webhook, `/api/email/events`), that the mail server refuses, or whose owner
opens the stop link (`/employer/stop`, a page that asks first, so a mail scanner opening the link changes nothing; its button posts to
`/api/employer/stop` with the link's signature) goes on the bounce list for a year. Its postings are hand-offs again at once (the job list
and `jobs_api.job_policy` both read the list).

**Test mode sends nothing.** `delivery: "test"` puts the application in the test inbox under the posting's address; `UAPLY_SIGNUP_TEST=1`
sends no email of any kind, even with real email settings (a swipe is then a hand-off).

**Coverage.** `/api/status` counts the postings that take applications by email (`apply.classes.postingEmail`). Before this change the
count was 0: no feed posting was ever emailed. How many postings name an address is the feeds bot's count.

## b. Automatic submit (phone app only, off)

The first-swipe box's Automatic submit tick sits right after the four ways and says where it applies, built from
`shared/assist-systems.json` by the same rule as the switch (today: "where a hiring system allows it; none is switched on yet"). The page
(`autoWhere` in `shared/uaply-live.js`) and the server (`consent_api.auto_text`) build the same words from the same file.

`shared/assist-systems.json` keeps `counsel_approved: false` for every system; Saif decides whether he flips it. The app passes mode
"automatic" only when the system's switch allows it and the account's consent record has the Automatic submit tick (`autoConsent` in
`shared/uaply-nav.js`). In the employer's page, `UAplyAssist.autoSubmit` first checks every condition again (no human check of any kind, no
required question or consent box left, the resume attached where the form takes one, a Submit button), shows "Submitting for you in 3" with
a Cancel button, and at 0 checks again and only then presses Submit. Cancel leaves the form for the person. Sent is said only on the
employer's confirmation page.

## c. One tap

A hand-off says "Saved to Job Tracker. One tap to finish on their site." only when the phone app has just opened the employer's form;
anywhere else (the website, a system the app does not fill) it says "Saved <company> to Job Tracker." Its Job Tracker row "Saved Oct 23" (only a send says Applied
or Sent). In the phone app, a swipe right that is a hand-off on Greenhouse, Lever, Workable or Ashby opens the employer's form at once (the same
assisted flow as Finish applying: the scan, UAply's question box for anything the profile lacks, then the form filled). A form with a human
check says "One tap to finish: this employer asks you to confirm you are a person." and is scrolled to the check's box (or to Submit when
the check is invisible). UAply never fills, starts or touches the check. Backing out keeps Finish on their site. SmartRecruiters (its bot
wall), employers' own careers sites and the website keep the hand-off as before.

Time from the swipe to the form being ready, measured on the mock forms (`tools/test-assist.js`, the app's two loads and its 150 ms asks)
and in the browser (`tools/ui-apply-paths.js`, UAply's own half with a stand-in for the plugin): see the latest run's `ONE-TAP-TIMES` and
`ONE-TAP-CLIENT` lines. A real employer page adds its own load time on the phone's network.

## d. The outreach queue

`python tools/outreach-queue.py` prints the week's invitations (SmartRecruiters' boards first: the largest share of jobs and an Application
API that applies on behalf of the candidate; then the most swiped-on; then by US jobs) and the queue's totals. `--mark system:board invited`
records each step in `docs/employers/outreach-queue.json`. It imports nothing that can send; `tools/test-outreach-queue.py` checks that and runs
it with the network taken away.

## Research behind it (October 23, 2026)

- Indeed Apply delivers to hiring-system partners as signed JSON posts to a URL in the job feed, after a developer agreement and review
  ([docs.indeed.com](https://docs.indeed.com/indeed-apply/ats)). ZipRecruiter's Apply Webhook does the same after a jobs integration
  ([ziprecruiter.com](https://www.ziprecruiter.com/partner/documentation/apply-webhook/)). LinkedIn Apply Connect is for approved developers
  under an API agreement ([Microsoft Learn](https://learn.microsoft.com/en-us/linkedin/talent/apply-connect)). Handshake applies in Handshake
  or redirects to the employer's site ([Handshake](https://support.joinhandshake.com/hc/en-us/articles/6772611653015-How-to-Use-Handshake-s-Workday-Integration)).
  None of them submits into another company's form without the employer's own integration; email, where used, is the employer's channel.
- The partner programs a job board can join all need the employer's key: Greenhouse's Job Board API, Ashby's `applicationForm.submit`,
  SmartRecruiters' Application API ([developers.smartrecruiters.com](https://developers.smartrecruiters.com/docs/application-api)), Lever and
  Workable. That is the connect kit (part d).
- The five systems' terms and measured human checks are in `docs/assisted-apply.md` and `shared/assist-systems.json`.
