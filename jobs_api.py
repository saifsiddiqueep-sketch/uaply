"""Job ingestion back end for the sandbox and dev instances (not used by prod).

How real job apps get postings, and what this does:
  * Employers publish openings in an applicant tracking system (ATS). Greenhouse, Lever and Ashby expose public,
    read-only job-board APIs so third parties can list those openings. Aggregators keep a list of company board
    names, poll those endpoints, normalize the fields, de-duplicate, and link applicants back to the employer.
  * Indeed and ZipRecruiter do not offer an open API for reading their listings (partner programs only, and Indeed's
    terms forbid keeping copies), so they are NOT used here.
  * Remotive publishes a free remote-jobs feed on the condition that listings link back to Remotive and name it as
    the source, and that it is polled at most ~4 times a day. Both are respected below.

LEGAL STATUS OF EACH SOURCE (checked October 2026; this is not legal advice, have a lawyer confirm before launch):
  * Partner employers (uaply-partners.json): AUTHORIZED. The employer gave us the posting and agreed to receive
    applications. This is the only source whose applications UAply sends to a person.
  * Remotive: its terms call using listings "to collect signups or email addresses" a breach, and UAply collects
    emails. Never enabled by default; do not enable without written permission.
  * Jobicy: must credit Jobicy and send applicants to the original job URL, so it is LINK-OUT ONLY.
  * The Muse: terms not found. Unverified; do not enable until verified in writing.
  * Greenhouse, Lever, Ashby, Workable public boards: meant for employers' careers pages; no terms found that cover third-party
    aggregation. Unverified, LINK-OUT ONLY.
  * USAJOBS (the federal government's own API, read October 16, 2026): its terms let public data be copied, stored and
    republished, commercial use included, without OPM approval; credit and a link to the official announcement are asked
    for, and nobody may be told an application was sent when it was not. LINK-OUT ONLY, credited "via USAJOBS". Needs a
    free key (feed_keys.usajobs); without one the source is skipped with the status "no key".
  * SmartRecruiters public Posting API (City of Philadelphia): public postings of a public body, no key, no published
    terms for readers. LINK-OUT ONLY, credited "City of Philadelphia on SmartRecruiters".
  * Simplify / Pitt CSC internship lists (GitHub), Himalayas, Remote OK: added October 21, 2026, LINK-OUT ONLY and credited on the card;
    their terms, and why Remotive, Adzuna and others are not used, are in docs/job-sources.md.
  * CareerOneStop (U.S. Department of Labor; National Labor Exchange): royalty-free license; credit both DOL ETA and Minnesota DEED
    where its data shows, do not alter the data, keep the key secret. LINK-OUT ONLY. Off ("no key") until UAPLY_COS_USER_ID and
    UAPLY_COS_TOKEN are set.
  Third-party feeds are OFF unless the owner lists them under "feeds" in uaply-config.json. Jobs from a feed are never
  emailed to anyone (the recruiter address is dropped); swiping right only opens the employer's own page.

get_jobs() returns {"fetched_at", "sources", "jobs", "merged", "aged_out"} where each job already matches the shape the app expects
(with postedDays, and updatedDays where the feed gives an update date). Postings older than MAX_AGE_DAYS are left out, and the same
job from two feeds is shown once ("merged" counts the copies left out).
"""
import codecs
import datetime
import hashlib
import html
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import ats_api

ROOT = os.path.dirname(os.path.abspath(__file__))
UA = "UAplyDev/0.1 (local prototype)"
DEFAULT_TTL = 30 * 60
TTL = {"remotive": 6 * 3600,          # Remotive allows roughly 4 requests a day
       "jobicy": 3600,                # Jobicy asks for at most one sync pass an hour
       "usajobs": 3 * 3600,           # federal postings change slowly; two searches every three hours
       "smartrecruiters": 3600,       # the City's list once an hour (each posting's description is read far less often, see SR_DESC_TTL)
       "simplify": 6 * 3600,          # the Simplify / Pitt CSC lists change daily; each listed posting is checked on its own board at most once a day
       "himalayas": 3 * 3600,         # no key: one public allowance shared with every caller, so a few pages every three hours
       "remoteok": 6 * 3600,          # one request for the whole list
       "careeronestop": 3 * 3600}     # 16 searches every three hours
PER_SOURCE = 14
STUDENT_PER_SOURCE = 10          # internships, co-ops and part-time roles are kept first so the student tabs are not empty
OTHER_PER_SOURCE = 6
# A public body's own list (the City, the federal government) is local and is kept whole up to this many postings, student roles first,
# instead of the 14 an employer board gets. SmartRecruiters is also read no further than this (so at most this many description reads).
KEEP = {"usajobs": 120, "smartrecruiters": 120, "simplify": 120, "careeronestop": 100}   # CareerOneStop: one page of 100 per search, kept whole
SR_DESC_TTL = 24 * 3600          # a SmartRecruiters posting's description is read once, then again only after a day or when the posting is re-released
# UAply launches in the Philadelphia region: a board may keep this many Pennsylvania, New Jersey or Delaware roles on top of its 14, so a
# national employer's tri-state openings are not cut just because they come after its first 14 postings. Matched on the posting's own
# location (case matters: ", PA", ", NJ", ", DE"; a German ", DE" never gets this far, see _us_ok).
LOCAL_PER_SOURCE = 10
LOCAL_RE = re.compile(r"\bPennsylvania\b|, PA\b|\bPhiladelphia\b|\bPittsburgh\b|\bKing of Prussia\b|\bConshohocken\b|\bAllentown\b|\bHarrisburg\b|"
                      r"\bNew Jersey\b|, NJ\b|\bTrenton\b|\bCamden\b|\bCherry Hill\b|\bJersey City\b|\bHoboken\b|\bPrinceton\b|\bNewark, (?:NJ|New Jersey)\b|"
                      r"\bDelaware\b|, DE\b|\bWilmington, (?:DE|Delaware)\b|[a-z] (?:PA|NJ|DE)$")
# A posting whose newest date (posted, or updated where the feed gives one) is older than this is not shown: it is most likely filled
# or forgotten. A posting with no date at all is kept (nothing says it is old). Partner employers' own postings are never aged out here:
# the employer opens and closes those itself.
MAX_AGE_DAYS = 60
DAY_MS = 86400 * 1000
# USAJOBS' search returns only announcements that are open now, each with its own closing date, so a long-open federal announcement
# (some run for months) is not stale and is not aged out.
AGE_EXEMPT = ("usajobs",)
# An hourly part-time or seasonal posting on the employer's own board is usually evergreen: one posting per store or studio, open all
# year (Insomnia Cookies: 852 of 1,063 part-time postings older than 60 days; solidcore coaches: years). Still listed on the employer's
# own board means still hiring, so those are not aged out there. An aggregator's copy still is.
EVERGREEN_KINDS = ("greenhouse", "lever", "ashby", "workable", "smartrecruiters")
EVERGREEN_TYPES = ("part-time", "temporary")

# (kind, board token, display name). Boards are the employer's own public careers feed.
SOURCES = [
    # The local public lists first: on a fresh start the boards are read FEED_PARALLEL at a time in this order, and with 60 sources the
    # City (120 description reads) came last and missed the first visitor's wait. They share no jobs with the boards below.
    ("smartrecruiters", "CityofPhiladelphia", "City of Philadelphia"),   # the City's own public SmartRecruiters postings (no key)
    # USAJOBS (needs a key: feed_keys.usajobs or UAPLY_USAJOBS_KEY): every federal posting around five tri-state cities, then the same areas
    # for the Students and Recent graduates hiring paths (Pathways) and for part-time schedules (both were cut by the 120 cap of a full search).
    # 15 searches, each every 3 hours = 120 requests a day (see USAJOBS_AREAS). The areas overlap on purpose; a posting is shown once.
] + [("usajobs", area + suffix, "USAJOBS") for suffix in ("", "-students", "-parttime") for area in ("philadelphia", "wilmington", "trenton", "newark", "camden")] + [
    ("greenhouse", "discord", "Discord"),
    ("greenhouse", "dropbox", "Dropbox"),
    ("greenhouse", "duolingo", "Duolingo"),
    ("greenhouse", "squarespace", "Squarespace"),
    ("ashby", "webflow", "Webflow"),              # moved from Greenhouse (404 there since October 2026) to Ashby
    # employers whose own public boards carried internships when checked (October 2026)
    ("greenhouse", "waymo", "Waymo"),
    ("greenhouse", "coinbase", "Coinbase"),
    ("greenhouse", "robinhood", "Robinhood"),
    ("greenhouse", "lyft", "Lyft"),
    ("greenhouse", "stripe", "Stripe"),
    ("greenhouse", "databricks", "Databricks"),
    ("greenhouse", "pinterest", "Pinterest"),
    ("greenhouse", "figma", "Figma"),
    ("greenhouse", "datadog", "Datadog"),
    ("greenhouse", "verkada", "Verkada"),
    ("greenhouse", "samsara", "Samsara"),
    ("greenhouse", "roblox", "Roblox"),
    ("greenhouse", "block", "Block"),
    ("greenhouse", "cloudflare", "Cloudflare"),
    ("greenhouse", "scaleai", "Scale AI"),
    ("greenhouse", "affirm", "Affirm"),
    ("greenhouse", "imc", "IMC Trading"),
    ("lever", "spotify", "Spotify"),
    ("workable", "huggingface", "Hugging Face"),  # Workable's public jobs feed (no key); most roles are remote, some US-based
    ("ashby", "linear", "Linear"),
    # Employers with Pennsylvania openings (checked October 20, 2026: total postings / of them in PA on the public board)
    ("lever", "gopuff", "Gopuff"),                # Philadelphia HQ: 810 / 44
    ("greenhouse", "perpay", "Perpay"),           # Philadelphia HQ: 22 / 22
    ("greenhouse", "motional", "Motional"),       # Pittsburgh office: 81 / 45
    ("greenhouse", "vynamic", "Vynamic"),         # Philadelphia HQ: 17 / 4
    ("greenhouse", "carvana", "Carvana"),         # 1,719 / 30 (inspection centers, customer advocates)
    ("greenhouse", "shipmonk", "ShipMonk"),       # 74 / 22 (Lehigh Valley warehouses)
    ("greenhouse", "doordashusa", "DoorDash"),    # 452 / 10
    ("greenhouse", "toast", "Toast"),             # 310 / 9
    ("greenhouse", "mongodb", "MongoDB"),         # 395 / 8
    ("greenhouse", "mejuri", "Mejuri"),           # 179 / 8 (stores)
    ("greenhouse", "charliehealth", "Charlie Health"),   # 258 / 6 (clinical)
    ("greenhouse", "strivehealth", "Strive Health"),     # 60 / 4 (clinical)
    # Large national boards with many US roles across functions: healthcare, retail, restaurants, operations, finance, support
    ("greenhouse", "oscar", "Oscar Health"),      # 248, all US
    ("greenhouse", "sweetgreen", "Sweetgreen"),   # 65
    ("greenhouse", "glossier", "Glossier"),       # 22 (stores)
    ("greenhouse", "twochairs", "Two Chairs"),    # 34 (therapists)
    ("greenhouse", "elationhealth", "Elation Health"),   # 18
    ("greenhouse", "axon", "Axon"),               # 486
    ("greenhouse", "instacart", "Instacart"),     # 123
    ("greenhouse", "airbnb", "Airbnb"),           # 182
    ("greenhouse", "chime", "Chime"),             # 71
    ("greenhouse", "brex", "Brex"),               # 261
    ("greenhouse", "point72", "Point72"),         # 215
    ("greenhouse", "gusto", "Gusto"),             # 101
    ("greenhouse", "twilio", "Twilio"),           # 133
    ("greenhouse", "reddit", "Reddit"),           # 153
    ("greenhouse", "faire", "Faire"),             # 78
    ("greenhouse", "ziprecruiter", "ZipRecruiter"),   # 43
    ("greenhouse", "wonderschool", "Wonderschool"),   # 39 (child care)
    ("lever", "zoox", "Zoox"),                    # 239, all US
    ("ashby", "ramp", "Ramp"),                    # 168, all US
    # Employers with New Jersey and Delaware openings (checked October 21, 2026: total postings / of them in NJ or DE)
    ("greenhouse", "crossriverbank", "Cross River Bank"),   # Fort Lee NJ: 36 / 28
    ("greenhouse", "legendcareers", "Legend Biotech"),      # Somerset NJ: 79 / 67
    ("workable", "thorlabs", "Thorlabs"),                   # Newton NJ: 84 / 47 (manufacturing)
    ("greenhouse", "lgelectronics", "LG Electronics"),      # Englewood Cliffs NJ: 115 / 23
    ("greenhouse", "genscript", "GenScript"),               # Piscataway NJ: 75 / 23 (labs)
    ("workable", "ascendis-pharma", "Ascendis Pharma"),     # Princeton NJ: 67 / 14
    ("greenhouse", "nice", "NICE"),                         # Hoboken NJ: 184 / 10
    ("lever", "BestEgg", "Best Egg"),                       # Wilmington DE: 10 / 9
    ("lever", "NJStateOfficeofInnovation", "New Jersey Office of Innovation"),   # the State's own public postings: 7 / 7
    ("greenhouse", "mettel", "MetTel"),                     # 20 / 6
    ("greenhouse", "fanduel", "FanDuel"),                   # Jersey City NJ: 83 / 4
    # National boards with many on-site roles in other states (clinics, warehouses, gyms, plants, launch sites)
    ("greenhouse", "mcmastercarr", "McMaster-Carr"),        # 30 (Robbinsville NJ and warehouses across the US)
    ("greenhouse", "onemedical", "One Medical"),            # 396 clinics and offices (10 in NJ)
    ("greenhouse", "tia", "Tia"),                           # 32 clinics
    ("smartrecruiters", "Equinox", "Equinox"),              # 740 clubs (97 of the first 100 in the US)
    ("smartrecruiters", "RedBull", "Red Bull"),             # 1,239 (54 of the first 100 in the US: sales and field roles)
    ("greenhouse", "lucidmotors", "Lucid Motors"),          # 445 (plant and studios)
    ("greenhouse", "rocketlab", "Rocket Lab"),              # 581
    ("greenhouse", "relativity", "Relativity Space"),       # 382
    ("greenhouse", "spacex", "SpaceX"),                     # 2,779 (32 MB, read a posting at a time)
    ("greenhouse", "flexport", "Flexport"),                 # 204
    # Part-time roles students can take: bakery stores and fitness studios (checked October 21, 2026: total / in PA, NJ or DE)
    ("lever", "insomniacookies", "Insomnia Cookies"),       # Philadelphia HQ: 1,253 / 94 (16.8 MB, read a posting at a time)
    ("lever", "solidcore", "solidcore"),                    # 253 / 29
    ("remotive", "software-dev", "Remotive"),
    ("jobicy", "engineering", "Jobicy"),      # credit Jobicy and link to its canonical job URL
    ("jobicy", "marketing", "Jobicy"),
    ("jobicy", "data-science", "Jobicy"),
    # every other Jobicy industry with US-open remote jobs (October 21, 2026): one request each, inside Jobicy's one sync pass an hour
] + [("jobicy", slug, "Jobicy") for slug in ("supporting", "admin-support", "accounting-finance", "healthcare", "education", "hr", "management",
                                            "business", "design-multimedia", "copywriting", "project-management", "legal")] + [
    ("muse", "Internship", "The Muse"),       # The Muse public jobs API; links go to the posting on The Muse
    ("muse", "Entry Level", "The Muse"),
    # CareerOneStop (U.S. Department of Labor): the National Labor Exchange, which the PA, NJ and DE state job banks run on. Needs
    # UAPLY_COS_USER_ID and UAPLY_COS_TOKEN; "no key" until then. All jobs, internships and part-time jobs posted in the last 7 days
    # around five tri-state cities, plus remote jobs nationwide: 16 searches, each every 3 hours = 128 requests a day (see COS_SEARCHES).
] + [("careeronestop", t, "CareerOneStop") for t in ("philadelphia", "wilmington", "trenton", "newark", "camden",
                                                    "philadelphia-internship", "wilmington-internship", "trenton-internship", "newark-internship", "camden-internship",
                                                    "philadelphia-parttime", "wilmington-parttime", "trenton-parttime", "newark-parttime", "camden-parttime", "remote")] + [
    # Internship lists kept on GitHub by Simplify and Pitt CSC (SimplifyJobs/Summer2027-Internships, formerly Summer2026). Only rows whose
    # apply link is a Greenhouse, Lever or SmartRecruiters posting are used, and each is read from that employer's own board first: a row
    # whose posting is gone is dropped. Credited on the card. Last: about 240 checks on a fresh start, so they never hold up the boards.
    ("simplify", "README.md", "Simplify and Pitt CSC"),             # summer internships
    ("simplify", "README-Off-Season.md", "Simplify and Pitt CSC"),  # fall, winter and spring internships and co-ops
    # Remote-job boards whose free APIs allow display with a link back (terms read October 21, 2026; see docs/job-sources.md)
    ("himalayas", "US", "Himalayas"),         # link to the job on Himalayas, apply link unchanged, never passed on to other boards
    ("himalayas", "US-intern", "Himalayas"),  # the same, internships only (935 open to the US on October 21, 2026)
    ("himalayas", "US-parttime", "Himalayas"),   # the same, part-time only (1,952)
    ("remoteok", "all", "Remote OK"),         # link back to the job on Remote OK and name Remote OK as the source
]
VIA = {"greenhouse": "%s on Greenhouse", "lever": "%s on Lever", "ashby": "%s on Ashby", "smartrecruiters": "%s on SmartRecruiters", "workable": "%s on Workable",
       "jobicy": "Jobicy", "muse": "The Muse", "usajobs": "USAJOBS", "remotive": "Remotive",
       "himalayas": "Himalayas", "remoteok": "Remote OK",
       # the CareerOneStop license: every page showing its data credits both the U.S. Department of Labor (ETA) and Minnesota DEED
       "careeronestop": "CareerOneStop (U.S. Department of Labor ETA and Minnesota DEED)"}       # the short credit line each source's jobs carry (Simplify rows: see _normalize)
