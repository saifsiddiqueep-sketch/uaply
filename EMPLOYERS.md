# How employers receive applications from UAply

## The short version
When someone swipes right, UAply can only **send** their application to an employer that has **agreed to receive it**. That is how every
job site works, and it is not a limitation we can code around:

| Site | How an application reaches the employer | Who has to set it up |
|---|---|---|
| Indeed | Sends each application as signed JSON to an HTTPS address the employer registers for each job; the employer's system must answer "success" or Indeed retries | The employer's applicant tracking system, under a developer agreement |
| LinkedIn | Delivers into the employer's applicant tracking system through "Apply Connect" | The employer, with a certified partner system |
| Greenhouse, Lever, Ashby, SmartRecruiters | Accept an application over their API only with a key the employer creates | The employer (a Greenhouse key, a Lever key from a Super Admin, an Ashby key with candidate-write rights, a SmartRecruiters Application API key) |

So UAply has two kinds of jobs:

- **Partner jobs** (the employer connected): swipe right sends the application, and the person gets a confirmation email.
- **Public postings** (real jobs from employers' own career pages): UAply cannot send anything to an employer that never agreed, so a swipe
  right saves the job to the person's Applied list, emails them a confirmation that says plainly "finish your application", and opens the
  employer's own page. Their details are listed in the email, ready to copy.

More partners means more one-swipe applications. Recruiting employers is the growth lever for this feature.

## What an employer chooses (any combination)
Add the employer to `uaply-partners.json` on the server (see `partners.example.json`). Keep the file out of GitHub.

1. **Email.** Give UAply a recruiting address (`"contact"`). Each application arrives as an email with the applicant's details and the resume
   attached as a real file.
2. **Webhook (the Indeed way).** Give UAply an HTTPS address (`"webhook"`) and a secret (`"webhook_secret"`). Each application is POSTed there as
   signed JSON. Your system answers with any 2xx status. If it fails UAply tries again up to three times (after 1 and 3 seconds); a 4xx
   answer other than 408 or 429 is treated as final. Redirects are never followed. Do not reject an application inside the request; accept it
   first and review it afterwards.
3. **Both.** The application counts as sent when at least one channel accepts it.

An employer with no recorded consent (`"consent"`) is ignored, so nothing is ever sent to a company by accident.

## The webhook, in detail
`POST <your address>` with these headers:

| Header | Meaning |
|---|---|
| `Content-Type` | `application/json` |
| `X-UAply-Delivery` | A unique id for this application. Use it to ignore a repeat. |
| `X-UAply-Timestamp` | Seconds since 1970 when it was sent. Reject anything older than a few minutes. |
| `X-UAply-Signature` | `sha256=` and a hex HMAC-SHA256 of `timestamp + "." + raw body`, keyed with your secret (sent only when a secret is set) |

The body (resume is `null` when the person has not uploaded one):

    {
      "id": "…", "event": "application.created", "source": "UAply", "created_at": "2026-10-13T23:54:00Z",
      "job": {"id": 200123, "title": "…", "company": "…", "location": "…", "url": "https://…", "type": "internship", "work_style": "hybrid"},
      "applicant": {
        "name": "…", "email": "…", "phone": "…", "title": "…", "location": "…", "years_experience": 1, "skills": ["Python", "SQL"],
        "headline": "…", "summary": "…",
        "education": {"level": "Bachelor", "school": "…", "major": "…", "graduation": "2026-06", "gpa": 3.7},
        "links": {"resume": "https://…", "linkedin": "https://www.linkedin.com/in/…", "portfolio": "https://…"},
        "work_authorization": "…", "needs_sponsorship": "no", "earliest_start": "…", "country": "US", "willing_to_relocate": "yes",
        "most_recent_employer": "…",
        "most_recent_job": {"employer": "…", "title": "…", "start": "2024-06", "end": "", "current": true}
      },
      "message": "", "match_percent": 87,
      "resume": {"name": "Resume.pdf", "type": "application/pdf", "size": 48211, "content_base64": "…"}
    }

`country` is `US`, `CA`, `GB`, `other` or empty; `willing_to_relocate` and `needs_sponsorship` are `yes`, `no` or empty; in `most_recent_job`,
`start` and `end` are months (`YYYY-MM`) and an empty `end` with a `start` means the person still works there (`current` is then `true`). Every
field is optional for the person, so any of them can be empty. `applicant.expected_yearly_pay_usd` (a whole number of US dollars) appears only
when your own application form required expected pay; otherwise the person's expected pay is never sent.

To check the signature, compute HMAC-SHA256 over `timestamp + "." + body` with your secret and compare with `X-UAply-Signature` in constant time.

## What UAply never sends
Voluntary answers (race, gender, veteran or disability status) are never sent. The applicant agreed to what is sent before their first
application, and every application email to the applicant lists exactly what was shared.

## Straight into the employer's hiring system (Greenhouse, Lever, Ashby, SmartRecruiters)
For an employer that uses **Greenhouse**, **Lever**, **Ashby** or **SmartRecruiters**, an application can go straight into their own hiring
system, so it appears in their pipeline with the resume attached and nobody retypes anything. This is the nearest thing to "swipe right and it
is applied", and it works only for employers who connect, because every one of these systems requires a key that the employer's administrator
creates:

| System | What the employer creates | Where | The board name | Posting questions |
|---|---|---|---|---|
| Greenhouse | A **Job Board API** key | Configure, Dev Center, API Credential Management | `boards.greenhouse.io/<board>` | Yes |
| Lever | A **Postings API** key (a Super Admin makes it) | Settings, Integrations and API | `jobs.lever.co/<site>` | No (Lever's API does not carry them) |
| Ashby | An **API key** with the **Candidates write** and **Jobs read** permissions | Admin, Integrations, API Keys | `jobs.ashbyhq.com/<board>` | Yes |
| SmartRecruiters | An **Application API** key (or OAuth with the `candidate_applications_manage` scope) | Settings, Admin, Credential Manager | `jobs.smartrecruiters.com/<company>` | Yes (screening questions) |

Give UAply the key and the board name from the employer's job-board address. On this computer use the **Connect an employer's hiring system** box
on `/setup`. On a host, put the connections in the `UAPLY_ATS_JSON` setting as one line of JSON:

    [{"kind": "greenhouse", "board": "acme", "api_key": "THE-KEY-THE-EMPLOYER-GAVE-YOU"},
     {"kind": "lever", "board": "acme", "api_key": "THE-KEY-THE-EMPLOYER-GAVE-YOU"},
     {"kind": "ashby", "board": "acme", "api_key": "THE-KEY-THE-EMPLOYER-GAVE-YOU"},
     {"kind": "smartrecruiters", "board": "AcmeInc", "api_key": "THE-KEY-THE-EMPLOYER-GAVE-YOU"}]

An employer who gives UAply its jobs (the partner list) can put the key in the same record instead: add `"ats": {"kind": "greenhouse", "board": "acme", "api_key": "..."}`
to the employer and `"ats_job_id"` to each job: the posting's number in Greenhouse, its id in Lever or Ashby (the long id at the end of the
posting's address), and for SmartRecruiters the posting's **uuid** (the id with dashes, not the number in the posting's address). UAply's own
Ashby and SmartRecruiters feeds already record the right id for every posting, so a connected employer's listed jobs need nothing more.
Run `python tools/mock-ats.py` to try a connection against a stand-in.

What then happens, for that employer's real postings on UAply:

- The job card says **Apply instantly**, so a person knows before swiping what swipe right does. Cards for other employers say **Opens employer site**.
- Swipe right, with a short window to Undo, sends the application: name, email, phone, links, the resume file, and answers to the posting's own
  questions where the person's profile has them (LinkedIn, website, current employer and job title, work authorization, sponsorship, country,
  willingness to relocate, how they heard of the job, and expected pay only when the form requires it). Greenhouse also receives the fields its
  own careers page fills in without asking: `country_short_name`, the location with its `latitude` and `longitude` (all three together, worked
  out from the person's ZIP code), and the most recent job as `employments[0][...]`.
- **Greenhouse**, **Ashby** and **SmartRecruiters** postings often have required questions of their own. If one cannot be answered from the profile,
  the app asks the person that question once and remembers the answer; if it still cannot be answered (a file other than the resume, or a kind of
  field UAply does not know how to fill), UAply sends nothing and the person finishes on the employer's page (the card says "Saved. Finish
  applying"), rather than guessing. **Lever** takes the standard fields only; its API does not carry a posting's custom questions.
- **Ashby**: UAply reads the posting's form with the employer's key (Ashby's public job board does not include it), answers it, and sends the
  answers with the resume file. Ashby's own voluntary questions (its EEOC survey) are a separate form that UAply never sends, and any gender, race,
  veteran or disability question inside the main form is skipped. An application refused by the employer's own limit on applications per person is
  reported as not sent.
- **SmartRecruiters**: UAply reads the posting's screening questions and consent settings with the employer's key and sends the person's name, email,
  phone, city, LinkedIn and website, school and degree, the resume file and their message. Questions marked as diversity questions are never
  answered. If the employer requires consent to its privacy policy, UAply gives it only when the person switched on "Acknowledge employers' notices
  for me" or answered that question themselves; optional consents (a talent pool, text messages) are never given. Work history is not sent,
  because SmartRecruiters requires a start date for each job and UAply's profile does not hold one.
- Requirements stay the same as for any direct send: a verified account whose email matches the application, `delivery` set to `live`, and the person's
  consent. Keys are never shown, logged or put in an error message. In test mode UAply never uses an employer's key: Ashby and SmartRecruiters forms
  are read only for a live send.
- Try it first with a test posting on the employer's side. None of these systems lets UAply test a key without really submitting, and for Ashby and
  SmartRecruiters even the form can only be read with the key, so a test posting is the only way to see a real one.

**What could not be checked without a real employer's key.** The Ashby and SmartRecruiters connections follow their published documentation:
Ashby's guide "Creating a custom careers page" and its API reference (the form definition, the multipart `applicationForm.submit` with the answers
as a JSON string and the file named by its field's value, Basic auth with the key), and SmartRecruiters' Application API reference (the
`/postings/{uuid}/configuration` questions, the JSON candidate with the resume in base64, answers as records of field ids, the `X-SmartToken`
header). The stand-in in `tools/mock-ats.py` checks every request against that documentation. What only a live key can confirm: the exact error
replies each system gives (for example whether Ashby answers a bad key with HTTP 401 or with "success": false), how often SmartRecruiters returns
consent settings and in which shape, field types Ashby adds later, and that an Ashby job board's posting id is always the id `jobPosting.info`
takes (Ashby's documentation and every public board seen so far say it is). Neither system documents its rate limits; a "too many requests" answer
is reported as a pause, like Lever's.

## What no site can do
Fill in and submit an application on an employer's website for them. Employers' pages are built to be completed by the applicant, they protect
themselves with bot checks, and driving them by program breaks their terms. None of Greenhouse, Lever, Ashby or SmartRecruiters documents a way to open an
application page already filled in from a link, either. The honest alternative for employers who have not connected is the one UAply uses:
save the job, show what will be asked, and open the employer's page with the person's answers ready to copy.

## Sources for this design
Indeed Apply documentation (`indeed-apply-postUrl`, success and retry rules); Greenhouse Job Board API (applications need an API key);
Lever Postings API (apply needs a key made by a Super Admin); Ashby API (`jobPosting.info` and `applicationForm.submit`, a key with the
candidatesWrite permission, and the guide "Creating a custom careers page"); SmartRecruiters Application API (`/postings/{uuid}/configuration`
and `/postings/{uuid}/candidates`, the `X-SmartToken` key or the `candidate_applications_manage` OAuth scope); LinkedIn Apply Connect (partner
applicant tracking systems). See the research notes in the pull requests that added this file and the Ashby and SmartRecruiters connections.
