# Job sources

Where UAply's jobs come from, what each source allows, and the free keys the owner can request. Checked October 21, 2026. This is
not legal advice: have the lawyer confirm before launch. The code is `jobs_api.py` (`SOURCES`, `VIA`, `TTL`, `KEEP`).

Every source is **off** unless its kind is listed in `UAPLY_FEEDS` (Render, Environment) or in `"feeds"` in `UAPLY_CONFIG_JSON`, for
example `UAPLY_FEEDS=greenhouse,lever,ashby,workable,smartrecruiters,usajobs,careeronestop,jobicy,muse,simplify,himalayas,remoteok`.
Jobs from every source are **link-out only**: swiping right opens the employer's (or the board's) own page. Nothing is emailed to
anyone, unless the employer is a partner or connected its own hiring system.

Rules for every source: postings older than 60 days are hidden (USAJOBS and partner jobs exempt), the same job from two feeds is shown
once (the employer's own board wins), every job carries `jobType` (full-time, part-time, internship, co-op, contract or temporary) and
`postedDays`, and each employer board keeps 14 roles plus up to 10 more in Pennsylvania, New Jersey or Delaware.

## Coverage

* **Anywhere in the US:** 80+ employer boards (tech, healthcare clinics, retail, restaurants, gyms, warehouses, plants, launch sites),
  remote jobs from Jobicy (15 industries), Himalayas (all, internships, part-time) and Remote OK, internships and co-ops from the
  Simplify / Pitt CSC lists. A remote job open to the US is shown to everyone; the distance filter never hides it (except "remote only").
* **Pennsylvania, New Jersey, Delaware:** USAJOBS around Philadelphia (50 mi), Wilmington DE (40), Trenton NJ (40), Newark NJ (40) and
  Camden NJ (25), each also for Pathways (students and recent graduates) and part-time schedules; CareerOneStop (the state job banks'
  jobs) around the same five cities; the City of Philadelphia; employers with PA, NJ and DE offices (`SOURCES` names each with its count).

## Adding employer boards in bulk

`tools/find-boards.py` finds employers' public boards on Greenhouse, Lever, Ashby, SmartRecruiters and Workable: from company names or
domains (`--names tools/data/board-seeds.txt`, slugs tried on every system) and from every board the Simplify / Pitt CSC lists link to
(`--simplify`). It checks each board live, counts its postings, US postings and PA / NJ / DE postings, and writes a review file
(`tools/data/board-candidates.json`). Boards with at least 5 US postings that pass review go in `job-boards.json` (kind, token, name and
the counts on the day they were checked); the app reads that file at start, after the hand-picked boards in `jobs_api.SOURCES`, and reads
each of those boards every 2 hours (spread out). The owner page `/api/feed-health` (owner password) lists every source with its jobs,
successes and failures; a source that fails 3 refreshes in a row is switched off for a day and then tried again by itself.

How the reading scales to hundreds of boards: 12 reader threads (not one per board); a Greenhouse board's list is read without
descriptions (about an eighth of the size) and only the postings that will be kept get their description read, once, and again only
when the posting changes; employer SmartRecruiters boards read at most 24 descriptions a day; boards are read as they arrive (never
whole); the list sent to the app is written straight into gzip and only the compressed copy is kept; past 300 MB of memory no new
board read starts. On a fresh start the first visitor is answered within about 8 seconds with what is ready, and the app asks again
until every board is in.

Discovery seeds (`tools/data/board-seeds-us.txt`): each state's large employers (hospital systems, universities, retailers, banks,
logistics, utilities) plus industry lists (dental groups, real estate, legal, medical groups, education, trades, manufacturing,
logistics, retail and hospitality, sports and recreation, nonprofits, accounting, media). Besides the five hiring systems the tool
looks for an iCIMS careers site (`careers-<name>.icims.com`) whose robots.txt allows its sitemap. Probes done in the last 30 days are
not repeated (`tools/data/board-probed.json`); Workable is asked at most one request every 1.5 seconds (it answers 429 sooner).

