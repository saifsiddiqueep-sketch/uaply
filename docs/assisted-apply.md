# Assisted apply in the phone app

October 21, 2026. Branch `bot2-assisted-apply`. Owner's rules for this feature: UAply fills the employer's own form from the
person's profile and attaches their resume; the person reviews it and taps Submit; UAply never fills a voluntary
self-identification question, never touches a human check, and never says Sent until the employer's confirmation page appears.
A per-system switch can allow automatic submit only where both the form has no human check and the system's terms do not forbid
agent submission; the owner's lawyer flips that switch, not the code.

**What this is, in plain words:** the person's own autofill, run in the person's own session on their own phone, on the
employer's own page, with the person pressing Submit. It is not a bot submission and it does not get past anything an employer
or its hiring system put in the way.

## 1. How it works

1. Job Tracker, a hand-off row: **Finish applying on their site** (unchanged on the website).
2. In the UAply phone app (Capacitor), that button calls the native plugin `UAplyAssist.open` (`shared/uaply-nav.js`, `assistedApply`)
   with: the employer's page (with UAply's source tag), the assist script `shared/uaply-assist.js` as text (served at
   `/uaply-assist.js`, so the app always runs what the site serves), the profile from `__uaplyAssistProfile()`, the job's company and
   role, the hiring system, and the mode from `shared/assist-systems.json` (served at `/assist-systems.json`).
3. **The bridge (October 22): questions first, form second.** The app first opens the form behind a cover ("Reading the application
   form...") and runs `UAplyAssist.scan`, which changes nothing (lists are opened to read their choices and closed again) and returns
   every question the profile cannot answer, with its kind (text, long text, number, date, month, list, tick-all) and its choices.
   UAply asks them in its own question box, "N questions from {company}": the required ones must be answered, the optional ones
   (marked "(optional)") may be left blank; "Continue to {company}'s form" goes on, "Not now" stops there. The answers are kept like
   every question-box answer (Profile setup, "Answers you gave employers"), so the next employer asking the same words gets them. An answer written for one employer (a cover letter, "why us", anything naming that company) is not reused for another:
   the bridge asks it again there.
   Voluntary self-identification, age, consent and certification questions and file uploads are never asked there.
4. `mobile/android/.../AssistActivity.java` then opens the form in a WebView under a bar "Applying at {company}" with **Close**.
   Every 1.5 s it asks the page: is this the confirmation page? is there a form not yet filled at this address? It fills each form once,
   from the profile and the answers just given.
5. The script fills what the profile answers, attaches the resume file, skips voluntary questions, leaves consent boxes and
   follow-ups ("If yes, ...") for the person, scrolls to Submit, outlines it, and shows **"Filled from your UAply profile. Answer
   the N questions left, review it, then tap Submit."**
6. If the person taps the page's own resume box, Android's file chooser is replaced by a choice: **Use my UAply resume** (a copy
   written to the app's cache, handed over through the app's FileProvider and deleted when the page closes) or **Choose another
   file**.
7. The person taps Submit on the employer's page. If a human check appears (reCAPTCHA, hCaptcha, Turnstile), the person answers
   it; UAply never touches it.
8. When the employer's confirmation page appears (`UAplyAssist.confirmed()`: thank-you wording or a /confirmation-style address,
   and the form gone), the page stays on screen 2.5 s, the app closes it and the Job Tracker row becomes **Sent**, with "Sent on
   {company}'s own page: their confirmation page appeared". Closed without that page: the row stays **Finish on their site** and
   the person sees "Not sent yet".

iOS: the same JavaScript and the same plugin interface; the native half (a WKWebView screen, `evaluateJavaScript`, a
`WKUIDelegate` file panel) is not written yet.

