# Job sources

Where UAply's jobs come from, what each source allows, and the free keys the owner can request. Checked against the code on
October 23, 2026 (origin/sandbox 666c81e). This is not legal advice: have the lawyer confirm before launch. The code is `jobs_api.py`
(`SOURCES`, `VIA`, `TTL`, `KEEP`) and the list of boards and careers sites is `job-boards.json`.

Every source is **off** unless its kind is listed in `UAPLY_FEEDS` (Render, Environment) or in `"feeds"` in `UAPLY_CONFIG_JSON`, for
example `UAPLY_FEEDS=greenhouse,lever,ashby,workable,smartrecruiters,careerpage,usajobs,careeronestop,jobicy,muse,simplify,himalayas,remoteok`.
Jobs from every source are **link-out only**: swiping right opens the employer's (or the board's) own page. Nothing is emailed to
anyone, unless the employer is a partner or connected its own hiring system.

Rules for every source: postings older than 60 days are hidden (USAJOBS and partner jobs exempt, and part-time and temporary roles on
an employer's board or careers site, which stay open for months), the same job from two feeds is shown once (the employer's own board
wins), every job carries `jobType` (full-time, part-time, internship, co-op, contract or temporary) and `postedDays`, and each employer
board keeps 14 roles (internships, co-ops and part-time roles first, up to 10 of them) plus up to 10 more in Pennsylvania, New Jersey
or Delaware. A public list is kept whole up to a limit instead: the City of Philadelphia and the Simplify lists 120 each,
CareerOneStop 100 per search. USAJOBS keeps every job each search lists (every page, 500 a page, up to 10,000 per search).

## Coverage

* **Anywhere in the US:** 4,487 employer sources (4,485 read on live): 2,254 Greenhouse, 1,409 Ashby, 230 Lever, 184 SmartRecruiters and
  98 Workable boards, plus 1 Workday job search and 1 Rippling board read only when switched on (live's `UAPLY_FEEDS` in render.yaml
  does not list them; the same holds for the 68 Recruitee boards, which are not counted here)
  (80 of them hand-picked in `SOURCES`, the rest from `job-boards.json`) and 310 employers' own careers sites (298 on Workday, 12 on
  iCIMS); remote jobs from Jobicy (15 industries), Himalayas (all, internships, part-time) and Remote OK; internships and co-ops from
  the Simplify / Pitt CSC lists. A remote job open to the US is shown to everyone; the distance filter never hides it (except "remote
  only").
* **Pennsylvania, New Jersey, Delaware:** USAJOBS around Philadelphia (50 mi), Wilmington DE (40), Trenton NJ (40), Newark NJ (40) and
  Camden NJ (25), each also for Pathways (students and recent graduates) and part-time schedules; CareerOneStop (the state job banks'
  jobs) around the same five cities (once its key arrives); the City of Philadelphia; employers with PA, NJ and DE offices, among them
  the careers sites of ChristianaCare, DuPont, Chemours, WSFS, Sallie Mae, Campbell's, Jefferson Health and Vanguard.

## Adding employer boards in bulk

`tools/find-boards.py` finds employers' public boards on Greenhouse, Lever, Ashby, SmartRecruiters and Workable: from company names or
domains (`--names tools/data/board-seeds.txt`, slugs tried on every system) and from every board the Simplify / Pitt CSC lists link to
(`--simplify`). It checks each board live, counts its postings, US postings and PA / NJ / DE postings, and writes a review file
(`tools/data/board-candidates.json`). Boards with at least 5 US postings that pass review go in `job-boards.json` (kind, token, name and
the counts on the day they were checked); the app reads that file at start, after the hand-picked boards in `jobs_api.SOURCES`, and reads
each of those boards every 2 hours (spread out). The owner page `/api/feed-health` (owner password) lists every source with its jobs,
successes and failures; a source that fails 3 refreshes in a row is switched off for a day and then tried again by itself.

How the reading scales to hundreds of boards: 8 reader threads (not one per board), and 20 more for careers sites (they mostly wait out crawl delays, on places of their own), boards queued round-robin across hiring systems; a Greenhouse board's list is read without
descriptions (about an eighth of the size) and only the postings that will be kept get their description read, once, and again only
when the posting changes; employer SmartRecruiters boards read at most 24 descriptions a day, and an unchanged posting (or careers-site page) is made into the same job again from the packed copy, without holding its description; boards are read as they arrive (never
whole); the list sent to the app is written straight into gzip and only the compressed copy is kept; past 300 MB of memory no new
board read starts. On a fresh start the first visitor is answered within about 8 seconds with what is ready, and the app asks again
until every board is in.

Discovery seeds (`tools/data/board-seeds-us.txt`): each state's large employers (hospital systems, universities, retailers, banks,
logistics, utilities) plus industry lists (dental groups, real estate, legal, medical groups, education, trades, manufacturing,
logistics, retail and hospitality, sports and recreation, nonprofits, accounting, media). Besides the five hiring systems the tool
looks for an iCIMS careers site (`careers-<name>.icims.com`) whose robots.txt allows its sitemap. Probes done in the last 30 days are
not repeated (`tools/data/board-probed.json`); Workable is asked at most one request every 1.5 seconds (it answers 429 sooner).

