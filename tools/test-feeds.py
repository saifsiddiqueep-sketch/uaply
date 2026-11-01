"""Tests the job sources added for launch (USAJOBS, the City of Philadelphia on SmartRecruiters), The Muse key, the "via" credit on every job,
the Job feed keys box on /setup and the feeds_off switch. No network: every feed answer comes from tools/fixtures/ (a recorded City of
Philadelphia answer and a USAJOBS sample built from its documented schema). All keys here are fake.
  python tools/test-feeds.py [port]
With a port it also starts a throwaway copy of the server (from a temporary copy of the code, so a saved key never lands next to the real
code) and checks the save endpoint over HTTP, the job list, and, when Chrome is installed, the card in a real browser (tools/ui-via.js)."""
import contextlib
import glob
import io
import gzip
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
TMP = tempfile.mkdtemp(prefix="uaply-feeds-")
os.environ["UAPLY_CONFIG_FILE"] = "none"            # never the owner's settings
os.environ["UAPLY_DATA_DIR"] = TMP
os.environ["UAPLY_CONFIG_JSON"] = "{}"
for v in ("UAPLY_FEEDS", "UAPLY_FEEDS_OFF"):
    os.environ.pop(v, None)

import jobs_api as J  # noqa: E402
# The recorded answers in tools/fixtures/ are fixed in time, so the 60-day rule would drop more of them every week and these counts would
# drift. It is switched off here; tools/test-jobs.py tests the rule itself against a fixed clock.
J.MAX_AGE_DAYS = 10 ** 6
import setup_api  # noqa: E402
import uaply_api  # noqa: E402
import emails  # noqa: E402

R = []


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


def cfg(**kw):
    os.environ["UAPLY_CONFIG_JSON"] = json.dumps(kw)


with open(os.path.join(HERE, "fixtures", "usajobs-sample.json"), encoding="utf-8") as f:
    USA = json.load(f)
with open(os.path.join(HERE, "fixtures", "smartrecruiters-cityofphiladelphia.json"), encoding="utf-8") as f:
    SR = json.load(f)
KEY = "FAKEusajobsKey0123456789abcdefABCDEFGH+/="          # shaped like a USAJOBS key, but made up
MUSE = "fake0muse0key0123456789abcdef0123456789abcdef"
CALLS = []


def fake_get(url, headers=None):
    """Answers like the real APIs, from the fixtures. Records every request."""
    CALLS.append((url, dict(headers or {})))
    if url.startswith("https://data.usajobs.gov/"):
        return USA["students" if "HiringPath=" in url else "philadelphia"]
    if url.startswith("https://api.smartrecruiters.com/"):
        if "?" in url:
            return SR["list"]
        d = SR["details"].get(url.rsplit("/", 1)[1])
        if d is None:
            raise OSError("no recorded description")             # most postings have no recorded description: the list entry is used
        return d
    if url.startswith("https://www.themuse.com/"):
        return {"results": []}
    raise OSError("unexpected request " + url)


J._get = fake_get
USA_PHL, USA_STU = ("usajobs", "philadelphia", "USAJOBS"), ("usajobs", "students", "USAJOBS")
CITY = ("smartrecruiters", "CityofPhiladelphia", "City of Philadelphia")

# ---------------- USAJOBS ----------------
cfg()
CALLS.clear()
t("USAJOBS without a key is skipped with the status 'no key'", J._fetch_source(USA_PHL), ([], "no key"))
t("...and nothing was requested or cached", (len(CALLS), USA_PHL in J._cache), (0, False))
cfg(feeds=["usajobs"])
summ = J.get_jobs()["sources"]
t("the job list names all 15 USAJOBS searches as 'no key'", sorted({v for k, v in summ.items() if k.startswith("USAJOBS/")}) + [len([k for k in summ if k.startswith("USAJOBS/")])],
  ["no key", 15])
want_areas = {"philadelphia": ("Philadelphia, Pennsylvania", "50"), "wilmington": ("Wilmington, Delaware", "40"), "trenton": ("Trenton, New Jersey", "40"),
              "newark": ("Newark, New Jersey", "40"), "camden": ("Camden, New Jersey", "25")}
t("USAJOBS covers the tri-state: five places and radii, each also for Pathways and part-time schedules",
  sorted((k, q["LocationName"], q["Radius"], q.get("HiringPath", ""), q.get("PositionScheduleTypeCode", "")) for k, q in J.USAJOBS_QUERIES.items() if k not in ("students", "parttime")),
  sorted([(a, n, r, "", "") for a, (n, r) in want_areas.items()] + [(a + "-students", n, r, "student;graduates", "") for a, (n, r) in want_areas.items()] +
         [(a + "-parttime", n, r, "", "2") for a, (n, r) in want_areas.items()]))