MULTI = ("jobicy", "muse", "usajobs", "simplify", "careeronestop", "himalayas")
HIMALAYAS_TYPES = {"intern": "Intern", "parttime": "Part Time"}       # the employment_type filter of Himalayas' search         # several feeds share one display name
# The two USAJOBS searches (documented at developer.usajobs.gov/api-reference/get-api-search; several values are joined with ';')
USAJOBS_AREAS = {"philadelphia": ("Philadelphia, Pennsylvania", "50"), "wilmington": ("Wilmington, Delaware", "40"),
                 "trenton": ("Trenton, New Jersey", "40"), "newark": ("Newark, New Jersey", "40"), "camden": ("Camden, New Jersey", "25")}
USAJOBS_QUERIES = {}
for _area, (_place_name, _radius) in USAJOBS_AREAS.items():
    _base = {"LocationName": _place_name, "Radius": _radius, "ResultsPerPage": "500", "Fields": "Full"}
    USAJOBS_QUERIES[_area] = dict(_base)
    USAJOBS_QUERIES[_area + "-students"] = dict(_base, HiringPath="student;graduates")
    USAJOBS_QUERIES[_area + "-parttime"] = dict(_base, PositionScheduleTypeCode="2")
USAJOBS_QUERIES["students"], USAJOBS_QUERIES["parttime"] = USAJOBS_QUERIES["philadelphia-students"], USAJOBS_QUERIES["philadelphia-parttime"]   # older names
# CareerOneStop searches: (keyword, place, radius in miles). Keyword "0" means every job around a city; a nationwide search needs a real keyword.
COS_PLACES = {"philadelphia": ("Philadelphia, PA", "50"), "wilmington": ("Wilmington, DE", "40"), "trenton": ("Trenton, NJ", "40"),
              "newark": ("Newark, NJ", "40"), "camden": ("Camden, NJ", "25")}
COS_SEARCHES = {"remote": ("remote", "US", "0")}
for _area, (_place_name, _radius) in COS_PLACES.items():
    COS_SEARCHES[_area] = ("0", _place_name, _radius)
    COS_SEARCHES[_area + "-internship"] = ("internship", _place_name, _radius)
    COS_SEARCHES[_area + "-parttime"] = ("part time", _place_name, _radius)
COS_DAYS, COS_PAGE = "7", "100"
COS_ID_RE = re.compile(r"^[A-Za-z0-9_-]{3,64}$")
COS_TOKEN_RE = re.compile(r"^[A-Za-z0-9+/=_.-]{16,600}$")
USAJOBS_EMAIL = "uaplytechnologies@gmail.com"   # USAJOBS wants the email the key was requested with as the User-Agent (feed_keys.usajobs_email, else owner_copy, else this)

SKILLS = [
    ("JavaScript", r"javascript|\bjs\b"), ("TypeScript", r"typescript"), ("React", r"\breact(?:\.js|js)?\b"),
    ("Node", r"\bnode(?:\.js|js)?\b"), ("Python", r"\bpython\b"), ("Java", r"\bjava\b"), ("SQL", r"\bsql\b"),
    ("PostgreSQL", r"postgres(?:ql)?"), ("AWS", r"\baws\b|amazon web services"), ("Docker", r"\bdocker\b"),
    ("Kubernetes", r"kubernetes|\bk8s\b"), ("Terraform", r"terraform"), ("Figma", r"\bfigma\b"),
    ("Excel", r"\bexcel\b"), ("Tableau", r"\btableau\b"), ("Django", r"\bdjango\b"), ("CSS", r"\bcss\b"),
    ("HTML", r"\bhtml\b"), ("Testing", r"\btesting\b|unit tests?|test automation"), ("SEO", r"\bseo\b"),
    ("Copywriting", r"copywrit"), ("Analytics", r"\banalytics\b"), ("Hiring", r"recruit(?:ing|er|ment)\b"),
    ("User research", r"user research"), ("Prototyping", r"prototyp"), ("Design systems", r"design systems?"),
    ("Roadmapping", r"roadmap"), ("Budgeting", r"\bbudget"), ("PyTorch", r"pytorch"),
]
SKILL_RES = [(n, re.compile(p, re.I)) for n, p in SKILLS]
# "recruiting" appears in nearly every company's boilerplate (equal-opportunity text, privacy notices), so "Hiring" counts as a skill only for people roles
TITLE_GATED = {"Hiring": re.compile(r"recruit|talent|people|\bhr\b|human resources|staffing|sourcer|hiring", re.I)}
REMOTE_WORD = re.compile(r"^\W*remote\b(?:\s*[-–—:,/]\s*|\s*\()?", re.I)


def _place(loc, mode):
    """The place shown next to a job's work style. A remote job whose location already begins with "Remote" would read
    "Remote - USA  Remote" on the card, so that repeated word is dropped ("USA"; a bare "Remote" becomes "United States",
    which is what the US-only rule above guarantees)."""
    m = REMOTE_WORD.match(loc or "") if mode == "remote" else None
    if m:                                                    # only a place that starts with "Remote" is changed; anything else is left exactly as listed
        rest = (loc or "")[m.end():]
        if m.group(0).rstrip().endswith("("):               # "Remote (US)": the opening bracket went with the word, so its closing one goes too
            rest = rest.replace(")", "", 1)
        loc = rest.strip(" -–—:,/") or "United States"
    return loc or "Not listed"

STATES = "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split()
STATE_NAMES = ("Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|District of Columbia|Florida|Georgia|Hawaii|Idaho|Illinois|"
               "Indiana|Iowa|Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|"
               "New Hampshire|New Jersey|New Mexico|New York|North Carolina|North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|Rhode Island|South Carolina|"
               "South Dakota|Tennessee|Texas|Utah|Vermont|Virginia|Washington|West Virginia|Wisconsin|Wyoming")
US_CITIES = ("San Francisco|New York|Seattle|Austin|Boston|Chicago|Denver|Los Angeles|Atlanta|Portland|Philadelphia|Pittsburgh|Harrisburg|Allentown|"
             "King of Prussia|Conshohocken|Trenton|Princeton|Camden|Cherry Hill|Jersey City|Hoboken|Newark|Wilmington|Dover|Baltimore|"
             "Washington,? D\\.?C|Miami|Dallas|Houston|San Antonio|Phoenix|San Diego|San Jose|Las Vegas|Nashville|Charlotte|Raleigh|Orlando|Tampa|Detroit|"
             "Columbus|Cleveland|Cincinnati|Indianapolis|Minneapolis|St\\.? Louis|Kansas City|Salt Lake City|Sacramento|New Orleans|Silicon Valley|Bay Area")
# bare state names count too ("New Jersey", "Remote - Delaware"), except Georgia, which is also a country
US_STATE_WORDS = "|".join(n for n in STATE_NAMES.split("|") if n != "Georgia")
US_RE = re.compile(r"United States|\bUSA\b|\bU\.S\.|\bUS\b|, (?:%s)\b|, (?:%s)\b|\b(?:%s)\b|\b(?:%s)\b|[a-z] (?:%s)$" % (
    "|".join(STATES), STATE_NAMES, US_STATE_WORDS, US_CITIES, "|".join(STATES)))       # the last: "Abilene TX" (Lever boards write places without the comma)
# "City, Region, CC" with a country code at the end (SmartRecruiters, Workable): "Munich, BY, DE" is Germany, "Mumbai, MH, IN" India
FOREIGN_CODE_RE = re.compile(r",\s*[A-Z]{2,3}\s*,\s*(?!US\b|USA\b)[A-Z]{2}\s*$")
FOREIGN_RE = re.compile(r"Germany|Mumbai|Bangalore|Bengaluru|Hyderabad|Chennai|Pune|Delhi|Gurugram|Gurgaon|Noida|Kolkata|Tel Aviv|Bogot|Medell|Manila|Cebu|Lagos|Nairobi|Warsaw|Krak|Prague|Bucharest|Kyiv|Istanbul|Cairo|Riyadh|Shanghai|Beijing|Shenzhen|Taipei|Bangkok|Jakarta|Kuala Lumpur|Ho Chi Minh|Hanoi|Buenos Aires|São Paulo|Sao Paulo|Mexico City|Guadalajara|Monterrey|Madrid|Barcelona|Milan|Rome|Zurich|Zürich|Geneva|Vienna|Stockholm|Copenhagen|Oslo|Helsinki|Brussels|Edinburgh|Manchester|Munich|Frankfurt|Hamburg|Cologne|Stuttgart|Düsseldorf|Dusseldorf|United Kingdom|\bUK\b|\bIndia\b|Canada|Ireland|France|Spain|Brazil|(?<!New )Mexico|Poland|Netherlands|Japan|Australia|New Zealand|\bANZ\b|Singapore|EMEA|APAC|Europe|LATAM|Latin America|Berlin|London|Dublin|Toronto|Vancouver|Montreal|Sydney|Amsterdam|Lisbon|Paris|Tokyo|Seoul|Hong Kong|Israel|Dubai|Philippines|Argentina|Colombia|Chile|Vietnam|Indonesia|Malaysia|Thailand|South Africa|Nigeria|Kenya|Egypt|Turkey|Romania|Ukraine|Czech|Portugal|Italy|Sweden|Norway|Denmark|Finland|Switzerland|Belgium|Austria", re.I)
EXPLICIT_US = re.compile(r"United States|\bUSA\b|\bU\.S\.|\bUS\b")


def _us_ok(loc, remote):
    """True when a posting can be done from the United States. A location is split on ';' and '|' (one posting can list
    several cities): any part that names the US, or is a US place with no foreign word, passes. A bare 'Remote' passes only
    when no foreign place is named. (', CA' is California; 'Toronto, ON, CA' is Canada and must not pass on that.)"""
    parts = [p for p in re.split(r"[;|]", loc) if p.strip()] or [loc]
    for p in parts:
        if FOREIGN_CODE_RE.search(p):
            continue
        if EXPLICIT_US.search(p) or (US_RE.search(p) and not FOREIGN_RE.search(p)):
            return True
    return bool(remote and not FOREIGN_RE.search(loc))
SAL_RE = re.compile(r"\$\s?(\d{2,3}(?:,\d{3})+|\d{2,3}\s?[kK])\s*(?:-|–|—|to)\s*\$?\s*(\d{2,3}(?:,\d{3})+|\d{2,3}\s?[kK])")
YRS_RE = re.compile(r"(\d{1,2})\+?\s*(?:or more\s*)?(?:years|yrs)", re.I)

_cache = {}
_lock = threading.Lock()
_disk = {"loaded": False, "dirty": False, "filled": False}   # filled: a saved list was loaded, or the first fill of an empty disk is done
_load_lock = threading.Lock()
hide_errors = False                # serve.py sets this on a hosted server: the public job list then says "unavailable right now" instead of a raw network error
DISK_MAX_AGE = 24 * 3600          # never trust a saved copy older than a day
CACHE_VERSION = 11              # raise this whenever the rules for keeping or classifying postings change: older saved copies are then ignored