Workday careers sites (`--workday tools/data/workday-seeds.txt`, and every Workday link on the Simplify lists): a site's robots.txt
names its sitemap (`https://<tenant>.wd5.myworkdayjobs.com/<Site>/siteMap.xml`); two job pages must carry JobPosting data and show no
human check. Workday's JobPosting names a building as the place and marks every posting TELECOMMUTE, so the place is read from the
page's own address (`/job/Newark-DE/...`) or the first "City, ST" of the description, and a job is remote only when it says so. A
stopped run picks up where it was (`--resume`, saved every 300 probes).

Greenhouse / Lever / Ashby sweep (October 30, 2026): board tokens taken from Common Crawl (2026 crawls 39, 34 and 30; 2026-43 and
part of 2026-39 failed with 502/503/504) and the Wayback Machine (Ashby only; its Lever and Greenhouse queries timed out), minus the
boards already listed: 5,574 Greenhouse, 27 Lever and 6,223 Ashby tokens found. 1,278 Greenhouse and 20 Lever boards were probed live
(counted with the app's US rule, `jobs_api._us_ok`) before the sweep stopped at 400+ qualifying boards; the Ashby tokens are not probed
yet. 460 boards had 5+ US jobs; the top 150 by US jobs were added, minus three ARCO sub-boards whose jobs the parent `arco` board already carries (145 Greenhouse, 2 Lever: 11,171 US jobs, 1,792 in PA, NJ or DE),
so the employer sources went from 1,926 to 2,073. Left out: repeated-ad boards (one title posted per place many times, such as
BoxLunch, BlueSky Telepsych, EquipmentShare, Curaleaf, Apartment Life, Luna Physical Therapy), staffing (Axiom Talent Platform, Aya
Healthcare) and names already listed under another token.

Round 2 (October 30, 2026), stage 1: the 5,866 Ashby tokens and the 3,676 Greenhouse tokens left over were probed live, and the
round-1 boards not yet added were checked again, all with the same US rule. 2,516 boards qualified (5+ US jobs, not already
listed). Stage 1 adds 485 of the top 500 by US jobs: 334 Greenhouse, 146 Ashby and 5 Lever boards (29,547 US jobs, 1,441 in PA, NJ
or DE), so the employer sources went from 2,073 to 2,558. Left out: 54 employers that post one role at many sites (BoxLunch,
EquipmentShare, Centria Autism, Datavant, Cortica, Horace Mann agents), 29 repeated-ad boards (such as Svetness Personal
Training), 10 staffing or recruiting firms and talent pools, 4 internal or referral-only boards (Elastic, Coupang, SanMar, Lush),
3 boards that repeat an employer already listed (PFM, Pediatrics Plus, YipitData), a venture fund's portfolio board (Pear VC),
38 names already listed or too generic to tell apart, 38 Ashby tokens with spaces, and Bjak (a global remote board).
2,015 further qualifying boards wait for stage 2.

Round 2, stage 2 (October 30, 2026): the 2,015 qualifying boards left after stage 1 were checked against the live titles of every
listed board. Stage 2 adds 1,927 of them: 1,083 Greenhouse and 844 Ashby boards (20,150 US jobs, 453 in PA, NJ or DE), so the
employer sources went from 2,558 to 4,485. Left out: 39 boards that share more than a quarter of their titles with a board already
listed (Harry's brands such as Lume Deodorant and Flamingo, Artefact, The Orchard, Cleo's India board), 17 employers that post one role at many sites
(A Place for Mom, Interview Engineering, Brooklyn Health), 12 venture fund or accelerator boards (Broadway Ventures, Forum
Ventures, Montauk Capital), 5 internal or referral-only boards (Misfits Market, Sprout, Thoughtworks), 3 recruiting boards and
talent pools (Birgo, a dev talent network, an internship pool), 11 names already listed (SingleStore, Coursera, Charlie Health)
and Ashby's demo board.

## Where a job is

Each job carries `geo` ([lat, lng], two decimals) when its place names a US city, town, borough, CDP or township with its state
("Cherry Hill, NJ", "El Segundo, California, United States", "Abilene TX", "US-PA-Malvern"), a big city named alone ("San Francisco",
"New York City"), or a ZIP code. The points come from `us-places.tsv.gz` (about 44,000 places; `tools/make-us-places.py` builds it from
the US Census Bureau's 2024 Gazetteer place and county-subdivision files, public domain), read on first use and kept as one string with
an index. The app's "near you" order and distance filter use `geo` first and its own city list after; "where you live" now knows every
ZIP code's first three digits. On October 21, 2026 the app's own list placed 52% of on-site jobs; with `geo`, 92% (the server's point
88%, the app's list the rest). Careers sites read their
co-op and internship pages first, then their Pennsylvania, New Jersey and Delaware ones, as each page's own address says.

## Human checks on application pages

`tools/scan-human-checks.py <saved /api/jobs answer>` looks at a sample of each source's application pages (20 per source, every posting
of a smaller one; fewer where robots.txt asks for a crawl delay, as Lever's 1 second does, so the whole scan fits in 28 minutes): one
plain GET per page as `UAplyApplyCheck/1.0`, robots.txt (with `*` and `$`) and its crawl delay honoured on every page and redirect, at
most 3 attempts per page, a source whose pages fail 3 times stopped and marked unknown. It records reCAPTCHA, hCaptcha, Turnstile,
Arkose and other captchas the page loads or is set up with, and challenge pages (Cloudflare, DataDome, PerimeterX, Imperva, "verify you
are human"); Cloudflare's quiet bot tag is noted but is not a check. A check is never solved, bypassed or set off on purpose, and a
challenge page is not asked for again. Per source it writes `humanCheck` (none / sometimes / always / unknown), `formKind` (html-form,
js-app, redirect to another system, sign-in) and the sample date to `human-checks.json`; `--merge --skip-known` adds new sources later
without reading the old ones again, and a stopped scan picks up from its checkpoint. The server reads the file at start: each job
carries `route` ("Ready" when UAply sends the application itself, "Ready, one tap" where a check is likely, "Ready" otherwise). A
source the scan has not sampled yet is "Ready, one tap" when at least 80% of the sampled sources on its hiring system had a check (on
October 21: Greenhouse, Lever, Ashby, SmartRecruiters and Workable), else "Ready". `/api/feed-health` shows each source's result and the
totals. No job is removed because of a check.

## Registry

Risk: **Low** = a public body's or the source's own published API whose terms we follow; **Medium** = public data with no terms that
clearly cover a third party showing it; **High** = terms that forbid our use (not switched on).

| Source (kind) | What it is | Terms | Allowed use | Credit shown on the card | Refresh | Apply path | Job types | Risk |
|---|---|---|---|---|---|---|---|---|
| Greenhouse boards (`greenhouse`) | Employers' own public job boards | https://developers.greenhouse.io/job-board.html | A public, keyless API meant for careers pages; no terms for third-party readers | "via Acme on Greenhouse" | 30 min for a hand-picked board, 2 h (spread) for one from `job-boards.json`; the same for Lever, Ashby and Workable | Employer's posting | Custom "Employment Type" field, else title | **Medium**: public and read only, but no terms say an aggregator may show it; we link out and never copy applications |
| Lever boards (`lever`) | Employers' own public postings | https://github.com/lever/postings-api | Same as Greenhouse | "via Acme on Lever" | 30 min | Employer's posting | `categories.commitment` | **Medium**: same reason |
| Ashby boards (`ashby`) | Employers' own public job boards | https://developers.ashbyhq.com/docs/public-job-posting-api | Same as Greenhouse | "via Acme on Ashby" | 30 min | Employer's posting | `employmentType` | **Medium**: same reason |
| Workable (`workable`) | Employers' own public jobs feed | https://help.workable.com/hc/en-us/articles/115012771647 | Documented for custom careers pages | "via Acme on Workable" | 30 min | Employer's posting | `employment_type` | **Medium**: same reason |
| SmartRecruiters (`smartrecruiters`) | City of Philadelphia (whole list) and employer boards (Equinox, Red Bull) | https://developers.smartrecruiters.com/docs/posting-api | Public Posting API, no key | "via City of Philadelphia on SmartRecruiters" | 1 h (an employer board: at most 24 descriptions, each read again after a day or when re-released) | Employer's posting | `typeOfEmployment` | **Low** for the City (public body's own postings); **Medium** for employers |
| USAJOBS (`usajobs`) | Federal jobs around 5 tri-state cities, plus Pathways and part-time searches: 15 searches every 3 h = 120 requests a day | https://developer.usajobs.gov/general/terms-of-service | Public data, may be copied and republished, commercial use included | "via USAJOBS; apply on the official announcement" | 3 h | The announcement on usajobs.gov | Schedule (part-time), Pathways = internship, Temporary offering | **Low**: the government's own API; we credit it and link to the announcement |
| CareerOneStop (`careeronestop`) | The National Labor Exchange (the PA, NJ and DE state job banks' jobs) around 5 tri-state cities (all, internship, part-time) plus remote: 16 searches every 3 h = 128 requests a day, the last 7 days | License shown on https://www.careeronestop.org/Developers/WebAPI/registration.aspx ; API https://www.careeronestop.org/Developers/WebAPI/Jobs/list-jobs.aspx | Royalty-free for the purpose stated at registration; no altering the data; credit both the U.S. Department of Labor ETA and Minnesota DEED on every page that shows it; key kept secret; license lasts 36 months | "via CareerOneStop (U.S. Department of Labor ETA and Minnesota DEED)" | 3 h | The posting on the NLx (jobsyn.org) | Title words, "part-time" in the summary | **Low**: public, free, attribution only. Note: new Jobs API access now goes through the NLx Research Hub; requested Oct 27, 2026 (ticket NLX-87), on hold while the NLx changes systems (see the key list) |
| Jobicy (`jobicy`) | Remote jobs open to the US, 15 industries | https://jobicy.com/jobs-rss-feed | Free; credit Jobicy, link to the job on Jobicy, at most one sync pass an hour | "via Jobicy" | 1 h | The job on Jobicy | `jobType` | **Low**: the source's own published conditions, followed |
| The Muse (`muse`) | Internship and entry-level jobs | https://www.themuse.com/developers/api/v2 | Public API; register an app (key) for production use | "via The Muse" | 30 min | The job on The Muse | The Internship level | **Medium** until the app is registered (key), then **Low** |
| Simplify and Pitt CSC lists (`simplify`) | GitHub lists of internships and co-ops, https://github.com/SimplifyJobs/Summer2027-Internships (README.md, README-Off-Season.md) | No license file, no reuse terms | Rows are facts (company, title, place, link); only rows linking to a Greenhouse, Lever or SmartRecruiters posting are used, each read from the employer's own board | "via Acme on Greenhouse, listed by Simplify and Pitt CSC" | 6 h (each posting checked daily) | Employer's own posting | Internship or co-op | **Medium**: no license; we credit the list and show only the employer's own data |
| Himalayas (`himalayas`) | Remote jobs open to the US: all, internships, part-time (3 pages each) | https://himalayas.app/api , https://himalayas.app/terms#api | Show on our own app only; link to the job on Himalayas; `applicationLink` unchanged; never pass jobs on to other boards, Google Jobs or LinkedIn; remove expired jobs | "via Himalayas" | 3 h | `applicationLink` | `employmentType` | **Low**: its published API terms, followed |
| Employers' careers sites (`careerpage`) | Employers whose own careers site publishes a sitemap of job pages with schema.org JobPosting data (iCIMS sites such as Hackensack Meridian Health, Piedmont, UnityPoint, OHSU, NYU Langone, Dental Care Alliance, Sonrava; Workday sites such as ChristianaCare), found with `tools/find-boards.py` and listed in `job-boards.json` with their sitemap | Each site's robots.txt (read first, its Disallow rules and Crawl-delay followed; a site whose robots.txt cannot be read is not read) | JobPosting data is published for search engines to show; UAply reads at most 40 job pages per site every 6 hours (14 on a site's first read; a page again only when its lastmod changes, or after 2 days when the sitemap gives none), one request at a time with at least 2 seconds between them, only pages on the sitemap's own host or another host of the same domain (an iCIMS site moves its pages to externalcareers-), only over public https (every redirect checked again), never a page behind a login or a human check (that page is left alone until it changes) | "via Acme careers site" | 6 h | The employer's own job page (assisted hand-off) | `employmentType` | **Medium**: public structured data meant to be shown by job search engines, read politely as robots.txt allows; each employer's site terms are not individually reviewed |
| Remote OK (`remoteok`) | Remote jobs | The notice in https://remoteok.com/api | Link back to the job on Remote OK (followed link) and name Remote OK; no logo | "via Remote OK" | 6 h | The job on Remote OK | Title words | **Low**: its published conditions, followed |
| Remotive (`remotive`) | Remote jobs | https://remotive.com/api-documentation | Forbids using listings to collect sign-ups or emails, which UAply does | n/a | n/a | n/a | n/a | **High**: **do not switch on** without written permission |
| Partner employers | Employers who post on UAply | UAply's own employer terms | The employer gave the posting and agreed to receive applications | "Posted on UAply by ..." | live | Sent to the employer | The employer's own pick | **Low** |

**Checked and not added:** the State of Delaware, Camden County, the cities of Camden, Wilmington, Trenton and Newark, NJ Transit,
Cooper University Health Care, Incyte, Navient, Subaru of America and the universities (Rutgers, Princeton, UDel) are not on a public
board UAply reads (they use NEOGOV, PeopleAdmin, other systems or their own sites). ChristianaCare, Chemours, WSFS, Sallie Mae and
Campbell's, on that list until October 21, are now read as Workday careers sites. Anduril's board is read without descriptions (an
eighth of its 44 MB), so it is under the 40 MB cap. Arbeitnow lists European jobs only; Reed is UK only. The Muse's API has no
internship filter beyond its levels.

**Never used, never scraped:** LinkedIn, Indeed, ZipRecruiter, Handshake and Glassdoor (closed or partner-only programs whose terms
forbid copying listings). Google for Jobs is a search feature, not an API.

## How careers sites and apply links are read

Every request to an employer's careers site (its robots.txt, its sitemap, each job page) and every check of a job's apply link goes
through a public-only opener: the host's name is looked up once and only public addresses are used (never private, loopback,
link-local such as the 169.254.169.254 metadata address, shared 100.64/10, reserved or multicast), the connection goes to those very
addresses, and every redirect is checked against the same rules before it is followed (careers sites: https only; the apply-link check:
http or https on the scheme's own port). The board APIs (Greenhouse, Lever, Ashby, SmartRecruiters, Workable, USAJOBS, CareerOneStop
and the lists) are read at their own fixed addresses. Feed text has its entities decoded before its tags are taken out.

## Coming after launch (round 4, not in this release)

On branch `feeds-round4` (f04a000), merged after launch: 21 more sources (law: DLA Piper, Skadden, Hogan Lovells, Jackson Lewis,
Ballard Spahr, Lewis Brisbois, Thomson Reuters, Consilio; dental: Dental365, Spark Dental Management; real estate: Bozzuto, CoStar,
Avison Young, Federal Realty, VTS, HomeLight, SmartRent, UWM, Sotheby's; HNTB and Rent the Runway); careers sites read 24 at a time
and boards 7 at a time; company names as plain text of at most 120 characters; CareerOneStop errors named plainly (a refused key, an
unknown user id, a rate limit) and `tools/check-careeronestop.py` to check the key once it arrives; no race on the Greenhouse caches.

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
   nlxresearchhub@naswa.org . **Status (Oct 30, 2026):** requested on Oct 27, 2026 from uaplytechnologies@gmail.com (NLx ticket
   NLX-87, "Job Feed syndicated partner request"); the NLx replied that it has paused Job Feed requests while it moves to a new
   access system, so the request is on hold on their side. The CareerOneStop key email was drafted but never sent; there is no need
   to send it, since Jobs API access goes through the NLx. When the user ID and token arrive: Render, Environment, `UAPLY_COS_USER_ID` and `UAPLY_COS_TOKEN`, and add
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

## What the app is sent (October 23, 2026)

- `GET /api/jobs`: the whole list, gzip-compressed when the browser takes it (every browser does), compact JSON. A feed job leaves out
  what no card shows (`jobs_api.LIST_DROP`): its description, the credit line (`credit`), the update date and its age (`updated`,
  `updatedDays`), the USAJOBS announcement; of `ats` only `kind` stays. The server reads all of these from its own copy anyway.
  Measured on 14,326 jobs: 13.3 MB of JSON (1.43 MB compressed) before, 10.9 MB (1.29 MB) after.
- `GET /api/jobs?size=200&page=1`: the same list a page at a time, in the same order: `{"jobs", "total", "page", "size", "next",
  "sources", "merged", "aged_out", "pending", "fetched_at"}`. `?cursor=<next>` gives the page after (it carries on where the last one
  ended even if the list was rebuilt; then `"changed": true`, and the app tells jobs apart by id). `?type=internship,coop` keeps the
  deck's stacks (`job`, `parttime`, `internship`, `coop`), and `total` counts only those. Size 200 by default, at most 1,000. A first
  page of 200 is about 230 KB of JSON, 36 KB compressed.
- `GET /api/jobs/<id>`: one job with every field (`{"job": ...}`), or 404 `{"code": "gone"}`. Behind the sign-in gate like the list.

## Recruitee careers sites (October 23, 2026)

- Kind `recruitee` (jobs_api `_recruitee_raw`): each company's careers site answers `GET https://{company}.recruitee.com/api/offers/`
  with no key (its robots.txt disallows only `/v/`). One request per board, every 2 hours like the other boards in job-boards.json.
- Pacing: every `*.recruitee.com` subdomain is treated as one service (jobs_api `HOST_FAMILY`): at most 2 requests at once over all
  its boards, request starts 1 second apart. Recruitee boards are read by 2 reader threads of their own (`_rc_readers`, `_rc_slots`),
  not the 8 shared board places, so the other boards never wait behind them on a fresh start.
- A job keeps Recruitee's offer number as its id (`_jid("recruitee", id)`, stable), `ats = {"kind": "recruitee", "board": company,
  "id": slug}`, `url` (the posting) and `applyUrl` (its form, `/o/{slug}/c/new`; left out of the list form, in `GET /api/jobs/<id>`).
  An application goes to `POST https://{company}.recruitee.com/api/offers/{slug}/candidates` (no employer key, `ats_api.recruitee_submit`):
  while the owner's switch `"recruitee_submit"` is on (the default; `uaply_api.recruitee_on`) a Recruitee job is an instant apply (the
  card says Ready); with it set to false the job is a hand-off like every other feed job.
- Sign-up test mode (`UAPLY_SIGNUP_TEST=1`, mail off) never posts to a real employer: a Recruitee application is recorded as simulated
  unless it goes to a stand-in on this computer (`UAPLY_ATS_BASE_RECRUITEE` at 127.0.0.1 or localhost); delivery mode "test"
  simulates every one.
- Offers outside the US are left out (one open in several places is placed in its first US one); pay is shown only in US dollars
  (hourly or yearly ranges); drafts and offers with an unsafe slug are skipped.
- 68 boards with at least 5 US jobs are in job-boards.json (found with a web search limited to recruitee.com and a Common Crawl
  sweep, checked with `tools/find-recruitee.py`): 1,327 US jobs when last checked (October 23 and 30), 66 of them in PA, NJ or DE.
  A second sweep (October 30: Common Crawl 2026 crawls plus the Wayback Machine, 751 more sites probed) added 10 boards (129 US jobs).
  Sweep 3 (October 30) probed the remaining 1,784 Common Crawl tokens: 3 new boards (Aetherflux, Certus, Miaplaza, 16 US jobs); the
  other hits were alternate tokens of boards already listed, or EWOR (243 fellowship postings, held for a decision).
  Recruitee is mostly European, and its US health care, dental, legal and hospitality sites are small (most have under 5 openings),
  so few of those passed the 5-job rule. Four boards found earlier were dropped for having under 5 US jobs: dillinggroup,
  anywhereworks, goodwall and hostaway.
- Recruitee US ceiling (measured October 30, 2026): 859 Recruitee sites found in Common Crawl, 787 of them live, with about 10,000
  offers, 582 of them in the US (about 5.7%). The sweep only covered sites that were not yet in this file, so that 582 splits into
  359 US jobs on the 17 boards added below (now part of the 1,327 above) and 128 on boards too small to list. The sweep found 19 sites
  with 5+ US jobs; two of them (chg, gainpro) redirect to boards already listed or kept (chgcareers, gain), so 17 distinct new boards
  were added (vertigis came from a follow-up probe).
  Another 59 boards with 1 to 4 US jobs (128 jobs) are left out by the 5-US rule. Recruitee alone cannot reach 50k US jobs.
- Switched on with the others: `"feeds"` must list `"recruitee"` (uaply-config.json or UAPLY_CONFIG_JSON / UAPLY_FEEDS).

## Workday, Rippling, Breezy HR and Teamtailor careers sites (October 31, 2026)

Four more board kinds read each careers site's own public list, no key. Each is read with the other job-boards.json boards (every
2 hours, the shared feed readers), after the site's robots.txt allows it, with the usual feed timeout and size limit. Their terms
have not been reviewed yet, so each kind stays off unless the owner lists it in `"feeds"` / `UAPLY_FEEDS`.

- Workday (`_workday`): `POST https://{company}.wd{n}.myworkdayjobs.com/wday/cxs/{company}/{site}/jobs` with the fixed body
  `{"limit": 20, "offset": 0, "searchText": ""}`, 20 a page, at most 200 postings a refresh. Token `{company}.wd{n}/{site}` (checked by
  `WORKDAY_TOKEN_RE`). Mapped: title, place (`locationsText`, or the first place in the posting's address when it says "3 Locations"),
  posted date ("Posted 3 Days Ago"), the posting's own page. No description in the list. A US place ("US, CA, Santa Clara" in the list
  or "US-CA-Santa-Clara" in the address) is stored as "Santa Clara, CA" so the map and distance filter can place it. Example row:
  NVIDIA (2,000 total, 1,910 US). Workday's reported total appears to stop at 2,000: NVIDIA's first page says 2,000 and its second
  page says 0, so the total is a ceiling, not a count. We read at most 200 postings (10 searches, and no more than 120 seconds across
  them, `WORKDAY_DEADLINE`) in Workday's own order; when the first page gives no total, searches go on until a short page. Like every
  board, each Workday site then keeps at most `PER_SOURCE` = 14 roles (internships, co-ops and part-time roles first, up to 10) plus up
  to 10 in Pennsylvania, New Jersey or Delaware (`jobs_api.py`, `PER_SOURCE` to `LOCAL_PER_SOURCE`). The internships-first and
  PA/NJ/DE-first picks only see those first 200 postings, so a big site's later internships or local roles are not found.
  Risk: terms not yet reviewed, so off unless listed in UAPLY_FEEDS.
- Rippling (`_rippling`): `GET https://api.rippling.com/platform/api/ats/v1/board/{slug}/jobs`. One row per place a job is open in:
  rows are merged by `uuid` and keep every place. Mapped: name, department, place (`workLocation.label`, a bare state code read as
  that US state), job page. Example row: Rippling (373 jobs, 199 in the US). Risk: terms not yet reviewed, so off unless listed in
  UAPLY_FEEDS.
- Breezy HR (`_breezy`): `GET https://{company}.breezy.hr/json`. Mapped: name, place (first US location; city, state, remote flag),
  department, type (internship), salary text, published date, job page. No example row yet: the `breezy` site has 3 US jobs, under
  the 5-US rule. Risk: terms not yet reviewed, so off unless listed in UAPLY_FEEDS.
- Teamtailor (`_teamtailor`): `GET https://{company}.teamtailor.com/jobs.rss`. Mapped: title, link, guid, `tt:locations` (first US
  one), `tt:department`, `remoteStatus` (fully remote, hybrid), pubDate, description. A feed that declares a DOCTYPE or ENTITY is
  refused before parsing. No example row yet: the `career` site has 2 US jobs, under the 5-US rule. Risk: terms not yet reviewed, so
  off unless listed in UAPLY_FEEDS.
- Pacing: every `*.myworkdayjobs.com`, `*.breezy.hr` and `*.teamtailor.com` subdomain is one service (`HOST_FAMILY`: 2 at once,
  request starts 0.5 seconds apart). A Breezy or Teamtailor token is one subdomain label (`SUBDOMAIN_RE`).
- Safety: every request of the four kinds goes through the careers-site opener (`_cp_open`: public addresses only, and a redirect is
  followed only to a public https address), and robots.txt is checked for the User-Agent the list is asked for with (`FEED_UA`,
  "UAply-jobs").
