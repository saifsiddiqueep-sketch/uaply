# UAply legal risk review (October 12, 2026)

**This is not legal advice and I am not an attorney.** It is a risk audit and a set of drafts prepared by an AI assistant. Nobody can promise "no legal risk." Have a licensed attorney (ideally one who handles app, privacy and employment law) review everything here before UAply is public or submitted to an app store. Facts below were checked on the web in October 2026; several came from law-firm blogs and secondary sources, and each is marked with how solid it is.

## 1. Where the jobs come from (the contract question)

| Source | What its terms say | Confidence | Decision |
|---|---|---|---|
| Remotive | Using its listings "to collect signups or email addresses constitutes a breach"; must link back and name Remotive; asks that jobs not go to third-party sites; about 4 requests a day | From Remotive's own API page | **Off.** UAply collects emails, so using it would breach the terms. Needs written permission. |
| Jobicy | Credit Jobicy; "all application buttons" must go to the original job URL | From Jobicy's own page | **Link-out only**, never auto-submitted, and off by default |
| The Muse | Terms not found | Could not verify | **Off** until verified in writing |
| Greenhouse, Lever, Ashby public boards | Public feeds for employers' careers pages; no terms found covering third-party aggregation | Could not verify | **Link-out only** and **off by default** |
| Indeed, ZipRecruiter | No open API; partner programs only; Indeed's terms forbid keeping copies | Vendor blogs, not the companies | **Never used** |
| Partner employers | The employer gave the posting and agreed to receive applications | Your own agreements | **The only source that receives applications.** Each needs a recorded consent. |

**What this means:** I can only call a job "authorized" if the employer gave it to you. Everything scraped or fed from a third party is either off or link-out only. Real third-party jobs need either written permission, a licensed job-data provider (for example the official USAJobs API for federal jobs, which is public data), or each employer's own opt-in.

## 2. Sending applications

- **Emailing a company that never asked** can be unwelcome, can damage your sender reputation, and may implicate the CAN-SPAM Act (commercial email rules) depending on content. So UAply emails **only** partner employers who opted in. For every other job the swipe sends the person to the employer's own page.
- **Submitting into an employer's applicant tracking system** needs a key issued by that employer (for example Greenhouse's job board application endpoint). Not available to third parties, so not done.
- **Server safeguards built:** the server decides who may receive an email (never the browser), strict address checks, one application per person per job, a daily cap, same-site requests only, and no cover note or message written for the recruiter.
- **First-use consent:** before the first application the app explains what is sent and to whom, and records agreement to the Terms and Privacy Policy.

## 3. Privacy law

- **Triggers:** about 20 states have comprehensive privacy laws in 2026; thresholds vary (revenue, number of consumers, share of revenue from selling data). **Whether any apply to you yet depends on size and where users live. Ask your attorney.** Writing to the strictest common standard is the safe default, which is what the draft policy does.
- **Sensitive data:** work authorization can reveal citizenship or immigration status, which California and other states treat as sensitive. It is optional, used only inside applications the person sends, and never in scoring.
- **Not collected:** race, ethnicity, sex, age, religion, disability, veteran status, Social Security number, payment cards.
- **Children:** the app is 18+. If you want students under 18, COPPA (under 13) and state teen rules need a separate plan.
- **Rights process:** request by email, 45-day response, appeal path. You need a real privacy email and a way to find and delete a person's records on the server.

## 4. AI and automated hiring rules

Current as of the sources found (verify each; they change often): New York City Local Law 144 (bias audit and candidate notice for employers using automated tools); Illinois' amended Human Rights Act (in effect January 1, 2026); California Civil Rights Council rules (October 1, 2025) and CCPA automated-decision rules (compliance dates 2026 and 2027); Colorado's replacement law effective January 1, 2027. These bind **employers** that use automated tools to evaluate candidates. UAply today uses a fixed scoring formula, not machine learning, and does not screen or reject anyone. The disclosure page says exactly that. **If you later add machine learning, resume ranking for employers, or auto-rejection, the analysis changes and you will likely need bias audits and notices.** Also keep the page true: it states the score weights and the 45% cap.

## 5. App Store and Google Play

- **Both stores** need a public privacy policy URL, and accurate privacy answers (Apple's App Privacy details, Google's Data safety form).
- **Account deletion:** if the app lets people create accounts, both stores require deletion inside the app (and, for Google, a web link). UAply has no accounts yet; building sign-in later triggers this.
- **Sign in with Apple:** needed if you offer other third-party sign-in (Google) in an iPhone app, unless an exception applies.
- **Payments:** subscriptions inside apps normally must use the store's billing (a commission of about 15 to 30%).
- **Apple's "minimum functionality" rule:** a thin wrapper around a website is a common reason for rejection. Plan a real app.
- I confirmed the account-deletion rules from older sources (2022 to 2023). **Read the current Apple App Review Guidelines and Google Play Developer Policy before submitting.**

## 6. What I could not verify

- Terms of The Muse, Greenhouse, Lever and Ashby (see section 1).
- Current text of Apple and Google policies.
- Which state laws apply to your business, your trademark availability for "UAply", and whether your applications qualify for any special treatment.
- Whether the "AI and matching" laws apply to you as a tool provider and not only to employers.

