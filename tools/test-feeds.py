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
  url, "https://data.usajobs.gov/api/search?LocationName=Philadelphia,%20Pennsylvania&Radius=50&ResultsPerPage=500&Fields=Full")
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
t("the student search adds HiringPath=student;graduates", CALLS[0][0].endswith("&HiringPath=student;graduates"), True)
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

# ---------------- the "via" credit for every kind ----------------
raw = dict(id=7, title="Data Analyst", company="Acme Corp", loc="Philadelphia, PA", remote=None, text="Python and SQL.", url="https://example.com/j/7", salary_text="", posted=0)
for kind, name, want in (("greenhouse", "Stripe", "Stripe on Greenhouse"), ("lever", "Spotify", "Spotify on Lever"), ("ashby", "Linear", "Linear on Ashby"),
                         ("smartrecruiters", "City of Philadelphia", "City of Philadelphia on SmartRecruiters"), ("jobicy", "Jobicy", "Jobicy"),
                         ("muse", "The Muse", "The Muse"), ("usajobs", "USAJOBS", "USAJOBS"), ("remotive", "Remotive", "Remotive")):
    n = J._normalize(dict(raw), kind, name, "board")
    t("%s jobs say 'via %s'" % (kind, want), (n["via"], n["credit"]),
      (want, "via USAJOBS; apply on the official announcement" if kind == "usajobs" else "via " + want))
t("partner and Hiring mode jobs carry no feed credit", [j for j in J.partner_jobs() if j.get("via")], [])

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
    data = os.path.join(TMP, "server-data")
    os.makedirs(data)
    # the job list starts from a saved copy of the recorded City jobs, so the server needs no network
    with open(os.path.join(data, "jobs-cache.json"), "w", encoding="utf-8") as f:
        # the server applies the real 60-day rule: 40 of the recorded jobs are dated five days ago, the other 27 ninety days ago
        now_ms = int(time.time() * 1000)
        dated = [dict(x, posted=now_ms - (5 if i < 40 else 90) * J.DAY_MS) for i, x in enumerate(city_jobs)]
        dated = [{k: v for k, v in x.items() if k != "updated"} for x in dated]
        json.dump({"|".join(CITY): {"at": time.time(), "jobs": dated, "status": "67 jobs"}, "_version": J.CACHE_VERSION}, f)
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
        # the same places tools/cdp.js looks: UAPLY_CHROME, the Windows install, a Playwright Chromium, google-chrome/chromium, the Mac app
        chrome = os.environ.get("UAPLY_CHROME") or next((p for p in [
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome", "Application", "chrome.exe"),
            *sorted(glob.glob(os.path.join(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers"), "chromium-*", "chrome-linux*", "chrome")), reverse=True),
            *[shutil.which(n) or "" for n in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")],
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"] if p and os.path.exists(p)), "")
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
