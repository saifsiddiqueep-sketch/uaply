# Changelog

How versions move: work happens in `sandbox`, is tested there, and goes to `dev` through a pull request. `dev` is the release
build: it is what the hosted site and the phone apps run. Each version is tagged on GitHub (Releases). `main` is the original
production page and only changes when the owner decides.

## Unreleased (sandbox)

### Job Tracker: a restored backup keeps its applications, and every hand-off can be marked finished (Mohammed, October 22)
- **A restore no longer drops applications.** Restoring a backup (Profile, Data & privacy, Restore) kept only the swipes whose job was in
  the list at that moment, and dropped what happened to each one (Sent, Sent (by you)), while saying everything was restored. On a new
  device or a month later most applications were gone. Now every swipe that carries its own row copy (title, company, place, link, kind:
  every swipe since October 22) comes back as a Job Tracker row, never a card on the deck, with its Sent or Mark as applied status, its
  Interview / Accepted / Rejected stage and its details. A swipe from an older file whose job is no longer listed cannot come back, and the
  message now starts with how many: "Restored, except for 1 application: its job is no longer listed, and the file has no copy of it."
  (`shared/uaply-nav.js` `importBackup`; the row-copy helper `__uaplyRowStub` in `shared/uaply-live.js` now always exists, not only when
  something was saved.)
- **A restore never sends an application by itself.** An application the file says was waiting to send comes back as "Not sent" with
  Try again, never as waiting to send: the next start used to send it to the employer (profile, resume and answers) with nobody tapping
  anything, from a file that could be months old or not the person's own. Only states the Job Tracker can show come back (Sent, Sent (by
  you), Sent (test), Finish on their site, Not sent, Not sent yet); anything else comes back as a hand-off, and what Undo of Mark as
  applied goes back to is cleaned the same way. A job id that is not a plain number (a hand-edited "1e6") is skipped: it used to stop
  the whole restore with a script error. The stand-ins are added only once the restore is saved.
- **Mark as applied on every hand-off of a real posting**, including a row whose copy has no link to the posting (before, no link meant no
  button, so that row said "Finish on their site" for ever).
- **Mark as applied counts for what UAply learns from swipes** as finishing on the employer's site, the strongest yes (`uaply-learn.js`
  `finish`, which only an opened employer link used before). Undo puts it back as it was.
- The 30-day and 400-job loss the card describes was already fixed on sandbox ("Job Tracker keeps every row" below); checked again with a
  seeded 31-day-old cache. The Sent / To finish counts are PR 51's (Trello K0QEMeQm) and are not repeated here.
- Test: `tools/ui-tracker-keep.js` 31 checks (16 new: a restore on a new device whose jobs left the list, a restored application that was
  waiting to send (no request to /api/apply after a reload with no tap), a hand-edited id, a hand-off with no link, Mark as applied and
  Undo in what UAply learns; the restore ones fail on the code before, the waiting-to-send one with a real POST /api/apply; its answers fixture is now written from inside the app's
  frame, so it no longer sets off a script error in the app). Trello EJDLrliG.

### Release candidate review, surgical fixes (Reviewer 2, October 22)
- **Careers sites:** every request (robots.txt, the sitemap, each page) goes through a public-only opener (`jobs_api._cp_open`): a
  redirect is followed only to a public https address, and the name is looked up once and refused unless every address is public (not
  private, loopback, link-local such as 169.254.169.254, shared or reserved); the connection goes to that checked address.
- **Mark as applied** needs a verified email (403 `verify` otherwise), keeps a mark only for a job in that person's reminder (any other
  mark writes nothing) and at most 200 per account. **Reminders** look at the account again right before sending: a deleted one gets
  nothing and its entry goes.