def _cache_file():
    """Where the last good postings are kept, so a restart or a new deploy shows jobs at once instead of waiting
    for every employer board (UAPLY_DATA_DIR on a host, ./data on this computer; never committed)."""
    return os.path.join(os.environ.get("UAPLY_DATA_DIR") or os.path.join(ROOT, "data"), "jobs-cache.json")


def _load_disk():
    with _load_lock:                   # a second request arriving meanwhile waits for the saved list instead of finding the cache empty
        if not _disk["loaded"]:
            _read_disk()
            _disk["loaded"] = True


def _read_disk():
    try:
        with open(_cache_file(), encoding="utf-8") as f:
            saved = json.load(f)
        if not isinstance(saved, dict) or saved.pop("_version", None) != CACHE_VERSION:
            return
        now = time.time()
        with _lock:
            for key, v in saved.items():
                kind, token, name = key.split("|", 2)
                if isinstance(v, dict) and isinstance(v.get("jobs"), list) and now - float(v.get("at", 0)) < DISK_MAX_AGE:
                    _cache.setdefault((kind, token, name), {"at": float(v["at"]), "jobs": v["jobs"], "status": str(v.get("status", ""))})
            if _cache:
                _disk["filled"] = True
    except Exception:
        pass


_save_lock = threading.Lock()      # one save at a time: background refreshes finish together, and two writers of the same .tmp file could
#                                    interleave into a broken saved list (or, on Windows, fail and lose the save)


def _save_disk():
    if not _disk["dirty"]:
        return
    with _save_lock:
        try:
            with _lock:
                if not _disk["dirty"]:
                    return
                snap = {"|".join(k): {"at": v["at"], "jobs": v["jobs"], "status": v["status"]} for k, v in _cache.items()}
                snap["_version"] = CACHE_VERSION
                _disk["dirty"] = False
            path = _cache_file()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + ".tmp"
            # one source at a time: json.dump of the whole list built the entire text in memory first (46 MB at the peak of a
            # fresh start with 80 sources, October 21, 2026); written this way the largest piece is one source's jobs
            with open(tmp, "w", encoding="utf-8") as f:
                f.write("{")
                for i, (k, v) in enumerate(snap.items()):
                    f.write(("," if i else "") + json.dumps(k) + ":" + json.dumps(v))
                f.write("}")
            os.replace(tmp, path)
            _disk["saved_at"] = time.time()
        except Exception as e:                  # jobs still work from memory; only a restart would have to wait for every feed again
            _disk["dirty"] = True               # so the next refresh tries again
            sys.stderr.write("[uaply] could not save the job cache: %s: %s\n" % (type(e).__name__, str(e)[:200]))


MAX_FEED_BYTES = 40 * 1000 * 1000    # the largest board (Databricks) answered 9.9 MB on October 17, 2026; anything past this is refused, not parsed
FEED_PARALLEL = 3                    # boards read and parsed at the same time. A board read whole cost about 4x its size while it was parsed (the
#                                      bytes, the text, then Python's objects), and memory a process has used is mostly not given back: reading all of
#                                      them at once took the live server (512 MB plan) from 45 MB to 275 MB, and to 491 MB when two rounds overlapped
#                                      (Oct 17). Employer boards are now read as they arrive (_get_items), a posting at a time, so a board costs a few
#                                      hundred KB however big it is; the smaller feeds and single postings still use _get.
_feed_slots = threading.BoundedSemaphore(FEED_PARALLEL)