What the profile carries (`__uaplyAssistProfile`): name, email, phone, LinkedIn, portfolio, street, city, state, ZIP, country,
current employer and title (only while the job has no end date), its start and end month, school, degree, major, graduation,
GPA, work authorization and sponsorship (yes or no), earliest start, relocation, on-site, "have you worked here before",
government official, PhD, salary (used only where a form requires it), About you, headline, "why us" (the person's own words,
with {company} and {role} filled in), 18 or older (yes: the person confirmed it in the first-swipe agreement), how they heard
("UAply"), the answers saved in UAply's question box, and the resume file.

**How a field is matched (the synonym map in `shared/uaply-assist.js`, October 22).** Each field's words (label, aria, question
block, placeholder, name) go through one ordered list of rules, with guards for questions that only share a word ("Why do you want
to work at X" is not "have you worked at X"; "Name pronunciation", "Portfolio password", "When did you graduate from high school",
"relatives employed by X", "without sponsorship" read the other way round). Name: whole, first, last, preferred, "first and last".
Phone: as written, digits only for a 10-digit box, and a phone country-code list (+1 United States). Address: street, whole home
address, city alone, "City, State and ZIP", state, ZIP, country. Links: LinkedIn, GitHub (only a github.com address), website and
portfolio. Education: school, degree (Bachelor matches "Bachelor's Degree", "BA", "BS"...), major, GPA, graduation as a date
picker (2026-05-01), a typed date in the field's own pattern (05/2026, 05/01/2026) or month and year apart. Work: current employer,
title and their start and end month and year. Yes/no pairs: authorization, sponsorship (also "I will not require sponsorship", read as
a no), "without sponsorship", 18 or older (never 21), relocation, on-site, worked here before, government official, PhD. Earliest
start into a notice-period list (Immediately, 2 weeks, 1 month). How did you hear: "UAply" if offered, else "Other" and "UAply" in
its "please specify" box, else a job-board choice. Lists, radios and Yes/No buttons are matched by their option's normalized words.
Pronouns and voluntary fields (and an "age range") are always skipped. Never the voluntary
answers (gender, race, ethnicity, veteran, disability) and never pronouns. The example profile is never used.

## 2. Per-system table

### Before and after the bridge (October 22, the same 80 postings, the Galaxy, nothing submitted)

| System | Fill, before (Oct 21, profile only) | Fill, after: profile + the person's bridge answers | after, if the person answers only the required ones | after, profile alone | Asked in the bridge (median, required / optional) | Required left at the form, median before → after | Required left after, all of it |
|---|---|---|---|---|---|---|---|
| Greenhouse | 65% | **96%** | 89% | 66% | 2.5 / 0.5 | 4 → **0** | at most 2 per form, all agreements (privacy statement, consent, code of conduct) |
| Lever | 64% | **98%** | 92% | 69% | 1.5 / 1 | 1.5 → **0** | at most 1, a consent-to-texts question |
| Ashby | 60% | **95%** | 72% | 61% | 0 / 3 | 0.5 → **0** | none (19 forms; one posting had closed) |
| Workable | 50% | **96%** | 85% | 57% | 4 / 2 | 5 → **0** | at most 1, "confirm everything is true" |
| SmartRecruiters | not measurable (bot page) | | | | | | |

How to read it: "after" is what the person finds when the form opens, once they answered what UAply's question box asked (the test
person answers every question, required and optional; the bridge marks the optional ones and lets them be skipped). Most of the gain
is the bridge: the profile alone fills about the same share as before (the new mappings add 1 to 7 points), because what was left
was the employer's own questions (essays, "how many years", referrals, cover letters, follow-ups), which no profile holds. Ashby's
optional questions (cover letter, X, GitHub, referral) are why its required-only figure is lower. What is still required at the form
is only what UAply must never answer: privacy, consent and certification questions. Command: `python tools/assist-measure.py --phone
<serial> --urls <saved list> --bridge all`; 296 requests that could have carried an application or a file were refused.

### Before (October 21, the profile alone)