## 7. Before you publish

1. Fill every yellow blank in the legal pages (legal name, address, emails, state, retention period, DMCA agent). `node check.js` lists how many remain.
2. Get a real contact and privacy email, and register a DMCA agent with the U.S. Copyright Office.
3. Sign partner agreements (or at least written consent) with every employer that will receive applications.
4. Decide whether to get written permission or a license for any third-party job feed.
5. Have an attorney review the Terms, Privacy Policy, AI page and your partner agreement, and clear the name (section 8).
6. Add in-app deletion before launching accounts.

## 8. The name "UAply" (checked October 12, 2026)

The app was first called "Aply", then briefly "UApply" (two p's), and is now **"UAply"** (U, A, p, l, y: one "p"). A web search found that **none of these names is clearly safe**:

- **"APLY" (the original name): a trademark application is pending.** A filing for the standard-character mark APLY was made in July 2024 and was awaiting examination. It describes a professional networking platform on a mobile app and website, with services that include job posting and recruitment. That is the same field as this app and is the likely reason "Aply" could not be used.
- **"UAply" contains APLY.** Adding a "U" in front may not be enough to avoid confusion with APLY, because the added letter is small and the field is the same. This is the main risk with the current name.
- A trademark record exists for **UAPPLY.COM, Inc.**, covering online links to education applications (Justia listing; I could not confirm whether it is still active). This is a closer match to the two-p spelling.
- **McGill University** runs a graduate admissions system named uApply.
- An iPhone app named **UApply** already exists in the App Store (it appears to be a study-abroad consultancy app).
- **uApply.ai** is a career-technology company that automates job applications with AI. It matches the two-p spelling and is in the same field.
- I found no exact results for "UAply" itself. That is not a clearance: it only means the search did not turn one up.

Apple and Google reject or remove apps over confusingly similar names, and a trademark owner can demand a change after launch. **Have an attorney run a proper clearance search (USPTO and common-law uses) and give an opinion before you spend money on branding, a domain or a store listing.** If it is not clear, picking a different name now is far cheaper than rebranding later. The rename is mechanical and was done in one pass, so it can be repeated.

## 9. Questions for your attorney

- Which state privacy laws apply to us, and do we need to register as a business or data broker anywhere?
- Is our "applies on your behalf" flow acceptable under the employers' terms and under agency law (are we the applicant's agent)?
- Do we owe employers a contract before sending them applications, and what should it say?
- Should we limit liability or require arbitration, and is a class waiver enforceable in our state?
- If we add AI ranking or auto-apply, what audits and notices will we need?

## 10. Decisions made after this review (October 13, 2026)

These were added at the product owner's request after the review above, so parts of sections 2 and 3 no longer describe the app. They need the attorney review before launch.