## Registry

Risk: **Low** = a public body's or the source's own published API whose terms we follow; **Medium** = public data with no terms that
clearly cover a third party showing it; **High** = terms that forbid our use (not switched on).

| Source (kind) | What it is | Terms | Allowed use | Credit shown on the card | Refresh | Apply path | Job types | Risk |
|---|---|---|---|---|---|---|---|---|
| Greenhouse boards (`greenhouse`) | Employers' own public job boards | https://developers.greenhouse.io/job-board.html | A public, keyless API meant for careers pages; no terms for third-party readers | "via Acme on Greenhouse" | 30 min | Employer's posting | Custom "Employment Type" field, else title | **Medium**: public and read only, but no terms say an aggregator may show it; we link out and never copy applications |
| Lever boards (`lever`) | Employers' own public postings | https://github.com/lever/postings-api | Same as Greenhouse | "via Acme on Lever" | 30 min | Employer's posting | `categories.commitment` | **Medium**: same reason |
| Ashby boards (`ashby`) | Employers' own public job boards | https://developers.ashbyhq.com/docs/public-job-posting-api | Same as Greenhouse | "via Acme on Ashby" | 30 min | Employer's posting | `employmentType` | **Medium**: same reason |
| Workable (`workable`) | Employers' own public jobs feed | https://help.workable.com/hc/en-us/articles/115012771647 | Documented for custom careers pages | "via Acme on Workable" | 30 min | Employer's posting | `employment_type` | **Medium**: same reason |
| SmartRecruiters (`smartrecruiters`) | City of Philadelphia (whole list) and employer boards (Equinox, Red Bull) | https://developers.smartrecruiters.com/docs/posting-api | Public Posting API, no key | "via City of Philadelphia on SmartRecruiters" | 1 h (descriptions daily, 40 a day for an employer board) | Employer's posting | `typeOfEmployment` | **Low** for the City (public body's own postings); **Medium** for employers |
| USAJOBS (`usajobs`) | Federal jobs around 5 tri-state cities, plus Pathways and part-time searches: 15 searches every 3 h = 120 requests a day | https://developer.usajobs.gov/general/terms-of-service | Public data, may be copied and republished, commercial use included | "via USAJOBS; apply on the official announcement" | 3 h | The announcement on usajobs.gov | Schedule (part-time), Pathways = internship, Temporary offering | **Low**: the government's own API; we credit it and link to the announcement |
| CareerOneStop (`careeronestop`) | The National Labor Exchange (the PA, NJ and DE state job banks' jobs) around 5 tri-state cities (all, internship, part-time) plus remote: 16 searches every 3 h = 128 requests a day, the last 7 days | License shown on https://www.careeronestop.org/Developers/WebAPI/registration.aspx ; API https://www.careeronestop.org/Developers/WebAPI/Jobs/list-jobs.aspx | Royalty-free for the purpose stated at registration; no altering the data; credit both the U.S. Department of Labor ETA and Minnesota DEED on every page that shows it; key kept secret; license lasts 36 months | "via CareerOneStop (U.S. Department of Labor ETA and Minnesota DEED)" | 3 h | The posting on the NLx (jobsyn.org) | Title words, "part-time" in the summary | **Low**: public, free, attribution only. Note: new Jobs API access now goes through the NLx Research Hub (see the key list) |
| Jobicy (`jobicy`) | Remote jobs open to the US, 15 industries | https://jobicy.com/jobs-rss-feed | Free; credit Jobicy, link to the job on Jobicy, at most one sync pass an hour | "via Jobicy" | 1 h | The job on Jobicy | `jobType` | **Low**: the source's own published conditions, followed |
| The Muse (`muse`) | Internship and entry-level jobs | https://www.themuse.com/developers/api/v2 | Public API; register an app (key) for production use | "via The Muse" | 30 min | The job on The Muse | The Internship level | **Medium** until the app is registered (key), then **Low** |
| Simplify and Pitt CSC lists (`simplify`) | GitHub lists of internships and co-ops, https://github.com/SimplifyJobs/Summer2027-Internships (README.md, README-Off-Season.md) | No license file, no reuse terms | Rows are facts (company, title, place, link); only rows linking to a Greenhouse, Lever or SmartRecruiters posting are used, each read from the employer's own board | "via Acme on Greenhouse, listed by Simplify and Pitt CSC" | 6 h (each posting checked daily) | Employer's own posting | Internship or co-op | **Medium**: no license; we credit the list and show only the employer's own data |
| Himalayas (`himalayas`) | Remote jobs open to the US: all, internships, part-time (3 pages each) | https://himalayas.app/api , https://himalayas.app/terms#api | Show on our own app only; link to the job on Himalayas; `applicationLink` unchanged; never pass jobs on to other boards, Google Jobs or LinkedIn; remove expired jobs | "via Himalayas" | 3 h | `applicationLink` | `employmentType` | **Low**: its published API terms, followed |
| Employers' careers sites (`careerpage`) | Employers whose own careers site publishes a sitemap of job pages with schema.org JobPosting data (iCIMS sites such as Hackensack Meridian Health, Piedmont, UnityPoint, OHSU, NYU Langone, Dental Care Alliance, Sonrava), found with `tools/find-boards.py` and listed in `job-boards.json` with their sitemap | Each site's robots.txt (read first, its Disallow rules and Crawl-delay followed; a site whose robots.txt cannot be read is not read) | JobPosting data is published for search engines to show; UAply reads at most 40 job pages per site every 6 hours (a page again only when its lastmod changes), one request at a time with at least 2 seconds between them, only pages on the sitemap's own host, never a page behind a login or a human check (the site is then left alone) | "via Acme careers site" | 6 h | The employer's own job page (assisted hand-off) | `employmentType` | **Medium**: public structured data meant to be shown by job search engines, read politely as robots.txt allows; each employer's site terms are not individually reviewed |
| Remote OK (`remoteok`) | Remote jobs | The notice in https://remoteok.com/api | Link back to the job on Remote OK (followed link) and name Remote OK; no logo | "via Remote OK" | 6 h | The job on Remote OK | Title words | **Low**: its published conditions, followed |
| Remotive (`remotive`) | Remote jobs | https://remotive.com/api-documentation | Forbids using listings to collect sign-ups or emails, which UAply does | n/a | n/a | n/a | n/a | **High**: **do not switch on** without written permission |
| Partner employers | Employers who post on UAply | UAply's own employer terms | The employer gave the posting and agreed to receive applications | "Posted on UAply by ..." | live | Sent to the employer | The employer's own pick | **Low** |

**Checked and not added:** the State of Delaware, Camden County, the cities of Camden, Wilmington, Trenton and Newark, NJ Transit,
ChristianaCare, Cooper University Health Care, Incyte, Chemours, WSFS, Sallie Mae, Navient, Campbell's, Subaru of America and the
universities (Rutgers, Princeton, UDel) are not on a public Greenhouse, Lever, Ashby, SmartRecruiters or Workable board (they use
Workday, iCIMS, NEOGOV, PeopleAdmin or their own sites, which UAply does not read). Anduril's board (44 MB) is over the 40 MB cap.
Arbeitnow lists European jobs only; Reed is UK only. The Muse's API has no internship filter beyond its levels.

**Never used, never scraped:** LinkedIn, Indeed, ZipRecruiter, Handshake and Glassdoor (closed or partner-only programs whose terms
forbid copying listings). Google for Jobs is a search feature, not an API.

## Keys the owner can request (Claude cannot fill in or submit these forms)

1. **USAJOBS** (the owner is submitting this one). https://developer.usajobs.gov/apirequest/ . Email: `uaplytechnologies@gmail.com`.
   Then in Render: `UAPLY_USAJOBS_KEY` = the key, `UAPLY_USAJOBS_EMAIL` = `uaplytechnologies@gmail.com`, and add `usajobs` to `UAPLY_FEEDS`.
2. **CareerOneStop / National Labor Exchange jobs** (recommended for PA, NJ, DE). Registration form:
   https://www.careeronestop.org/Developers/WebAPI/registration.aspx (Type of request: New Request; Organization: UAply; URL:
   `https://uaply.net`; name, address, phone and email `uaplytechnologies@gmail.com`). Text to paste under "Where and how will data be used
   or displayed?": *UAply (https://uaply.net) is a free job-search app for people in the US, starting in Philadelphia, New Jersey and
   Delaware. We would show job postings from the CareerOneStop Jobs API (title, company, location, posting date and the short
   description) as cards in the app, unchanged, each linking to the original posting, with the credit "CareerOneStop, sponsored by the
   U.S. Department of Labor, Employment and Training Administration, and the Minnesota Department of Employment and Economic
   Development" on every screen that shows them. We do not resell the data or pass it to other sites.* **Important:** CareerOneStop's
   page says new Jobs API access is now approved by the NLx Research Hub (National Association of State Workforce Agencies): if the
   registration does not include the Jobs API, send the same text as a data request at https://nlxresearchhub.org or to
   nlxresearchhub@naswa.org . When the user ID and token arrive: Render, Environment, `UAPLY_COS_USER_ID` and `UAPLY_COS_TOKEN`, and add
   `careeronestop` to `UAPLY_FEEDS`. Until then the 16 searches show "no key". If the NLx issues a different API shape, the client
   (`_careeronestop` in `jobs_api.py`) needs a small change. Expected volume once on (an estimate, not measured: there is no key yet): 16
   searches x up to 100 postings from the last 7 days = at most 1,600; the five areas overlap (Camden lies inside Philadelphia's 50 miles),
   so after the same-job rule roughly 700-1,200 tri-state jobs, mostly on-site, many part-time.
3. **The Muse** (recommended). https://www.themuse.com/developers/api/v2 , "Register an app". App name `UAply`; website `https://uaply.net`;
   description: *UAply is a job-search app: people swipe through jobs and open the posting on The Muse to apply. We show the job title,
   company, location and a short summary, credit The Muse on every card, and link to the job page on The Muse.* The key goes in
   `UAPLY_CONFIG_JSON` as `"feed_keys":{"muse":"..."}`.
4. **Himalayas** (recommended, free). Sign in at https://himalayas.app and create an API key on https://himalayas.app/api . With a key
   UAply gets its own 60 requests a minute instead of the shared public allowance. (Not wired up yet: today UAply calls without a key.)
5. **Findwork** (optional, free). Sign up at https://findwork.dev/accounts/signup/ , then copy the token on https://findwork.dev/developers/ .
   Remote and tech jobs; the terms page must be read before it is switched on (not wired up yet).
6. **Jooble** (optional). https://jooble.org/api/about , form fields: name, position, email, website (`https://uaply.net`), phone.
   Text to paste where it asks what the key is for: *A job-search app for people in the US (Philadelphia first). We would show Jooble
   results with a link to the job on Jooble and credit Jooble on every card.* Ask them in the same message whether attribution or a
   revenue share is required for commercial use. Not wired up yet.
7. **Adzuna** (only with a license). https://developer.adzuna.com/signup gives a key at once, but its terms allow commercial use only
   for a 14-day trial (to check coverage); after that "a licence agreement is required" for a product that earns money or generates leads,
   and every advert must carry the word "Adzuna" (at least 116 x 23 pixels) linking to Adzuna. Ask Adzuna for a license before building it.
8. **Careerjet** (optional). https://www.careerjet.com/partners/ : a partner (publisher) program. Its attribution and commercial
   terms were not checked here; read them before signing up.