t("15 searches every 3 hours: 120 USAJOBS requests a day", (len([x for x in J.SOURCES if x[0] == "usajobs"]), 24 // (J.TTL["usajobs"] // 3600) * 15), (15, 120))

cfg(feed_keys={"usajobs": KEY})
CALLS.clear()
jobs, status = J._fetch_source(USA_PHL)
url, hdr = CALLS[0]
t("with a key: one search, answered", (len(CALLS), status), (1, "3 jobs"))
t("the search is Philadelphia, 50 miles, 500 a page, full fields",
  url, "https://data.usajobs.gov/api/search?LocationName=Philadelphia,%20Pennsylvania&Radius=50&ResultsPerPage=500&Fields=Full&Page=1")
t("the headers are the ones USAJOBS documents (Host, User-Agent = email, Authorization-Key)",
  (hdr.get("Host"), hdr.get("User-Agent"), hdr.get("Authorization-Key")), ("data.usajobs.gov", "uaplytechnologies@gmail.com", KEY))
by = {j["role"]: j for j in jobs}
it = by.get("IT Specialist (Applications Software)") or {}
t("PositionTitle, OrganizationName, PositionLocationDisplay -> title, employer, place",
  (it.get("role"), it.get("co"), it.get("loc")), ("IT Specialist (Applications Software)", "Defense Logistics Agency", "Philadelphia, Pennsylvania"))
t("yearly PositionRemuneration -> pay", it.get("sal"), [92108, 119746])
t("ApplyURI[0] -> the link, PositionURI kept as the official announcement",
  (it.get("url"), it.get("announcement")), ("https://www.usajobs.gov:443/job/900000101/apply", "https://www.usajobs.gov/job/900000101"))
t("PublicationStartDate (with its 4-digit fraction) -> the posting date", it.get("posted"), 1790812800000)
t("JobSummary and MajorDuties -> the text the summary is made from", ("supply chain software" in it.get("desc", ""), "Python and SQL development" in it.get("desc", "")), (True, True))
t("source 'USAJOBS', link-out only, never a recruiter address", (it.get("source"), it.get("apply"), it.get("contact")), ("USAJOBS", "link", ""))
t("the credit line on the record", (it.get("via"), it.get("credit")), ("USAJOBS", "via USAJOBS; apply on the official announcement"))
cs = by.get("Contract Specialist") or {}
t("'Multiple Locations' names the first two places", cs.get("loc"), "Philadelphia, Pennsylvania; Camden, New Jersey +1 more")
t("no ApplyURI: the announcement is the link", cs.get("url"), "https://www.usajobs.gov/job/900000102")
t("hourly pay stays hourly, as the posting gives it (never turned into a yearly range)", (cs.get("sal"), cs.get("salUnit")), ([28.1, 36.5], "hour"))
t("a yearly range carries no hourly unit", it.get("salUnit"), None)
# pay is read as the posting gives it, never guessed or converted (October 23: "Pay not listed" rule)
t("text: '$18 - $22 per hour' and '$28.10-$36.50/hr' are hourly ranges as written", (J._hourly("Pay: $18 - $22 per hour"), J._hourly("$28.10 - $36.50/hr")), ([18.0, 22.0], [28.1, 36.5]))
t("text: 'competitive pay', 'up to $25/hr', '$80k+' give no pay at all (nothing estimated)", (J._hourly("competitive pay"), J._hourly("up to $25/hr"), J._salary("Salary: $80k+")), (None, None, [0, 0]))
t("text: a yearly range is never read as hourly", J._hourly("$120,000 - $140,000 per year"), None)
import emails as EM   # noqa: E402
t("the application summary's pay line: yearly a year, hourly an hour, none 'Not listed'",
  (EM._money([60000, 80000]), EM._money([18, 22.5], "hour"), EM._money([0, 0])), ("$60k to $80k a year", "$18 to $22.50 an hour", "Not listed"))
t("an overseas posting (Ramstein, Germany) is dropped by the US rule", "Budget Analyst" in by, False)
rm = by.get("Management and Program Analyst") or {}
t("a remote federal job is kept as remote", (rm.get("mode"), rm.get("loc")), ("remote", "Anywhere in the U.S. (remote job)"))

CALLS.clear()
jobs, status = J._fetch_source(USA_STU)
t("the student search adds HiringPath=student;graduates", CALLS[0][0].endswith("&HiringPath=student;graduates&Page=1"), True)

one_page = len(J._usajobs("philadelphia"))
def two_pages(url, headers=None):
    CALLS.append((url, dict(headers or {})))
    d = json.loads(json.dumps(USA["philadelphia"]))
    d["SearchResult"]["UserArea"] = {"NumberOfPages": "2"}               # the API sends the page count as text
    return d
CALLS.clear()
J._get = two_pages
both = len(J._usajobs("philadelphia"))
J._get = fake_get
t("a search with more than one page reads every page (Page=1, Page=2) and keeps the jobs of both",
  ([c[0].rsplit("&", 1)[1] for c in CALLS], both), (["Page=1", "Page=2"], 2 * one_page))
t("USAJOBS keeps every job a search lists, not 120", J.KEEP["usajobs"] >= J.USAJOBS_MAX_PAGES * 500, True)
types = {j["role"]: j["type"] for j in jobs}
t("'Student Trainee' on the Students hiring path is an internship", types.get("Student Trainee (Information Technology)"), "internship")
t("a 'Pathways Intern' title is an internship", types.get("Pathways Intern - Engineering"), "internship")
t("a Recent Graduates posting stays an entry-level job", types.get("Accountant (Recent Graduate)"), "job")
t("internships come first in the kept list", jobs[0]["type"], "internship")

cfg(feed_keys={"usajobs": KEY, "usajobs_email": "owner.feeds@example.com"}, owner_copy="copy@example.com")
CALLS.clear()
J._fetch_source(USA_PHL)
t("the email the key was requested with is the User-Agent", CALLS[0][1].get("User-Agent"), "owner.feeds@example.com")
cfg(feed_keys={"usajobs": KEY}, owner_copy="copy@example.com")
CALLS.clear()
J._fetch_source(USA_PHL)
t("...else the owner's email from the settings", CALLS[0][1].get("User-Agent"), "copy@example.com")
cfg(feed_keys={"usajobs": "short"})
t("a key that is not key-shaped counts as no key", J._fetch_source(USA_PHL), ([], "no key"))

# a removed key stops the source at once, even with a fresh copy in the cache
cfg(feed_keys={"usajobs": KEY})
J._load_source(USA_PHL)
cfg()
t("after the key is removed, the cached federal jobs are not served", J._load_source(USA_PHL), ([], "no key"))

# a refused key, and a key inside an error message, never reach the status line or the log
real_get = J._get


def refuse(url, headers=None):
    raise urllib.error.HTTPError(url, 401, "Unauthorized", {}, None)


def leak(url, headers=None):
    raise OSError("connection reset while reading " + url + " key=" + (headers or {}).get("Authorization-Key", ""))


cfg(feed_keys={"usajobs": KEY, "muse": MUSE})
for label, fn, src in (("a refused USAJOBS key", refuse, USA_PHL), ("an error naming the USAJOBS key", leak, USA_STU), ("an error naming The Muse key in its address", leak, ("muse", "Internship", "The Muse"))):
    J._get = fn
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        _, status = J._fetch_source(src)
    t("%s: the status says what went wrong without the key" % label, (status.startswith("error"), KEY in status, MUSE in status), (True, False, False))
    t("%s: the server log line has no key" % label, (KEY in err.getvalue(), MUSE in err.getvalue(), len(err.getvalue()) > 0), (False, False, True))
J._get = refuse
with contextlib.redirect_stderr(io.StringIO()):
    _, status = J._fetch_source(USA_PHL)
t("a refused key says so in plain words", "refused the key (HTTP 401)" in status, True)
J._get = real_get

# ---------------- The Muse key ----------------
for keys, want in (({}, False), ({"muse": MUSE}, True)):
    cfg(feed_keys=keys)
    CALLS.clear()
    J._fetch_source(("muse", "Entry Level", "The Muse"))
    t("The Muse requests %s the api_key" % ("carry" if want else "do not carry"),
      [("api_key=" + MUSE) in u for u, _ in CALLS], [want, want])

# ---------------- City of Philadelphia on SmartRecruiters ----------------
cfg()
J._sr_desc.clear()
CALLS.clear()
jobs, status = J._fetch_source(CITY)
lists = [u for u, _ in CALLS if "?" in u]
details = [u for u, _ in CALLS if "?" not in u]
t("all 67 recorded City postings are kept", (status, len(jobs)), ("67 jobs", 67))
t("one list request (totalFound 67 fits one page of 100) and one description read per posting",
  (lists, len(details)), (["https://api.smartrecruiters.com/v1/companies/CityofPhiladelphia/postings?limit=100&offset=0"], 67))
e = next(j for j in jobs if j["url"].endswith("/744000155798810"))
t("name, company, city/region -> title, employer, place",
  (e["role"], e["co"], e["loc"]), ("EBS Technical – Interface Lead", "City of Philadelphia", "Philadelphia, PA"))
t("the job link is jobs.smartrecruiters.com/{company}/{id}", e["url"], "https://jobs.smartrecruiters.com/CityofPhiladelphia/744000155798810")
t("the description comes from jobAd.sections.jobDescription", "Interface Lead will play a key role" in e["desc"], True)
t("compensation (USD, yearly) -> pay", e["sal"], [85000, 95000])
t("releasedDate -> the posting date", e["posted"], J._ts("2026-10-15T15:58:25.580Z"))
t("typeOfEmployment Full-time with an ordinary title is a job", e["type"], "job")
t("source and credit", (e["source"], e["via"], e["credit"], e["apply"]),
  ("City of Philadelphia's careers page", "City of Philadelphia on SmartRecruiters", "via City of Philadelphia on SmartRecruiters", "link"))
nodesc = next(j for j in jobs if j["role"] == "IT Network Engineer")
t("a posting without a description still lists, matched on its department", (nodesc["skills"], nodesc["sal"]), (["Office of Innovation & Technology"], [0, 0]))
CALLS.clear()
J._fetch_source(CITY)
t("the next refresh reads only the list: descriptions come from the cache (one read per posting per day)", len(CALLS), 1)

# a re-released posting gets its description read again; nothing else does
orig = SR["list"]["content"][0]["releasedDate"]
SR["list"]["content"][0]["releasedDate"] = "2026-10-16T09:00:00.000Z"
CALLS.clear()
J._fetch_source(CITY)
t("a re-released posting is read again, alone", [u.rsplit("/", 1)[1] for u, _ in CALLS if "?" not in u], ["744000155798810"])
SR["list"]["content"][0]["releasedDate"] = orig

# pagination and the 120 cap: a company with 150 postings
base = SR["list"]["content"]
many = [dict(base[i % len(base)], id=str(900000000000 + i)) for i in range(150)]


def paged(url, headers=None):
    CALLS.append((url, {}))
    if "?" in url:
        off = int(url.split("offset=")[1].split("&")[0])
        rows = [m for m in many if ((m.get("location") or {}).get("country") or "us") == "us"] if "country=us" in url else many   # the API's own filter
        return {"offset": off, "limit": 100, "totalFound": len(rows), "content": rows[off:off + 100]}
    raise OSError("no description")


J._get = paged
J._sr_desc.clear()
CALLS.clear()
real_whole, J.SR_WHOLE = J.SR_WHOLE, ("BigCo",)                    # a public body's whole list (the City's rule)
jobs, status = J._fetch_source(("smartrecruiters", "BigCo", "BigCo"))
lists = [u.split("?")[1] for u, _ in CALLS if "?" in u]
t("pages are read 100 at a time by offset", lists, ["limit=100&offset=0", "limit=100&offset=100"])
t("no more than 120 postings are kept, and no more than 120 descriptions read", (len(jobs), len([1 for u, _ in CALLS if "?" not in u])), (120, 120))
J.SR_WHOLE = real_whole
# a company that is not a public body (Equinox, Red Bull): US postings only, tri-state ones first, at most SR_BOARD_READ (24) descriptions, 14 + tri-state extras
mixed = [dict(m, location=dict(m.get("location") or {}, country="de", region="BY", city="Munich")) if i % 3 == 0 else
         dict(m, location=dict(m.get("location") or {}, country="us", region="TX" if i % 3 == 1 else "NJ", city="Austin" if i % 3 == 1 else "Trenton"))
         for i, m in enumerate(many)]
many_saved, many[:] = list(many), mixed
J._sr_desc.clear()
CALLS.clear()
J._cache.pop(("smartrecruiters", "GymCo", "GymCo"), None)
jobs, status = J._fetch_source(("smartrecruiters", "GymCo", "GymCo"))
read = [u.rsplit("/", 1)[1] for u, _ in CALLS if "?" not in u]
by_id = {m["id"]: m for m in mixed}
t("an employer's SmartRecruiters board: at most 24 descriptions read, none for a posting outside the US",
  (len(read), sum(1 for i in read if by_id[i]["location"]["country"] != "us")), (J.SR_BOARD_READ, 0))
t("...New Jersey postings are read first", sum(1 for i in read if by_id[i]["location"]["region"] == "NJ"), J.SR_BOARD_READ)
t("...with one request for its US postings only (country=us); the City's whole list is read without it",
  [u.split("?")[1] for u, _ in CALLS if "?" in u], ["limit=100&offset=0&country=us"])
t("...and it keeps 14 plus up to 10 tri-state extras, never a German one", (len(jobs) <= 24, any("Munich" in j["loc"] for j in jobs)), (True, False))
many[:] = many_saved


def one(**over):
    p = dict(base[0], id="1", **over)
    return {"offset": 0, "limit": 100, "totalFound": 1, "content": [p]}


for label, over, want in (("typeOfEmployment Internship", {"typeOfEmployment": {"id": "intern", "label": "Internship"}}, "internship"),
                          ("typeOfEmployment Part-time", {"typeOfEmployment": {"id": "part_time", "label": "Part-time"}}, "parttime")):
    J._get = lambda url, headers=None, o=over: one(**o) if "?" in url else {}
    J._sr_desc.clear()
    jobs, _ = J._fetch_source(("smartrecruiters", "T", "T"))
    t("%s -> %s" % (label, want), [j["type"] for j in jobs], [want])
J._get = lambda url, headers=None: one(location={"city": "Toronto", "region": "ON", "country": "ca", "fullLocation": "Toronto, ON, Canada"}) if "?" in url else {}
J._sr_desc.clear()
t("a SmartRecruiters posting outside the US is dropped", J._fetch_source(("smartrecruiters", "T2", "T2"))[0], [])
J._get = fake_get

# ---------------- Recruitee: the careers site's public offers (a saved sample, tools/fixtures/recruitee-offers.json) ----------------
with open(os.path.join(HERE, "fixtures", "recruitee-offers.json"), encoding="utf-8") as f:
    RC = json.load(f)
RC_CALLS = []
real_items = J._get_items


def fake_items(url, key=None):
    RC_CALLS.append((url, key))
    if url == "https://acmedental.recruitee.com/api/offers/":
        return iter(RC[key])
    raise OSError("unexpected request " + url)


ROBOTS = {"acmedental.recruitee.com": ["User-agent: *", "Disallow: /v/"], "closeddental.recruitee.com": ["User-agent: *", "Disallow: /api/"]}
real_robots = J._robots_for


def fake_robots(host):
    RC_CALLS.append(("robots", host))
    if host not in ROBOTS:
        return None                                       # robots.txt could not be read
    rp = J.RobotsTxt()
    rp.parse(ROBOTS[host])
    return rp


J._get_items, J._robots_for = fake_items, fake_robots
RCS = ("recruitee", "acmedental", "Acme Dental Group")
rjobs, rstatus = J._fetch_source(RCS)
t("Recruitee: robots.txt is asked first, then one request for the careers site's own offers list", RC_CALLS, [("robots", "acmedental.recruitee.com"), ("https://acmedental.recruitee.com/api/offers/", "offers")])
RC_CALLS.clear()
closed = J._fetch_source(("recruitee", "closeddental", "Closed Dental"))
t("Recruitee: a site whose robots.txt disallows /api/ is not read (no jobs, no request for the offers)", (closed[0], RC_CALLS, "robots" in closed[1]),
  ([], [("robots", "closeddental.recruitee.com")], True))
RC_CALLS.clear()
unread = J._fetch_source(("recruitee", "unreadable", "Unreadable"))
t("Recruitee: a site whose robots.txt cannot be read is not read either", (unread[0], RC_CALLS), ([], [("robots", "unreadable.recruitee.com")]))
J._get_items, J._robots_for = real_items, real_robots
by = {j["role"]: j for j in rjobs}
t("Recruitee: the US offers are kept; London, an offer with a bad slug and a draft are not", sorted(by), ["Billing Specialist", "Dental Hygienist", "Front Desk Intern", "Practice Office Manager"])
t("Recruitee: the status line counts them", rstatus, "4 jobs")
hy = by["Dental Hygienist"]
t("Recruitee: a stable id, made from the offer number", (hy["id"], J._jid("recruitee", 9100001)), (hy["id"], hy["id"]))
t("Recruitee: ats is kind recruitee, the careers site, and the offer slug (where an application goes)", hy["ats"],
  {"kind": "recruitee", "board": "acmedental", "id": "dental-hygienist-philadelphia"})
t("Recruitee: the link is the posting, applyUrl its application form",
  (hy["url"], hy["applyUrl"]), ("https://acmedental.recruitee.com/o/dental-hygienist-philadelphia", "https://acmedental.recruitee.com/o/dental-hygienist-philadelphia/c/new"))
t("Recruitee: place, pay per hour, part-time, credit", (hy["loc"], hy["mode"], hy["sal"], hy.get("salUnit"), hy["jobType"], hy["via"]),
  ("Philadelphia, PA", "onsite", [32.0, 40.0], "hour", "part-time", "Acme Dental Group on Recruitee"))
t("Recruitee: the posted date is read from Recruitee's 'UTC' form", (hy["posted"], hy.get("updated")), (J._ts("2026-10-10T14:00:00+00:00"), J._ts("2026-10-12T09:30:00+00:00")))
om = by["Practice Office Manager"]
t("Recruitee: a remote US offer with a yearly range", (om["mode"], om["sal"], om.get("salUnit"), om["jobType"]), ("remote", [55000, 65000], None, "full-time"))
fd = by["Front Desk Intern"]
t("Recruitee: an offer in Dublin and Cherry Hill NJ is placed in its US place, and an internship", (fd["loc"], fd["jobType"], fd["type"]), ("Cherry Hill, NJ", "internship", "internship"))
bs = by["Billing Specialist"]
t("Recruitee: hybrid in Wilmington DE; a range in euros is not shown as dollars", (bs["mode"], bs["sal"]), ("hybrid", [0, 0]))
t("Recruitee: no key, no email: a hand-off like every feed job", (hy["apply"], hy["contact"], J.job_policy(hy["id"])), ("link", "", "link"))
t("Recruitee: the list form keeps only ats.kind and leaves applyUrl to GET /api/jobs/<id>",
  ({k: v for k, v in J._out_job(hy, 0, {}, True).items() if k in ("ats", "applyUrl")}, J._out_job(hy, 0, {}, True, full=True).get("applyUrl")),
  ({"ats": {"kind": "recruitee"}}, hy["applyUrl"]))
t("Recruitee boards from job-boards.json are read (kind recruitee is allowed there)", "recruitee" in J.BOARD_KINDS and any(s_[0] == "recruitee" for s_ in J.SOURCES), True)

# ---------------- the "via" credit for every kind ----------------
raw = dict(id=7, title="Data Analyst", company="Acme Corp", loc="Philadelphia, PA", remote=None, text="Python and SQL.", url="https://example.com/j/7", salary_text="", posted=0)
for kind, name, want in (("greenhouse", "Stripe", "Stripe on Greenhouse"), ("lever", "Spotify", "Spotify on Lever"), ("ashby", "Linear", "Linear on Ashby"),
                         ("smartrecruiters", "City of Philadelphia", "City of Philadelphia on SmartRecruiters"), ("jobicy", "Jobicy", "Jobicy"),
                         ("muse", "The Muse", "The Muse"), ("usajobs", "USAJOBS", "USAJOBS"), ("remotive", "Remotive", "Remotive")):
    n = J._normalize(dict(raw), kind, name, "board")
    t("%s jobs say 'via %s'" % (kind, want), (n["via"], n["credit"]),
      (want, "via USAJOBS; apply on the official announcement" if kind == "usajobs" else "via " + want))
t("partner and Hiring mode jobs carry no feed credit", [j for j in J.partner_jobs() if j.get("via")], [])

# ---------------- Workday, Rippling, Breezy HR, Teamtailor: each careers site's own public list (answers built inline, no network) ----------------
NK_CALLS = []
NK_ANS = {}
NK_OPENERS = []
real_get, real_robots = J._get, J._robots_for


def nk_get(url, headers=None, as_text=False, opener=None, data=None):
    NK_CALLS.append((url, dict(headers or {}), json.loads(data) if data else None))
    NK_OPENERS.append(opener)
    ans = NK_ANS.get(url)
    if callable(ans):
        return ans(json.loads(data) if data else None)
    if ans is None:
        raise OSError("unexpected request " + url)
    return ans


def nk_robots(host):
    NK_CALLS.append(("robots", host))
    rp = J.RobotsTxt()
    rp.parse(["User-agent: *", "Disallow: /private/"] if host not in ("closed.breezy.hr", "uaonly.breezy.hr") else
             ["User-agent: UAply-jobs", "Disallow: /"] if host == "uaonly.breezy.hr" else ["User-agent: *", "Disallow: /"])
    return rp


def nk_fetch(src):
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        got = J._fetch_source(src)
    return got[0], got[1], err.getvalue()


J._get, J._robots_for = nk_get, nk_robots
WD = "https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/AcmeCareers/jobs"


def wd_page(body):
    off = body["offset"]
    rows = [dict(title="Software Engineer %d" % i, externalPath="/job/US-CA-Santa-Clara/Software-Engineer-%d_JR%d" % (i, i),
                 locationsText="US, CA, Santa Clara", postedOn="Posted %d Days Ago" % (i % 9 + 2)) for i in range(off, min(off + 20, 25))]
    if off == 0:
        rows[0] = dict(title="Data Analyst Intern", externalPath="/job/US-TX-Austin/Data-Analyst-Intern_JR1", locationsText="3 Locations", postedOn="Posted Today")
        rows[1] = dict(title="Network Engineer", externalPath="/job/US-NC-Remote/Network-Engineer_JR2", locationsText="2 Locations", postedOn="Posted Yesterday")
        rows[2] = dict(title="Software Engineer", externalPath="/job/Taiwan-Taipei/Software-Engineer_JR3", locationsText="Taiwan, Taipei", postedOn="Posted 30+ Days Ago")
        return {"total": 25, "jobPostings": rows}
    rows[0] = dict(rows[0], externalPath="/job/US-TX-Austin/Data-Analyst-Intern_JR1")     # a posting repeated on the next page: read once
    return {"jobPostings": rows}          # Workday gives the total on the first page only


NK_ANS[WD] = wd_page
WDS = ("workday", "acme.wd5/AcmeCareers", "Acme Corp")
wraw = list(J._iter_raw(*WDS))
t("Workday: robots.txt first, then a POST of the job search, 20 at a time, until the first page's total",
  [c if c[0] == "robots" else (c[0], c[1].get("User-Agent"), c[1].get("Content-Type"), c[2]) for c in NK_CALLS],
  [("robots", "acme.wd5.myworkdayjobs.com"),
   (WD, "UAply-jobs/1.0 (+https://uaply.net)", "application/json", {"limit": 20, "offset": 0, "searchText": ""}),
   (WD, "UAply-jobs/1.0 (+https://uaply.net)", "application/json", {"limit": 20, "offset": 20, "searchText": ""})])
t("Workday: every posting once (one repeated on page 2 is not read twice)", len(wraw), 24)
by_wd = {r["id"]: r for r in wraw}
t("Workday: a posting in '3 Locations' is placed in the place its address names; Remote in its address is remote",
  (by_wd["/job/US-TX-Austin/Data-Analyst-Intern_JR1"]["loc"], by_wd["/job/US-NC-Remote/Network-Engineer_JR2"]["loc"], by_wd["/job/US-NC-Remote/Network-Engineer_JR2"]["remote"]),
  ("Austin, TX", "Remote, NC", True))
t("Workday: the link is the posting on the careers site", by_wd["/job/US-TX-Austin/Data-Analyst-Intern_JR1"]["url"],
  "https://acme.wd5.myworkdayjobs.com/AcmeCareers/job/US-TX-Austin/Data-Analyst-Intern_JR1")
now = time.time()
t("Workday: 'Posted Today', 'Yesterday', 'N Days Ago' and '30+ Days Ago' are dates", [round((now * 1000 - J._workday_posted(s, now)) / 86400000) for s in
  ("Posted Today", "Posted Yesterday", "Posted 4 Days Ago", "Posted 30+ Days Ago", "soon")], [0, 1, 4, 30, round(now / 86400)])
wjobs, wstatus, werr = nk_fetch(WDS)
t("Workday: the Taipei posting is left out; the rest are kept up to the per-board cap, credited 'on Workday'",
  (len(wjobs), any("Taipei" in j["loc"] for j in wjobs), wjobs[0]["via"], werr), (J.PER_SOURCE, False, "Acme Corp on Workday", ""))
NK_CALLS.clear()
NK_ANS[WD] = lambda body: {"total": 5000, "jobPostings": [dict(title="Software Engineer", externalPath="/job/US-CA-X/SE_%d" % (body["offset"] + i),
                                                                locationsText="US, CA, X", postedOn="Posted Today") for i in range(20)]}
t("Workday: at most 200 postings (10 searches) per site per refresh", (len(list(J._iter_raw(*WDS))), len([c for c in NK_CALLS if c[0] == WD])), (200, 10))
t("Workday: a site token is '{company}.wd{n}/{site}'; anything else is refused before an address is built",
  [J._board_token_ok("workday", x) for x in ("acme.wd5/AcmeCareers", "acme", "acme.wd5/../x", "evil.com/x", "acme.wd5/a/b", "acme.wd5.evil.com/x")],
  [True, False, False, False, False, False])
NK_CALLS.clear()
bad = nk_fetch(("workday", "acme", "Bad Token"))
t("Workday: a bad token asks for nothing and logs one failure line", (bad[0], NK_CALLS, bad[2].strip()),
  ([], [], "[uaply] job feed workday/acme/Bad Token failed: not a Workday site"))
t("Workday: a token with a trailing newline or a non-ASCII digit is refused (fullmatch, [0-9])",
  [J._board_token_ok("workday", x) for x in ("acme.wd5/AcmeCareers\n", "acme.wd\u0665/AcmeCareers")] + [J._board_token_ok("breezy", "acme\n")],
  [False, False, False])
WD2 = "https://geo.wd1.myworkdayjobs.com/wday/cxs/geo/Ext/jobs"
NK_ANS[WD2] = {"total": 2, "jobPostings": [
    dict(title="Analyst", externalPath="/job/Santa-Clara/Analyst_JR10", locationsText="US, CA, Santa Clara", postedOn="Posted Today"),
    dict(title="Nurse", externalPath="/job/US-PA-Philadelphia/Nurse_JR11", locationsText="2 Locations", postedOn="Posted Today")]}
geo_raw = list(J._iter_raw("workday", "geo.wd1/Ext", "Geo"))
t("Workday: 'US, CA, Santa Clara' (list text) and 'US-PA-Philadelphia' (address) become 'City, ST' and get a map point",
  [(r["loc"], bool(J.job_geo(r["loc"]))) for r in geo_raw], [("Santa Clara, CA", True), ("Philadelphia, PA", True)])
t("Workday: job_geo has a point for 'Santa Clara, CA' and 'Philadelphia, PA'", [J.job_geo(x) is not None for x in ("Santa Clara, CA", "Philadelphia, PA")], [True, True])
NK_CALLS.clear()
NK_ANS[WD] = lambda body: {"jobPostings": [dict(title="Engineer", externalPath="/job/US-CA-X/E_%d" % (body["offset"] + i), locationsText="US, CA, X",
                                                 postedOn="Posted Today") for i in range(20 if body["offset"] < 40 else 5)]}
t("Workday: a first page with no total is read on until a short page (still at most 10 searches)",
  (len(list(J._iter_raw(*WDS))), [c[2]["offset"] for c in NK_CALLS if c[0] == WD]), (45, [0, 20, 40]))
NK_CALLS.clear()
real_deadline, J.WORKDAY_DEADLINE = J.WORKDAY_DEADLINE, -1
t("Workday: past WORKDAY_DEADLINE no further search is started (what was read is kept)",
  (len(list(J._iter_raw(*WDS))), len([c for c in NK_CALLS if c[0] == WD])), (20, 1))
J.WORKDAY_DEADLINE = real_deadline
NK_ANS["https://bad.wd1.myworkdayjobs.com/wday/cxs/bad/Ext/jobs"] = lambda body: (
    {"jobPostings": [dict(title="E", externalPath="/job/US-CA-X/E_%d" % i, locationsText="US, CA, X") for i in range(20)]} if body["offset"] == 0
    else {"errorCode": "HTTP_500"})
bad_wd = nk_fetch(("workday", "bad.wd1/Ext", "Bad WD"))
t("Workday: a full first page with no total, then an answer with no jobPostings: the source is marked failed, nothing raised",
  (bad_wd[0], bad_wd[1].startswith("error:"), "[uaply] job feed workday/bad.wd1/Ext/Bad WD failed: the answer has no jobPostings list" in bad_wd[2]),
  ([], True, True))

RP = "https://api.rippling.com/platform/api/ats/v1/board/acme/jobs"
NK_ANS[RP] = [
    {"uuid": "11111111-aaaa", "name": " Account Executive (Arkansas) ", "department": {"id": "Sales", "label": "Sales"},
     "url": "https://ats.rippling.com/acme/jobs/11111111-aaaa", "workLocation": {"label": "AR", "id": "AR"}},
    {"uuid": "11111111-aaaa", "name": " Account Executive (Arkansas) ", "department": {"id": "Sales", "label": "Sales"},
     "url": "https://ats.rippling.com/acme/jobs/11111111-aaaa", "workLocation": {"label": "Boston, MA", "id": "x"}},
    {"uuid": "22222222-bbbb", "name": "Software Engineer", "department": {"label": "Engineering"},
     "url": "https://ats.rippling.com/acme/jobs/22222222-bbbb", "workLocation": {"label": "Hybrid (New York, New York, US)"}},
    {"uuid": "33333333-cccc", "name": "Software Engineer", "department": {"label": "Engineering"},
     "url": "https://ats.rippling.com/acme/jobs/33333333-cccc", "workLocation": {"label": "London, UK"}},
    {"uuid": "bad uuid!", "name": "Bad", "url": "https://ats.rippling.com/acme/jobs/x", "workLocation": {"label": "Boston, MA"}}]
NK_CALLS.clear()
rraw = list(J._iter_raw("rippling", "acme", "Acme"))
t("Rippling: robots.txt, then one GET of the board's jobs", [c if c[0] == "robots" else (c[0], c[1].get("User-Agent"), c[2]) for c in NK_CALLS],
  [("robots", "api.rippling.com"), (RP, "UAply-jobs/1.0 (+https://uaply.net)", None)])
t("Rippling: one posting per uuid with all its places (a bare state code is that state); a bad uuid is skipped",
  [(r["id"], r["title"], r["loc"], r["fallback"]) for r in rraw],
  [("11111111-aaaa", "Account Executive (Arkansas)", "AR, United States; Boston, MA", "Sales"),
   ("22222222-bbbb", "Software Engineer", "Hybrid (New York, New York, US)", "Engineering"),
   ("33333333-cccc", "Software Engineer", "London, UK", "Engineering")])
rjobs2, _, rerr = nk_fetch(("rippling", "acme", "Acme"))
t("Rippling: the London posting is left out; the US ones kept, credited 'on Rippling', with the ats reference",
  (sorted(j["loc"] for j in rjobs2), rjobs2[0]["via"], rjobs2[0]["ats"]["kind"], rerr),
  (["AR, United States; Boston, MA", "Hybrid (New York, New York, US)"], "Acme on Rippling", "rippling", ""))
t("Rippling: an unsafe board token is refused", J._board_token_ok("rippling", "../acme"), False)

BZ = "https://acme.breezy.hr/json"
loc_us = {"country": {"name": "United States", "id": "US"}, "state": {"id": "FL", "name": "Florida"}, "city": "Jacksonville", "is_remote": False, "name": "Jacksonville, FL"}
NK_ANS[BZ] = [
    {"id": "aaa111", "name": "Flight Instructor", "url": "https://acme.breezy.hr/p/aaa111-flight-instructor", "published_date": "2026-10-20T14:37:22.684Z",
     "type": {"id": "fullTime", "name": "Full-Time"}, "location": loc_us, "locations": [loc_us], "department": "Training", "salary": "$25 - $30 / hour"},
    {"id": "bbb222", "name": "Marketing Intern", "url": "https://acme.breezy.hr/p/bbb222-marketing-intern", "published_date": "2026-10-21T10:00:00Z",
     "type": {"id": "internship", "name": "Internship"}, "location": dict(loc_us, is_remote=True, city="", state=None, name="United States"),
     "locations": [{"country": {"id": "CA", "name": "Canada"}, "city": "Toronto"}, dict(loc_us, is_remote=True, city="", state=None, name="United States")]},
    {"id": "ccc333", "name": "Software Engineer", "url": "https://acme.breezy.hr/p/ccc333", "published_date": "2026-10-22T10:00:00Z",
     "type": {"id": "fullTime", "name": "Full-Time"}, "location": {"country": {"id": "GB", "name": "United Kingdom"}, "city": "London"}},
    {"id": "../x", "name": "Bad id", "url": "https://acme.breezy.hr/p/x"}]
NK_CALLS.clear()
braw = list(J._iter_raw("breezy", "acme", "Acme Flight"))
t("Breezy: robots.txt, then one GET of the careers site's /json", [c if c[0] == "robots" else (c[0], c[1].get("User-Agent")) for c in NK_CALLS],
  [("robots", "acme.breezy.hr"), (BZ, "UAply-jobs/1.0 (+https://uaply.net)")])
t("Breezy: place (first US one), country, remote, type, pay text, date; a bad id is skipped",
  [(r["id"], r["loc"], r["country"], r["remote"], r["emp"], r["force_type"], r["salary_text"], r["posted"]) for r in braw],
  [("aaa111", "Jacksonville, FL", "us", None, "Full-Time", None, "$25 - $30 / hour", J._ts("2026-10-20T14:37:22.684Z")),
   ("bbb222", "Remote - United States", "us", True, "Internship", "internship", "", J._ts("2026-10-21T10:00:00Z")),
   ("ccc333", "London", "gb", None, "Full-Time", None, "", J._ts("2026-10-22T10:00:00Z"))])
bjobs, _, berr = nk_fetch(("breezy", "acme", "Acme Flight"))
t("Breezy: the London position is left out; the rest credited 'on Breezy HR', the hourly pay read",
  (sorted(j["role"] for j in bjobs), bjobs[0]["via"], [j["sal"] for j in bjobs if j["role"] == "Flight Instructor"], berr),
  (["Flight Instructor", "Marketing Intern"], "Acme Flight on Breezy HR", [[25.0, 30.0]], ""))
NK_CALLS.clear()
closed_bz = nk_fetch(("breezy", "closed", "Closed"))
t("Breezy: a site whose robots.txt disallows the list is not read, and one line says so",
  (closed_bz[0], NK_CALLS, "[uaply] job feed breezy/closed/Closed failed: robots.txt does not allow it" in closed_bz[2]), ([], [("robots", "closed.breezy.hr")], True))
t("Breezy and Teamtailor: a token is one subdomain label", [J._board_token_ok(k, x) for k in ("breezy", "teamtailor") for x in ("acme-co", "a.b", "-acme", "acme/x")],
  [True, False, False, False] * 2)

TT = "https://acme.teamtailor.com/jobs.rss"
TT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:tt="https://teamtailor.com/locations"><channel><title>Acme</title><link>https://acme.teamtailor.com/jobs</link>
<item><title>Head of Marketing</title><description>&lt;p&gt;Lead &lt;b&gt;marketing&lt;/b&gt; and SEO.&lt;/p&gt;</description>
<pubDate>Wed, 28 Oct 2026 22:13:17 +0100</pubDate><link>https://acme.teamtailor.com/jobs/1-head-of-marketing</link><remoteStatus>hybrid</remoteStatus>
<guid>5c189e36-797b-4e58-8540-defb85b3668a</guid><tt:locations><tt:location><tt:name>Chicago</tt:name><tt:city>Chicago</tt:city><tt:country>United States</tt:country></tt:location></tt:locations>
<tt:department>Marketing</tt:department></item>
<item><title>Data Engineer</title><description>Python and SQL.</description><pubDate>Thu, 29 Oct 2026 13:25:57 +0100</pubDate>
<link>https://acme.teamtailor.com/jobs/2-data-engineer</link><remoteStatus>fully</remoteStatus><guid>6c189e36-797b-4e58-8540-defb85b3668b</guid>
<tt:locations><tt:location><tt:city>Stockholm</tt:city><tt:country>Sweden</tt:country></tt:location><tt:location><tt:city>Austin</tt:city><tt:country>United States</tt:country></tt:location></tt:locations></item>
<item><title>Solution Architect</title><description>Sales.</description><pubDate>Thu, 29 Oct 2026 13:25:57 +0100</pubDate>
<link>https://acme.teamtailor.com/jobs/3-solution-architect</link><remoteStatus>none</remoteStatus><guid>7c189e36-797b-4e58-8540-defb85b3668c</guid>
<tt:locations><tt:location><tt:city>Paris</tt:city><tt:country>France</tt:country></tt:location></tt:locations></item>
</channel></rss>"""
NK_ANS[TT] = TT_XML
NK_CALLS.clear()
traw = list(J._iter_raw("teamtailor", "acme", "Acme"))
t("Teamtailor: robots.txt, then one GET of the careers site's jobs.rss as text", [c if c[0] == "robots" else (c[0], c[1].get("User-Agent")) for c in NK_CALLS],
  [("robots", "acme.teamtailor.com"), (TT, "UAply-jobs/1.0 (+https://uaply.net)")])
t("Teamtailor: place (first US one), hybrid and fully remote, date, text and department read from the RSS",
  [(r["id"], r["loc"], r["country"], r["remote"], r["posted"], r["fallback"]) for r in traw],
  [("5c189e36-797b-4e58-8540-defb85b3668a", "Chicago, United States (hybrid)", "us", None, J._ts("2026-10-28T22:13:17+01:00"), "Marketing"),
   ("6c189e36-797b-4e58-8540-defb85b3668b", "Remote - Austin, United States", "us", True, J._ts("2026-10-29T13:25:57+01:00"), None),
   ("7c189e36-797b-4e58-8540-defb85b3668c", "", "other", None, J._ts("2026-10-29T13:25:57+01:00"), None)])
t("Teamtailor: the description's HTML is turned into text", traw[0]["text"], "Lead marketing and SEO.")
tjobs, _, terr = nk_fetch(("teamtailor", "acme", "Acme"))
t("Teamtailor: the Paris posting is left out; the US ones credited 'on Teamtailor'", (sorted(j["role"] for j in tjobs), tjobs[0]["via"], terr),
  (["Data Engineer", "Head of Marketing"], "Acme on Teamtailor", ""))
NK_ANS["https://evil.teamtailor.com/jobs.rss"] = ('<?xml version="1.0"?><!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
                                                   '<rss><channel><item><title>&x;</title></item></channel></rss>')
NK_ANS["https://lol.teamtailor.com/jobs.rss"] = '<rss><!ENTITY a "aaaa"><channel/></rss>'
xx, xe = nk_fetch(("teamtailor", "evil", "Evil")), nk_fetch(("teamtailor", "lol", "Lol"))
t("Teamtailor: a feed with an external entity or any <!ENTITY / <!DOCTYPE is refused before parsing, one failure line each",
  (xx[0], xe[0], xx[2].strip(), xe[2].strip()),
  ([], [], "[uaply] job feed teamtailor/evil/Evil failed: the feed declares entities; refused",
   "[uaply] job feed teamtailor/lol/Lol failed: the feed declares entities; refused"))
NK_ANS["https://broken.teamtailor.com/jobs.rss"] = "<rss><channel><item><title>Half"
NK_ANS["https://api.rippling.com/platform/api/ats/v1/board/notalist/jobs"] = {"jobs": []}
NK_ANS["https://notjson.breezy.hr/json"] = lambda body: json.loads("<html>not json</html>")
bad_kinds = [nk_fetch(s) for s in (("teamtailor", "broken", "Broken TT"), ("rippling", "notalist", "Not A List"), ("breezy", "notjson", "Not JSON"))]
t("Teamtailor bad XML, Rippling JSON that is not a list, Breezy non-JSON: each source marked failed with one line, nothing raised",
  [(b[0], b[1].startswith("error:"), b[2].count("[uaply] job feed ")) for b in bad_kinds], [([], True, 1)] * 3)
t("Teamtailor: a pubDate ending '-0000' (no zone given) is read as UTC",
  J._teamtailor_raw(J.ET.fromstring('<item><title>T</title><link>https://a.teamtailor.com/jobs/1</link><guid>abc-1</guid>'
                                    '<pubDate>Thu, 29 Oct 2026 13:25:57 -0000</pubDate></item>'), "A")["posted"], J._ts("2026-10-29T13:25:57Z"))
NK_CALLS.clear()
uaonly = nk_fetch(("breezy", "uaonly", "UA Only"))
t("robots.txt is checked for the User-Agent the list is asked for with (UAply-jobs), not the careers-site crawler's",
  (uaonly[0], NK_CALLS, "robots.txt does not allow it" in uaonly[2]), ([], [("robots", "uaonly.breezy.hr")], True))
t("Workday, Rippling, Breezy, Teamtailor: every list is asked for with the careers-site opener (public hosts and redirects only)",
  (len(NK_OPENERS) > 20, set(NK_OPENERS)), (True, {J._cp_open}))
J._get, J._robots_for = real_get, real_robots
t("the four new kinds are board kinds with an ats reference and a 'via' credit",
  [(k in J.BOARD_KINDS, k in J.ATS_REF_KINDS, k in J.VIA) for k in ("workday", "rippling", "breezy", "teamtailor")], [(True, True, True)] * 4)
cfg()
t("the four new kinds are off unless listed in feeds", [k for k in ("workday", "rippling", "breezy", "teamtailor") if k in J.feeds_allowed()], [])
cfg(feeds=["workday", "teamtailor"])
t("listing a new kind in feeds turns that kind (and only it) on", sorted(J.feeds_allowed()), ["teamtailor", "workday"])
cfg()

# ---------------- feeds_off ----------------
cfg(feeds=["greenhouse", "remotive", "smartrecruiters"])
t("a kind listed in feeds is on", "remotive" in J.feeds_allowed(), True)
cfg(feeds=["greenhouse", "remotive", "smartrecruiters"], feeds_off=["remotive"])
t("feeds_off turns that kind off by name; the rest stay on", sorted(J.feeds_allowed()), ["greenhouse", "smartrecruiters"])
os.environ["UAPLY_FEEDS"] = "remotive,lever"
t("feeds_off also wins over UAPLY_FEEDS", sorted(J.feeds_allowed()), ["greenhouse", "lever", "smartrecruiters"])
os.environ.pop("UAPLY_FEEDS")
cfg(feeds=["remotive", "jobicy"])
os.environ["UAPLY_FEEDS_OFF"] = "Remotive"
t("UAPLY_FEEDS_OFF does the same from the host's settings (any capitals)", sorted(J.feeds_allowed()), ["jobicy"])
os.environ.pop("UAPLY_FEEDS_OFF")
real_load = J._load_source
J._load_source = lambda src: ([], "0 jobs")
cfg(feeds=["remotive", "jobicy"], feeds_off=["remotive"])
names = J.get_jobs()["sources"]
J._load_source = real_load
t("a switched-off feed is not even asked for (not in the job list's sources)", ("Remotive" in names, any(k.startswith("Jobicy/") for k in names)), (False, True))
t("Remotive itself is still in the source list (the owner decides)", any(s[0] == "remotive" for s in J.SOURCES), True)

# ---------------- the application record and receipt name the source ----------------
cfg()
uaply_api.init("feedtest")
J._sr_desc.clear()
city_jobs, _ = J._fetch_source(CITY)
J._cache[CITY] = {"at": time.time(), "jobs": city_jobs, "status": "67 jobs"}
job = city_jobs[0]
code, out = uaply_api.submit({"consent": True, "profile": {"ext": {"phone": "215-555-0100"}, "name": "Feed Tester", "email": "feed.tester@example.com"},
                              "job": dict({k: job[k] for k in ("id", "co", "role", "url", "loc")}, via="via a site the browser made up", credit="made up")})
rec = uaply_api.APPS[-1]
t("a swipe right on a City job is a hand-off (finish on the City's site)", (code, out.get("status")), (200, "handoff"))
t("the record keeps the server's own credit, not what the browser sent", rec["job"].get("via"), "via City of Philadelphia on SmartRecruiters")
subject, text, page = emails.applicant_receipt(uaply_api._mail_ctx(uaply_api.config(), rec, "", "feed.tester@example.com"))
t("the applicant's receipt names the source", ("Source: via City of Philadelphia on SmartRecruiters" in text, "via City of Philadelphia on SmartRecruiters" in page), (True, True))
J._cache[USA_PHL] = {"at": time.time(), "jobs": [it], "status": "1 jobs"}
code, out = uaply_api.submit({"consent": True, "profile": {"ext": {"phone": "215-555-0100"}, "name": "Feed Tester", "email": "feed.tester@example.com"}, "job": {k: it[k] for k in ("id", "co", "role", "url", "loc")}})
rec = uaply_api.APPS[-1]
subject, text, page = emails.applicant_receipt(uaply_api._mail_ctx(uaply_api.config(), rec, "", "feed.tester@example.com"))
t("a federal job's receipt says 'via USAJOBS; apply on the official announcement' and links the announcement",
  ("Source: via USAJOBS; apply on the official announcement" in text, "Official announcement: https://www.usajobs.gov/job/900000101" in text), (True, True))

# ---------------- the Job feed keys box (function level, temporary settings file) ----------------
uaply_api.CONFIG_PATH = os.path.join(TMP, "uaply-config.json")
with open(uaply_api.CONFIG_PATH, "w", encoding="utf-8") as f:
    json.dump({"feeds": ["greenhouse"], "smtp": {"host": "smtp.example", "password": "keep-me"}}, f)
s, out = setup_api.save_feed_keys({"usajobs": "too-short"})
t("a key that does not look like a key is refused", (s, out["ok"]), (400, False))
s, out = setup_api.save_feed_keys({})
t("an empty form is refused", (s, out["ok"]), (400, False))
s, out = setup_api.save_feed_keys({"usajobs": " " + KEY + "\n", "usajobs_email": "owner.feeds@example.com", "muse": MUSE})
saved = json.load(open(uaply_api.CONFIG_PATH, encoding="utf-8"))
t("fake keys are saved under feed_keys (trimmed), other settings kept",
  (s, out["saved"], saved["feed_keys"], saved["feeds"], saved["smtp"]["password"]),
  (200, True, {"usajobs": KEY, "usajobs_email": "owner.feeds@example.com", "muse": MUSE}, ["greenhouse"], "keep-me"))
t("the answer never echoes a key", (KEY in json.dumps(out), MUSE in json.dumps(out)), (False, False))
html = setup_api.page("localhost:8767", "http").decode("utf-8")
t("the setup page shows 'saved' for both keys and neither key", (html.count("key: <b>saved</b>"), KEY in html, MUSE in html), (2, False, False))
t("the page links to where each key comes from", ('href="https://developer.usajobs.gov/APIRequest/"' in html, 'href="https://www.themuse.com/developers/api/v2"' in html), (True, True))
s, out = setup_api.save_feed_keys({"muse": ""})
t("a blank field changes nothing (the saved key stays)", (s, json.load(open(uaply_api.CONFIG_PATH, encoding="utf-8"))["feed_keys"].get("muse")), (400, MUSE))
s, out = setup_api.save_feed_keys({"remove": ["muse"]})
t("Remove drops one key and keeps the other", (s, sorted(json.load(open(uaply_api.CONFIG_PATH, encoding="utf-8"))["feed_keys"])), (200, ["usajobs", "usajobs_email"]))
t("...and the page says so", setup_api.page("localhost:8767", "http").decode("utf-8").count("not added yet") >= 1, True)
uaply_api.CONFIG_PATH = uaply_api.REAL_CONFIG_PATH

# ---------------- UAPLY_USAJOBS_KEY / UAPLY_USAJOBS_EMAIL: the key as its own host variable ----------------
ENV_KEY = "FAKEenvUsajobsKey9876543210zyxwvuZYXWVU+/="
cfg(feed_keys={"usajobs": KEY, "usajobs_email": "config.mail@example.com"})
os.environ["UAPLY_USAJOBS_KEY"], os.environ["UAPLY_USAJOBS_EMAIL"] = ENV_KEY, "env.mail@example.com"
try:
    k = J.feed_keys()
    t("UAPLY_USAJOBS_KEY and UAPLY_USAJOBS_EMAIL win over feed_keys", (k["usajobs"], k["usajobs_email"]), (ENV_KEY, "env.mail@example.com"))
    os.environ["UAPLY_USAJOBS_KEY"], os.environ["UAPLY_USAJOBS_EMAIL"] = "not a key!", "not-an-address"
    k = J.feed_keys()
    t("a malformed variable is ignored and feed_keys is used", (k["usajobs"], k["usajobs_email"]), (KEY, "config.mail@example.com"))
    cfg()
    os.environ["UAPLY_USAJOBS_KEY"], os.environ["UAPLY_USAJOBS_EMAIL"] = " " + ENV_KEY + "\n", "env.mail@example.com"
    t("the variable alone switches USAJOBS on (trimmed)", J.feed_keys().get("usajobs"), ENV_KEY)
    t("...and the setup page counts it as saved", setup_api.feed_status()["usajobs"], True)
    CALLS.clear()
    J._fetch_source(USA_PHL)
    t("the USAJOBS request carries the variable's key and email", [(h.get("Authorization-Key"), h.get("User-Agent")) for u, h in CALLS][:1],
      [(ENV_KEY, "env.mail@example.com")])
    t("the variable's key is scrubbed from error text like any other key", J._scrub("HTTP 401 for key " + ENV_KEY), "HTTP 401 for key [key]")
finally:
    os.environ.pop("UAPLY_USAJOBS_KEY", None)
    os.environ.pop("UAPLY_USAJOBS_EMAIL", None)
    cfg()
t("without the variable or feed_keys USAJOBS is skipped again", J._fetch_source(USA_PHL), ([], "no key"))


# ---------------- over HTTP, on a throwaway copy of the server ----------------
def http_checks(port):
    copy = os.path.join(TMP, "code")
    shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns(".git", "node_modules", "mobile", "marketing", "data", "uaply-config.json*", "uaply-partners.json*", "__pycache__"))
    # no employer boards from job-boards.json on this server (about 180 of them are SmartRecruiters boards, which its feeds switch on): it
    # read them live, and whichever answered first could take the top card from the recorded City jobs the browser check looks for
    with open(os.path.join(copy, "job-boards.json"), "w", encoding="utf-8") as f:
        json.dump({"boards": [], "note": "emptied by tools/test-feeds.py: this test server reads no boards"}, f)
    data = os.path.join(TMP, "server-data")
    os.makedirs(data)
    # the job list starts from a saved copy of the recorded City jobs, so the server needs no network
    with open(os.path.join(data, "jobs-cache.json"), "w", encoding="utf-8") as f:
        # the server applies the real 60-day rule: 40 of the recorded jobs are dated five days ago, the other 27 ninety days ago
        now_ms = int(time.time() * 1000)
        dated = [dict(x, posted=now_ms - (5 if i < 40 else 90) * J.DAY_MS) for i, x in enumerate(city_jobs)]
        dated = [{k: v for k, v in x.items() if k != "updated"} for x in dated]
        # every other SmartRecruiters board (the hand-picked ones in SOURCES) is saved as fresh and empty, so nothing is read from the
        # network: a live board that answered before the browser check could take the top card from the City jobs it looks for
        saved = {"|".join(s_): {"at": time.time(), "jobs": [], "status": "0 jobs"} for s_ in J.SOURCES if s_[0] == "smartrecruiters" and s_ != CITY}
        saved.update({"|".join(CITY): {"at": time.time(), "jobs": dated, "status": "67 jobs"}, "_version": J.CACHE_VERSION})
        json.dump(saved, f)
    env = dict(os.environ, UAPLY_CONFIG_FILE="none", UAPLY_DATA_DIR=data, HOST="127.0.0.1",
               UAPLY_CONFIG_JSON=json.dumps({"feeds": ["smartrecruiters", "usajobs"], "delivery": "test", "smtp": {}, "google": {}, "owner_copy": ""}),
               UAPLY_SIGNUP_TEST="1")          # sign-up test mode (never public): the sign-in gate's test person is confirmed at once
    env.pop("OWNER_PASSWORD", None)
    log = open(os.path.join(TMP, "server.log"), "w")
    srv = subprocess.Popen([sys.executable, os.path.join(copy, "serve.py"), str(port), os.path.join(copy, "dev"), "--api"], env=env, stdout=log, stderr=log)
    base = "http://127.0.0.1:%d" % port

    def call(method, path, body=None, origin=base, cookie=""):
        h = {"Content-Type": "application/json"}
        if origin:
            h["Origin"] = origin
        if cookie:
            h["Cookie"] = cookie
        rq = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None, headers=h, method=method)
        try:
            with urllib.request.urlopen(rq, timeout=30) as r:
                return r.status, r.read().decode("utf-8")
        except urllib.error.HTTPError as x:
            return x.code, x.read().decode("utf-8")

    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(base + "/api/apply/config", timeout=2)
                break
            except Exception:
                time.sleep(0.2)
        s, body = call("POST", "/api/setup/save-feed-keys", {"usajobs": KEY}, origin="https://evil.example")
        t("HTTP: a save from another site is refused", s, 403)
        s, body = call("POST", "/api/setup/save-feed-keys", {"usajobs": KEY}, origin=None)
        t("HTTP: a save with no Origin is refused", s, 403)
        s, body = call("POST", "/api/setup/save-feed-keys", {"usajobs": "nope"})
        t("HTTP: a bad key is refused with a reason", (s, "does not look like" in body), (400, True))
        s, body = call("POST", "/api/setup/save-feed-keys", {"usajobs": KEY, "muse": MUSE})
        t("HTTP: fake keys are saved and the answer has no key", (s, json.loads(body).get("saved"), KEY in body, MUSE in body), (200, True, False, False))
        with open(os.path.join(copy, "uaply-config.json"), encoding="utf-8") as f:
            t("HTTP: the keys landed in the throwaway copy's settings file", json.load(f).get("feed_keys"), {"usajobs": KEY, "muse": MUSE})
        s, page = call("GET", "/setup")
        t("HTTP: /setup has the Job feed keys box and never the keys", (s, 'id="feeds"' in page, KEY in page, MUSE in page), (200, True, False, False))
        sys.path.insert(0, HERE)
        import gate_session                    # the sign-in gate: the job list needs a signed-in, confirmed person
        ck = gate_session.cookie(base)
        s, body = call("GET", "/api/jobs", cookie=ck)
        data_out = json.loads(body)
        city = [j for j in data_out["jobs"] if j.get("via") == "City of Philadelphia on SmartRecruiters"]
        t("HTTP: the job list serves the City's 40 jobs from the last 60 days (not the 27 older ones; two postings with one title stay two), each with its via label and postedDays",
          (len(city), sorted({j["postedDays"] for j in city}), data_out.get("aged_out"), data_out.get("merged")), (40, [5], 27, 0))
        t("HTTP: USAJOBS is listed as skipped (this server reads no settings file)", data_out["sources"].get("USAJOBS/philadelphia"), "no key")
        t("HTTP: the job list never contains a key", (KEY in body, MUSE in body), (False, False))
        # ---- the list form, the paged form and one job (October 23: 16,424 jobs were 14.8 MB on a phone) ----
        one = city[0]
        t("HTTP: the list form leaves out what no card shows (description, credit line, update date, announcement); of ats only its kind",
          ([k for k in ("desc", "credit", "updated", "updatedDays", "announcement") if any(k in j for j in data_out["jobs"])],
           sorted({tuple(sorted(j["ats"])) for j in data_out["jobs"] if j.get("ats")})), ([], [("kind",)]))
        s, b1 = call("GET", "/api/jobs/%d" % one["id"], cookie=ck)
        full = json.loads(b1).get("job") or {}
        t("HTTP: GET /api/jobs/<id> answers the whole job: its credit line and its full employer-system reference",
          (s, full.get("id"), full.get("credit"), sorted(full.get("ats") or {})), (200, one["id"], "via City of Philadelphia on SmartRecruiters", ["board", "id", "kind"]))
        t("HTTP: a job that is not listed: 404 'gone'", (call("GET", "/api/jobs/1", cookie=ck)[0], json.loads(call("GET", "/api/jobs/1", cookie=ck)[1]).get("code")), (404, "gone"))
        t("HTTP: one job is behind the sign-in gate too", call("GET", "/api/jobs/%d" % one["id"])[0], 401)
        s, pb = call("GET", "/api/jobs?size=7&page=1", cookie=ck)
        pg = json.loads(pb)
        whole = [j["id"] for j in data_out["jobs"]]
        t("HTTP: ?size=7&page=1 is the first 7 jobs of the whole list, the total and a cursor, with the list's sources",
          (s, [j["id"] for j in pg["jobs"]], pg["total"], pg["page"], pg["size"], bool(pg["next"]), "sources" in pg), (200, whole[:7], len(whole), 1, 7, True, True))
        seen_ids, cur, n = [], None, 0
        while n < 50:
            pg = json.loads(call("GET", "/api/jobs?size=7" + ("&cursor=" + cur if cur else ""), cookie=ck)[1])
            seen_ids += [j["id"] for j in pg["jobs"]]
            cur, n = pg["next"], n + 1
            if not cur:
                break
        t("HTTP: following the cursor walks the whole list once, in order, and the last page has no cursor", (seen_ids == whole, n, cur), (True, -(-len(whole) // 7), None))
        t("HTTP: ?page=2 is the next 7", [j["id"] for j in json.loads(call("GET", "/api/jobs?size=7&page=2", cookie=ck)[1])["jobs"]], whole[7:14])
        types = sorted({j.get("type") for j in data_out["jobs"]})
        want = types[0]
        pt = json.loads(call("GET", "/api/jobs?type=%s&size=1000" % want, cookie=ck)[1])
        t("HTTP: ?type= keeps one stack (%s): its jobs only, and the total counts just those" % want,
          ([j["id"] for j in pt["jobs"]], pt["total"]), ([j["id"] for j in data_out["jobs"] if j.get("type") == want], sum(1 for j in data_out["jobs"] if j.get("type") == want)))
        t("HTTP: a size over 1000 is held to 1000, a size that is not a number is 200", (json.loads(call("GET", "/api/jobs?size=99999", cookie=ck)[1])["size"],
          json.loads(call("GET", "/api/jobs?size=lots", cookie=ck)[1])["size"]), (1000, 200))
        t("HTTP: a cursor that is not ours starts at the beginning", [j["id"] for j in json.loads(call("GET", "/api/jobs?size=3&cursor=nonsense", cookie=ck)[1])["jobs"]], whole[:3])
        t("HTTP: the paged form is behind the sign-in gate too", call("GET", "/api/jobs?size=5")[0], 401)
        rq = urllib.request.Request(base + "/api/jobs?size=40", headers={"Cookie": ck, "Accept-Encoding": "gzip"})
        with urllib.request.urlopen(rq, timeout=30) as r:
            gz_page = (r.headers.get("Content-Encoding"), json.loads(gzip.decompress(r.read()))["total"])
        rq = urllib.request.Request(base + "/api/jobs", headers={"Cookie": ck, "Accept-Encoding": "gzip, deflate, br"})
        with urllib.request.urlopen(rq, timeout=30) as r:
            gz_all = (r.headers.get("Content-Encoding"), len(json.loads(gzip.decompress(r.read()))["jobs"]))
        t("HTTP: a page and the whole list are both sent gzip-compressed when the browser takes it", (gz_page, gz_all), (("gzip", len(whole)), ("gzip", len(whole))))
        with open(os.path.join(TMP, "server.log"), encoding="utf-8", errors="replace") as f:
            t("HTTP: the server log never contains a key", any(k in f.read() for k in (KEY, MUSE)), False)
        # the same places tools/cdp.js looks: UAPLY_CHROME, the Windows install, a Playwright Chromium, google-chrome/chromium, the Mac app, then on Windows a Chrome for all users and Edge
        chrome = os.environ.get("UAPLY_CHROME") or next((p for p in [
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
            *sorted(glob.glob(os.path.join(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers"), "chromium-*", "chrome-linux*", "chrome")), reverse=True),
            *[shutil.which(n) or "" for n in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")],
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            *[os.path.join(pf, *sub) for sub in (("Google", "Chrome", "Application", "chrome.exe"), ("Microsoft", "Edge", "Application", "msedge.exe"))
              for pf in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles")) if pf]] if p and os.path.exists(p)), "")
        if chrome and os.path.exists(chrome) and shutil.which("node"):
            r = subprocess.run(["node", os.path.join(HERE, "cdp.js"), os.path.join(HERE, "ui-via.js")], env=dict(os.environ, PORT=str(port), W="390", H="844"),
                               capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
            print(r.stdout.strip())
            t("browser: the card shows 'via ...' next to its apply wording (tools/ui-via.js)", r.returncode == 0 and "FAIL" not in r.stdout and "PASS" in r.stdout, True)
        else:
            print("SKIP browser check: Chrome or node not found")
    finally:
        srv.terminate()
        try:
            srv.wait(10)
        except subprocess.TimeoutExpired:
            srv.kill()
        log.close()


if len(sys.argv) > 1:
    http_checks(int(sys.argv[1]))

shutil.rmtree(TMP, ignore_errors=True)
print(sum(R), "/", len(R))
sys.exit(0 if all(R) else 1)
