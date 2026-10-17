# Receiving applications from UAply: the employer kit

UAply is a job app. A person swipes right on a job to apply. UAply sends that application to an employer only when the employer has agreed
in writing and set up one way to receive it. Without that, UAply sends nothing: the person finishes on the employer's own careers page.

Pick the page for the system you use. Each one says what UAply sends, where you create the key, what the key can do, how to turn it off,
and what you see for each application.

| You use | Page | What you create |
|---|---|---|
| Greenhouse | [greenhouse.md](greenhouse.md) | A Job Board API key |
| Lever | [lever.md](lever.md) | A Postings API key (made by a Super Admin) |
| Ashby | [ashby.md](ashby.md) | An API key with Candidates write and Jobs read |
| SmartRecruiters | [smartrecruiters.md](smartrecruiters.md) | An Application API key |
| Workable | [workable.md](workable.md) | An API access token with the r_jobs and w_candidates scopes |
| None of these, or you prefer email | [email-and-webhook.md](email-and-webhook.md) | A recruiting email address, or an HTTPS address and a secret |

Before UAply sends anything, you sign or reply to the [consent letter](consent-letter.md). It records what you agreed to and how to stop.

## The same for every system
- **Only people who chose to apply.** Each application is one person who swiped right on your job, reviewed what would be sent, and agreed.
- **Never voluntary self-identification.** UAply never sends gender, race or ethnicity, veteran status or disability status, even when
  your form asks. Those questions are left for the person to answer with you directly.
- **No guessing.** If your form has a required question the person's profile cannot answer, UAply asks the person. If it still cannot be
  answered (for example a file other than a resume), UAply sends nothing and the person finishes on your page.
- **Your key stays on UAply's server.** It is never shown in the app, written to a log or put in an error message. Test mode never uses it.
- **You can stop at any time** by revoking the key (the steps are on each page) and telling us. Revoking works at once, without us.
- **You make every hiring decision.** UAply does not rank, reject or screen applicants for you.

Menu names are the ones each company documented in October 2026. They rename menus from time to time; if a step does not match, search
your system's help center for the key name in the table.

Questions: the contact on [UAply's support page](../../legal/support.html).