- **Voluntary self-identification** (Profile setup, last step "Eligibility and extras", in a folded optional section): Hispanic or Latino, race or ethnicity, gender, veteran status and disability status, the questions many employers ask on their forms. Safeguards built: every question is optional and starts as "Not answered", each has "Prefer not to say", answers are stored only on the person's device (never sent to the server or to employers automatically), are never used to score, rank, filter or hide listings, and leave the device only when the person taps "Copy my answers". The Privacy Policy draft and the first-application notice now say this. **Ask the attorney:** whether a job app may offer this at all, whether these answers count as sensitive data under the state laws that apply to you, and whether "on the device only" changes that.
- **Message to the hiring manager** (Profile setup, last step "Eligibility and extras"): an opt-in, Plus and Pro only preference that adds a short message, filled in from the profile and the listing with a fixed template (not AI), to the application. It goes only where an application goes: to partner employers that agreed to receive applications. The Privacy Policy draft and the first-application notice mention it. **Ask the attorney:** whether writing this message on the person's behalf changes the "applies on your behalf" (agency) question in section 9, and what changes if an AI later writes it (section 4).
- **Help assistant (chatbot)** (Help button, sandbox and dev): answers support questions only from `help/articles.json`, names the article used, and offers a person ("Talk to a person"). It discloses that it is automated at the first message and labels itself **AI** (answers written by an AI model through our AI provider's API, only when the owner adds an API key) or **Automated** (help-article answers). Rules searched October 13, 2026 (law-firm and vendor blogs; check the statutes): the EU AI Act Article 50 requires telling people at the start that they are talking to AI (enforceable August 2, 2026); California's B.O.T. Act, Maine and New Jersey have bot-disclosure rules for sales contexts; the FTC treats undisclosed bots as potentially deceptive. Chat text is sent to our AI provider when AI is on and is not stored by UAply; feedback is stored in `data/<instance>/feedback.jsonl` and removed with the account. **Ask the attorney:** whether the disclosure wording and the AI provider's data terms are enough for the states and countries you serve, and how long feedback should be kept.
- **Accounts:** email and password sign-up with an 18+ and Terms confirmation, hashed passwords, and in-app account deletion that also removes the person's receipts and server application records (section 5 asked for deletion before accounts launch). A signed-in person gets an email receipt of each application at their own address.

## 11. Assisted apply in the phone app (October 21, 2026)

Added at the owner's request; needs the attorney review before launch. Full research, measurements and sources: `docs/assisted-apply.md`.

- **What it does:** in the UAply phone app, "Finish applying on their site" opens the employer's own application page inside the app, fills it from the person's UAply profile and attaches their resume file. The person reviews it and taps the employer's Submit. UAply never fills voluntary self-identification questions, never ticks consent or certification boxes, never touches a human check (reCAPTCHA, hCaptcha, Turnstile), and marks the job Sent only when the employer's confirmation page appears.
- **Consent recorded at the first swipe (consent version 3, stored with the time):** the first-swipe agreement now reads, in bold, "You authorize UAply to complete and submit job applications on your behalf using the information you provide." followed by what that means today (connected employers receive the application; elsewhere the app fills the employer's form and the person submits it). Everyone who agreed to version 2 sees the box once more.
- **Draft clause for the Terms of Service** (not yet in `legal/terms.html`): "Applications on your behalf. You authorize UAply to complete and submit job applications on your behalf using the information you provide. For employers connected to UAply, UAply sends your application when you swipe right. On other employers' sites, the UAply app fills in the employer's application form from your profile and you review and submit it yourself; UAply submits there for you only where this is allowed and you can see that it did. UAply never answers voluntary self-identification questions, never completes security checks such as CAPTCHAs, and tells you an application was sent only when the employer confirms it. You are responsible for the accuracy of your profile and of every application you submit."
- **The per-system switch:** `shared/assist-systems.json` can allow automatic submit for a hiring system only when the attorney has approved it (`counsel_approved`) and none of its measured forms has a human check. Today every system is "assisted". Measured findings: Greenhouse, Lever and Workable put a human check on every form; Ashby on none; SmartRecruiters blocks automated sessions. None of the five publishes candidate terms that address agents, except SmartRecruiters' Candidate Terms of Use (May 14, 2019), whose prohibited conduct includes using automatic means to access other users' data.
- **Ask the attorney:** (1) does the clause above make UAply the person's agent, and is that what we want; (2) may UAply press Submit for the person on a system with no human check (Ashby), given the employer's own terms with its hiring system; (3) is "the person presses Submit" enough to treat this as the person's own autofill everywhere else; (4) do the employers' privacy notices, which the person acknowledges themselves, change anything; (5) what notice is needed that the profile is put into the employer's page to fill it.

## 12. A swipe right that submits (October 23, 2026, pending the lawyer)

Saif's direction: a swipe right should submit the application as far as the law and the employers' own channels allow, with the person's
recorded consent. Built on the sandbox branch b2-swipe-submits; the research and the plan are in `docs/apply-by-email.md`.

- **Consent version 4, on the account.** The first-swipe box (`shared/uaply-live.js`) now says, in Reviewer 3's words, that a swipe right
  authorizes UAply to submit the application, the four ways it goes, and how to stop it (below). When the
  person agrees, the server keeps on the account the version, the time, the visitor's address and the SHA-256 of the exact words
  (`consent_api.py`, `POST /api/consent`). No application leaves UAply without that record: the server answers 403 "consent" otherwise.
  Not agreeing when the box is shown again from Settings takes it back. Everyone who agreed to version 3 sees the box once more.
- **The separate tick, off by default, right after the four ways:** "Automatic submit: where a hiring system allows it; none is switched on
  yet. Where one is, a swipe right fills the employer's form from your profile and presses Submit for you. UAply never answers voluntary
  self-identification questions, never ticks consent or certification boxes, and never completes a security check; if one is needed it
  stops and you finish." The "where" comes from `shared/assist-systems.json`, so once Saif switches a system on (counsel approved, no
  human check measured) the line names it, and the words a person agrees to then are the ones kept with their record.
- **Apply by email.** Only when a posting's own text asks for applications by email ("send your resume to ...") at an address on the
  employer's own domain; never a free mailbox, an agency, an accommodations or questions address. Each email names why it came and carries a
  link that stops UAply emailing that address. Limits: one application per person per job, at most 10 a day per employer domain, UAply's own
  daily limit, and the bounce list. Question: is an application the posting itself asked for transactional email (CAN-SPAM), as we think?
- **The words are Reviewer 3's** (box version 4 and Terms section 3, relayed October 23): the authorization, the four ways a swipe right
  goes, and **Send applications for me** in Profile, Account to stop it (off, every swipe right only saves the job; the server honors it).
  Settled October 23: an emailed application counts as sent "when UAply's email service accepts it for delivery; UAply cannot see
  whether the employer read it" (Terms section 3 and the receipt, matching what the app does: a later bounce turns the posting into a
  hand-off but does not change that Job Tracker row), and the box's third way says it happens "only if you turn on Automatic submit
  below". The match-percentage line and its How matching works link stay in the box, under the authorization.
- **Ask the attorney:** (1) the version 4 box and Terms section 3 wording; (2) the email route as described; (3) whether the automatic
  submit tick should be shown before any system is approved; (4) how long consent records should be kept after an account is deleted
  (today they go with the account).