def _get(url, headers=None, as_text=False):
    """One feed answer, parsed as JSON (or the plain text with as_text=True), refused past MAX_FEED_BYTES."""
    req = urllib.request.Request(url, headers=dict({"User-Agent": UA, "Accept": "text/plain" if as_text else "application/json"}, **(headers or {})))
    started, parts, size = time.time(), [], 0
    with urllib.request.urlopen(req, timeout=FEED_TIMEOUT) as r:
        while True:                                     # in parts, so a feed that trickles is stopped at FEED_DEADLINE
            part = r.read(STREAM_CHUNK)
            if not part:
                break
            parts.append(part)
            size += len(part)
            if size > MAX_FEED_BYTES:
                break
            if time.time() - started > FEED_DEADLINE:
                raise TimeoutError("the feed took longer than %d s; tried again at the next refresh" % FEED_DEADLINE)
    body = b"".join(parts)
    del parts
    if len(body) > MAX_FEED_BYTES:
        raise ValueError("the answer is larger than %d MB" % (MAX_FEED_BYTES // 1000000))
    text = body.decode("utf-8", "replace")
    del body                              # the bytes go before the parse starts: one copy fewer of a board held at the peak
    return text if as_text else json.loads(text)


FEED_TIMEOUT = 20                     # seconds one network read may wait (connect, or the next part of the answer)
FEED_DEADLINE = 90                    # seconds one feed answer may take in all (SpaceX's 32 MB board takes about 10): past that it is dropped,
#                                       its download slot goes to the next feed, the last good copy stays, and it is tried again 2 minutes later
STREAM_CHUNK = 256 * 1024              # how much of a board's answer is read from the network at a time
_DEC = json.JSONDecoder()
_WS = re.compile(r"[ \t\n\r]*")


def _get_items(url, key=None):
    """The postings of one board answer, one at a time, read from the network as they arrive: the items of the list under `key` in the
    top-level object ({"jobs": [...]}: Greenhouse, Ashby, Workable), or of the top-level list itself (key None: Lever). Only the part of
    the answer not yet worked through is held (a few hundred KB), instead of the whole answer, its text and every parsed posting at once:
    Carvana's 19 MB board cost about 75 MB that way. Past MAX_FEED_BYTES the answer is refused, as in _get."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    started = time.time()
    with urllib.request.urlopen(req, timeout=FEED_TIMEOUT) as r:
        dec = codecs.getincrementaldecoder("utf-8")("replace")
        st = {"buf": "", "pos": 0, "read": 0, "done": False}

        def more():
            if st["done"]:
                return False
            chunk = r.read(STREAM_CHUNK)
            st["read"] += len(chunk)
            if time.time() - started > FEED_DEADLINE:
                raise TimeoutError("the feed took longer than %d s; tried again at the next refresh" % FEED_DEADLINE)
            if st["read"] > MAX_FEED_BYTES:
                raise ValueError("the answer is larger than %d MB" % (MAX_FEED_BYTES // 1000000))
            if not chunk:
                st["done"] = True
                st["buf"] = st["buf"][st["pos"]:] + dec.decode(b"", final=True)
            else:
                st["buf"] = st["buf"][st["pos"]:] + dec.decode(chunk)       # what was worked through is dropped here
            st["pos"] = 0
            return True

        def skip_ws():
            while True:
                st["pos"] = _WS.match(st["buf"], st["pos"]).end()
                if st["pos"] < len(st["buf"]) or not more():
                    return

        def peek():
            skip_ws()
            return st["buf"][st["pos"]] if st["pos"] < len(st["buf"]) else ""

        def take(ch):
            if peek() != ch:
                raise ValueError("unexpected answer: wanted %r" % ch)
            st["pos"] += 1

        def value():
            skip_ws()
            while True:
                try:
                    v, end = _DEC.raw_decode(st["buf"], st["pos"])
                except ValueError:
                    if more():                         # most likely cut off by the end of the chunk: read on and try again
                        continue
                    raise
                if end == len(st["buf"]) and not st["done"] and isinstance(v, (int, float)):
                    more()                             # a number at the very end of the chunk may go on in the next one
                    continue
                st["pos"] = end
                return v

        def items():
            take("[")
            if peek() == "]":
                st["pos"] += 1
                return
            while True:
                yield value()
                c = peek()
                st["pos"] += 1
                if c == "]":
                    return
                if c != ",":
                    raise ValueError("unexpected answer in a list")

        if key is None:
            yield from items()
            return
        take("{")
        if peek() == "}":
            return
        while True:
            k = value()
            take(":")
            if k == key:
                if peek() == "[":
                    yield from items()
                else:
                    value()
                return                                 # what follows the list (meta, counts) is not needed
            value()                                    # a small value before the list (Ashby's apiVersion): read and dropped
            c = peek()
            st["pos"] += 1
            if c == "}":
                return
            if c != ",":
                raise ValueError("unexpected answer in an object")


KEY_RE = re.compile(r"^[A-Za-z0-9+/=_.-]{16,200}$")      # what a feed's API key looks like (USAJOBS: about 44 letters, digits, + / =)


def feed_keys():
    """The job feeds' own API keys the owner pasted on the setup page ('feed_keys' in uaply-config.json, or in UAPLY_CONFIG_JSON on a
    host): {"usajobs": ..., "usajobs_email": ..., "muse": ...}. Only well-formed values are returned. These are secrets: never logged, never
    sent to a browser, never shown on a page (see _scrub).
    On a host the USAJOBS key can also be its own variable, UAPLY_USAJOBS_KEY (with UAPLY_USAJOBS_EMAIL, the address the key was requested
    with), so it is pasted once in the dashboard instead of inside the UAPLY_CONFIG_JSON line. A well-formed variable wins over feed_keys."""
    cfg = _cfg()
    k = cfg.get("feed_keys") if isinstance(cfg.get("feed_keys"), dict) else {}
    out = {n: k[n].strip() for n in ("usajobs", "muse") if isinstance(k.get(n), str) and KEY_RE.match(k[n].strip())}
    env_key = (os.environ.get("UAPLY_USAJOBS_KEY") or "").strip()
    if KEY_RE.match(env_key):
        out["usajobs"] = env_key
    EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")   # one plain address (the module-level one was removed as unused)
    mail = next((m.strip() for m in (os.environ.get("UAPLY_USAJOBS_EMAIL"), k.get("usajobs_email"), cfg.get("owner_copy"))
                 if isinstance(m, str) and EMAIL_RE.fullmatch(m.strip())), "")
    out["usajobs_email"] = mail or USAJOBS_EMAIL
    cid, ctok = (os.environ.get("UAPLY_COS_USER_ID") or "").strip(), (os.environ.get("UAPLY_COS_TOKEN") or "").strip()
    if COS_ID_RE.match(cid) and COS_TOKEN_RE.match(ctok):          # both, well formed, or CareerOneStop stays off ("no key")
        out["cos_user"], out["cos_token"] = cid, ctok
    return out


def _scrub(text):
    """Error text with every feed key taken out, so a key can never reach the server's log or the job list's status line."""
    keys = feed_keys()                     # read once (it reads the settings file), not once per key
    for n in ("usajobs", "muse", "cos_token", "cos_user"):
        v = keys.get(n)
        if v:
            text = text.replace(v, "[key]").replace(urllib.parse.quote(v, safe=""), "[key]")
    return text


ROLE_HEAD = re.compile(r"(?:About (?:the|this) (?:role|job|internship|position|opportunity|team)|The (?:role|opportunity|internship|position)|Role overview|"
                       r"Position summary|Job summary|Job description|Overview|What you.?ll (?:do|be doing)|Your role|In this role|Responsibilities)\b[:\s-]*", re.I)


def _role_summary(text, limit=650):
    """A short, readable description of the job for emails. Postings usually open with a paragraph about the company, so when the
    posting has a role section ("About the role", "What you'll do", ...) the summary starts there. It ends on a whole sentence."""
    t = text.strip()
    m = ROLE_HEAD.search(t, 0, 6000)
    if m and m.start() > 0:
        t = t[m.start():]
    if len(t) <= limit:
        return t
    cut = t[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return (cut[:end + 1] if end > limit * 0.5 else cut.rsplit(" ", 1)[0] + "…")


def _text(s):
    s = html.unescape(s or "")
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()[:20000]


def _ts(v):
    """Posting date as epoch milliseconds (0 if the feed gives none or an unreadable one)."""
    try:
        if isinstance(v, (int, float)):
            return int(v if v > 1e11 else v * 1000)
        if isinstance(v, str) and v.strip():
            d = datetime.datetime.fromisoformat(v.strip().replace("Z", "+00:00"))
            if d.tzinfo is None:
                d = d.replace(tzinfo=datetime.timezone.utc)
            return int(d.timestamp() * 1000)
    except Exception:
        pass
    return 0


# Benefits a posting mentions in its own text. A mention is not a guarantee, and silence is not "none": many
# postings simply do not list benefits, so the app treats these as "mentions", never as proof of absence.
PERK_RES = [
    ("health", re.compile(r"health(?:care)? (?:insurance|coverage|benefits|plans?)|medical (?:insurance|coverage|benefits|plans?)|medical,? dental", re.I)),
    ("dental", re.compile(r"\bdental\b", re.I)),
    ("vision", re.compile(r"\bvision (?:insurance|coverage|benefits|care|plans?)\b|dental,? (?:and |& )?vision|medical,? dental,? (?:and |&)?vision", re.I)),
    ("k401", re.compile(r"401\s?\(?k\)?", re.I)),
    ("match", re.compile(r"401\s?\(?k\)?[^.]{0,80}match|(?:employer|company) match|matching contributions?", re.I)),
    ("loan", re.compile(r"student loan", re.I)),
    ("stock", re.compile(r"stock options?|equity (?:grants?|compensation|package)|\bRSUs?\b|\bESPP\b|stock purchase", re.I)),
    ("pto", re.compile(r"\bPTO\b|paid time off|paid vacation|unlimited (?:vacation|time off)|vacation days", re.I)),
    ("maternity", re.compile(r"paid (?:maternity|parental)|maternity leave|parental leave", re.I)),
    ("paternity", re.compile(r"paid (?:paternity|parental)|paternity leave|parental leave", re.I)),
    ("tuition", re.compile(r"tuition (?:assistance|reimbursement|support)|education(?:al)? (?:assistance|reimbursement)", re.I)),
]


# Postings that say pay is commission only. A heuristic on the posting's own words, not a verified fact.
COMM_RE = re.compile(r"commission[- ]only|100% commission|straight commission|commission[- ]based (?:pay|compensation|position|role|only)|no base (?:salary|pay)|1099 commission", re.I)


PERK_KEYS = [k for k, _ in PERK_RES]


def _perks(text):
    return [k for k, rx in PERK_RES if rx.search(text or "")]


def _money(tok):
    tok = tok.replace(",", "").replace(" ", "")
    return int(tok[:-1]) * 1000 if tok[-1] in "kK" else int(tok)


def _salary(*texts):
    for t in texts:
        m = SAL_RE.search(t or "")
        if m:
            lo, hi = _money(m.group(1)), _money(m.group(2))
            if 20000 <= lo < hi <= 600000:
                return [lo, hi]
    return [0, 0]


def _iter_raw(kind, token, name):
    """The raw postings of one board, one at a time: dicts with id, title, company, loc, remote, text, url, salary_text. A generator, so a
    board's postings are worked through as they are read instead of all being held (each with up to 20,000 characters of text) first."""
    if kind == "greenhouse":
        for j in _get_items("https://boards-api.greenhouse.io/v1/boards/%s/jobs?content=true" % token, "jobs"):
            yield dict(id=j["id"], title=j["title"], company=j.get("company_name") or name,
                       loc=(j.get("location") or {}).get("name", ""), remote=None,
                       text=_text(j.get("content")), url=j["absolute_url"], salary_text="",
                       posted=_ts(j.get("first_published") or j.get("updated_at")), updated=_ts(j.get("updated_at")), emp=_gh_emp(j),
                       fallback=_dept(j.get("departments")))     # a store or clinic role names no software skill: its department is what it is scored on
    elif kind == "lever":
        for j in _get_items("https://api.lever.co/v0/postings/%s?mode=json" % token):
            cat = j.get("categories") or {}
            yield dict(id=j["id"], title=j["text"], company=name, loc=cat.get("location", "") or "",
                       remote=(j.get("workplaceType") == "remote") or None,
                       text=_text((j.get("descriptionPlain") or "") + " " + (j.get("additionalPlain") or "")),
                       url=j["hostedUrl"], salary_text="", posted=_ts(j.get("createdAt")), emp=cat.get("commitment"),
                       fallback=(cat.get("team") or cat.get("department") or "").strip() or None)
    elif kind == "ashby":
        for j in _get_items("https://api.ashbyhq.com/posting-api/job-board/%s" % token, "jobs"):
            if j.get("isListed") is False:
                continue
            yield dict(id=j["id"], title=j["title"], company=name, loc=j.get("location", "") or "",
                       remote=bool(j.get("isRemote")) or j.get("workplaceType") == "Remote" or None,
                       text=_text(j.get("descriptionPlain") or j.get("descriptionHtml")),
                       url=j["jobUrl"], salary_text="", posted=_ts(j.get("publishedAt")), emp=j.get("employmentType"),
                       fallback=(j.get("department") or j.get("team") or "").strip() or None)
    elif kind == "workable":
        # Workable's public jobs feed (no key): https://www.workable.com/api/accounts/{subdomain}?details=true lists the account's published jobs
        # with their descriptions (help.workable.com/hc/en-us/articles/115012771647, "Build a custom careers page using Workable's API"). It may
        # answer through apply.workable.com/api/v1/widget/accounts/{subdomain}, the same list. The posting id Workable's API takes is the shortcode.
        for j in _get_items("https://www.workable.com/api/accounts/%s?details=true" % urllib.parse.quote(token, safe=""), "jobs"):
            if not isinstance(j, dict) or not j.get("shortcode") or not j.get("title"):  # "state" is the region here, not a status: the feed lists published jobs only
                continue
            locs = [l for l in (j.get("locations") or []) if isinstance(l, dict) and not l.get("hidden")]
            loc = "; ".join(p for p in (", ".join(x for x in (l.get("city"), l.get("region"), l.get("country")) if x) for l in locs) if p)
            loc = loc or ", ".join(x for x in (j.get("city"), j.get("state"), j.get("country")) if x)      # one place per posting in older replies
            yield dict(id=j["shortcode"], title=j["title"], company=name, loc=loc, remote=True if j.get("telecommuting") is True else None,
                       text=_text(j.get("description") or "") + " " + _text(j.get("requirements") or ""), url=j.get("url") or j.get("shortlink") or "",
                       salary_text="", posted=_ts(j.get("published_on") or j.get("created_at")), emp=j.get("employment_type"),
                       force_type="parttime" if re.search(r"part", j.get("employment_type") or "", re.I) else
                                  ("internship" if re.search(r"intern", j.get("employment_type") or "", re.I) else None))
    elif kind == "remotive":
        for j in _get("https://remotive.com/api/remote-jobs?category=%s&limit=60" % token).get("jobs", []):
            loc = j.get("candidate_required_location") or ""
            if not re.search(r"usa|united states|worldwide|americas|north america|anywhere", loc, re.I):
                continue
            yield dict(id=j["id"], title=j["title"], company=j["company_name"], loc="Remote (%s)" % loc, remote=True,
                       text=_text(j.get("description")) + " " + " ".join(j.get("tags") or []),
                       url=j["url"], salary_text=j.get("salary") or "", posted=_ts(j.get("publication_date")), emp=j.get("job_type"))
    elif kind == "jobicy":
        data = _get("https://jobicy.com/api/v2/remote-jobs?count=30&geo=usa&industry=%s" % token)
        for j in data.get("jobs", []):
            sal = None
            lo, hi = j.get("salaryMin"), j.get("salaryMax")
            if j.get("salaryPeriod") == "yearly" and j.get("salaryCurrency") == "USD" and isinstance(lo, (int, float)) \
                    and isinstance(hi, (int, float)) and 20000 <= lo < hi <= 600000:
                sal = [int(lo), int(hi)]
            yield dict(id=j["id"], title=j["jobTitle"], company=j["companyName"],
                       loc="Remote (%s)" % re.sub(r"\s+", " ", j.get("jobGeo") or "USA").strip(), remote=True,
                       text=_text(j.get("jobDescription")), url=j["url"], salary_text="", sal=sal,
                       posted=_ts(j.get("pubDate")), emp=j.get("jobType"),
                       fallback=(j.get("jobIndustry") or [None])[0])
    elif kind == "muse":
        key = feed_keys().get("muse")         # registered key (The Muse: required beyond testing; 3,600 requests an hour instead of 500)
        for page in (1, 2):
            data = _get("https://www.themuse.com/api/public/jobs?page=%d&level=%s" % (page, urllib.parse.quote(token)) +
                        ("&api_key=%s" % urllib.parse.quote(key, safe="") if key else ""))
            for j in data.get("results", []):
                locs = [l.get("name", "") for l in j.get("locations", [])]
                loc = ", ".join(locs[:2]) + (" +%d more" % (len(locs) - 2) if len(locs) > 2 else "")
                cats = [c.get("name") for c in j.get("categories", []) if c.get("name")]
                yield dict(id=j["id"], title=j["name"], company=j["company"]["name"], loc=loc or "Not listed",
                           remote=any(re.search("remote|flexible", l, re.I) for l in locs) or None,
                           text=_text(j.get("contents")), url=j["refs"]["landing_page"], salary_text="",
                           fallback=cats[0] if cats else None, posted=_ts(j.get("publication_date")), emp=j.get("levels"),
                           force_type="internship" if token == "Internship" else None)
    elif kind == "himalayas":
        # https://himalayas.app/api : link to the job on Himalayas, use applicationLink unchanged, show only on our own app, remove expired jobs
        now = time.time()
        for page in (1, 2, 3):
            country, _, only = token.partition("-")
            data = _get("https://himalayas.app/jobs/api/search?country=%s&page=%d" % (urllib.parse.quote(country, safe=""), page) +
                        ("&employment_type=%s" % urllib.parse.quote(HIMALAYAS_TYPES[only], safe="") if only in HIMALAYAS_TYPES else ""))
            for j in data.get("jobs") or []:
                if not isinstance(j, dict) or not j.get("title") or not str(j.get("guid") or "").startswith("https://himalayas.app/"):
                    continue
                if isinstance(j.get("expiryDate"), (int, float)) and j["expiryDate"] < now:
                    continue
                where = [c for c in (j.get("locationRestrictions") or []) if isinstance(c, str)]
                if where and not any(re.search(r"United States|\bUSA?\b", c) for c in where):
                    continue
                sal = None
                lo, hi = j.get("minSalary"), j.get("maxSalary")
                if j.get("currency") == "USD" and j.get("salaryPeriod") in ("annual", "yearly") and isinstance(lo, (int, float)) \
                        and isinstance(hi, (int, float)) and 20000 <= lo < hi <= 600000:
                    sal = [int(lo), int(hi)]
                link = j.get("applicationLink") if str(j.get("applicationLink") or "").startswith("https://") else j["guid"]
                yield dict(id=j["guid"], title=j["title"], company=j.get("companyName") or "Himalayas", loc="Remote (%s)" % (", ".join(where[:3]) or "Worldwide"),
                           remote=True, text=_text(j.get("description") or j.get("excerpt")), url=link, salary_text="", sal=sal,
                           posted=_ts(j.get("pubDate")), emp=j.get("employmentType"),
                           fallback=next((c.replace("-", " ") for c in (j.get("categories") or []) if isinstance(c, str)), None))
    elif kind == "remoteok":
        # https://remoteok.com/api : the first entry is the legal notice (link back to the job on Remote OK, name Remote OK as the source)
        for j in _get("https://remoteok.com/api")[1:]:
            if not isinstance(j, dict) or not j.get("position") or not str(j.get("url") or "").lower().startswith("https://remoteok.com/"):
                continue
            sal = None
            lo, hi = j.get("salary_min"), j.get("salary_max")
            if isinstance(lo, (int, float)) and isinstance(hi, (int, float)) and 20000 <= lo < hi <= 600000:
                sal = [int(lo), int(hi)]
            yield dict(id=j.get("id") or j["url"], title=j["position"], company=j.get("company") or "Remote OK",
                       loc="Remote" + (" (%s)" % j["location"] if j.get("location") else ""), remote=True,
                       text=_text(j.get("description")) + " " + " ".join(t for t in (j.get("tags") or []) if isinstance(t, str)),
                       url="https://remoteok.com/" + str(j["url"]).split("/", 3)[3], salary_text="", sal=sal,
                       posted=_ts(j.get("date")), fallback=next((t for t in (j.get("tags") or []) if isinstance(t, str)), None))
    elif kind == "simplify":
        yield from _simplify(token, name)
    elif kind == "careeronestop":
        yield from _careeronestop(token)
    elif kind == "usajobs":
        yield from _usajobs(token)
    elif kind == "smartrecruiters":
        yield from _smartrecruiters(token, name)


def _fetch_raw(kind, token, name):
    """All raw postings of one board as a list (tools and tests; the job list itself reads them one at a time through _iter_raw)."""
    return list(_iter_raw(kind, token, name))


_sr_desc = {}            # (company, posting id) -> {"at", "released", "detail"}: each description is read once a day at most


def _sr_detail(token, pid, released):
    """One posting's full record (description, pay), from the cache when it is fresh and the posting was not re-released."""
    key = (token, pid)
    with _lock:
        c = _sr_desc.get(key)
    if c and c["released"] == released and time.time() - c["at"] < SR_DESC_TTL:
        return c["detail"]
    at = time.time()
    try:
        d = _get("https://api.smartrecruiters.com/v1/companies/%s/postings/%s" % (urllib.parse.quote(token, safe=""), urllib.parse.quote(pid, safe="")))
        if isinstance(d, dict):                  # keep only what _smartrecruiters reads (120 full records stayed in memory all day before)
            secs = ((d.get("jobAd") or {}).get("sections")) or {}
            d = {"jobAd": {"sections": {k: {"text": (secs.get(k) or {}).get("text") or ""} for k in ("jobDescription", "qualifications", "additionalInformation")}},
                 "compensation": d.get("compensation") or {}}
    except Exception:
        d = c["detail"] if c else None           # keep the last description if this read fails, and try again at the next hourly refresh
        at = time.time() - SR_DESC_TTL + TTL["smartrecruiters"] - 60
    with _lock:
        _sr_desc[key] = {"at": at, "released": released, "detail": d}
    return d


SR_WHOLE = ("CityofPhiladelphia",)    # public bodies whose whole list is kept (up to KEEP); any other SmartRecruiters company is an employer board
SR_BOARD_READ = 40                     # an employer board: at most this many US postings get their description read (once a day each)


def _smartrecruiters(token, name):
    """A company's public SmartRecruiters postings: the list page by page (100 at a time, until totalFound, at most KEEP postings),
    then each posting's own record for its description. Shapes as seen on the live API (October 16, 2026). For a company that is not a
    public body (Equinox, Red Bull ...), postings outside the US are left out before any description is read, and at most SR_BOARD_READ
    descriptions are read (it keeps 14 plus tri-state extras, like any employer board)."""
    whole = token in SR_WHOLE
    cap = KEEP["smartrecruiters"]
    base = "https://api.smartrecruiters.com/v1/companies/%s/postings" % urllib.parse.quote(token, safe="")
    items, offset = [], 0
    while len(items) < cap:
        page = _get("%s?limit=100&offset=%d" % (base, offset))
        got = page.get("content") or []
        items += got
        offset += len(got)
        if not got or offset >= int(page.get("totalFound") or 0):
            break
    items = [p for p in items if isinstance(p, dict) and p.get("id")]
    if not whole:                                   # US postings only, Pennsylvania, New Jersey and Delaware ones first
        items = [p for p in items if ((p.get("location") or {}).get("country") or "us").lower() == "us"]
        items.sort(key=lambda p: ((p.get("location") or {}).get("region") or "").upper() not in ("PA", "NJ", "DE"))
        items = items[:SR_BOARD_READ]
    items = items[:cap]
    with ThreadPoolExecutor(max_workers=4) as ex:                # four at a time: gentle on their API, and quick enough
        details = list(ex.map(lambda p: _sr_detail(token, str(p["id"]), p.get("releasedDate") or ""), items))
    out = []
    for p, d in zip(items, details):
        d = d if isinstance(d, dict) else {}
        L = p.get("location") or {}
        city, region = (L.get("city") or "").strip(), (L.get("region") or "").strip()
        loc = city + (", " + region if region and region not in city else "")
        if (L.get("country") or "us").lower() != "us":
            loc = L.get("fullLocation") or (loc + ", " + (L.get("country") or "").upper())
        secs = ((d.get("jobAd") or {}).get("sections")) or {}
        text = " ".join((secs.get(k) or {}).get("text") or "" for k in ("jobDescription", "qualifications", "additionalInformation"))
        comp = d.get("compensation") or {}
        sal = None
        if comp.get("currency") == "USD" and comp.get("period") == "YEARLY" and isinstance(comp.get("min"), (int, float)) and isinstance(comp.get("max"), (int, float)) \
                and 20000 <= comp["min"] < comp["max"] <= 600000:
            sal = [int(comp["min"]), int(comp["max"])]
        kind_label = ((p.get("typeOfEmployment") or {}).get("label") or "").lower()
        force = "internship" if "intern" in kind_label else ("parttime" if "part" in kind_label else None)
        dept = re.split(r"\s[-–—]\s", (p.get("department") or {}).get("label") or "")[0].strip()      # "Law Department – Tax Unit" -> "Law Department"
        func = (p.get("function") or {}).get("label") or ""
        fallback = dept or (func if func.lower() != "other" else "") or (p.get("industry") or {}).get("label") or None
        out.append(dict(id=p["id"], title=(p.get("name") or "").strip(), company=(p.get("company") or {}).get("name") or name, country=L.get("country") or "us",
                        loc=loc or "Not listed", remote=True if L.get("remote") else None,
                        text=_text(text) or (p.get("name") or ""), url="https://jobs.smartrecruiters.com/%s/%s" % (token, p["id"]),
                        salary_text="", sal=sal, posted=_ts(p.get("releasedDate")), fallback=fallback, force_type=force, emp=kind_label,
                        ats_id=str(p.get("uuid") or "")))     # the Application API addresses a posting by its uuid, not by its number
    return [r for r in out if r["title"]]


USA_INTERN = re.compile(r"\bintern(?:ship)?s?\b|student trainee|\bpathways\b", re.I)
USA_GRAD = re.compile(r"recent grad|graduates?\b", re.I)


def _usajobs(token):
    """One USAJOBS search (USAJOBS_QUERIES[token]). Headers as USAJOBS' Authentication guide says: Host, User-Agent = the email the key was
    requested with, Authorization-Key = the key. Field names as in the Search API reference."""
    keys = feed_keys()
    q = USAJOBS_QUERIES.get(token) or USAJOBS_QUERIES["philadelphia"]
    url = "https://data.usajobs.gov/api/search?" + "&".join("%s=%s" % (k, urllib.parse.quote(v, safe=",;")) for k, v in q.items())
    data = _get(url, {"Host": "data.usajobs.gov", "User-Agent": keys["usajobs_email"], "Authorization-Key": keys.get("usajobs", "")})
    out = []
    for item in ((data or {}).get("SearchResult") or {}).get("SearchResultItems") or []:
        d = item.get("MatchedObjectDescriptor") or {}
        det = (d.get("UserArea") or {}).get("Details") or {}
        title = d.get("PositionTitle") or ""
        if not title:
            continue
        loc = d.get("PositionLocationDisplay") or ""
        places = [p.get("LocationName", "") for p in d.get("PositionLocation") or [] if isinstance(p, dict) and p.get("LocationName")]
        if not loc or loc.lower().startswith("multiple locations"):        # "Multiple Locations": name the first two, as The Muse cards do
            loc = "; ".join(places[:2]) + (" +%d more" % (len(places) - 2) if len(places) > 2 else "") or loc
        pay = (d.get("PositionRemuneration") or [{}])[0] or {}
        sal, sal_text = None, ""
        try:
            lo, hi = float(pay.get("MinimumRange") or 0), float(pay.get("MaximumRange") or 0)
            money = lambda n: "{:,.0f}".format(n) if n >= 1000 else "{:,.2f}".format(n)   # noqa: E731  (yearly in dollars, hourly with cents)
            sal_text = ("$%s - $%s %s" % (money(lo), money(hi), pay.get("Description") or "")).strip() if hi else ""
            if pay.get("RateIntervalCode") == "PA" and 20000 <= lo < hi <= 600000:
                sal = [int(lo), int(hi)]                                   # yearly pay only; hourly pay stays in the text
        except (TypeError, ValueError):
            pass
        duties = det.get("MajorDuties")
        duties = " ".join(x for x in duties if isinstance(x, str)) if isinstance(duties, list) else (duties if isinstance(duties, str) else "")
        paths = det.get("HiringPath")
        paths = [p.lower() for p in (paths if isinstance(paths, list) else [paths]) if isinstance(p, str)]
        # Pathways: a student internship when the title or the hiring path says so; a Recent Graduates posting stays an (entry-level) job
        intern = (USA_INTERN.search(title) and not USA_GRAD.search(title)) or ("student" in paths and "graduates" not in paths and not USA_GRAD.search(title))
        sched = " ".join(s.get("Name", "") for s in d.get("PositionSchedule") or [] if isinstance(s, dict))
        cats = [c.get("Name") for c in d.get("JobCategory") or [] if isinstance(c, dict) and c.get("Name")]
        apply_uri = [u for u in d.get("ApplyURI") or [] if isinstance(u, str) and u.startswith("https://")]
        # dates come as 2026-10-01T00:00:00.0000: the 4-digit fraction is dropped so any Python version reads them (the host runs 3.12)
        out.append(dict(id=item.get("MatchedObjectId") or d.get("PositionID"), title=title, company=d.get("OrganizationName") or d.get("DepartmentName") or "USAJOBS",
                        loc=loc, remote=True if (det.get("RemoteIndicator") is True or re.search(r"remote", loc, re.I)) else None,
                        text=_text(" ".join(x for x in (det.get("JobSummary"), duties, d.get("QualificationSummary")) if isinstance(x, str))),
                        url=(apply_uri[0] if apply_uri else d.get("PositionURI") or ""), announcement=d.get("PositionURI") or "",
                        salary_text=sal_text, sal=sal, posted=_ts(re.sub(r"\.\d+$", "", str(d.get("PublicationStartDate") or ""))), fallback=cats[0] if cats else None,
                        force_type="internship" if intern else None,
                        emp=(sched + " " + " ".join(s.get("Name", "") for s in d.get("PositionOfferingType") or [] if isinstance(s, dict) and s.get("Name") == "Temporary")).strip()))
    return out


def _careeronestop(token):
    """One CareerOneStop job search (COS_SEARCHES[token]), as its List Jobs API documents it (careeronestop.org/Developers/WebAPI/Jobs/
    list-jobs.aspx): GET /v1/jobsearch/{userId}/{keyword}/{location}/{radius}/{sortColumns}/{sortOrder}/{startRecord}/{pageSize}/{days}
    with "Authorization: Bearer <token>". The answer is {"JobCount", "Jobs": [{"JvId", "JobTitle", "Company", "DescriptionSnippet",
    "AcquisitionDate", "URL", "Location", "Fc"}]}; field names are matched without regard to case, and a posting without a title or an
    https link is skipped. Titles, companies and places are shown as given (the license forbids altering the data)."""
    keys = feed_keys()
    keyword, place, radius = COS_SEARCHES.get(token) or COS_SEARCHES["philadelphia"]
    q = lambda v: urllib.parse.quote(v, safe="")              # noqa: E731
    url = "https://api.careeronestop.org/v1/jobsearch/%s/%s/%s/%s/acquisitiondate/DESC/0/%s/%s" % (
        q(keys.get("cos_user", "")), q(keyword), q(place), q(radius), COS_PAGE, COS_DAYS)
    data = _get(url, {"Authorization": "Bearer " + keys.get("cos_token", "")})
    low = {str(k).lower(): v for k, v in (data or {}).items()} if isinstance(data, dict) else {}
    for j in low.get("jobs") or []:
        if not isinstance(j, dict):
            continue
        f = {str(k).lower(): v for k, v in j.items()}
        title, link = str(f.get("jobtitle") or "").strip(), str(f.get("url") or "").strip()
        if not title or not link.startswith("https://"):
            continue
        loc = str(f.get("location") or "").strip()
        yield dict(id=f.get("jvid") or link, title=title, company=str(f.get("company") or "").strip() or "Employer not named",
                   loc=loc or ("Remote" if token == "remote" else place), remote=True if token == "remote" or re.search(r"\bremote\b", loc, re.I) else None,
                   text=_text(f.get("descriptionsnippet") or ""), url=link, salary_text="", posted=_ts(f.get("acquisitiondate")),
                   fallback="Jobs")


def _newest(j):
    """The newest date a posting carries (epoch ms; 0 when it has none): posted, or updated where the feed gives that too."""
    return max(j.get("posted") or 0, j.get("updated") or 0)


def _too_old(j, now_ms):
    """True when the posting's newest date is more than MAX_AGE_DAYS ago. No date at all is not 'old'."""
    newest = _newest(j)
    return bool(newest) and now_ms - newest > MAX_AGE_DAYS * DAY_MS


def _days(ms, now_ms):
    return max(0, int((now_ms - ms) // DAY_MS))


def _with_age(j, now_ms):
    """A copy of a job with postedDays (whole days since it was posted) and, when the feed gives a later update, updatedDays. The cached
    job itself is shared by every request, so it is never changed here."""
    out = dict(j)
    if j.get("posted"):
        out["postedDays"] = _days(j["posted"], now_ms)
    if j.get("updated"):
        out["updatedDays"] = _days(j["updated"], now_ms)
    return out


_CO_SUFFIX = re.compile(r"\b(?:inc|llc|ltd|corp|corporation|co|company|the)\b")


def _norm(s):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).split())


def _same_job_key(j):
    """Two postings from two different feeds are the same job when company, title and place match after letter case, punctuation, spacing
    and company suffixes (Inc, LLC, Corp ...) are set aside: the same opening reached through two feeds (see get_jobs)."""
    return (_norm(_CO_SUFFIX.sub(" ", (j.get("co") or "").lower())), _norm(j.get("role")), _norm(j.get("loc")))


# Job type (jobType on every job): one of these six. The feed's own field is read first; the title (and, for part-time, the start of
# the text) is the fallback. "Full-time" is what most hiring systems fill in by default, interns included, so a title that says
# intern, co-op, part-time, contract, seasonal or temporary wins over a plain "Full-time" field.
JOB_TYPES = ("full-time", "part-time", "internship", "co-op", "contract", "temporary")
LEGACY_TYPE = {"internship": "internship", "co-op": "coop", "part-time": "parttime"}     # the older `type` field (the service tabs); anything else is "job"
FORCE_TO_JOBTYPE = {"internship": "internship", "coop": "co-op", "parttime": "part-time"}
TITLE_TYPES = [("co-op", re.compile(r"\bco-?op\b", re.I)),
               ("internship", re.compile(r"\binterns?\b|\binternships?\b", re.I)),
               ("part-time", re.compile(r"\bpart[- ]time\b", re.I)),
               ("temporary", re.compile(r"\bseasonal\b|\btemporary\b|\(temp\)|\btemp\s*[-–—:]", re.I)),
               # "Contract Manager" is a full-time job about contracts: only a bracketed or trailing "Contract", 1099 or contract-to-hire counts
               ("contract", re.compile(r"\((?:[^)]*[\s,/])?contract(?:or)?(?:[\s,/][^)]*)?\)|[-–—:,|]\s*contract(?:or)?\s*$|\b1099\b|\bcontract[- ]to[- ]hire\b", re.I))]


# Board names that carry a careers-site label: "Perpay - Career's Page", "Point72 ", "DRW - University Jobs", "Hometap Jobs",
# "ATOMS Careers page", "Astera Labs Early Career - North America 2027", "MORSE Corp Co-op Opportunities", "Jobs at Acme".
# A label is only taken off the end (or "Jobs at" off the start) when a name is left: "CourseCareers" and "Jobs for Humanity" stay.
CO_TAIL = re.compile(r"(?:\s*[-–—|:,]\s*|\s+)(?:(?:university|campus|early|student|internship|intern|co-?op)\s+)?"
                     r"(?:careers?(?:'s)?(?:\s+(?:page|site|portal|board))?|jobs?(?:\s+(?:page|board|site))?|job\s+board|opportunities|openings|"
                     r"hiring|recruiting|early\s+careers?(?:\b.*)?|university\s+recruiting(?:\b.*)?)\s*$", re.I)
CO_HEAD = re.compile(r"^\s*(?:jobs|careers)\s+(?:at|with)\s+", re.I)


def _clean_company(name, fallback=""):
    """A company name without the careers-site label a board added to it, spaces trimmed (see CO_TAIL). Empty: the fallback."""
    n = re.sub(r"\s+", " ", str(name or "")).strip()
    for _ in range(3):                                  # "Acme University Jobs - Careers Page": labels can be stacked
        m = CO_HEAD.match(n)
        cut = n[m.end():].strip() if m else n
        cut = CO_TAIL.sub("", cut).strip(" -–—|:,")
        if cut == n or not re.search(r"[A-Za-z0-9]", cut):
            break
        n = cut
    if not n or re.fullmatch(r"(?:careers?|jobs?|job board)(?:\s+page)?", n, re.I):     # nothing but a label: the board's own name
        n = re.sub(r"\s+", " ", str(fallback or "")).strip() or n
    return n


# Licensed and degree-gated roles, by title (checked against the live feeds' titles, October 2026). The lowest level a person can hold
# the job with: a Registered Nurse can be licensed with an associate degree, a therapist or counselor needs a master's, a psychologist,
# pharmacist, physician, dentist, physical therapist or lawyer a doctorate.
EDU_BY_TITLE = [
    ("Doctorate", re.compile(r"\bpsychologist|\bpsychiatrist\b|\bphysicians?\b(?!\s+assistant)|\bpharmacists?\b|\bdentists?\b|\bphysical therapist|"
                             r"\bDPT\b|\bPharmD\b|\battorneys?\b|\blawyers?\b|\bsolicitor\b|\bassociate general counsel|\bveterinarian|\boptometrist|"
                             r"\bresearch scientist\b.*\bph\.?d|\bph\.?d\b", re.I)),
    ("Master", re.compile(r"\bnurse practitioner|\bphysician assistant|\bPA-C\b|\bCRNA\b|\bLCSW\b|\bLICSW\b|\bLPCC?\b|\bLMFT\b|\bLMHC\b|\bLCPC\b|"
                          r"\b(?:licensed|clinical|mental health|staff|primary|outpatient|family|child|telehealth|bilingual)\s+(?:\w+\s+)?(?:therapist|counselor|social worker|clinician)|"
                          r"\bpsychotherapist|\btherapist\b|\bsocial worker\b|\bspeech[- ]language pathologist|\bSLP\b|\boccupational therapist|\bdietitian|"
                          r"\bMBA\b|\bmaster'?s\b", re.I)),
    ("Associate", re.compile(r"\bregistered nurse|\bRN\b|\bLPN\b|\bLVN\b|\bnurse\b|\bradiolog\w* tech|\bsonographer|\brespiratory therapist|"
                             r"\bdental hygienist|\bsurgical tech|\bmedical lab(?:oratory)? tech", re.I)),
]
EDU_RANK = {"High school": 0, "Associate": 1, "Bachelor": 2, "Master": 3, "Doctorate": 4}
EDU_TEXT = [  # what the text requires (a "preferred" degree is not a requirement)
    ("Doctorate", re.compile(r"(?:\bmust (?:have|hold|possess)|\brequires?|\brequired:?)\s+(?:an?\s+|the\s+)?(?:ph\.?d|doctoral degree|doctorate|pharm\.?d|psy\.?d|J\.D\.|M\.D\.|juris doctor)|"
                              r"(?:\bph\.?d\b|\bdoctoral degree|\bdoctorate\b|\bpharm\.?d\b|\bpsy\.?d\b|\bJ\.D\.|\bM\.D\.|\bjuris doctor)[^.;]{0,40}?\b(?:is |are )?(?:required|needed|necessary)\b", re.I)),
    ("Master", re.compile(r"(?:\bmust (?:have|hold|possess)|\brequires?|\brequired:?)\s+(?:an?\s+)?(?:master'?s|MSW|MBA|graduate degree)|"
                          r"(?:\bmaster'?s degree|\bMSW\b|\bMBA\b|\bgraduate degree)[^.;]{0,40}?\b(?:is |are )?(?:required|needed|necessary)\b", re.I)),
    ("Bachelor", re.compile(r"\bbachelor'?s?\b|\bB\.?S\.? degree|\bB\.?A\.? degree|\b4[- ]year degree|\bfour[- ]year degree|\bundergraduate degree|\bcollege degree|"
                            r"\b(?:BS|BA|B\.S\.|B\.A\.)(?=,|\s*/|\s+(?:or|in)\b)", re.I)),
    ("Associate", re.compile(r"\bassociate'?s? degree|\btwo[- ]year degree|\b(?:active|current|valid|unrestricted)\s+(?:state\s+)?(?:RN|LPN|LVN|nursing|clinical|professional|medical|pharmacy|therapy|counseling|social work)\s+(?:\w+\s+){0,2}licen[sc]e\b", re.I)),
]
# an internship or co-op asks what a student is studying for, not what they hold: graduate-only ones are marked (ranked after the others)
GRAD_TITLE = re.compile(r"\bph\.?d\b|\bdoctoral\b|\bMBA\b|\bmaster'?s\b|\bgraduate (?:student|intern|research)|\bpostdoc", re.I)
GRAD_TEXT = re.compile(r"(?:pursuing|enrolled in|candidate for|working toward|studying for|currently in)\s+(?:a|an|your)?\s*(?:ph\.?d|doctoral|doctorate|master'?s|MBA|graduate)", re.I)
UNDERGRAD_TEXT = re.compile(r"\bundergrad|\bbachelor|\bB\.?S\.?\b|\bB\.?A\.?\b|\bsophomore|\bjunior year|\brising (?:junior|senior|sophomore)|\bfreshm[ae]n|\bassociate'?s? degree|\bhigh school", re.I)


def _grad_only(title, text):
    """True for an internship or co-op only graduate students can take (a PhD, master's or MBA program in the title, or the text asks
    for one and never mentions undergraduates)."""
    return bool(GRAD_TITLE.search(title) or (GRAD_TEXT.search(text) and not UNDERGRAD_TEXT.search(text)))


def _edu(title, text, jtype="full-time"):
    """The education level a job needs (High school, Associate, Bachelor, Master, Doctorate): a licensed or degree-gated title first,
    then what the text requires. For an internship or co-op it is what a student must have finished: High school for an undergraduate
    one, Bachelor for a graduate-only one."""
    if jtype in ("internship", "co-op"):
        return "Bachelor" if _grad_only(title, text) else "High school"
    by_title = next((lvl for lvl, rx in EDU_BY_TITLE if rx.search(title)), "High school")
    by_text = next((lvl for lvl, rx in EDU_TEXT if rx.search(text)), "High school")
    return max(by_title, by_text, key=lambda lvl: EDU_RANK[lvl])


def _dept(departments):
    """Greenhouse's first department name ("Store Operations", "Clinical"), or None."""
    for d in departments or []:
        if isinstance(d, dict) and str(d.get("name") or "").strip():
            return str(d["name"]).strip()[:60]
    return None


def _gh_emp(j):
    """Greenhouse has no standard employment-type field; many employers add one as a custom field ("Employment Type", "Time Type")."""
    for m in j.get("metadata") or []:
        if isinstance(m, dict) and re.search(r"employ|job type|time type|worker type|schedule|commitment", str(m.get("name") or ""), re.I):
            return m.get("value") if isinstance(m.get("value"), (str, list)) else ""
    return ""


def _emp_type(v):
    """A feed's own employment-type value (Lever "Intern", Ashby "PartTime", SmartRecruiters "Full-time", USAJOBS "Part-time Temporary",
    Himalayas "Contractor" ...) as one of JOB_TYPES, or "" when it says nothing usable."""
    if isinstance(v, (list, tuple)):
        v = " ".join(str(x.get("name") or x.get("label") or "") if isinstance(x, dict) else str(x) for x in v)
    s = re.sub(r"[_\s]+", " ", re.sub(r"([a-z])([A-Z])", r"\1 \2", str(v or ""))).lower()
    for t, rx in (("co-op", r"\bco ?-?op\b"), ("internship", r"\bintern"), ("part-time", r"\bpart\b|\bpart-time\b|\bparttime\b"),
                  ("contract", r"\bcontract|\bfreelance"), ("temporary", r"\btemp|\bseasonal|\bintermittent"), ("full-time", r"\bfull|\bpermanent|\bregular")):
        if re.search(rx, s):
            return t
    return ""


PT_WORDS = re.compile(r"\bpart[- ]time\b(?![- ]?(?:and|or|/)\s*full)|\bPT\b(?=\s*(?:position|role|schedule|shift))|\bweekend (?:and evening )?shifts\b", re.I)
PT_HOURS = re.compile(r"(?:(\d{1,2})\s*(?:-|–|to)\s*)?(\d{1,2})\+?\s*(?:hours|hrs)\s*(?:per|a|each|/)\s*week", re.I)
FT_WORDS = re.compile(r"\bfull[- ]time\b(?![- ]?(?:and|or|/)\s*part)|\b40\s*(?:hours|hrs)\s*(?:per|a|/)\s*week", re.I)


def _part_time_text(text):
    """True when the start of a posting describes a part-time schedule: "part-time" (not "full-time or part-time"), or hours a week of
    30 or fewer ("15-25 hours per week", "up to 20 hrs/week"), and it does not also say full-time first."""
    # "full-time or part-time" / "part-time and full-time" says neither: taken out before looking
    head = re.sub(r"\b(?:full|part)[- ]time\s*(?:,|and|or|/|&)\s*(?:full|part)[- ]time\b", " ", text[:1500], flags=re.I)
    pt, ft = PT_WORDS.search(head), FT_WORDS.search(head)
    if pt and not (ft and ft.start() < pt.start()):
        return True
    hours = [int(m.group(2)) for m in PT_HOURS.finditer(head)]
    return bool(hours) and max(hours) <= 30 and not ft


def _job_type(raw):
    """One of JOB_TYPES for a raw posting: a type the feed forced (USAJOBS Pathways, The Muse's Internship level), then the feed's own
    field, then the title, then "part-time" near the start of the text, then the list's own kind (an internship list), else full-time."""
    forced = FORCE_TO_JOBTYPE.get(raw.get("force_type") or "")
    if forced:
        return forced
    feed = _emp_type(raw.get("emp"))
    title = raw.get("title") or ""
    by_title = next((t for t, rx in TITLE_TYPES if rx.search(title)), "")
    if by_title in ("internship", "co-op"):              # interns are often entered as temporary or contract workers: the title says what it is
        return "co-op" if feed == "co-op" else by_title
    if feed and feed != "full-time":
        return feed
    if by_title:
        return by_title
    if feed == "full-time":
        return "full-time"
    if _part_time_text(raw.get("text") or ""):
        return "part-time"
    return raw.get("default_type") or "full-time"


def _type(raw):
    """The older type field (internship, coop, parttime or job) the service tabs use, from _job_type. Cheap, so it is known before the costly part."""
    return LEGACY_TYPE.get(_job_type(raw), "job")


def _normalize(raw, kind, name, board=None):
    list_credit = raw.get("list_credit")
    if list_credit:                                     # a Simplify / Pitt CSC row: it is the employer's own posting, read from its own board
        kind, board, name = raw["ats_kind"], raw["board"], raw["company"]
    title, loc, text = raw["title"], raw["loc"], raw["text"]
    if str(raw.get("country") or "us").strip().lower() not in ("us", "usa", "united states", "united states of america"):
        return None
    remote = raw["remote"] if raw["remote"] is not None else bool(re.search(r"\bremote\b", loc, re.I))
    if not _us_ok(loc, remote):
        return None
    if FOREIGN_RE.search(title) and not EXPLICIT_US.search(loc):
        return None                                     # a region-specific role (for example "ANZ" or "Toronto") listed as just "Remote"
    if raw["url"].startswith("http://"):                # some employers list their careers page as http:// (Squarespace, Block): open it securely
        raw = dict(raw, url="https://" + raw["url"][len("http://"):])
    if not raw["url"].startswith("https://"):
        return None
    hay = (title + " ") * 2 + text
    found = []
    for skill, rx in SKILL_RES:
        if skill in TITLE_GATED and not TITLE_GATED[skill].search(title):
            continue
        n = len(rx.findall(hay))
        if n:
            found.append((n, skill))
    if found:
        skills = [s for _, s in sorted(found, key=lambda x: -x[0])[:4]]
    elif raw.get("fallback"):
        skills = [raw["fallback"]]      # no known skill in the text: score on the posting's own category
    else:
        return None
    mode = "remote" if remote else ("hybrid" if re.search(r"hybrid", loc + " " + text[:600], re.I) else "onsite")
    jtype = _job_type(raw)
    typ = LEGACY_TYPE.get(jtype, "job")
    m = YRS_RE.search(text)
    yrs = min(int(m.group(1)), 15) if m else 0
    edu = _edu(title, text, jtype)
    blurb = text[:170].rsplit(" ", 1)[0] + "…" if len(text) > 170 else text
    desc = _role_summary(text)                                                    # what the emails show about the job
    jid = 100000 + int(hashlib.sha1(("%s:%s" % (kind, raw["id"])).encode()).hexdigest()[:6], 16)
    company = _clean_company(raw["company"], name)
    src = name if kind in ("remotive", "jobicy", "muse", "usajobs", "himalayas", "remoteok", "careeronestop") else "%s's careers page" % company
    # Where this posting lives in the employer's own hiring system. It is only an address (not a credential): it is used when, and only when, the
    # employer has connected with their own key (see ats_connections); otherwise it is never used and apply stays "link".
    # Ashby: the job board's own posting id is the jobPostingId its API takes. SmartRecruiters: the posting's uuid (see _smartrecruiters).
    pid = str(raw.get("ats_id") or raw["id"])
    ats = {"kind": kind, "board": board, "id": pid} if (kind in ats_api.KINDS and board and ats_api.TOKEN_RE.match(board) and ats_api.ID_RE.match(pid)) else None
    # contact is deliberately empty and apply is "link": a third-party feed never gets an application emailed to anyone
    out = dict(id=jid, co=company, role=title, loc=_place(loc, mode), mode=mode,
               sal=raw.get("sal") or _salary(raw["salary_text"], text), yrs=yrs, edu=edu, skills=skills, blurb=blurb, desc=desc,
               type=typ, jobType=jtype, url=raw["url"], source=src, contact="", apply="link", live=True, ats=ats,
               posted=_ts(raw.get("posted")), perks=_perks(text), comm=bool(COMM_RE.search(text)))
    if jtype in ("internship", "co-op") and _grad_only(title, text):
        out["gradOnly"] = True                                    # the Internship and Co-op stacks show undergraduate roles first
    # dates in epoch ms whatever the caller gave (_ts: seconds are converted): a date in seconds reads as January 1970, and the 60-day rule
    # (MAX_AGE_DAYS) would drop the posting without a word
    if _ts(raw.get("updated")) > out["posted"]:
        out["updated"] = _ts(raw.get("updated"))                  # Greenhouse: the employer touched the posting after first publishing it
    # Credit every feed, on the card ("via ...") and in the application record ("credit"): each free feed asks for it, and an employer board is the employer's own
    out["via"] = VIA.get(kind, "%s").replace("%s", name) + (", listed by " + list_credit if list_credit else "")
    out["credit"] = "via USAJOBS; apply on the official announcement" if kind == "usajobs" else "via " + out["via"]
    if (raw.get("announcement") or "").startswith("https://"):
        out["announcement"] = raw["announcement"]                 # USAJOBS: the official announcement, kept next to the apply link
    return out


_refreshing = {}          # source -> threading.Event, set when the read in progress is done (see _start_refresh)


def known_webhook(job_id):
    """(url, secret) the employer registered for this job, or None. Only partner employers have one."""
    partner_jobs()
    return _hooks.get(job_id)


def job_info(job_id):
    """What this server itself holds about a job (partner list or feed cache), or None. Used so an email describes the job from
    our own data rather than from whatever the browser sends."""
    for j in partner_jobs():
        if j["id"] == job_id:
            return j
    with _lock:
        for c in _cache.values():
            for j in c["jobs"]:
                if j["id"] == job_id:
                    return j
    return None


def known_contact(job_id):
    """The recruiter address this server itself holds for a job ('' if none or unknown). Only partner employers have one."""
    for j in partner_jobs():
        if j["id"] == job_id:
            return j.get("contact", "") or ""
    with _lock:
        for c in _cache.values():
            for j in c["jobs"]:
                if j["id"] == job_id:
                    return j.get("contact", "") or ""
    return ""


FIRST_WAIT = 90                  # seconds the very first request on an empty disk waits for a board (every later request waits for none)
_failed = {}                     # source -> (when, status) of a read that failed with no copy to fall back on: not tried again for 2 minutes


def _trim():
    """Hand memory freed after reading the boards back to the system (Linux, glibc). Without it the process keeps its high-water mark."""
    try:
        import ctypes
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass


SAVE_EVERY = 30                  # seconds: while many boards are being read, the saved copy is written at most this often (and after the last one)


def _refresh_in_background(src, done):
    try:
        _fetch_source(src)
        with _lock:
            others = len(_refreshing) > 1
        if not others or time.time() - _disk.get("saved_at", 0) >= SAVE_EVERY:
            _save_disk()
    finally:
        with _lock:
            _refreshing.pop(src, None)
            last = not _refreshing
        done.set()
        if last:
            _save_disk()                         # the last board of a round: whatever a skipped save left unwritten goes to disk now
            _trim()


def _start_refresh(src):
    """Read one board in a background thread unless it is already being read. Call with _lock held. Returns the event set when it is done.
    Every read of a board goes through here, so a board is never read twice at once (on October 17 every visitor who arrived during the first
    fill read the missing boards again, alongside the warm-up)."""
    ev = _refreshing.get(src)
    if ev is None:
        ev = _refreshing[src] = threading.Event()
        threading.Thread(target=_refresh_in_background, args=(src, ev), daemon=True).start()
    return ev


def _load_source(src):
    """Serve what is cached right away, even if stale, and refresh it in the background. Never makes a visitor wait for a board while the
    saved list has anything to show (a board that is new, or failed last time, shows up at the next request). Only on an empty disk (the
    very first start) does the first request wait for the boards, as there is nothing else to show."""
    ttl = TTL.get(src[0], DEFAULT_TTL)
    if _no_key(src[0]):
        return _fetch_source(src)                # no key: skipped right away, never served from an older copy
    with _lock:
        c = _cache.get(src)
        if c:
            if time.time() - c["at"] >= ttl:
                _start_refresh(src)
            return c["jobs"], c["status"]
        f = _failed.get(src)
        if f and time.time() - f[0] < 120:
            return [], f[1]
        ev = _start_refresh(src)
        if _disk["filled"]:                      # the saved list has the other boards: do not hold this visitor up for this one
            return [], "loading"
    # every visitor of the first fill shares one deadline (FIRST_WAIT from the first wait), so the boards are waited for together
    with _lock:
        until = _disk.setdefault("first_wait_until", time.time() + FIRST_WAIT)
    ev.wait(max(0.0, until - time.time()))
    with _lock:
        c = _cache.get(src)
        f = _failed.get(src)
    return (c["jobs"], c["status"]) if c else ([], f[1] if f else "loading")


def _start_missing(sources):
    """On the very first fill, start reading every board that has nothing saved, all at once (FEED_PARALLEL of them actually download
    at a time), so the sources can then be collected one after another without a thread per source per visitor."""
    if _disk["filled"]:
        return
    keys = feed_keys()                     # read before the lock: it reads and parses the settings file
    with _lock:
        for src in sources:
            if not _no_key(src[0], keys) and src not in _cache and not (src in _failed and time.time() - _failed[src][0] < 120):
                _start_refresh(src)


# ---------- the Simplify / Pitt CSC internship lists (GitHub) ----------
SIMPLIFY_REPO = "https://raw.githubusercontent.com/SimplifyJobs/Summer2027-Internships/dev/"
SIMPLIFY_CHECK_TTL = 24 * 3600         # each listed posting is read from its own board at most once a day
# The apply links UAply can check on the employer's own public board, and the board API address each one is read from. The pieces are
# matched strictly (letters, digits, - _ . and numeric or uuid ids) and only ever put into these fixed API hosts: a list row can never
# make the server fetch an address of its choosing.
SIMPLIFY_ATS = [
    ("greenhouse", re.compile(r"^https://(?:job-)?boards\.greenhouse\.io/([A-Za-z0-9_-]{1,80})/jobs/(\d{1,20})(?:[/?#]|$)"),
     "https://boards-api.greenhouse.io/v1/boards/%s/jobs/%s"),
    ("lever", re.compile(r"^https://jobs\.lever\.co/([A-Za-z0-9_.-]{1,80})/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(?:[/?#]|$)"),
     "https://api.lever.co/v0/postings/%s/%s?mode=json"),
    ("smartrecruiters", re.compile(r"^https://jobs\.smartrecruiters\.com/([A-Za-z0-9_-]{1,80})/(\d{6,20})(?:[-/?#]|$)"),
     "https://api.smartrecruiters.com/v1/companies/%s/postings/%s"),
]
_simplify_checked = {}                 # (kind, board, posting id) -> {"at", "raw", "lists"}: raw is None when the posting is gone from its board
SIMPLIFY_TEXT = 4000                   # characters of a checked posting kept (skills, pay, schedule and the summary are read from the start)
SIMPLIFY_FIELDS = ("id", "title", "company", "loc", "remote", "text", "url", "salary_text", "posted", "updated", "emp", "ats_id", "country")


def _simplify_rows(text):
    """The open rows of one README table: (company, title, location, apply link, age in days). A row marked closed (a lock) or with no
    apply link is left out; a company cell of "↳" repeats the company above."""
    rows, company = [], ""
    for tr in re.findall(r"<tr>(.*?)</tr>", text, re.S):
        cells = re.findall(r"<td>(.*?)</td>", tr, re.S)
        if len(cells) < 5:
            continue
        name = _text(cells[0]).replace("\U0001f525", "").strip()
        company = company if name in ("↳", "") else name
        if "\U0001f512" in tr:
            continue
        # the summer list has 5 columns, the off-season one 6 (a Terms column): the apply cell is the one with the Apply button, the age is last
        apply_cell = next((c for c in cells if 'alt="Apply"' in c), "")
        link = re.search(r'<a href="(https://[^"]+)"', apply_cell)
        age = re.match(r"\s*(\d+)\s*(d|mo)\b", _text(cells[-1]))
        if not link or not age or not company:
            continue
        days = int(age.group(1)) * (30 if age.group(2) == "mo" else 1)
        place = "; ".join(p for p in (_text(x).strip() for x in re.split(r"<br\s*/?>|</br>", re.sub(r"<summary>.*?</summary>", "", cells[2], flags=re.S))) if p)
        rows.append((company, _text(cells[1]).strip(), place, html.unescape(link.group(1)).split("?", 1)[0], days))
    return rows


def _simplify_check(kind, board, pid, api):
    """The posting as its own board shows it (a raw posting), or None when the board no longer has it. Cached for SIMPLIFY_CHECK_TTL."""
    key = (kind, board, pid)
    with _lock:
        c = _simplify_checked.get(key)
    if c and time.time() - c["at"] < SIMPLIFY_CHECK_TTL:
        return c["raw"]
    raw = None
    try:
        j = _get(api % (urllib.parse.quote(board, safe=""), urllib.parse.quote(pid, safe="")))
        if kind == "greenhouse" and isinstance(j, dict) and j.get("id"):
            raw = dict(id=j["id"], title=j.get("title") or "", company=j.get("company_name") or "", loc=(j.get("location") or {}).get("name", ""),
                       remote=None, text=_text(j.get("content")), url=j.get("absolute_url") or "", salary_text="",
                       posted=_ts(j.get("first_published") or j.get("updated_at")), updated=_ts(j.get("updated_at")), emp=_gh_emp(j))
        elif kind == "lever" and isinstance(j, dict) and j.get("id"):
            cat = j.get("categories") or {}
            raw = dict(id=j["id"], title=j.get("text") or "", company="", loc=cat.get("location", "") or "", remote=(j.get("workplaceType") == "remote") or None,
                       text=_text((j.get("descriptionPlain") or "") + " " + (j.get("additionalPlain") or "")), url=j.get("hostedUrl") or "",
                       salary_text="", posted=_ts(j.get("createdAt")), emp=cat.get("commitment"))
        elif kind == "smartrecruiters" and isinstance(j, dict) and j.get("id") and j.get("active") is not False:
            L = j.get("location") or {}
            secs = ((j.get("jobAd") or {}).get("sections")) or {}
            raw = dict(id=j["id"], title=j.get("name") or "", company=(j.get("company") or {}).get("name") or "",
                       loc=", ".join(x for x in (L.get("city"), L.get("region"), (L.get("country") or "").upper()) if x), remote=True if L.get("remote") else None,
                       text=_text(" ".join((secs.get(k) or {}).get("text") or "" for k in ("jobDescription", "qualifications", "additionalInformation"))),
                       country=L.get("country") or "us",
                       url="https://jobs.smartrecruiters.com/%s/%s" % (board, j["id"]), salary_text="", posted=_ts(j.get("releasedDate")),
                       emp=((j.get("typeOfEmployment") or {}).get("label") or ""), ats_id=str(j.get("uuid") or ""))
        ok = True
    except urllib.error.HTTPError as e:
        ok = e.code in (404, 410)              # gone from the board: remembered as gone; any other error is tried again next time
    except Exception:
        ok = False
    if ok:
        if raw:                                # only what _simplify and _normalize read, and the start of the text (a posting can be 20,000 characters)
            raw = {k: raw[k] for k in SIMPLIFY_FIELDS if k in raw}
            raw["text"] = (raw.get("text") or "")[:SIMPLIFY_TEXT]
        with _lock:
            _simplify_checked[key] = {"at": time.time(), "raw": raw, "lists": set()}
    return raw


def _simplify_forget(token, keys_now):
    """After one list is read: entries this list no longer names lose it, and an entry no list names, or checked more than two days ago,
    is dropped (the map used to keep every posting ever checked)."""
    now = time.time()
    with _lock:
        for key in list(_simplify_checked):
            e = _simplify_checked[key]
            lists = e.setdefault("lists", set())
            if key in keys_now:
                lists.add(token)
            else:
                lists.discard(token)
            if not lists or now - e["at"] > 2 * SIMPLIFY_CHECK_TTL:
                del _simplify_checked[key]


def _simplify(token, name):
    """Open, recent (60 days at most), US rows of one Simplify / Pitt CSC README whose apply link is a Greenhouse, Lever or SmartRecruiters
    posting, each read from that board (newest rows first, at most KEEP["simplify"] checks). Rows on other systems cannot be checked and
    are left out. The README is plain text (about 1-2 MB): parsed and dropped before any check starts."""
    text = _get(SIMPLIFY_REPO + token, as_text=True)
    rows = _simplify_rows(text)
    del text
    todo, seen = [], set()
    for company, title, place, link, days in sorted(rows, key=lambda r: r[4]):
        if days > MAX_AGE_DAYS or not _us_ok(place, bool(re.search(r"\bremote\b", place, re.I))):
            continue
        for kind, rx, api in SIMPLIFY_ATS:
            m = rx.match(link)
            if m and (kind, m.group(1), m.group(2)) not in seen:
                seen.add((kind, m.group(1), m.group(2)))
                todo.append((company, kind, m.group(1), m.group(2), api))
                break
        if len(todo) >= KEEP["simplify"]:
            break
    with ThreadPoolExecutor(max_workers=4) as ex:                # four at a time, as for SmartRecruiters
        found = list(ex.map(lambda t: _simplify_check(t[1], t[2], t[3], t[4]), todo))
    _simplify_forget(token, {(k, b, i) for _, k, b, i, _ in todo})
    default = "internship" if token == "README.md" else None     # the summer list is internships only; the off-season one mixes co-ops in
    for (company, kind, board, pid, _), raw in zip(todo, found):
        if raw and raw["title"] and raw["url"].startswith("https://"):
            yield dict(raw, company=raw["company"] or company, ats_kind=kind, board=board, list_credit=name,
                       default_type=default or ("co-op" if re.search(r"\bco-?op\b", raw["title"], re.I) else "internship"))


def _no_key(kind, keys=None):
    """True for a feed that needs a key the owner has not added: USAJOBS (UAPLY_USAJOBS_KEY or feed_keys), CareerOneStop (both
    UAPLY_COS_USER_ID and UAPLY_COS_TOKEN). `keys`: feed_keys() already read (it reads uaply-config.json), for a caller checking many."""
    if kind not in ("usajobs", "careeronestop"):
        return False
    keys = feed_keys() if keys is None else keys
    return not keys.get("usajobs" if kind == "usajobs" else "cos_token")


def _fetch_source(src):
    kind, token, name = src
    ttl = TTL.get(kind, DEFAULT_TTL)
    if _no_key(kind):
        with _lock:
            _cache.pop(src, None)               # a key that was removed stops the source at once (no copy is served from before)
        return [], "no key"                     # skipped, nothing fetched or cached: the source starts the moment the owner adds the key
    try:
        student, other, local, old = [], [], [], 0
        now_ms = time.time() * 1000
        keep = KEEP.get(kind) if (kind != "smartrecruiters" or token in SR_WHOLE) else None   # a whole public list, or None for an employer board
        with _feed_slots:                        # at most FEED_PARALLEL boards downloaded and parsed at once (memory, see FEED_PARALLEL)
            for raw in _iter_raw(kind, token, name):
                if kind not in AGE_EXEMPT and _too_old(raw, now_ms) and not (kind in EVERGREEN_KINDS and _job_type(raw) in EVERGREEN_TYPES):
                    # (before the caps, so a stale posting never takes a fresh one's place)
                    old += 1
                    continue
                # only the first STUDENT_PER_SOURCE student roles and PER_SOURCE others can be kept below, so a posting past those is not worked
                # through at all (a big board lists hundreds; reading every one cost about 35 CPU seconds, a minute or more on a small host)
                bucket, cap = (other, PER_SOURCE) if _type(raw) == "job" else (student, STUDENT_PER_SOURCE)
                if keep:                                             # the City and USAJOBS keep up to 120 (student roles first), so read them all
                    cap = keep
                if len(bucket) >= cap:
                    # past the caps only a Pennsylvania, New Jersey or Delaware role is still worked through, up to LOCAL_PER_SOURCE of them
                    if not keep and len(local) < LOCAL_PER_SOURCE and LOCAL_RE.search(raw.get("loc") or ""):
                        j = _normalize(raw, kind, name, token)
                        if j:
                            local.append(j)
                    continue
                j = _normalize(raw, kind, name, token)
                if j:
                    (student if j["type"] in ("internship", "coop", "parttime") else other).append(j)
        # keep the student-type roles first (a board can list hundreds of senior roles ahead of its internships)
        if keep:
            jobs = (student + other)[:keep]
        else:
            n_other = max(OTHER_PER_SOURCE, PER_SOURCE - len(student[:STUDENT_PER_SOURCE]))
            jobs = student[:STUDENT_PER_SOURCE] + other[:n_other]
            # tri-state roles cut by the split above go first among the extras, then the ones found past the caps
            spill = [j for j in other[n_other:] if LOCAL_RE.search(j["loc"])]
            jobs += (spill + local)[:LOCAL_PER_SOURCE]
        status = "%d jobs" % len(jobs) + ("; %d older than %d days left out" % (old, MAX_AGE_DAYS) if old else "")
    except Exception as e:                      # keep serving the last good copy if the feed is down
        c = _cache.get(src)
        jobs = c["jobs"] if c else []
        why = _scrub(str(e))                    # a feed key is never written to the log or the status line
        if isinstance(e, urllib.error.HTTPError) and e.code in (401, 403) and kind in ("usajobs", "muse"):
            why = "the feed refused the key (HTTP %d); check it on the setup page" % e.code
        status = "error: %s" % why[:80]
        sys.stderr.write("[uaply] job feed %s failed: %s\n" % ("/".join(src), why[:200]))      # the reason is kept in the server's own log
        with _lock:
            if c:
                c["at"] = time.time() - ttl + 120   # retry in two minutes
            else:
                _failed[src] = (time.time(), status)   # nothing to fall back on: say so, and try again in two minutes (not at every request)
        return jobs, status
    with _lock:
        _cache[src] = {"at": time.time(), "jobs": jobs, "status": status}
        _failed.pop(src, None)
        _disk["dirty"] = True
    return jobs, status


def _cfg():
    """uaply-config.json, with UAPLY_CONFIG_JSON from the environment on top (same rule as uaply_api.config)."""
    cfg = {}
    try:
        if os.environ.get("UAPLY_CONFIG_FILE") != "none":      # same rule as uaply_api.config
            with open(os.path.join(ROOT, "uaply-config.json"), encoding="utf-8") as f:
                cfg.update(json.load(f))
    except Exception:
        pass
    try:
        env = json.loads(os.environ.get("UAPLY_CONFIG_JSON") or "{}")
        if isinstance(env, dict):
            cfg.update(env)
    except ValueError:
        pass
    return cfg


def feeds_allowed():
    """Third-party feeds the owner has explicitly switched on (default: none). See the legal notes at the top.
    A source kind is on when it is listed in "feeds" (uaply-config.json / UAPLY_CONFIG_JSON) or in UAPLY_FEEDS. "feeds_off" (a list, or
    UAPLY_FEEDS_OFF=remotive,muse) switches a kind off by name and wins over both, so one line turns a feed off without touching the others:
    {"feeds_off": ["remotive"]}. The kinds: greenhouse, lever, ashby, smartrecruiters, workable, usajobs, jobicy, muse, remotive."""
    cfg = _cfg()
    f, off = cfg.get("feeds"), cfg.get("feeds_off")
    on = {x for x in f if isinstance(x, str)} if isinstance(f, list) else set()
    on |= {x.strip().lower() for x in (os.environ.get("UAPLY_FEEDS") or "").split(",") if x.strip()}     # e.g. UAPLY_FEEDS=greenhouse,lever,ashby
    off = {x.strip().lower() for x in off if isinstance(x, str)} if isinstance(off, list) else set()
    off |= {x.strip().lower() for x in (os.environ.get("UAPLY_FEEDS_OFF") or "").split(",") if x.strip()}
    return on - off


# ---- partner employers: postings an employer gave us and who agreed to receive applications ----
_partners = {"path": None, "mtime": None, "jobs": []}
_hooks = {}          # job id -> (webhook url, secret). Kept apart from the job dicts: those go to browsers, the secret must not
_ats_jobs = {}       # partner job id -> {kind, board, id, key}: the employer's own hiring system. Same rule: the key never goes to a browser
_ats_conn = {"stamp": None, "map": {}}


def _clean(v, n):
    return re.sub(r"\s+", " ", v).strip()[:n] if isinstance(v, str) else ""


def partners_file(for_writing=False):
    """Where the employer list is kept: on a host on the persistent disk (UAPLY_DATA_DIR), else next to the code. With for_writing, the path to create.
    With UAPLY_DATA_DIR set, ONLY that folder is used. It used to fall back to the file next to the code, so a test run (which always sets
    UAPLY_DATA_DIR) read the owner's real employer list and the Connect box test wrote a test key into it; and on a host a first save went
    to the code folder, which a redeploy wipes."""
    folder = os.environ.get("UAPLY_DATA_DIR") or ROOT
    path = os.path.join(folder, "uaply-partners.json")
    return path if (for_writing or os.path.exists(path)) else None


def _file_stamp(path):
    """What tells a changed file from an unchanged one: the modification time to the nanosecond and the size. The time alone can stay the
    same across two quick writes (a busy computer, a coarse file system), so a removed connection or employer could keep being served."""
    st = os.stat(path)
    return (st.st_mtime_ns, st.st_size)


def ats_connections():
    """{(kind, board): api_key} for employers who connected their own hiring system (Greenhouse, Lever, Ashby, SmartRecruiters or Workable) with a key they created. Read from the
    UAPLY_ATS_JSON setting (a host's dashboard) and from 'ats_connections' in the employer list. Anything malformed is skipped."""
    env, path = os.environ.get("UAPLY_ATS_JSON") or "", partners_file()
    try:
        stamp = (env, path, _file_stamp(path) if path else None)
    except OSError:
        stamp = (env, path, None)
    if _ats_conn["stamp"] == stamp:
        return _ats_conn["map"]
    lists = []
    if env:
        try:
            lists.append(json.loads(env))
        except ValueError:
            pass
    if path:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                lists.append(data.get("ats_connections"))
        except Exception:
            pass
    out = {}
    for lst in lists:
        for c in (lst if isinstance(lst, list) else []):
            if isinstance(c, dict) and ats_api.valid_connection(c.get("kind"), c.get("board"), c.get("api_key")):
                out[(c["kind"], c["board"])] = c["api_key"]
    _ats_conn.update(stamp=stamp, map=out)
    return out


def partner_jobs():
    """Every job an employer gave UAply directly: the partner list plus postings made in Hiring mode (sandbox only)."""
    import employers_api           # imported here: employers_api imports uaply_api, which imports this module
    return _file_partner_jobs() + employers_api.feed_jobs()


def _file_partner_jobs():
    """Jobs from uaply-partners.json. Each employer must record how it consented. An employer with a contact address
    receives applications directly; without one it is link-out only. partners.example.json is documentation only and is
    never served as jobs."""
    # on a host, keep the real list on the persistent disk (UAPLY_DATA_DIR) so it is never in the repository
    path = partners_file()
    if not path:
        return []
    try:
        mtime = _file_stamp(path)
        if _partners["path"] == path and _partners["mtime"] == mtime:
            return _partners["jobs"]
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return _partners["jobs"]
    out = []
    new_hooks, new_ats = {}, {}
    for e in data.get("employers", []) if isinstance(data, dict) else []:
        name, consent = _clean(e.get("name"), 100), _clean(e.get("consent"), 300)
        if not name or not consent or consent.lower().startswith("placeholder"):
            continue                                   # no recorded consent (or the example text still in place), no listing
        # the employer's own hiring system (Greenhouse, Lever, Ashby, SmartRecruiters or Workable) and the key they created for it: applications to their jobs go straight in
        a = e.get("ats") if isinstance(e.get("ats"), dict) else {}
        ats_cfg = a if ats_api.valid_connection(a.get("kind"), a.get("board"), a.get("api_key")) else None
        contact = _clean(e.get("contact"), 120)
        contact = contact if re.match(r"^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$", contact) else ""
        # Indeed-style delivery: an HTTPS address the employer registered; each application is POSTed there as signed JSON
        hook_url = _clean(e.get("webhook"), 400)
        local_ok = os.environ.get("UAPLY_ALLOW_LOCAL_WEBHOOK") == "1" and re.match(r"^http://(127\.0\.0\.1|localhost)[:/]", hook_url)
        hook = (hook_url, _clean(e.get("webhook_secret"), 200)) if (hook_url.startswith("https://") or local_ok) and " " not in hook_url else None
        for j in e.get("jobs", []):
            raw_skills = j.get("skills")
            role, skills = _clean(j.get("role"), 120), [_clean(s, 40) for s in (raw_skills if isinstance(raw_skills, list) else [])[:6] if _clean(s, 40)]
            if not role or not skills:
                continue
            url = _clean(j.get("url") or e.get("url"), 400)
            sal = j.get("sal") if isinstance(j.get("sal"), list) and len(j["sal"]) == 2 else [0, 0]
            try:
                sal = [max(0, int(sal[0])), max(0, int(sal[1]))]
            except (TypeError, ValueError):
                sal = [0, 0]
            jid = 200000 + int(hashlib.sha1(("partner:%s:%s" % (name, role)).encode()).hexdigest()[:6], 16)
            if hook:
                new_hooks[jid] = hook
            ats_id = _clean(j.get("ats_job_id"), 80)
            ats = {"kind": ats_cfg["kind"], "board": ats_cfg["board"], "id": ats_id, "key": ats_cfg["api_key"]} if (ats_cfg and ats_api.ID_RE.match(ats_id)) else None
            if ats:
                new_ats[jid] = ats
            out.append(dict(
                id=jid,
                co=name, role=role, loc=_clean(j.get("loc"), 80) or "Not listed",
                mode=j.get("mode") if j.get("mode") in ("remote", "hybrid", "onsite") else "remote", sal=sal,
                yrs=min(15, max(0, int(j.get("yrs") or 0))) if str(j.get("yrs") or 0).isdigit() else 0,
                edu=j.get("edu") if j.get("edu") in ("High school", "Associate", "Bachelor", "Master", "Doctorate") else "High school",
                skills=skills, blurb=_clean(j.get("blurb"), 220),
                type=j.get("type") if j.get("type") in ("job", "parttime", "internship", "coop") else "job",
                url=url if url.startswith("https://") else "", source="Direct from %s (partner employer)" % name,
                contact=contact, apply="direct" if (contact or hook or ats) else "link", webhook=bool(hook), partner=True, live=True,
                instant=bool(contact or hook or ats),       # the card says "Apply instantly": swipe right really sends the application
                # optional filter data the employer can give: "posted" (a date), "perks" (keys from PERK_RES), "commission_only"
                posted=_ts(j.get("posted")),
                perks=sorted(set([p for p in (j.get("perks") or []) if p in PERK_KEYS] + _perks(j.get("blurb") or ""))),
                comm=j.get("commission_only") is True or bool(COMM_RE.search(j.get("blurb") or ""))))
    _partners.update(path=path, mtime=mtime, jobs=out)
    _hooks.clear()
    _hooks.update(new_hooks)
    _ats_jobs.clear()
    _ats_jobs.update(new_ats)
    return out


def job_policy(job_id):
    """How an application to this job may be handled: 'direct' (the employer opted in), 'link' (send the person to the
    employer's own page; nothing is emailed) or 'unknown' (an example listing)."""
    for j in partner_jobs():
        if j["id"] == job_id:
            return j["apply"]
    conns = ats_connections()
    with _lock:
        for c in _cache.values():
            for j in c["jobs"]:
                if j["id"] == job_id:
                    # a real posting whose employer connected their hiring system with their own key can be applied to instantly
                    return "direct" if _connected(j, conns) else "link"
    return "unknown"


def _connected(job, conns):
    """True when this feed posting's employer connected their hiring system (so a swipe right can send the application into it)."""
    a = job.get("ats") if isinstance(job, dict) else None
    return bool(a and (a.get("kind"), a.get("board")) in conns)


def known_ats(job_id):
    """{kind, board, id, key} for the hiring system this server may send an application to for this job, or None. Either a partner employer that gave
    its key with its jobs, or a real posting whose employer connected. Only this server ever holds the key; browsers get only a yes in 'instant'."""
    partner_jobs()
    a = _ats_jobs.get(job_id)
    if a:
        return dict(a)
    conns = ats_connections()
    with _lock:
        for c in _cache.values():
            for j in c["jobs"]:
                if j["id"] == job_id and _connected(j, conns):
                    return {"kind": j["ats"]["kind"], "board": j["ats"]["board"], "id": j["ats"]["id"], "key": conns[(j["ats"]["kind"], j["ats"]["board"])]}
    return None


_LOAD_SOURCE = _load_source


def get_jobs():
    _load_disk()
    allowed = feeds_allowed()
    sources = [s for s in SOURCES if s[0] in allowed]
    # One after another, not a thread per source: with 80 sources and three visitors on a fresh start that was 240 threads waiting
    # (about 30 MB of the 135 MB peak, October 21, 2026). The boards themselves are read in the background (_start_refresh).
    if _load_source is _LOAD_SOURCE:                 # (a test that stands in its own _load_source reads nothing)
        _start_missing(sources)
    results = [_load_source(src) for src in sources]
    _disk["filled"] = True
    jobs, seen, same, summary = [], set(), {}, {}            # same: a job's _same_job_key -> the source that listed it first
    now_ms = time.time() * 1000
    merged = aged = 0
    for pj in partner_jobs():
        seen.add(pj["id"])
        same[_same_job_key(pj)] = "partner"  # a feed's copy of a partner's posting is dropped below: the partner's own one can really be applied to
        jobs.append(_with_age({k: v for k, v in pj.items() if k != "contact"} if pj.get("emp") else pj, now_ms))    # an employer's account email stays on this server
    summary["Partner employers"] = "%d jobs" % len(jobs)
    # Feeds in SOURCES order, so when two feeds carry the same job the employer's own board (listed first) is the copy that is kept.
    # Only copies from two different feeds are merged: one employer listing a title twice in one place (the City's two "Technical Support
    # Specialist" postings are for different departments) keeps both, as they can be two openings.
    for src, (js, status) in zip(sources, results):
        summary[src[2] + ("/" + src[1] if src[0] in MULTI else "")] = "unavailable right now" if hide_errors and status.startswith("error") else status
        for j in js:
            if j["id"] in seen:
                continue
            if src[0] not in AGE_EXEMPT and _too_old(j, now_ms) and not (src[0] in EVERGREEN_KINDS and j.get("jobType") in EVERGREEN_TYPES):
                # (a saved copy can be up to a day old: one that turned 60 days since goes now)
                aged += 1
                continue
            key = _same_job_key(j)
            if same.get(key, src) != src:
                merged += 1
                continue
            seen.add(j["id"])
            same.setdefault(key, src)
            jobs.append(_with_age(j, now_ms))
    if not sources:
        summary["Third-party feeds"] = "off (not verified as permitted)"
    conns = ats_connections()
    if conns:           # a posting whose employer connected is marked here, on a copy, so the shared cache stays as fetched
        jobs = [dict(j, apply="direct", instant=True) if _connected(j, conns) else j for j in jobs]
    _save_disk()
    return {"fetched_at": int(time.time()), "sources": summary, "jobs": jobs, "merged": merged, "aged_out": aged}


def get_json():
    return json.dumps(get_jobs()).encode("utf-8")