Measured on the owner's Galaxy (SM-S176V, Chrome 138, its own tab through `adb forward tcp:20571`), 20 real postings per system,
same test person (Sam Rivera, a made-up profile and a test resume), **nothing submitted** (section 4). "Fill rate" = fields the
script filled / fields it saw that are not voluntary self-identification (consent boxes, essays, follow-ups and questions the
profile has no answer for count as seen and not filled). Human-check share = forms out of 20 that loaded a check, found on the
page (its element or script) and, on 76 of the 80 forms that had one, also in the page's network requests.

| System | Postings (form reached) | Fields seen | Filled | Fill rate (median per form) | Required left for the person (median per form) | Resume attached | Human check | Voluntary questions skipped | Submit found | Time to ready (median) |
|---|---|---|---|---|---|---|---|---|---|---|
| **Greenhouse** | 20 (20) | 381 | 247 | **65%** (74%) | 4 | 20/20 | 20/20, reCAPTCHA, invisible | 68 | 20/20 | 6.4 s |
| **Lever** | 20 (20) | 360 | 230 | **64%** (74%) | 1.5 | 20/20 | 20/20, hCaptcha, invisible | 104 | 20/20 | 2.5 s |
| Ashby | 20 (20) | 184 | 110 | 60% (54%) | 0.5 | 20/20 | 0/20 | 36 | 20/20 | 2.3 s |
| Workable | 20 (20) | 312 | 156 | 50% (50%) | 5 | 20/20 | 20/20, Turnstile, invisible | 0 (no EEO section on these) | 20/20 | 5.0 s |
| SmartRecruiters | 20 (0) | - | - | not measurable | - | - | bot wall on 20/20 | - | - | - |

What is left for the person is mostly the employer's own questions the profile has no answer for (essays, "how many years of P&L",
"are you 18 or older", relatives at the company), consent and certification boxes, and follow-ups ("If yes, ..."). Filled answers
were checked by hand against each question's words (run with `DEBUG=1`, which lists every field as read); labels that share a word
with a profile answer but ask something else ("Why do you want to work at ...", "Name pronunciation", "without sponsorship") are
handled and covered in `tools/test-assist.js`. The raw report and phone screenshots: `report-phone-final2.json`, `phone-shots-final/`
in the bot's scratch space (not in git).