- **Help chat:** with AI answers on, the server sends a message to the AI only with `aiOk: true` (the page's Continue); otherwise the help
  articles answer (`aiConsent: true`).
- **Feed text:** tags are taken out after the last unescape (`jobs_api._text`).
- **The site's share of code emails** is never below one connection's own 80 (80 at the default 500, so a campus keeps its 80), and only
  the share groups an IPv6 /64 (`auth_api.share_key`); the per-connection limits count each address on its own again.
- Assisted apply's field map knows `twitter`.
- Tests: test-career-pages 45 (15 new), test-emails 78 (7 new), test-chat 6 (new), test-public-auth 109, test-swipe-e2e 328 (+1).

### Launch day: the runbook, the owner's self-check, and the hosting docs as they are today (October 22)
- **The owner's self-check** in `/api/status` (owner only: this computer, or the owner password): when a job board was last read
  successfully, when an email last went out (kept on the disk in `mail-count.json`), the data disk's free and total room, and plain
  warnings (no good board read in 2 hours, under 100 MB free, a data folder that is not a persistent disk). Next to the outside uptime
  check (`docs/uptime.md`), which only knows whether the site answers. `tools/test-self-check.py` (18 checks), in the runner and CI.
- **`docs/runbook-launch.md`**: Saturday's exact sequence: a backup, the release PR and tag, the deploy and its start-up line,
  `live-check.py --expect all`, `ui-live.js`, the Galaxy phone walk, a real sign-up with a real code, a real Google sign-in, what to watch
  every 2 hours, and the one-command rollback to rc.13 (`e6aced4`) through Render's API (or two clicks in Events).
- **HANDOFF.md, DEPLOY.md and render.yaml** say what runs today: one hand-made Render service `uaply` behind Cloudflare (proxied, SSL/TLS
  Full (strict), `CF-Connecting-IP` trusted only from Cloudflare's ranges), a private repository with no GitHub Pages, `UAPLY_PUBLIC_URL`
  and the USAJOBS key as their own variables, manual deploys until the Render GitHub app is linked, rollback and the self-check.

### Release review fixes (Reviewer 2, October 22): what an employer's page can get, the site's hour of codes, busy hiring systems
- **Assisted apply hands a page nothing it does not ask for.** Only the hiring systems' own hosts (`hosts` in
  `shared/assist-systems.json`) and this job's own page are ever filled; on a redirect, a tapped link, a look-alike host or http,
  nothing goes in and nothing is read (`AssistActivity` checks the address before every call, `AssistActivity.CALL` again inside the
  page). The script lives under a random name, new each time the screen opens, frozen and fixed: a page's own `window.UAplyAssist`
  (which used to be handed the profile) is never called, and the old `window.__uaplyScan` / `__uaplyRep` globals are gone. The scan
  gets stand-ins for the person's details; the fill gets only what the scan saw the form ask for (`assistShape`, `assistOnly`), and
  fills the five mock forms exactly as the whole profile did; a saved answer whose question names another employer is not handed over
  either (it told the page where else the person applied). The measurement tool now hands pages the same.
- **The site's hour of code emails:** one address may use at most 5% of it (25 of 500), an IPv6 visitor counts by its /64
  (`serve.limit_key`, for every limit), and an account's owner (known-device cookie, or signed in to that verified account) is never
  held back by it.
- **A busy hiring system:** a 429 from an employer's system is remembered for a minute (readiness no longer asks it again on every
  card), and requests for the same posting at the same moment share one read (`ats_api.one_read`, also for Greenhouse's public form).
- Tests: `tools/test-assist-hostile.js` (new, 33), test-assist 226 (12 new), ui-assist-tracker 31 (4 new), test-public-auth 107
  (10 new), test-ats-flow 52 (10 new). Both assist tests now run in `tools/run-all-tests.sh`.

### The phone walk checks the sign-up card; two fit fixes it found (October 22)
- `tools/phone-walk.js` walks the sandbox's sign-up card by real touch: Continue with Google, email, names, the 18+ tick, the code from
  the stand-in inbox, the two questions, sign out, sign-in by code, and Google through the stand-in Google. Not finding a sign-up form is a
  FAIL (it used to be skipped). Taps count the keyboard's offset and are measured again when Chrome's address bar changes the page.
- A short turned phone (667x375): the Help button scrolls with the header row instead of lying over the card's Last name box.
- With a person's own profile, the job type buttons (All, Remote, Hybrid, On-site) are 44 px targets again on short phones (they were 39).
- Checked on the Galaxy A17: 38 screens, 0 fit problems; `ui-phone.js` green at 440x956, 375x667, 390x844 and turned at 667x375,
  844x390 and 832x384 (the two turned sizes are now in `tools/run-all-tests.sh`).

### Employer outreach kit and "Test this connection" (the first connected employer)
- **docs/employers/connect-kit.md**: the outreach email (a swipe right *starts* an application; it is *sent* only where the employer
  connected), the one-page kit with the ten-minute steps for Greenhouse, Lever, Ashby, SmartRecruiters and Workable and the privacy line,
  rendered to **connect-kit.pdf** by `node tools/cdp.js tools/render-connect-kit.js` (fails if it stops fitting one page), and the top 50
  employers in the feed by US jobs with their careers sites, written by `python tools/employer-targets.py --write`. Nothing was sent.
- **/setup, Connect an employer's hiring system: Test this connection** (and **Test** on each saved connection): reads the employer's
  own open postings and reports the count, and checks the key where the system has a read for it (Ashby's job list, SmartRecruiters'
  posting form, Workable's jobs); Greenhouse and Lever keys are checked by the first application. Nothing is sent or saved; the key is
  never shown. On the hosted site it tests the saved keys only. `POST /api/setup/test-ats`, owner only.
- **docs/employers/first-connection.md**: our own SmartRecruiters account as launch day's first connected employer, step by step
  (including what to do if the free plan has no API key). SmartRecruiters' API keys give full access (its own developer page): the kit,
  the SmartRecruiters page and /setup now say so, and that UAply uses only the Application API.
- Tests: test-setup 65 (13 new against the stand-in systems, which now serve each system's public posting list and Ashby's job.list),
  ui-setup, test-ats-flow 42, the per-system ATS suites, test-public 79.

### Sign-in, server side (PR #49 review): the real visitor's address everywhere, one set of limits, a site-wide cap, Google asks the owner's tick
- **The visitor's address** for every limit and lock-out is the last hop the host's proxy added (`serve.client_ip`, with Cloudflare's
  CF-Connecting-IP when that hop is Cloudflare's), never what the sender wrote first in X-Forwarded-For. The same helper as learn-cache.
- **One set of limits:** 40 sign-ups an hour per address, 5 per address and email; codes 3 an hour per account, 80 per address, 5 per
  address and email, on every route that emails a code (Create my account, Email me a code, Resend).
- **A site-wide hour:** at most 500 code emails an hour for the whole site (`UAPLY_CODE_SENDS_PER_HOUR`); past it, "UAply is sending a lot of
  sign-in codes right now. Try again in a few minutes, or use Continue with Google."
- **Google and an account nobody proved:** joining it now asks this person's own 18+ / Terms tick and records it (`terms_at`), on every
  server, as the code sign-in already did. `oauth_login` says `created` only when it made the account; "made in the last 60 seconds"
  is gone, so signing in with Google twice no longer says "Account created" twice.
- Tests: test-public-auth 97 (forged first entries, Cloudflare, campus limits, the code routes' real address and 80 an hour, the site
  cap, Google's tick and the created flag; 17 of them fail on 6552edf), test-accounts 144 (4 fail on 6552edf), test-signup-flow 123.
  docs/reviews/pr49-ui-fixes.md proposes the card's two remaining fixes for Mohammed.

### Data fixes from the release review (October 22): job ids, Job Tracker rows, answers per employer, the minimum to apply
- **Job ids never collide** (`jobs_api._claim_id`). An id was 100000 plus 6 hex digits of a hash, so 20,000 postings shared an id about
  12 times: the second posting was never shown, and a swipe saved under that id could later point at another job. Every id handed out is
  now kept with a fingerprint of its posting (`job-ids.json` beside `jobs-cache.json` in the data folder, forgotten after 180 days
  unused); a second posting whose 6 digits are taken gets 7, then 8 ... up to 13 digits. An id that never collided is exactly what it
  was, so saved swipes still match. Partner employers' ids use the same rule.
  **One-time note:** on the first start with this file, a pair of postings that already shared an id is settled by which is read first,
  which may be the one that was hidden before. Live (uaply.net) lists 428 jobs today: about 0.005 shared ids expected, so no live swipe
  is affected; on the sandbox (20,000) about a dozen swipes may now show the other posting of their pair.
- **Job Tracker keeps every row** (`shared/uaply-live.js`). Each swipe carries a short copy of its row (title, company, place, link, kind);
  a swiped job's saved copy never ages out (it used to go after 30 days); applications are kept up to 2,000, passes up to the newest 1,000
  (the oldest pass goes first). A job in neither the list nor the saved copy comes back from its row copy as a stand-in that is never a
  card. Older swipes get their row copy the next time their job is in the list or the saved copy.
- **Answers about one employer stay with that employer** (`autofill.norm`, `uaply-assist.js` `akey`). A question that names the employer
  or asks why this company or role is kept under "{at employer}": Stripe's "Why us?" is never sent to Plaid (it used to be, as
  "why ... {co}"). Questions about the person (work authorization, start date, 18 or older) are still asked once for every employer.
  The phone app now keys a question exactly as the server does, so one answered in either place is not asked again.
  The filter runs on every path: the app sends a swipe or a plan only this employer's and the general answers (`answersFor`), the
  phone app hands an employer's page only those, and the server drops any other (`autofill.clean_answers(raw, company)`), so an answer
  written for employer A never reaches employer B's form whatever a browser sends.
- **The server checks the minimum to apply** (`uaply_api._validate`): no phone number and no resume (file or link) is refused with a
  plain sentence, as the app already did (READY_MIN). Reading a form (`/api/apply/plan`) is unchanged.
- Tests: `tools/test-job-ids.py` (15: 20,000 postings with 60 forced pairs, none lost; restart in the opposite order), `tools/ui-tracker-keep.js`
  (13: reload 31 days later and after 500 swipes; 1,000 passes and one more), `tools/test-autofill.py` (+12, one through the server's sandbox form to Plaid), `tools/test-delivery.py` (+5),
  `tools/ui-tracker-keep.js` (+2: what a swipe sends), `tools/ui-assist-tracker.js` (+1), `tools/test-assist.js` (+1, the bridge keys as the server does);
  the other tests' applicants now have a phone number.

### The daily reminder: Mark as applied reaches the server, and swipes never wait for the reminder's email (October 22)
- **Mark as applied** in Job Tracker now tells the server (`POST /api/apply/mark`, signed in): the day's "finish your application"
  reminder stops listing that job, and a later hand-off of the same job is not put back (`uaply_api.mark_applied`, up to 500 job ids kept
  per person). A swipe record that already carries the mark (`"marked": true`) is never reminded. Undo only stops skipping it.
- **The reminder is sent outside the lock** every swipe takes (`send_finish_digests`): what each reminder lists is copied under the lock,
  the email goes without it, and then only those jobs leave the list, so a job swiped (or marked) while the email was on its way is
  neither lost nor sent twice. One sender at a time.
- Tests: `tools/test-emails.py` (+9: mark, a later hand-off, a marked record, Undo, a bad job id, a swipe during a slow send, two senders),
  `tools/test-swipe-e2e.py` (+3: the route signed in, a bad job, signed out).

### Assisted apply: questions first, then the form (fill 95-98% on the Galaxy, nothing required left but agreements)
- **The bridge.** Before the employer's form opens, the phone app reads it (`UAplyAssist.scan`, which changes nothing) and UAply asks
  what the profile cannot answer in its own question box ("Continue to {company}'s form"); required questions must be answered,
  optional ones may be skipped; the answers are kept like every question-box answer. Then the form opens filled with them.
  `AssistActivity` scan mode (behind a cover), `AssistPlugin` returns the questions, `askSheet` takes optional questions and new words.
- **The synonym map** in `shared/uaply-assist.js`: preferred names, "first and last name", phone digits and country-code lists,
  date pickers and typed dates in the field's own pattern, graduation month and year apart, degree names (Bachelor's, BA, BS), notice
  periods, current role (its end date is not asked), 18 or older (from the first-swipe agreement), "without sponsorship", yes/no
  choices read by meaning, How did you hear: UAply or Other then UAply. Privacy, consent and certification questions in any form
  (lists, radios, Yes/No buttons), pronoun "Custom" boxes and age ranges are never filled or asked.
- **Measured on the same 80 postings** (`python tools/assist-measure.py --phone <serial>`, one command): fill Greenhouse 65% to 96%,
  Lever 64% to 98%, Ashby 60% to 95%, Workable 50% to 96%; required left at the form, median, 0 on all four (only agreements remain).
  With only the required questions answered: 89%, 92%, 72%, 85%. docs/assisted-apply.md has the table.
- Tests: `tools/test-assist.js` 213 checks (every new mapping and the bridge on a mock form per system), `tools/ui-assist-tracker.js`
  26 (the bridge in Job Tracker: asks, blocks a blank required answer, skips answered ones, Not now opens nothing, keeps a cover letter to its employer).
### Apply wording from the job's route; learner, caching and uptime
- **The card and the Job Tracker row read the job's `route`:** connected or email: "Applies instantly"; one-tap: "Ready, one tap on their
  site"; assisted or ready: "Ready" (the server's labels "Ready" and "Ready, one tap" read the same). "Apply instantly" and "Opens employer
  site" are gone from the app, the help answer, the employers page and the Play listing. tools/ui-route.js checks every route at 390 and 1280.
- **Learns from your swipes** no longer pushes strong matches down for a new person: no reordering before 8 swipes or while every swipe
  is a yes, an attribute counts from 2 swipes, and before 30 swipes a 90%+ match loses at most 10 points.
- **Scripts and the legal style sheet are cached a year** under content-hashed names (uaply-nav.<hash>.js); pages, /api and the service
  worker stay no-store; a changed file gets a new name at once.
- **docs/uptime.md**: the UptimeRobot free monitor for https://uaply.net/healthz, for the owner to set up.

### Sign-up, nothing hidden: no password, an emailed code, two questions (Mohammed's design, Oct 21)
- **One card in the middle of the Account screen**, with the UAply mark directly above it and the two centered together on phones and
  laptops. In Mohammed's order: Continue with Google, "or", Email, First name, Last name, the 18+ / Terms tick, Create my account, "Have an
  account? Sign in". Google tapped before the tick: the box shakes (not with reduced motion), says "Tick the box first, then Continue with
  Google." and scrolls into view. The email box offers "Did you mean gmail.com?" for a typo. No password, no privacy map.
- **No password.** Create my account emails a 6-digit code (six boxes, paste, auto-advance, Resend after 30 seconds); nobody is signed in
  until it is typed. Google skips the code for Gmail and Google-run addresses. Returning people: Google, or Email me a code, whose answer
  never says whether an address has an account. Mohammed can flip this back to a password (today's password routes are untouched).
- **After the account exists:** "Account created, {first}." (or "Account created." and "What should employers call you?" when the name was
  lost to a refresh or typed on another device, and after Google), then "What kind of work are you after?" and "Where do you want to work?",
  each with Back, Skip/Continue, Enter and Esc, beside a preview of what an employer sees. The preview counts the app's minimum to apply
  (`READY_MIN`: name, email, a phone number or a resume). The end says "You're ready to swipe." only when that minimum is met; otherwise
  "Almost ready" with Add a phone number / Add a resume, one tap from the field.
- **Kept honestly:** the account (email, when the box was ticked) on the server; name, work picks and place on this device only, in the
  app's own profile. A name saved for an earlier account on the same device is never reused. Work picks only sort jobs.
- **Google is asked for `openid email` only**, as today (asking for the name is a question for Saif). The card says UAply keeps only the
  email and the Google account number. A password nobody had proven, removed by a Google sign-in, is said on the card.
- Server (sandbox only, `CODE_SIGNIN` in `serve.py`; `UAPLY_CODE_SIGNIN=0` turns it off on a sandbox, nothing turns it on elsewhere; a
  public server with no email set up keeps today's card): `POST /api/auth/signup` with `"passwordless": true`, `POST /api/auth/code/send`,
  `POST /api/auth/code/verify`, `codeSignin` in `/api/auth/providers`. On dev every one answers exactly as before. A code sign-in that
  first proves an inbox shuts out a password nobody had proven and a Google login Google did not vouch for, and ends every session they
  had, and says when it took Google off (`googleRemoved`; the card then stops offering Google to that person). Any account whose address
  was never proven is finished only with the code typer's own 18+ tick (`needsAgree`), recorded as theirs. Limits: 3 code emails an hour
  per address and per account (shared with Resend), 12 per connection, 6 a day per address; 15 wrong codes for one address in a day stop
  code sign-in for it until the next day. The daily stats count a no-password sign-up when its code is typed.
- **Sign out, then the next person:** the card starts empty (no email, no name, the box unticked). A redraw of the Account screen while
  someone types (a late start-up answer on a slow connection) keeps them in the same box with the caret where it was. The last screen's
  button says "Show me jobs" until a swipe right can apply, "Start swiping" once it can.
- `shared/uaply-signup.js` (the "Sign-up, nothing hidden" experiment, on in the sandbox) and four guarded hooks in `shared/uaply-nav.js`
  (`check.js` fails if one goes missing). The app's signed-in card says "You sign in with an emailed code or with Google" there.
- Tests: `tools/test-signup-flow.py` (89 checks) and `tools/ui-signup.js` (58 checks in a browser at 1280x720 and 390x844, including
  hostile text in the card's boxes, Sign out, and a redraw while typing). `tools/run-all-tests.sh` runs both, and runs the sandbox's `ui-inject.js` (unchanged) against a
  second sandbox with the card off (18770).

### Assisted apply in the phone app: UAply fills the employer's form, the person taps Submit
- **Finish applying on their site**, in the UAply phone app, opens the employer's own page inside the app (`AssistPlugin`,
  `AssistActivity` in `mobile/android`), fills it from the profile with `shared/uaply-assist.js` (served at `/uaply-assist.js`), attaches
  the resume file, scrolls to Submit and says **Review and tap Submit**. Voluntary self-identification, consent boxes, follow-ups and
  human checks are left to the person. The page's own resume box offers **Use my UAply resume** first. On the website nothing changes.
- **Sent only on the employer's confirmation page:** the Job Tracker row becomes **Sent** ("Sent on {company}'s own page: their
  confirmation page appeared") only then; closed earlier, it stays **Finish on their site**.
- **The per-system switch** `shared/assist-systems.json` (served at `/assist-systems.json`): "assisted" for every system. "automatic"
  takes the attorney's approval and a measured human-check share of 0, and the page is checked again before any submit.
- **First-swipe agreement, version 3:** adds "You authorize UAply to complete and submit job applications on your behalf using the
  information you provide." (recorded with the time); the Terms draft is in LEGAL-REVIEW.md section 11.
- **Measured** on the owner's Galaxy, 20 real postings per system, nothing submitted: see `docs/assisted-apply.md`.
- Tests: `tools/test-assist.js` (mock form per system in `tools/fixtures/assist/`), `tools/ui-assist-tracker.js` (Job Tracker with a
  stand-in plugin), `tools/assist-measure.js` (real postings, every application-carrying request refused).
### Five fixes from the October 22 audit
- **Rate limits count the real visitor.** The visitor's address is the last hop the host's proxy added to X-Forwarded-For (an internal hop
  after it is skipped), or CF-Connecting-IP when that hop is a Cloudflare server (Cloudflare's published ranges, read at start and every
  24 hours, with a built-in copy). A script writing a new made-up first entry every try is now locked out like anyone else. The limits are
  campus-friendly: 40 sign-ups an hour per address (was 5), 5 per address and email, codes 3 per account, 80 per address (was 12), 5 per
  address and email; each refusal says what to do.
- **Mark as applied.** A hand-off row in Job Tracker has Mark as applied: the row then says Sent (by you) with the date; Undo once.
- **One reminder a day.** A hand-off swipe no longer sends its own "Finish your application" email: the jobs wait and go together, the first
  reminder 30 minutes after the first such swipe, then at most one a day (kind "digest", held by the daily limit like other mail that can
  wait; removed with the account). Receipts for applications UAply sends are unchanged.
- **/.well-known/security.txt**: the company's contact address, the privacy page, and an expiry a year from now.
- **Help chat and the outside AI.** With AI answers on, the first message shows a one-line notice that it goes to Anthropic, with Continue or
  Not now (remembered on the device); Not now sends nothing.
- A short message after a swipe is no longer a narrow column (phones use the screen's width; at least 320 px elsewhere).
- Tests: tools/test-public-auth.py (forged X-Forwarded-For, Cloudflare, sign-up and code limits), tools/test-emails.py (the reminder),
  tools/test-pages.py (security.txt), tools/ui-journey.js (Mark as applied, the chat notice); each fails on 512bf84.

### Apply journey fixes (50 real swipes on the Galaxy A17 and a laptop, October 22)
- **The card tells the truth before the swipe.** Where the server previews forms in test mode (the sandbox), a swipe right on any Greenhouse
  posting reads its form and asks its questions; the card now asks the server for that same plan (POST /api/apply/plan) and says
  "N answers needed" instead of "Ready". `/api/apply/config` says `formPreview`; one rule (`uaply_api.form_preview`) decides both.
- **The question box on a phone.** It opens with no field focused (the keyboard no longer covers it before it is read), and it is fitted to
  the screen left above the keyboard (the top page's visual viewport), with Send application pinned to its bottom.
- **Start date.** "When can you start?" from Profile, Account goes with the application when Profile setup's start date is empty, and fills
  the employer's start-date question (`autofill._NOTICE`).
- **Finish applying opens the form**, not the posting: Lever `/apply`, Ashby `/application`, SmartRecruiters `?oga=true` (its own API's
  applyUrl), added as text so nothing else in the address changes. Learns from your swipes still recognises the job.
- **Old messages go.** A "Saved ... Undo" message whose time ran out while the tab was hidden goes when the tab is shown again.
- **Job Tracker after a reload.** A swiped job is saved with the swipe, so its row is still there after a phone reloads the tab, even when the
  server's list no longer has the job (job 14769135 on the Galaxy).
- Tests: `tools/ui-journey.js` (10 checks, run by `tools/ui-questions.py`), 2 more in `tools/ui-questions.js` (phone keyboard, focus), 3 in
  `tools/test-autofill.py`. Each fails on the code before this change.

### A swipe right only sends a complete application (the front end of the readiness rule)
- **The minimum, in one place.** `READY_MIN` in `shared/uaply-nav.js`: a name, an email employers can reply to, and a phone number or a
  resume. The deck, the cards and every checklist read it. Below it, a swipe right (finger, Apply or the arrow key) opens **Finish your
  profile first** with exactly what is missing, sends nothing, and the card stays on top.
- **A checklist** on Account and at the bottom of the last setup step: name, email, phone, resume, work authorization, education, city,
  earliest start. Each missing item is one tap from its field (the setup step opens with the field focused).
- **Ready or not, on each card.** A connected employer's form is read ahead through the new `POST /api/apply/plan` (the same reading a
  swipe right does, nothing recorded or sent), kept per posting until the profile or a saved answer changes: **Ready to apply** or **N
  answers needed** (also Sign in to apply, Finish on their site). Email employers and hand-offs say **Ready**.
- **At the swipe** the question box asks only what is missing; answered, it sends. Left for later (or a resume file to add), the job waits
  in Job Tracker as **Not sent yet** with **Answer now** (it used to go back to the deck).
- **Learning:** each question an employer's form asked is counted by its key and kind (no answer, no person), in the instance's own
  `question-stats.json`; `/api/status` shows the counts to the owner only.
- Tests: `tools/test-swipe-e2e.py` runs `tools/ui-swipe-ready.js` (every apply path with no phone, no resume, no work authorization, below
  the minimum, and an employer's own question on four systems) and `tools/ui-ready-walk.js` (a half-finished student at 390 x 844 and
  1280 x 800, by finger). The stand-in Greenhouse now checks every form's required questions and every stand-in records what it refused
  (`/__rejected`, which must stay empty). Server-side refusal of incomplete applications is UAP-10.

### Taps and focus: no blue tap box, a keyboard ring that matches the app
- On Android, tapping "Try again" on the starting-up screen painted Chrome's default light-blue rectangle over the round button (the
  owner saw it on a Galaxy A17). One rule, `shared/uaply-focus.css`, now goes word for word into every page UAply serves (the app,
  dev's and the sandbox's outer pages, every legal page, the offline / starting-up screen, the 404 and "moved" pages, /setup, /feedback,
  the test inbox, the phone app's "can't connect" screen): no tap highlight, no ring after a tap or a click, a 3 px ring in the accent
  colour for keyboard users. The standalone pages also get a pressed state. Server-built pages take it from `ui_rules.py`.
- The starting-up screen checks `/healthz` every 3 seconds for the first minute, then 1.5 times longer each try (15 seconds at most),
  and reopens the page on the first 200 (the page is sent with `Cache-Control: no-store`, so it is never a saved copy). Its cached copy
  in the service worker is now `uaply-shell-v2`.
- Tests: `tools/test-focus.py` (12 checks: every copy word for word; `--sync` rewrites them after a change) and `tools/ui-focus.js`
  (28 checks in Chrome at 390 px with touch: the computed tap highlight of every element on every page, no ring after a real touch,
  the keyboard ring, the retries against a /healthz answering 503). Run against the code before this change, 23 of its first 25 checks failed.

### Google Play listing pack
- `mobile/store/play/`: app name, short (80) and full (3,5xx of 4,000) descriptions in the app's own honest wording, the 512 px icon, the
  1024 x 500 feature graphic, five phone and five 7-inch tablet screenshots at 1080 x 1920 (Jobs, Dashboard, Profile setup, Filters, Help),
  the Data safety answers, the content rating answers, the App content declarations (privacy policy, ads, app access, 18+), the closed-test
  invite and steps, and a README mapping each Play Console screen to its file. `docs/play-store.md`: the ten steps to production.
- `tools/make-play-assets.js` draws the pictures from the app itself (a sandbox switched to the release build's features, example jobs and
  an example person); `tools/test-play-listing.py` (22 checks) checks every picture's exact size and format and every text's length.

### "Dashboard" is now "Job Tracker"
- The job seeker's middle tab and everything that names it say **Job Tracker**: the bottom bar, the Free and early-access plan lists
  ("The full Job Tracker"), the empty deck's note, the help articles, the swipe-right emails ("Open UAply, then Job Tracker, then
  Applied"), the email previews in `marketing/email-previews/` and the sandbox's feature note. The tab label stays on one line at 375 px.
- Nothing internal changed: the ids (`nb-dash`, `pane-track`, `tab-dash`), the `dash:...` links in the help articles, saved state and
  storage keys are the same, so saved settings and deep links keep working. "dashboard" stays a search word in the help.
- Hiring mode has no Dashboard screen; nothing there changed.
- Tests: `tools/ui-buttons-bar.js` checks the tab reads exactly "Job Tracker" on one line inside its tab and the bar at every size it
  runs (375, 390, 440, 1280; dev and sandbox); the tests that named the screen follow the new word.

### Google Play: an installable website and the Trusted Web Activity
- **Installable.** `/uaply.webmanifest` (UAply, start `/`, standalone, the app's `#FDF0F2` background) with 192 and 512 px icons, ordinary and maskable (`shared/uaply-icon-*.png`, made from `mobile/assets/icon-only.png` by `tools/make-web-icons.js`), linked from dev and the sandbox. Chrome reports nothing missing to install it.
- **Offline and "starting up" screen.** The service worker `/uaply-sw.js` saves only `/uaply-offline.html` and its icon. When a page cannot load (no connection, or the host's 502/503/504 during a deploy) it shows that screen at the same address; the screen checks `/healthz` every few seconds and reopens the page by itself. It never caches the app's code, never touches `/api/`, `/healthz`, `/.well-known/`, the owner pages or other sites. The pages' security policy adds `manifest-src 'self'; worker-src 'self'`. The hosted copies (`share/`) leave both out.
- **`/.well-known/assetlinks.json`** for the package `com.uaply.app`, from `UAPLY_ASSETLINKS_SHA256` (the Play signing and upload key fingerprints, comma-separated): no rebuild when a key changes; a plain 404 when unset; answered on every address without a redirect.
- **`/legal/delete-account.html`**, the account-deletion page Google Play asks for, linked from the Privacy Policy, Support and the legal index.
- **`mobile/twa/`**: the Bubblewrap `twa-manifest.json` (host uaply.net, `fallbackType: customtabs`) and the owner's steps in its README.
- Tests: 20 more checks in `tools/test-pages.py`; `tools/ui-installable.js` (15 checks in Chrome: installable, cache contents, server down, offline, a 502 deploy, back by itself).

### A student's first visit (the October 21 walk as a Drexel junior)
- **Fill from your resume, for students.** A club office under "Leadership & Activities" (and "Activities & Leadership", "Campus involvement" and similar headings) is no longer read as the most recent job. Skills with a note in brackets ("Microsoft Excel (pivot tables, VLOOKUP)", "SQL (basic)") stay one skill each instead of half-bracket pieces, and a job title keeps its own bracket ("Barista and Shift Lead (part-time)"). PDF text is passed on as UTF-8, so bullets and accented names arrive whole on a Windows computer too (before, "Jordan Álvarez" came out as "Jordan �lvarez" and the name was not found, and bullets were not seen as bullets).
- **A student's part-time job is not their target title.** While the resume's graduation month is still ahead, the latest job fills Your job title there, the employer and the start month, and becomes the target title only when it is an internship or co-op. Target titles decide which jobs show, so "Barista" hid every internship.
- **Never a plain "Applied" for an application nothing was sent for.** A job whose employer's form has questions is marked "Not sent yet ... Answer now" the moment the question box opens, so leaving the box open, going to Applied or closing the app no longer leaves a row that looks sent.
- Help and Profile setup say "Jobs" (the bottom bar's name), not "Services".
- **Target titles never empty a section.** "Hide roles that do not match my target titles" (on for every new profile) no longer applies to Internships and Co-op at all: a student's two marketing titles hid 99 of 105 internships and the menu read "Internships 0". On Full-time and Part-time, where no listing matches the titles, the roles are shown with "Showing all roles: none matched your target titles" and a link to Filters; where some match, the rest are still hidden. Tests: `tools/ui-title-filter.js` (13 checks, at 390x844 and 1280x800, in the runner); `tools/ui-walk.js` step 4 follows the new behaviour.
- **Posting dates are always epoch ms.** A date given in seconds was read as January 1970 and the 60-day rule dropped the posting without a word (it emptied `tools/ui-apply-paths.py`'s public postings: 15 failures). 1 more check in `tools/test-jobs.py`.
- **Swipes survive a reload.** The app's start-up read kept only decisions whose job was already in its list, and the saved copy of the job list kept the last 400 postings of a feed that is now over 1,000, so most of a person's Applied and Passed jobs vanished on reload, and the next save made it permanent. A swipe on a real posting is now always kept, and the saved list holds every swiped job first (`shared/uaply-live.js`).
- **The app starts without waiting on the font site.** Its features (the agreement box, the navigation, live jobs, the learner) went on at the page's load event, which waits for Google Fonts: 10 to 27 s on a slow or blocked network. They now go on when the page is parsed, and the font stylesheet no longer blocks the page (`shared/uaply-envs.js`, `prod/index.html`). In this test this took the agreement box from about 20 s to 1 s.
- **No job counts anywhere a person sees** (the owner's rule). The Jobs menu no longer shows how many jobs each section has (it read "Internships 0" or "Full-time 834"), the line above the deck no longer says "N jobs left" (only the person's own "N applied"), and an empty section says so in words: "No internships match your filters yet. Widen them in Filters, or pick another kind of job in the Jobs menu." with a working Filters link. Counts stay on the owner's pages and in `/api/status`; Dashboard keeps the person's own application counts. Tests: `tools/ui-title-filter.js` +5 (no number on any Jobs menu item at 390x844 and 1280x800, no "jobs left", the wordless empty state and its link; all fail on the old code); `tools/ui-walk.js` step 4 follows.
- `tools/ui-learn.js` drags where a finger would: the part of the card in sight above Pass / Undo / Apply (a notice above the deck can push the card's upper third under that row).
- Tests: `tools/ui-boot.js` (5 checks, dev and sandbox, in the runner; both halves fail on the old code); `tools/ui-installable.js` +3 (a slow page is never replaced by the offline screen: the service worker is network-first with no timeout); `tools/ui-swipes.js` section 9 checks the confirmation in the test inbox, since the quiet swipe (Oct 21) no longer names it in the message.
- Tests: a seventh resume (`tools/fixtures/resumes/business.pdf`) and 4 more checks in `tools/test-resume.py`; 3 in `tools/ui-resume.js`; 2 in `tools/ui-questions.js`.

### Workable, the fifth hiring system an employer can connect
- **Workable jobs in the feed.** Workable's public, keyless jobs list (`www.workable.com/api/accounts/{subdomain}?details=true`) is a new feed kind, `workable`, off like every other feed until the owner lists it under `feeds`. Each posting records its subdomain and shortcode, so it becomes "Apply instantly" the moment that employer connects. First board: Hugging Face.
- **Swipe right into an employer's Workable.** With the token the employer's Admin made (scopes `r_jobs` and `w_candidates`), UAply reads the job's questions, answers them with the same rules as the other systems, and creates the candidate on that job as an applicant (`"sourced": false`), with the resume file, education, most recent job, LinkedIn and the source `UAply`. Gender, race, veteran and disability questions are never answered; a required question the profile cannot answer is asked once or left to the person; test mode never uses the token. Everything follows Workable's API reference (cited in `ats_api.py`).
- The **Connect** box on `/setup` offers Workable and says where its Admin makes the token.
- Tests: `tools/test-ats-workable.py` (41 checks) against a Workable stand-in in `tools/mock-ats.py` that checks every request against the reference; 5 more checks in `tools/test-ats-flow.py` and 3 in `tools/test-setup.py`.

### The employer kit
- `docs/employers/`: one plain page per way of receiving applications (Greenhouse, Lever, Ashby, SmartRecruiters, Workable, email and webhook) with what UAply sends, the exact menu path for the key, what the key can do, how to revoke it and what the employer sees; a consent letter the employer signs or replies to before anything is sent; and an index. Linked from `EMPLOYERS.md` and from a new short "For employers" legal page.

## 1.0.0-rc.11 (release candidate)

The swipe buttons a new visitor could not find, and small things the October 17 audit turned up.

### Pass, Undo and Apply always in sight on first open
- **The three swipe buttons are always visible above the bottom bar**, on first open and after the agreement, at every phone size and on a laptop. The cause was not the bar: the job card has a 430 px minimum height, and with the tips, the example-profile notice, the location box and the filters above it the content was taller than the scrolling area, so the buttons sat below its bottom edge (on a 390x844 phone the buttons were at 946 px with the bar at 740 px). One rule keeps the button row stuck to the bottom of the scrolling area, just above the bar. When the content is taller than the screen the buttons cover the lower part of the card until you scroll; scrolled to the end, the card ends above them.
- The location question waits until you have tapped Agree, so there is never more than one question on first open.
- New browser test `tools/ui-buttons-bar.js` (23 checks at each of four sizes, dev and sandbox) measures the boxes instead of trusting a screenshot: 12 of 22 failed before the fix.

### Small things
- The Account screen no longer promises an email receipt on a server where email is not switched on.
- The Filters pay line reads "No minimum set" instead of "You want $0k+".
- The help assistant answers "pricing", "fees", "is it expensive" and "do you charge" with the prices.
- `/favicon.ico` and `/robots.txt` load; an address that does not exist shows UAply's own "Page not found" page with a Back to UAply button; every legal page has a "Back to UAply" link at the top.

### An after-deploy check of the live site
- `python tools/live-check.py --base https://uaply.onrender.com` checks the live site from outside (health, headers, jobs, sign-in lock-out, owner pages closed, legal pages, and whether email, Google and payments are on); `--expect all` fails if something that should be on is off. `node tools/cdp.js tools/ui-live.js --base ...` walks the live site in a real browser at phone and laptop size, and with `--email` signs up one address by email code. `GET /api/status` reports only yes/no facts (never a key, an address or a path).

## 1.0.0-rc.10 (release candidates 9 and 10, October 17)

rc.9: the agreement at first open, learning from swipes, Plan & billing decided by the server, the support page, honest hosted previews. rc.10: everything below.


### Google sign-in and Stripe ready for real accounts and real cards
- **Continue with Google uses Google's full-page sign-in on every device** once the client secret is set (not only iPhone and iPad).
  The app runs inside a srcdoc frame whose `location.origin` is "null", which Google's pop-up button script reads, and the pop-up also
  depends on third-party cookies and Chrome's FedCM prompt; the full-page sign-in depends on none of these. The request to Google now also
  says `access_type=online`. Setup problems (wrong secret, Google error words) are written to the server log with what to change, and the
  start line says `Google sign-in: on`.
- **Google's token checks** forgive a minute of clock difference, refuse tokens claiming to last more than a day, fetch Google's key list
  at most once a minute for unknown key ids, and keep working with known keys during an outage at Google.
- **Stripe: a plan needs a real, successful payment.** Every event is re-read from Stripe (late or out-of-order events cannot switch a plan
  on), only our exact Plus and Pro prices count, a live server ignores test-mode events (test cards cannot unlock a plan on the real site),
  handled event ids are kept in the database (a restart does not forget them), and every call pins the Stripe API version. `invoice.paid`
  and `invoice.payment_failed` are handled: after the third failed renewal the plan pauses and the Plan screen says to update the card; it
  comes back when a payment works. Deleting an account first cancels its subscription at Stripe, immediately (nobody is left to use or manage the rest of the month); if Stripe refuses, the account is kept and the person is told to cancel in Manage billing first, and the delete screen says the plan will be cancelled. The Plan screen no longer shows "Pro is active"
  for a typed `?billing=success&plan=pro` address where real payments are on, and says so if Stripe has not confirmed a payment.
- **Owner's guides:** DEPLOY.md section 3 (Google, with the exact addresses, the JSON to paste and an "if you see X, do Y" table) and new
  section 4 (Stripe go-live: prices, portal, retries, webhook events, keys, Radar rules, test cards); `/setup` matches. `render.yaml` lists the
  four Stripe settings for dev.
- Tests: `test-billing.py` 29 -> 70 (declined, fake and Radar-blocked cards, forged, tampered, old, future and replayed events, live/test
  mode, a foreign price, failed renewals, portal cancel, account deletion with an active plan, a Stripe failure that keeps the account); `test-google.py`, `test-google-token.py`, `test-public-auth.py`,
  `test-setup.py` and `ui-google-ios.js` (a computer now uses the full-page sign-in too) extended.

### Fill Profile setup from your resume (sandbox only)
- **Profile setup, Background and links has a new "Fill from your resume" box.** Choose your resume (PDF, Word .docx or text, up to
  5 MB) and UAply fills every empty field it finds: name, email, phone, LinkedIn, portfolio or GitHub, headline, About you, school,
  major, graduation month, GPA, most recent employer and title, skills, city, state and ZIP. Before this, a resume file was only
  attached to applications and never read.
- **Nothing you typed is changed.** Where your resume says something different, the list offers Replace (or Add them, for skills).
  Each answer shows the line of your resume it came from, unsure ones say "Check this", and the filled fields are outlined until you
  change them. Nothing is saved until you save the step, as with typing.
- **The same file becomes the resume sent with your applications** when you have none yet (through the existing resume file box, so
  there is still one place it is kept, on your device). If you already added a different file, you are asked first. A file over 1 MB
  is read but not kept for applications, as before.
- **The file is read on the server for a moment and not kept**: `POST /api/profile/resume` (no account needed, 12 a minute per
  address) answers with the fields only, never the file or its text, and the log says only "resume read #N". The Privacy Policy and
  the assistant's resume answer say so. PDFs are read by `pypdf` (new in `requirements.txt`, pure Python) in a separate process with a
  15-second and memory limit; Word files are read as plain XML from the zip; nothing in a file is ever run.
- **Plain sentences when a file cannot be read:** over 5 MB, an older .doc, a photo, a scanned PDF (no text in it), a password-protected
  PDF, or a file with no readable text. Without `pypdf` installed, a PDF gets "use a Word or text file for now".
- New `resume_parse.py` handles one- and two-column layouts, headings in any case, letter-spaced or with the list on the same line
  ("Skills: Python, SQL"), and dates such as "Jan 2024 – Present", "01/2024 - 05/2025", "Summer 2024", "2023-2025", dates before or
  after the job. It cannot read scanned resumes (no OCR) or PDFs whose columns were drawn line by line across the page.
- New tests: `tools/test-resume.py` (250 checks: six made-up resumes in `tools/fixtures/resumes/`, all 88 of their fields found; layouts
  and date styles; every refused file; the endpoint on a real server, nothing written to disk, rate limit) and `tools/ui-resume.js`
  (22 checks at iPhone size). Both run in `tools/run-all-tests.sh`; the Python test also runs in GitHub's checks, which now install pypdf.

### Swipe right applies straight into Ashby and SmartRecruiters, for employers who connect
- **Employers on Ashby or SmartRecruiters can now connect** the same way as Greenhouse and Lever: they create a key in their own system (Ashby:
  Admin, Integrations, API Keys, with Candidates write and Jobs read; SmartRecruiters: Settings, Admin, Credential Manager, an Application API
  key) and the owner pastes it into the Connect box on the setup page, or into the host's settings. Their real postings then say **Apply
  instantly**, and a swipe right puts the application into their pipeline with the resume attached.
- **The posting's own questions are answered from the profile**, with the same rules Greenhouse uses (work authorization, sponsorship, LinkedIn,
  how they heard, why this company, and the rest). A required question the profile cannot answer is asked once and remembered; one the app cannot
  ask (a file other than the resume, or a kind of field UAply does not know) means nothing is sent and the person finishes on the employer's page.
  UAply never guesses.
- **Voluntary questions stay unanswered**: SmartRecruiters' diversity questions and any gender, race, veteran or disability question on an Ashby
  form are skipped. A privacy consent the employer requires is given only when the person switched on "Acknowledge employers' notices for me" or
  answered it themselves, and optional consents (talent pool, text messages) are never given.
- **Test mode never uses an employer's key**: their form is read only for a live send.
- The real City of Philadelphia and Ashby feeds already record where each posting lives, so a connected employer's listed jobs work without
  extra setup; SmartRecruiters postings now remember the id its application service needs.
- New tests: `tools/test-ats-ashby.py` (29 checks) and `tools/test-ats-smartrecruiters.py` (29 checks) against a stand-in that checks every request
  against the two systems' published documentation, plus new end-to-end checks in `tools/test-ats-flow.py` and `tools/test-setup.py`. A real key
  has not been tried yet: the first connected employer should start with a test posting.

### Profile setup asks what employers' forms require, so more swipes apply without a question
- **New answers in Profile setup, all optional:** Willing to relocate for the right job (Yes or No; the Willing to relocate box under
  Work style is the same answer, so changing one changes the other), Expected yearly pay in US dollars, Country you live in (United
  States, Canada, United Kingdom or Other, asked right after your ZIP code), and, under your most recent employer, your job title there
  and the months you started and ended (leave the end blank if you still work there; an end before the start is pointed out).
- **Fewer questions after a swipe right:** "Are you willing to relocate?", "What are your salary expectations?", "Which country do you
  live in?", "What is your current job title?", "Dates of employment" and "Are you currently employed?" are now answered from your
  profile on employers' Greenhouse forms. Your title at your most recent employer is used for "current title"; the title you are
  looking for is used only when that is blank.
- **Expected pay goes only where a form requires it.** An optional pay box is left blank, a yes or no question about a pay range is
  never given a number, and anywhere else your expected pay is not sent, not kept in the application record and not listed in your
  receipt. Leave it blank and a form that requires it asks you each time.
- **Greenhouse gets the fields its own careers page fills in without asking:** your country as a two-letter code, your location
  ("Philadelphia, Pennsylvania, United States") with its map position from your ZIP code (all three together or none, since Greenhouse
  ignores a location without the map position), and your most recent job (company, title, start month, and end month or "current").
- **Your receipt, the employer's email and the webhook** now list your country, willingness to relocate, your job title and dates at
  your most recent employer, and expected pay only when that employer's form required it, so the receipt still lists exactly what was
  shared. The Privacy Policy and `EMPLOYERS.md` list the new fields.
- The stand-in Greenhouse (`tools/mock-ats.py`) has a job (1006) with these questions and the location box, and refuses a location
  without its map position or a half-filled job entry. `tools/test-autofill.py` has 31 new checks (67 in all).

### Sign-in ready for the live site (uaply.net), iPhones and Google
- **Continue with Google on iPhone and iPad** now uses Google's full-page sign-in (a white "Continue with Google" button with
  Google's G), because Google says its pop-up button needs that on iPhone (Safari's tracking protection breaks the pop-up).
  Computers and Android phones keep Google's own button. The full-page sign-in needs the client secret on the server.
- **The phone apps hide Google** on Android too, not only iPhone: Google refuses to sign anyone in inside an app's built-in web
  view. Password sign-up works there.
- **Someone can no longer sign up first with another person's Gmail** and keep a way in: when Google proves a Gmail (or Google
  Workspace) address and links it to a password account that never confirmed its email, that password is removed and every other
  session of the account is signed out. The person is told and can add a password with Forgot password. Likewise, using an emailed
  reset link on an account whose email was never confirmed unlinks a Google login Google did not vouch for.
- **Password guessing is stopped even when the attacker fakes a new address for every try**: on top of 5 wrong passwords per
  connection, one account takes at most 20 wrong passwords in 15 minutes from all connections together. Forgot password and Google
  still work during that time. Old rate-limit entries are forgotten after an hour, so the server's memory cannot grow without end.
- **Google returns people to the address they started on** (uaply.net, www.uaply.net or the onrender.com address) instead of always
  the configured public address, where the sign-in cookie did not exist and every full-page Google sign-in failed as "expired".
- After coming back from Google, the "Signed in with Google" message (or the reason it failed) no longer vanishes when the
  page's other start-up answers arrive a moment later.
- New tests: `tools/test-public-auth.py` (71 checks, the server as Render runs it: cookies, the same-site check for every real
  address, good and forged Google tokens, linking, a restart, password rules, lock-out, codes) and `tools/ui-google-ios.js`
  (21 checks in a real browser as an iPhone, through a stand-in Google). The /setup page's Google steps use Google's current
  console pages (Google Auth Platform).

### Ready for Render: proven start, stop and restart
- **Deploys no longer cut a swipe off half-way.** Render stops the server (SIGTERM) at every deploy. The server now stops taking new
  requests, finishes the ones in progress (a sign-up, a swipe sending its email), writes `[uaply] stopped` in the log and exits normally.
  Before, it died at once and the request in progress was lost.
- **One line in Render's log says what the server will do:** public or not, where records are kept and whether that folder is really
  Render's persistent disk, which job feeds, email, owner pages, AI answers and payments are on, and whether `UAPLY_CONFIG_JSON` is valid
  JSON. Never a secret, only on or off. A data folder that is not a disk gets a WARNING line (everything there vanishes at the next deploy).
- **A data folder that cannot be written** (the disk is not attached) stops the server with a plain reason instead of a traceback;
  a blank port number does the same.
- **A record cut short** (a full disk, a forced stop) no longer hides every application after it at the next start, and the next record
  is never glued onto it. The log names any broken line it skipped.
- **The job list is read about 5 times faster** (25.6 to 5.1 CPU seconds for the 24 boards): only the postings that can be shown are
  worked through. The list is identical (checked on the same 5,632 postings). The first start on an empty disk went from 33 to 24 seconds,
  which matters on Render's half-CPU Starter plan.
- `render.yaml`: the start command uses `${PORT:-10000}`, both services run in Virginia (nearest to Philadelphia; cannot change later), the
  sandbox gets the same job feeds as dev, and the comments say what the free plan lacks and that secrets are asked for only once.
- `DEPLOY.md`: the full Render steps checked against the code: the settings line with `public_url`, why `feeds` stays out of it, the log
  line to check after deploying, the Cloudflare records, and what a deploy does.
- New test `tools/test-render.py` (74 checks, about 10 seconds, also in GitHub's checks on Render's Python 3.12): starts the server exactly as
  Render does, stops it with SIGTERM mid-request, restarts it on the same disk and checks everything above.

### Phone apps ready for the stores
- The apps now open **https://uaply.net** (was the Render dev address).
- **Google Play's new rule:** since August 31, 2026 new apps must target Android 16 (API 36). The Android project targeted
  API 35 and would have been refused; it now targets API 36 (Android Gradle Plugin 8.10.1, which API 36 needs).
- **Offline screen really shows now:** the "can't connect" page existed but was never wired up, so a phone without internet
  saw a blank error. It now appears whenever the site does not load, and Try again (or reconnecting) goes back to the site.
- Android 15 and 16 draw apps edge to edge; the app now keeps the page between the status bar and the navigation bar.
- **"Continue with Google" is hidden inside the phone apps** (Android too, not only iPhone): Google refuses its sign-in
  inside an app's built-in web view, so the button could only fail there. The website keeps it.
- iPhone project: iPhone-only (no iPad screenshots or iPad review), and it declares standard encryption only, so App Store
  Connect stops asking the export question on every build.
- New `mobile/build-android.ps1`: one command builds the Android test app or the signed Play bundle on Windows (downloads the
  free tools with checksum checks; you accept Google's SDK license yourself; the upload key and its password never go in git).
- New `codemagic.yaml`: builds, signs and uploads the iPhone app to TestFlight on Codemagic's free cloud Mac (manual start only).

### Swipe right always ends in the right place, and says so (sandbox and dev)
- Every swipe-right path was tested end to end against local servers with a stand-in mail server and a stand-in
  Greenhouse/Lever (`python tools/ui-apply-paths.py` replays them in a browser). Fixes:
- The employer's Reply always goes to the applicant's verified email (a name written like an address could take it over),
  and every UAply email shows the sender as UAply.
- Test mode now says exactly where the live app would send the application (an employer's hiring system, not a made-up
  email address); a job that left the employer's board is a hand-off in test mode too.
- The Applied list shows every outcome: a failed delivery says "Not sent" with Try again; a second swipe on a job already
  applied to shows what happened the first time; an application waiting for a connection is retried every 30 seconds when
  UAply's server, not the device, was the problem. Undo or Withdraw after an application went out says the employer still
  has it, and the Undo button during the live countdown cancels it cleanly.
- Receipts and owner copies say where the resume really went (no receipt carries the file), the test banner follows the real
  channel, the owner copy is labelled [TEST] in test mode, education reads "graduation June 2027", accented resume file
  names are kept, and receipts link back to the site even when `public_url` is not set.

### Post a job from an existing job post (sandbox) — Mohammed
- **Post a job** shows two options on one page. Option 1, at the top: "Start from your existing job post": paste a link, or
  paste the job text, and UAply fills in the form (title, job type, work style, place, pay, years, education, skills, majors,
  GPA, graduation dates, sponsorship, who can apply, benefits, relocation, summary, description). Option 2, right below: the
  form to fill in yourself. Filled fields are marked "From your post", and anything the post did not say is listed as still
  needed. Career pages that show a Greenhouse job (?gh_jid=) are read too, and a slow site gives up after 12 seconds.
- Links are read from the standard job-posting block career sites carry for Google Jobs, and from the public Greenhouse, Lever,
  Ashby and SmartRecruiters feeds. LinkedIn, Indeed, ZipRecruiter, Glassdoor, Handshake, Monster and Hiring Cafe are never
  read (their terms forbid it or they need a login); the screen asks for the pasted text instead.
- The server reads only public web pages (never this computer, private networks or cloud metadata addresses), one page per
  request, at most 3 MB, and a few a minute per account.
- No lookbehind patterns in the scripts any more, so iPhones before iOS 16.4 can run them.

### Paying for Plus and Pro in the sandbox (Stripe, test mode) — Mohammed
- On the hosted sandbox (no server), **Choose Plus** and **Choose Pro** open Stripe's own secure checkout through Stripe Payment
  Links in the "UAply sandbox" Stripe account (test mode: card 4242 4242 4242 4242, no real money). After paying, Stripe sends the
  person back to the sandbox and the plan is switched on, with the payment listed as "Stripe test".
- On a UAply server the existing Stripe Checkout, webhook and billing portal are used instead. The sandbox Render service now
  names the two Stripe prices; the secret key and webhook secret are typed into Render, never stored in GitHub.

### Hiring mode for employers (sandbox only for now) — Mohammed
- A **Switch to hiring** pill in the header (next to the account button) opens the employer hub; **Switch to job search** goes back.
  Same UAply account for both.
- **Company profile** once: name, logo upload (PNG, JPEG or WebP, resized for you), industry and number of employees (both
  dropdowns, required), United States or Canada, state or province, city, website and About the company.
- **Post a job** on one page with a live preview of the swipe card. Each section says which job seeker fields it is matched to:
  title, job type, work style, city, relocation help, yearly pay range, commission only, minimum experience and education,
  skills, preferred majors, minimum GPA, graduation window, who can apply (work authorization), visa sponsorship, start date,
  benefits, a one-line summary and a full description. **Meet the hiring team**: name, title, email and LinkedIn; the name and
  title can show on the card, the email and LinkedIn stay on the server for the Plus/Pro "message the hiring manager" option.
- **Hub**: Overview (open jobs, applicants, new this week, average match), Jobs (edit, pause, close, reopen, delete), Applicants
  (best match first, must-haves checked, "only people who meet every must-have", stage New to Hired, private notes), Company,
  Billing. Prices are **TBD**; posting is free while testing.
- **Job seekers** see employer jobs in the same deck with the logo, "What the company asks for" checked against their own
  answers, "Meet the hiring team", and About the job and company. A new filter hides jobs they are not eligible for. Paused and
  closed jobs leave the deck at once and refuse new applications.
- Applications go to the employer's **verified account email**, never to an address typed into a form; browsers never receive it.
- The consent screen now shows **once, before the first swipe**; after that every swipe is just a swipe (sandbox only).
- Removed coding-tool credits from the app, docs and legal pages; the AI disclosure page now credits the founders, Mohammed and Saif.

### Profile setup, and what really changes your matches
- **Profile setup** is now one guided flow, five short steps (About you, Jobs you want, Where and pay, Background and links,
  Eligibility and extras), saved as you go, the same on phone and desktop. The old Settings, Resume and links, and Preferences
  screens are folded into it, so the Profile menu has five items instead of seven. On desktop (960px and wider) a live "What
  employers see" card sits beside the questions.
- Deleting an account is tucked under "More account options", with a short skippable exit survey (anonymous).
- **Your answers now do more work.** Your headline, About you and major count as skills a job asks for. Work style: tick nothing
  and every style scores full points; the new "Hide work styles I did not pick" filter hides the rest. The opportunity types you
  pick open first in Services. State and ZIP code help find where you live for the distance filter. One completeness score is used
  everywhere. Optional EEO answers, work authorization and GPA are never used to score, rank or hide jobs.
- dev now includes the Application profile (phone, links, school, work authorization, opportunity types) so those details reach
  employers; before, dev sent none of them.
- Fixed: errors on the Account screen were off-screen; a new profile was pre-filled with a stranger's email; restoring a backup
  dropped the Application profile answers; the Account screen showed fake Google/Apple/phone sign-in previews next to the real
  form; the desktop form was capped at half width; password, file and month inputs were unstyled; tap targets under 44px.

### Jobs near you (sandbox only for now)
- On first open the browser's own "share your location?" prompt appears, with a card above the jobs saying why. If location is
  blocked in the browser, the card says so once and how to turn it on. The position is rounded to about a mile, kept only on the
  device and never sent to the server.
- Nearby in-person jobs score higher (full location points within 25 miles, partial to 60), and cards say "In your area" or
  "About N miles from you".
- Filters has a **Commute distance** slider: Remote only, 5 to 100 miles, Any distance. dev keeps the old distance choice.
- Fixed: in the sandbox, Bottom navigation stopped part-way with "Cannot read properties of undefined (reading 'up')" (the
  auto-message check read the sign-in state before it existed), which also left out everything that loads after it.

### Swipe right fills in the real application form, swipes that work on phones, email from uaply.net
Swipe right fills in the employer's real application form, asks only what the person alone can answer (once), and says honestly what happened.

- **Autofill engine** (`autofill.py`). Greenhouse publishes every job's application form (questions, field types, options) through its public Job
  Board API, with no key. UAply reads that form and answers each question from the profile: name, email, phone, resume file, LinkedIn, website,
  location, US state (by full name or two-letter code), ZIP code, the hidden map position behind the location box (from the ZIP code, using the
  Census Bureau's public ZIP data in `autofill_zip3.json`), school, degree, major, graduation date, GPA, current employer, work authorization and
  sponsorship (including forms whose options are whole sentences), OPT, 18 or older, former employee, government official, office work, relocation,
  "how did you hear", and the person's own "why this company" text. Voluntary self-identification (gender, race, veteran, disability) is never
  answered. Privacy and AI-use acknowledgments are ticked only if the person chose that in Profile.
- **Asked once, then remembered.** A required question the profile cannot answer is asked in a short sheet after the swipe ("2 questions from
  Dropbox"); the answer is saved on the device and used for every later form that asks the same thing, at any company. On 59 real forms from
  today's feed: 9 were complete from the profile alone, the typical form left 2 questions, and after answering each new question once, 58 of 59
  were complete.
- **Where it applies by itself.** Employers that connected their Greenhouse: the filled form goes straight in. Every other employer: nothing is
  sent, the job is kept as "Not sent yet" with a Finish on their site button. In the sandbox (test mode), every Greenhouse posting is filled in
  the same way and delivered to the test inbox, which now shows the employer's form exactly as UAply filled it in. Nothing reaches an employer.
- **Profile, Preferences, "Questions employers ask"**: office work, former employee, government official, PhD, pronouns, notices, "why" text.
  Relocation comes from the existing "Willing to relocate".
- **The Applied list tells the truth.** It said "Application sent to the company" for jobs where nothing was sent (the employer's own page
  was needed). Now: sent, sent to the test inbox, not sent yet (finish on their site), or waiting to send.
- **A swipe that sends nothing goes back to the deck** (missing name or email, the weekly limit, unverified email, too fast) instead of sitting
  in Applied. Offline swipes are kept as "waiting to send" and sent when the connection returns. Undo takes back that exact job, never just
  "the last one".
- **Server**: at most 40 applications and 150 swipes per minute per visitor (a script can no longer fill the disk); the weekly plan limit counts
  only real applications, not hand-offs.
- **Fixed earlier in this round**: the first-application agreement reappearing on every swipe; the browser test runner always reporting success
  (now it fails on any failed check, and each check has a 10-minute limit); three stale test expectations that the old runner had hidden.
- **Email from your own domain.** The Connect email box on `/setup` now takes Brevo (sends from an address such as uaplytechnologies@uaply.net with Brevo's
  SMTP login and key) as well as a Gmail App Password, and says what to check in Brevo when it refuses the login (including blocked IP addresses).
- `tools/shot-real-apply.js`: one complete application in the sandbox, signed in as a real address, to an employer that receives applications by email.
- **Swiping on phones** (new "Phone swipe" feature, on in sandbox and dev). On a phone a thumb curves; the card left vertical moves to the
  browser, which then treated curved swipes as scrolls and cancelled them, so swipes "worked here and there". Touch now uses a direction
  lock: the first few pixels decide sideways (a swipe; the browser may no longer scroll) or up and down (scroll the card, never a swipe).
  A swipe counts at 18% of the card's width (at most 80px) or as a quick flick, instead of a fixed 110px. Mouse and pen are unchanged.
- **Nothing covers a button.** The round help button sat on the corner of Profile in the bottom menu on big phones, and the message after a
  swipe covered the menu (or Pass, Undo and Apply on a small phone) for up to 12 seconds. Both now sit just above the menu on every screen
  size, and taps pass through the message except on its own button.
- `tools/ui-phone.js` (in the full run at 440x956 and 375x667): every menu item tapped by a real touch, no control covered at its center or
  corners on 18 screens, and 7 kinds of swipe (straight, a quick flick, curved thumb swipes, a slow drag, plus a scroll, a nudge and a tap
  that must not swipe). Before the fix, 0 of the 6 real swipes worked at phone size.
- **The test run can no longer use the owner's real settings.** It set its own settings on top of uaply-config.json instead of replacing it,
  so once real email was connected, two runs sent a few real emails (two test emails to the owner and some codes to made-up example.com
  addresses, which bounced). `UAPLY_CONFIG_FILE=none` now makes every server skip the owner's file; the full run sets it.
- New tests: `test-autofill.py` (34, real forms saved in `tools/fixtures/`), more in `test-ats-flow.py` (20); `tools/shot-autofill.js` shows the
  whole flow in the sandbox at phone size.
- **Squarespace and Block jobs are back (28 more jobs).** Both list their job links as http:// instead of https://, and UAply dropped every
  such job. Those links now open securely (https://, which both sites serve); a link that is not a web address is still dropped. The
  feed-health bot found both boards "empty"; all 30 boards now answer with jobs.
- **Webflow's jobs are back.** Webflow moved its job board from Greenhouse (404 since October 2026) to Ashby; UAply now reads it there
  (9 US jobs on October 16).
- **A refused request always gets its answer.** When the server refuses a request without reading what was sent (a garbled length, too
  large, cross-site, unknown address), it now says "Connection: close" and reads away the rest before hanging up. Before, Windows could
  reset the connection first, so about 1 in 200 such requests lost the "bad request" answer (found by the hostile-input test).
- `tools/feed-health.py` and `tools/daily-checks.py`: the read-only reports behind the scheduled "feed health" and "code checks" bots.

### Combining Mohammed's and Saif's sandbox work
- Both fixed swiping on iPhones. **Phone swipe** (touch direction lock) decides every swipe in sandbox and dev; Easy swipe and Axis lock,
  with Mohammed's iPhone fixes, stay on in the sandbox as the fallback when Phone swipe is switched off. dev uses Phone swipe instead of
  Axis lock, and now also includes Profile setup.
- The consent screen keeps both fixes: shown once before the first swipe (sandbox), and never shown again because of a problem while applying.
- A swipe made while that first consent screen is open (the keyboard can still reach the cards) now waits for the answer and then goes
  on, or back to the deck, instead of being lost. Only one waits, so a double tap still applies once.
- Messages and the privacy policy pointed to screens that no longer exist ("Profile, Settings", "Profile, Resume and links"). They now
  name the Profile setup step: About you, Jobs you want, Where and pay, Background and links, or Eligibility and extras.
- Five browser tests still opened the old Settings, Resume and Preferences screens; they now fill in Profile setup step by step.
- **A removed employer connection is really removed.** The server remembered employer connections until the file's time changed; two
  quick writes on a busy computer could share a time, so a removed connection kept being used. It now also compares the size and a finer time.

## 1.0.0-rc.8 (release candidate)

Swipe right can now apply by itself: straight into the employer's own hiring system, for employers who connect.

- **Researched first.** Greenhouse and Lever each document a call that submits an application, but both need a key created by the employer's own
  administrator (Lever's API also cannot carry a posting's custom questions). None of Greenhouse, Lever or Ashby documents opening an application page
  pre-filled from a link. So no site can apply for a person on an employer that never agreed; Indeed and LinkedIn work the same way, through employers'
  connected systems. See EMPLOYERS.md.
- **Greenhouse and Lever delivery** (`ats_api.py`): name, email, phone, links, the resume file, and answers to the posting's own questions where the
  profile has them (LinkedIn, website, current employer, work authorization, sponsorship, how they heard). A required question the profile cannot
  answer means nothing is sent and the person finishes on the employer's page; it never guesses. Keys are never shown, logged or put in a message.
- **Apply instantly badge.** Cards for connected employers say "Apply instantly"; every other real job says "Opens employer site", so people know
  before they swipe. Instant jobs get the same 5-second Undo window.
- **Connecting an employer**: the new box on `/setup` (this computer), `UAPLY_ATS_JSON` (a host), or `ats` and `ats_job_id` in the employer list.
- Ashby is not built: its request format could not be verified from public documentation.
- New tests: `test-ats.py` (24, against `tools/mock-ats.py`), `test-ats-flow.py` (19, end to end), more in setup (34) and the public server.

## 1.0.0-rc.7 (release candidate)

Sign-in and email that behave like the real thing, and a help chat whose requests go somewhere. Found by using the app the way a new user does.

- **No more accidental test accounts.** On the sandbox Account screen, below the real sign-up form, a "Preview of other ways to sign in" block had a
  simulated "Continue with Google" button that signed the browser into a fake account. It is gone whenever a real server is running; the simulated
  sign-ins remain only on the hosted preview, which has no server.
- **"Continue with Google" is always visible on your own computer.** When no Google client ID is set yet, the button opens the setup page instead of
  vanishing (visitors of a live site never see it). The setup page is now a guide: clickable steps to Google's own pages, the exact addresses to give
  Google with Copy buttons (Google needs both `http://localhost:8767` and `http://localhost`), and an explanation of why a test inbox is still showing.
- **Google sign-in follows Google's own guidance on email trust.** Google is the authority on an address only for Gmail and Workspace accounts. Any
  other "verified" address can still sign in by its Google account number, but it can no longer be merged into an existing UAply account with that
  address (that was a takeover risk) and a new account made with it must pass the emailed code check.
- **The verification code email is now a proper email** (a big readable code, how long it works, "ignore this if it was not you"), and the screen says
  what really happened: emailed to the address, could not be sent, or (this computer, no Gmail connected) in the test inbox. The Connect Gmail link
  sits right there.
- **Your swipe now produces a confirmation even for an unverified account when no real email is connected** (it is saved in the test inbox).
  Before, an unverified account got nothing at all, and nothing said why. With a real mail login the verified-only rule still applies.
- **Help requests are emailed to the team.** "Talk to a person" and problem reports from the assistant are emailed to `support_email` (or the owner
  address) with the person's own address as the Reply-To, so answering is pressing Reply. A short acknowledgement goes to the person only if that
  address is a verified account address (nobody can make UAply email a stranger). The chat now says what happened: "Sent to the UAply team",
  "saved, but the email did not go through", or on your own computer "saved, not emailed" with buttons for the Feedback inbox and Connect Gmail. The
  Feedback page marks each request emailed or not. At most 60 help emails an hour reach the inbox; the rest are still saved.
- **Visitors never see raw error text on a hosted server.** Server errors, job-feed network errors and mail-server errors now show a plain sentence;
  the real reason goes to the server log. Your own computer still shows details where useful.
- **Crashes fixed** found by a new fuzz test (4,525 odd requests): an application whose `skills`, or feedback whose `articles`, arrived as a number,
  a boolean or a dictionary caused a server error.
- **`start-uaply.bat`**: double-click to start prod, sandbox and dev after the computer restarts (a restart stops them, and the app then says
  "Could not reach the server").
- **Privacy Policy** now covers help requests being emailed to the support inbox.
- New tests: `test-support.py` (31), `fuzz-api.py`, `ui-errors.js` (the app when the server fails), `ui-inject.js` (hostile text in every form,
  and the owner's inbox), `ui-effects.js`, `ui-checklist.js`; setup 27, Google 26 and 33, verification 36, delivery 43, jobs 48.

## 1.0.0-rc.6 (release candidate)

A sweep of the whole site and app (every file, every screen at iPhone size, the server with bad input), and what it found.

- **Privacy fix: the emailed verification code is no longer kept.** The saved copy of the email (subject and body) held the 6-digit code even after
  the email was really sent, which contradicted "only a hash of the code is stored". Now, once a real email was attempted, the saved copy says only
  that a code was emailed. The test inbox on the owner's own computer still shows it (that is its purpose). Covered by new tests, including a failed send.
- **Privacy Policy updated to match the product:** Google sign-in (what Google tells us and what we keep), the emailed code, Google's button loading from
  Google when the sign-in screen opens (and its own cookie), and that deleting an account also removes the linked Google number and any pending code.
  Still a draft for an attorney to review. Tests now prove that deleting an account removes its code, sessions, saved email and Google link.
- **A new profile no longer starts with a made-up email.** The Settings form was pre-filled with a sample person's address while the name and skills
  were blank; a person who typed only a name would have kept it as their reply address.
- **Job cards:** "Hiring" is listed as a skill only on recruiting and people roles (company boilerplate about "recruiting" put it on a firmware co-op).
  A remote job's place no longer repeats the word ("Remote - USA  Remote" is now "USA  Remote"). A "100%" score now fits inside its ring.
- **Server:** an address with a null byte (`%00`) now gets a clean 400 instead of a dropped connection, and an empty POST gets 400 instead of "too large".
  A burst of visitors no longer gets connections refused: Python's default waiting line of 5 overflowed when 300 requests arrived at once, so it is now 128.
  A new test (`tools/stress.py`, part of the full run) fires 300 simultaneous reads three times, 24 simultaneous sign-ups and a 24-guess password attack: no
  server errors, no locked database, and the lock-out holds.
- **Repository hygiene:** a local-only copy of the partner list (`uaply-partners.json.bak`) had been committed; it is untracked and `.gitignore` now covers
  backups. The file audit now fails on any tracked backup, temporary or log file and on stray control characters (the sign of a mangled backslash).
  The pull-request check now also runs the five behavior tests that need no browser (jobs, codes, delivery, setup form, emails). The test runner prints
  each test's real count. The README clone address is the real repository. Help wording says "Coop" like the menu.
- New tools: `tools/ui-effects.js` (skill chips, empty Add, the three file downloads), `tools/ui-checklist.js` (every profile checklist item lands on
  its field), `tools/ui-polish.js` (measures the ring, place line, blank email, assistant answer), `tools/shot-all.js` (a screenshot of every screen).
  More tests: jobs 46, verification 34, public server 46.
- **Not code, but needed before launch:** the phone app is set to load `https://uaply-dev.onrender.com`, which does not exist yet (deploy with
  `render.yaml`, see DEPLOY.md); the legal pages are drafts that say a lawyer has not reviewed them.

## 1.0.0-rc.5 (release candidate)

Sign-in the way the big job sites do it: Google's own button, and an email code that proves an email is real.

- **Continue with Google** now uses Google's own button (Google Identity Services, as on LinkedIn and Indeed). It shows the Google accounts already
  signed in on the person's browser; one tap signs them in. UAply never sees their Google password. It needs only the **public client ID**, no secret.
  The server checks Google's signed token itself (`jwt_rs256.py`, standard library only): the signature against Google's published keys, that it was
  issued for UAply's own client ID, the issuer, the expiry, that Google says the email is verified, and it only accepts the RS256 algorithm (forged,
  expired, wrong-app, tampered, "none" and shared-secret tokens are all refused). People are identified by Google's permanent id, not their email.
  The older redirect sign-in is kept as a fallback.
- **Email verification code for password accounts:** sign-up emails a 6-digit code (10 minutes, 5 tries, one use, stored only as a hash, at most 3
  new codes an hour). Until verified, a person can still swipe but gets no confirmation emails and cannot apply directly to an employer. Accounts made
  with Google, or confirmed through an emailed reset link, are verified automatically.
- **Direct applications to employers need a verified account** whose email is the one on the application, so replies go to an address proven theirs.
- **Bug fixed:** Google's button sets its own cookie (`g_state`), and the server's cookie parser threw away the whole header, signing people out. The
  server now reads cookies tolerantly. Found by running the real browser flow; covered by a test.
- **Setup page:** a "Connect Google sign-in" box (paste the public client ID) next to Connect Gmail. Both only work on the owner's own computer.
- **iPhone note:** Google blocks its sign-in inside an app's built-in browser, so the iPhone app keeps the Google button hidden until a native Google
  sign-in plugin (and Sign in with Apple) is added. Email and password sign-up works there.
- New tests: `tools/test-google-token.py` (27), `tools/test-verify.py` (24), `tools/ui-verify.js`, more in the delivery, setup and public suites.

## 1.0.0-rc.4 (release candidate)

- **The swipe message now says where the test confirmation is.** With no real email connected, a signed-in swipe saves the confirmation in the test
  inbox page of the owner's own server, and the message gives its address (for example `http://localhost:8767/outbox`). Before, it only said
  "in the test inbox". A hosted server has no such page, so real users are told nothing about it. `tools/ui-swipes.js` checks both.

## 1.0.0-rc.3 (release candidate)

Applications now reach employers who connect, with the person's resume, and swiping is covered by tests of every gesture.

- **Employers can connect two ways** (`EMPLOYERS.md`): an email address, and/or a signed webhook (the model Indeed Apply uses: an HTTPS
  address per employer that receives each application as JSON, retried up to three times, never followed through a redirect).
  Employers who did not connect are never sent anything, so those jobs stay a hand-off to the employer's own page.
- **The resume file is sent.** The file uploaded under Preferences travels with the application: attached to the employer's email and
  inside the webhook. It is checked by content (a real PDF, Word or text file under 1 MB) and never stored on the server.
- **LinkedIn, phone, portfolio and the short summary now reach the employer in the release build.** They were saved under Resume and links
  but never sent, because only the optional profile form's fields were. The LinkedIn box says it is sent, and only real linkedin.com
  links are accepted.
- **Swipe-right messages are short:** "Applied to X." or "Saved. Finish applying at X.", plus one short line about the confirmation email.
  No more "A copy was emailed to you" or sign-in instructions beyond one sentence.
- **One swipe, one email** when the signed-in account is the owner address (the owner copy is skipped).
- **Job descriptions in emails start at the role** ("What you'll do"), not the company's introduction, and end on a whole sentence.
- **Connect Gmail form on the setup page:** paste the Gmail address and App Password into a local page (never into chat); it saves them in the
  git-ignored config and sends a test email. Hosted servers refuse it (their secrets live in the host's dashboard).
- **Menu wording:** Services now says "Coop" (was "Co-ops").
- New tests: `tools/test-delivery.py` (32), `tools/test-setup.py` (17), `tools/ui-swipes.js` (every gesture: buttons, keyboard, finger drags in
  both directions, undo, double tap, reload), and more in the email and job suites.

## 1.0.0-rc.2 (release candidate)

Found by running dev the way a real host runs it (public, behind HTTPS, cold start, no test data), and fixed.

- **Cold start:** for ~20-40 seconds after a restart a visitor saw a made-up example job. The release build now shows
  "Finding jobs for you…", and "Could not load jobs" if the feed fails; it never shows example jobs.
- **Restarts are instant:** the last good postings are saved on disk (`jobs-cache.json` in the data folder), so a restart or a new
  deploy shows jobs at once and refreshes in the background. Feed fetches now run 16 at a time.
- **Honest scores:** a new visitor now sees "Matches below use an example profile. Enter your details" (it was hidden in dev, so
  the card claimed a 100% match for a person with no profile). The "N jobs left" counters stay off.
- **Forgot password on a server without email** now says reset by email is not available and points to Help, instead of
  promising a link that goes to a private test inbox.
- **Right swipe emails rewritten** (`emails.py`): every swipe right now sends the applicant a clear receipt and the owner a copy. Each
  one says what happened in a plain headline, shows the job (company, title, place, type, work style, pay, match, date and time),
  the job description, what was shared, what a swipe right means, what happens next and where to track it. A swipe that sends nothing
  (the employer takes applications on its own site) says so and gives a "Finish your application" button. In test mode the subject
  starts with [TEST] and a banner explains that nothing went to the employer. Plain text plus HTML; all text from people and job feeds
  is escaped. The design follows what Handshake and Indeed document about their confirmations; LinkedIn and ZipRecruiter do not
  publish theirs. With an email login set up, receipts are really sent in test mode too (to the applicant's own address only).
- **Foreign jobs removed from the US feed:** "Toronto, ON, CA" was read as California, and roles titled ANZ or LATAM passed because
  their location said "Remote". Locations are now checked part by part; the saved job cache is versioned so old results are dropped.
- **Test emails to the owner:** the owner copy address and the setup page's test email can be pointed at any address. The setup page
  now says "no App Password yet" instead of a mail-server error.
- **Old name leftovers fixed:** the backup file, the applications CSV and calendar reminders still used "aply"; old backups still import.
- **Deep file audit** (`tools/audit-files.py`, also run in CI): every file by type, links, secrets, line endings, git hygiene.
- **The test suite no longer touches your servers:** `tools/run-all-tests.sh` uses its own ports (18766 and up).
- A pull request template and `CONTRIBUTING.md` set the standard: every PR gets a plain-words title and a full description.
- New tests: `tools/test-emails.py` (41), `tools/test-jobs.py` (23), `tools/test-public.py` (cookies, headers, owner pages, path traversal, limits: 33), `tools/test-smtp.py` with
  `tools/fake-smtp.py` (real SMTP end to end: 12), `tools/ui-widths.js` (nothing cut off from 320 to 430 px) and
  `tools/run-all-tests.sh`, which runs everything with one command on throwaway data.

## 1.0.0-rc.1 (release candidate)

The first release build. Everything below is in `dev`.

### What a user gets
- Swipe through **real postings** from employers' own public career pages (Greenhouse, Lever, Ashby), with internships,
  part-time roles and co-ops under Services. Swiping right on a real job opens the employer's own application page; UAply never
  emails an employer that has not agreed to receive applications.
- **Accounts** with email and password: sign up (18+ and Terms), log in, **forgot password** by emailed one-hour link, change
  password, delete account. **Sign in with Google** is built and switches on when Google keys are added.
- Dashboard (Applied, Accepted, Rejected, Interviews), Profile (Settings, Resume and links, Preferences, Filters), Data and
  privacy (backup, restore, delete, and the legal pages).
- UAply Assistant: help answers from written articles (AI answers when an AI provider key is set), plus feedback.

### What is different from sandbox (the release build)
- No developer bar, no "SANDBOX / TEST MODE" labels, no simulated Google/Apple/email-link/phone sign-in.
- No made-up example companies; only real postings.
- No paid plans or test payments (Apple requires its own in-app purchase for those; left out of version 1).
- A new profile starts **blank** (it used to be pre-filled with a sample person, which hid every real job).
- The assistant's answers use the release wording and do not mention plans.
- Inside the iPhone app, the Google button stays hidden until Sign in with Apple exists (App Store guideline 4.8).

### Fixed on the way
- Hosted pages broke on phones when `$` sequences in the navigation script were mangled by the page builder.
- A board with hundreds of senior roles used to push its internships out of the feed.
- The documentation example employer ("Example Partner Co") was served as a real job when no partner file existed.
- An email login with no password used to count as "email is set up".

### Checks that guard this release
`node check.js` (syntax of every script, Python lint, JSON, legal pages, release flags, hosted builds) runs on every push and pull
request. Browser tests in `tools/`: `ui-release.js` (no test or developer content on any screen), `ui-sweep.js`, `ui-audit.js`
(every button at iPhone size), `ui-reset.js`; Python tests `test-reset.py` and `test-google.py`.

### Not done yet (the owner's steps)
See `DEPLOY.md`: host the server, add the Google and Gmail keys, fill the blanks in the legal pages and have an attorney review
them, enroll in the Apple Developer Program, and build the iPhone app. Not built: email verification at sign-up, Sign in with Apple.
