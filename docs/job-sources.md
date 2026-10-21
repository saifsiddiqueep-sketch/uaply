# Job sources

Where UAply's jobs come from, what each source allows, and the free keys the owner can request. Checked October 21, 2026. This is
not legal advice: have the lawyer confirm before launch. The code is `jobs_api.py` (`SOURCES`, `VIA`, `TTL`, `KEEP`).

Every source is **off** unless its kind is listed in `UAPLY_FEEDS` (Render, Environment) or in `"feeds"` in `UAPLY_CONFIG_JSON`, for
example `UAPLY_FEEDS=greenhouse,lever,ashby,smartrecruiters,usajobs,jobicy,muse,simplify,himalayas,remoteok`. Jobs from every source are
**link-out only**: swiping right opens the employer's (or the board's) own page. Nothing is emailed to anyone, unless the employer is
a partner or connected its own hiring system.

Rules for every source: postings older than 60 days are hidden (USAJOBS and partner jobs exempt), the same job from two feeds is shown
once, and every job carries `jobType` (full-time, part-time, internship, co-op, contract or temporary) and `postedDays`.

## Registry

| Source (kind) | What it is | Terms | Credit shown on the card | Refresh | Apply path | Job types it gives |
|---|---|---|---|---|---|---|
| Greenhouse boards (`greenhouse`) | Employers' own public job boards, 50+ listed in `SOURCES` | https://developers.greenhouse.io/job-board.html (public board API; no terms for third-party readers) | "via Acme on Greenhouse" | 30 min | Employer's Greenhouse posting | Custom "Employment Type" field when the employer has one; title words otherwise |
| Lever boards (`lever`) | Employers' own public postings | https://github.com/lever/postings-api | "via Acme on Lever" | 30 min | Employer's Lever posting | `categories.commitment` |
| Ashby boards (`ashby`) | Employers' own public job boards | https://developers.ashbyhq.com/docs/public-job-posting-api | "via Acme on Ashby" | 30 min | Employer's Ashby posting | `employmentType` |
| Workable (`workable`) | Employers' own public jobs feed | https://help.workable.com/hc/en-us/articles/115012771647 | "via Acme on Workable" | 30 min | Employer's Workable posting | `employment_type` |
| SmartRecruiters (`smartrecruiters`) | City of Philadelphia's public postings | https://developers.smartrecruiters.com/docs/posting-api | "via City of Philadelphia on SmartRecruiters" | 1 h (descriptions daily) | The City's posting | `typeOfEmployment` |
| USAJOBS (`usajobs`) | Federal jobs within 25 miles of Philadelphia: all, Pathways (students and recent graduates), part-time schedules | https://developer.usajobs.gov/general/terms-of-service (public data; credit and link to the official announcement) | "via USAJOBS; apply on the official announcement" | 3 h | The announcement on usajobs.gov | `PositionSchedule` (part-time), Pathways = internship, `PositionOfferingType` Temporary |
| Jobicy (`jobicy`) | Remote jobs, US | https://jobicy.com/jobs-rss-feed (credit Jobicy, link to the job on Jobicy, at most one pass an hour) | "via Jobicy" | 1 h | The job on Jobicy | `jobType` |
| The Muse (`muse`) | Internship and entry-level jobs | https://www.themuse.com/developers/api/v2 (register an app; key recommended) | "via The Muse" | 30 min | The job on The Muse | The Internship level |
| Simplify and Pitt CSC lists (`simplify`) | GitHub lists of internships and co-ops, https://github.com/SimplifyJobs/Summer2027-Internships (README.md and README-Off-Season.md) | No license file and no reuse terms in the repository; the rows are facts (company, title, place, link). UAply uses only rows whose link is a Greenhouse, Lever or SmartRecruiters posting, reads each posting from the employer's own board, and shows the employer's own data | "via Acme on Greenhouse, listed by Simplify and Pitt CSC" | 6 h (each posting checked at most daily) | Employer's own posting | Internship or co-op (the title, the board's field, the list's own kind) |
| Himalayas (`himalayas`) | Remote jobs open to the US | https://himalayas.app/api and https://himalayas.app/terms#api: link to the job on Himalayas, use `applicationLink` unchanged, show only on our own app, never pass jobs on to other boards, Google Jobs or LinkedIn, remove expired jobs | "via Himalayas" | 3 h (3 pages of 20) | `applicationLink` (the job on Himalayas) | `employmentType` (Full Time, Part Time, Contractor, Temporary, Intern) |
| Remote OK (`remoteok`) | Remote jobs | The notice in https://remoteok.com/api: link back to the job on Remote OK (a followed link) and name Remote OK as the source; no logo without permission | "via Remote OK" | 6 h | The job on Remote OK | Title words |
| Remotive (`remotive`) | Remote jobs | https://remotive.com/api-documentation: forbids using listings to collect sign-ups or emails, which UAply does | n/a | n/a | n/a | **Do not switch on** without written permission |
| Partner employers | Employers who post on UAply | UAply's own employer terms | "Posted on UAply by ..." | live | Sent to the employer | The employer's own pick |

**Not used, and never scraped:** LinkedIn, Indeed, ZipRecruiter and Handshake (closed or partner-only programs whose terms forbid
copying listings). Google for Jobs is a search feature, not an API. Arbeitnow's free API lists European jobs only. Reed is UK only.

## Keys the owner can request (Claude cannot fill in or submit these forms)

1. **USAJOBS** (the owner is submitting this one). https://developer.usajobs.gov/apirequest/ . Email: `uaplytechnologies@gmail.com`.
   Then in Render: `UAPLY_USAJOBS_KEY` = the key, `UAPLY_USAJOBS_EMAIL` = `uaplytechnologies@gmail.com`, and add `usajobs` to `UAPLY_FEEDS`.
2. **The Muse** (recommended). https://www.themuse.com/developers/api/v2 , "Register an app". App name `UAply`; website `https://uaply.net`;
   description: *UAply is a job-search app: people swipe through jobs and open the posting on The Muse to apply. We show the job title,
   company, location and a short summary, credit The Muse on every card, and link to the job page on The Muse.* The key goes in
   `UAPLY_CONFIG_JSON` as `"feed_keys":{"muse":"..."}`.
3. **Himalayas** (recommended, free). Sign in at https://himalayas.app and create an API key on https://himalayas.app/api . With a key
   UAply gets its own 60 requests a minute instead of the shared public allowance. (Not wired up yet: today UAply calls without a key.)
4. **Findwork** (optional, free). Sign up at https://findwork.dev/accounts/signup/ , then copy the token on https://findwork.dev/developers/ .
   Remote and tech jobs; the terms page must be read before it is switched on (not wired up yet).
5. **Jooble** (optional). https://jooble.org/api/about , form fields: name, position, email, website (`https://uaply.net`), phone.
   Text to paste where it asks what the key is for: *A job-search app for people in the US (Philadelphia first). We would show Jooble
   results with a link to the job on Jooble and credit Jooble on every card.* Ask them in the same message whether attribution or a
   revenue share is required for commercial use. Not wired up yet.
6. **Adzuna** (only with a license). https://developer.adzuna.com/signup gives a key at once, but its terms allow commercial use only
   for a 14-day trial (to check coverage); after that "a licence agreement is required" for a product that earns money or generates leads,
   and every advert must carry the word "Adzuna" (at least 116 x 23 pixels) linking to Adzuna. Ask Adzuna for a license before building it.
7. **Careerjet** (optional). https://www.careerjet.com/partners/ : a partner (publisher) program. Its attribution and commercial
   terms were not checked here; read them before signing up.