Phone screenshots (Galaxy, after the fill, nothing submitted), in `docs/assisted-apply-shots/`: Greenhouse
([questions](assisted-apply-shots/greenhouse-questions.png), [Submit](assisted-apply-shots/greenhouse-submit.png)), Lever
([top: resume attached, name filled, pronouns untouched](assisted-apply-shots/lever-top.png), [Submit](assisted-apply-shots/lever-submit.png)),
[Ashby](assisted-apply-shots/ashby-submit.png), [Workable](assisted-apply-shots/workable-submit.png),
[SmartRecruiters' bot page](assisted-apply-shots/smartrecruiters-blocked.png).

Two things the measurement itself causes, because it refuses uploads: Lever says it "couldn't autofill" from the resume (its
`parseResume` call was refused), and Workable's page turns into its error page a moment after the resume is attached (its upload to
Workable's storage was refused; [screenshot](assisted-apply-shots/workable-after-refused-upload.png)). Fields were counted before
that. In real use the upload goes through exactly as when the person picks the file themselves; that was not tried, since it would
send the test resume to the employer's storage.

| System | Form structure (stable names and labels) | Human check | Terms on agent or automated submission | Default mode |
|---|---|---|---|---|
| Greenhouse | job-boards.greenhouse.io Remix/React form; `label[for]` on every field; ids `first_name`, `last_name`, `email`, `phone`, `country`, `candidate-location`, `resume`, `question_<id>`; yes/no and lists are React Select (open on touchend on a phone); EEO block `gender`, `hispanic_ethnicity`, `veteran_status`, `disability_status`; employment and education blocks on some boards | reCAPTCHA (invisible, score based) on 20/20; Greenhouse documents it for job boards ([support article](https://support.greenhouse.io/hc/en-us/articles/11402458580379)) | No candidate or website terms of use ([greenhouse.com/legal](https://www.greenhouse.com/legal)). The [Master Subscription Agreement](https://www.greenhouse.com/master-subscription-agreement) binds employers; 4(c)(ix) bars the customer from circumventing technological protective measures. Nothing on candidates using agents. | assisted |
| Lever | jobs.lever.co/<co>/<id>/apply, server-rendered with jQuery; `li.application-question > label > .application-label + .application-field`; names `name`, `email`, `phone`, `location` (+ hidden `selectedLocation`), `org`, `urls[LinkedIn]`, `urls[GitHub]`, `urls[Portfolio]`, `urls[Other]`, `cards[<id>][field<n>]`, `eeo[gender]`, `eeo[race]`, `eeo[veteran]`, `consent[...]`, `resume`; the location box searches on keydown and empties itself on blur unless a suggestion is chosen | hCaptcha (invisible until Lever asks for it) on 20/20 | [Terms of Service](https://www.lever.co/legal/terms-of-service) (August 25, 2023) bind customers only; no candidate terms, no clause on automated means. | assisted |
| Ashby | jobs.ashbyhq.com/<org>/<id>/application, React; `label[for]`; `_systemfield_name`, `_systemfield_email`, `_systemfield_phone`, `_systemfield_resume`, custom field ids; location is a searching combobox; yes/no are two buttons in the question block; EEO as checkboxes named by the answer; privacy acknowledgement box | none on 20/20: no reCAPTCHA, hCaptcha or Turnstile on the page or in its requests | [Customer Terms of Service](https://www.ashbyhq.com/terms) (September 29, 2025) bind customers; 5.1(f) bars circumventing security features. No candidate terms on [Terms and Policies](https://www.ashbyhq.com/resources/terms-and-policies). | assisted (the only system where the "no human check" half holds) |
| Workable | apply.workable.com/<acct>/j/<code>/apply/, React; fields named by `aria-labelledby` (`firstname`, `lastname`, `email`, `phone`, `address`, `CA_<id>`, `QA_<id>`); yes/no is `fieldset[role=radiogroup]` with hidden radios inside `[role=radio]` wrappers; lists are readonly comboboxes with a hidden `aria-hidden` copy; the address is pre-filled from the visitor's network location | Cloudflare Turnstile (invisible) on 20/20 | [Terms of Use](https://www.workable.com/terms) (March 2, 2026) bind customers and their users (4.5.3 no harming the service, 4.5.4 no circumventing limits). The [candidate terms page](https://www.workable.com/candidate-terms) is a privacy-notice template for employers, not terms for candidates. | assisted |
| SmartRecruiters | not reachable by automation: jobs.smartrecruiters.com answered all 20 postings with its "Access is temporarily restricted" page, which lists automated activity and inspection tools among the reasons, in headless Chrome and in the real phone's Chrome while inspected. Structure from its published Application API configuration (questions of RADIO, SINGLE_SELECT, TEXT fields, compliance questions, consent scopes) | a bot wall in front of the form (not a form check); unknown inside | [Candidate Terms of Use](https://www.smartrecruiters.com/legal/terms-of-use/) (May 14, 2019) **bind candidates**; prohibited conduct includes "Use automatic means to access content or data from other users". That is about other users' data, but it is the only candidate-side clause found in any of the five, and SmartRecruiters plainly blocks automated sessions. | assisted |

**Automatic submit is not allowed for any system today.** Greenhouse, Lever and Workable fail the "no human check" half on every
measured form. Ashby passes it on 20 of 20, but no lawyer has read its terms for agent submission (`counsel_approved: false`).
SmartRecruiters blocks automated sessions outright.

## 3. The switch (`shared/assist-systems.json`)

One entry per system: `mode` ("assisted" or "automatic"), `counsel_approved` (the lawyer's yes), `human_check_share` (measured),
and the findings. The app (`assistMode` in `shared/uaply-nav.js`) passes "automatic" to the native screen only when all three
hold: `mode` is "automatic", `counsel_approved` is true, `human_check_share` is 0. The page then checks again at that moment
(`UAplyAssist.submitIfAllowed`): no human check of any kind on the page, no required question left, the resume attached. Any
"no" means the person taps Submit. Every system ships "assisted" with `counsel_approved: false`; `tools/test-assist.js` fails
if that changes without the test changing too. Unknown systems (Workday, iCIMS, a company's own site) are always "assisted".

## 4. How it was measured (and why nothing was sent)

- One command reruns it: `python tools/assist-measure.py --phone <adb serial>` (or without `--phone`, headless Chrome here, which
  Greenhouse refuses). It takes 20 postings per system from the systems' own public job lists (the same employers each time; `--urls`
  reuses a saved list), opens this run's own Chrome tab on the phone through its own `adb forward` port, runs
  `tools/assist-measure.js`, closes that tab, removes that forward, and prints the table below (`--bridge required|all|off`).
- `tools/assist-measure.js` drives that one tab, opens each posting's form, injects the script, runs the bridge (scan, then a test
  person's plain answers: "N/A", "3", "60000", a short sentence, the first sensible choice, "No" to relatives and referrals) and fills
  it.
- Every request that could carry an application is refused by the browser before it leaves: any POST/PUT/PATCH whose address or
  body mentions submit, upload, draft, attachment or apply, any multipart upload, and any body holding the test person's details.
  The final phone run refused 301 such requests (Greenhouse's resume uploads to its storage, Lever's `parseResume`, Workable's form
  uploads). Pages still load their own data (Ashby's GraphQL reads). Nothing is clicked but the employer's own Apply link.
- After each posting, any browser storage item holding the test person's details is removed from the phone's Chrome.
- Postings: 20 per system from UAply's own job feed and the systems' public posting lists: Greenhouse 7 employers (Robinhood,
  IMC, Figma, Discord, Verkada, Scale AI, Affirm), Lever 5 (Spotify, Gopuff, Zoox, Best Egg, [solidcore]), Ashby 2 (Webflow,
  Linear), Workable 3 (Hugging Face, Thorlabs, Ascendis Pharma), SmartRecruiters 1 (City of Philadelphia). Fill rates depend on each
  employer's own questions, so a wider spread of employers will move them.
- Greenhouse's hosted form refuses headless Chrome (CloudFront 403) and SmartRecruiters shows its bot page; neither was worked
  around (no user-agent change, no other trick). Greenhouse was measured in the phone's real Chrome, where it loads; SmartRecruiters
  was not measurable at all. The SmartRecruiters page named the network's address as flagged, which the laptop's earlier headless
  tries on the same network may have caused.
- Time to ready = page load until the form is filled and the bar shows, on the phone over its own connection.

## 5. Human checks, as found

| System | Check | Seen how | What UAply does |
|---|---|---|---|
| Greenhouse | Google reCAPTCHA, invisible (badge only) | script and requests to google.com/recaptcha on 20/20 | nothing; if Google asks for a challenge after Submit, the person answers it |
| Lever | hCaptcha, invisible | `.h-captcha` element and hcaptcha.com requests on 20/20 | nothing; same |
| Workable | Cloudflare Turnstile, invisible | `.cf-turnstile` on 20/20, challenges.cloudflare.com requests on 16/20 | nothing; same |
| Ashby | none | no check element, script or request on 20/20 | n/a |
| SmartRecruiters | bot wall before the form | "Access is temporarily restricted" on 20/20 | nothing; the app shows the page as it is |

The script reads these only to report them and to keep "automatic" off; it never clicks, focuses or types into them (the mock
forms count any touch of the check and the tests require zero).

## 6. How others fill forms (for comparison)

- **Simplify Copilot** (Chrome extension): detects supported application pages (Greenhouse, Lever, Workday and others), fills
  them from the Simplify profile, uploads the default resume, reuses answers to unique questions, and says the person reviews
  and submits the application themselves ([help article](https://help.simplify.jobs/articles/2415391-using-copilot-to-autofill-applications)).
  It can also fill demographic questions; UAply does not.
- **LazyApply** (Chrome extension): fills and submits applications in bulk on job boards (mainly LinkedIn Easy Apply and Indeed),
  with daily caps; reviews describe autofill working on simple forms only. That is the auto-submit model UAply does not use.
- **Teal** (Chrome extension): job tracker with an "autofill job applications" feature across 40+ job boards; no public detail on
  submission found. Comparable tools advertise "never auto-submits" and leave sponsorship, salary, EEO and custom questions to the
  person.

UAply differs in running inside its own phone app (no browser extension on phones), filling only from what the person saved,
never filling voluntary questions, and saying Sent only on the employer's confirmation page.

## 7. Legal notes (honest version)

- The person is on the employer's real page, sees every answer, can change any of them, and presses Submit. Nothing reaches the
  employer that the person did not see and send. That is autofill, like a browser's or a password manager's, not a bot
  submission. Calling it "applied for you" would be wrong; the app says "Filled from your UAply profile" and "Sent" only after
  the employer's confirmation.
- UAply does not get past any check: it never interacts with reCAPTCHA, hCaptcha or Turnstile, does not change its browser
  identity, and does not work around SmartRecruiters' bot wall or Greenhouse's headless block.
- The new first-swipe agreement (consent version 3) adds the owner's clause, recorded with the time: "You authorize UAply to
  complete and submit job applications on your behalf using the information you provide." It is followed by what that means
  today (connected employers get the application; elsewhere the app fills the form and the person submits). The clause is drafted
  for the Terms in LEGAL-REVIEW.md section 11; the Terms page itself is not changed until the attorney reads it.
- Automatic submit would make UAply the one pressing Submit, as the person's agent. Even where a form has no human check, that
  needs the attorney's reading of the system's terms (and the employer's), which is why `counsel_approved` exists.
- Data: the profile is passed to the employer's page as a function argument while the form fills (the page receives what it
  asks for, as with any autofill); the resume copy for the file chooser is deleted when the page closes. A hostile page could read
  the profile during the fill or fake a confirmation page; the employers here are the ones the person chose to apply to.

## 8. What is done, and what is not

Done: the script (`shared/uaply-assist.js`); the switch file and its rule; the app side in Job Tracker; the Android plugin and screen
(`AssistPlugin.java`, `AssistActivity.java`, registered in `MainActivity`, declared in the manifest); consent version 3; mock forms
for all five systems (`tools/fixtures/assist/`, every mapping and the bridge on each) and tests (`tools/test-assist.js`, 213 checks;
`tools/ui-assist-tracker.js`, 26 checks, the bridge in Job Tracker); the measurement in one command (`tools/assist-measure.py`).

Not done, and why:
- **The UAply app itself was not built or installed on the Galaxy.** Building needs Google's Android SDK, whose license only the
  owner can accept (`mobile/build-android.ps1`). The Java was written against Capacitor 7's plugin API but has not been compiled.
  The Galaxy measurement ran the same script in the phone's Chrome 138, the engine Android's WebView uses, so the fill results
  carry over; the native parts (file chooser, the bar, the confirmation hand-back) need a build to be seen working. One difference to
  check then: Android's WebView names itself with "wv" in its browser identity, and a hiring system could treat it differently from
  Chrome.
- iOS native screen: not written.
- SmartRecruiters: not measurable (bot wall); Workday, iCIMS and companies' own sites: not covered.
- The server is not told about an assisted Sent (the Job Tracker row and the account's saved decisions are); the application
  record on the server is Mohammed's side (UAP cards).

Owner steps to see it in the app: run `powershell -ExecutionPolicy Bypass -File mobile\build-android.ps1`, accept Google's
license, install the test build on the Galaxy, swipe right on a Greenhouse or Lever hand-off job, open Job Tracker, tap
**Finish applying on their site**.
