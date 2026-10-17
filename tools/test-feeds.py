"""Tests the job sources added for launch (USAJOBS, the City of Philadelphia on SmartRecruiters), The Muse key, the "via" credit on every job,
the Job feed keys box on /setup and the feeds_off switch. No network: every feed answer comes from tools/fixtures/ (a recorded City of
Philadelphia answer and a USAJOBS sample built from its documented schema). All keys here are fake.
  python tools/test-feeds.py [port]
With a port it also starts a throwaway copy of the server (from a temporary copy of the code, so a saved key never lands next to the real
code) and checks the save endpoint over HTTP, the job list, and, when Chrome is installed, the card in a real browser (tools/ui-via.js)."""
import contextlib
import glob
import io
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
t("the job list names both USAJOBS searches as 'no key'", (summ.get("USAJOBS/philadelphia"), summ.get("USAJOBS/students")), ("no key", "no key"))

cfg(feed_keys={"usajobs": KEY})
CALLS.clear()
jobs, status = J._fetch_source(USA_PHL)
url, hdr = CALLS[0]
t("with a key: one search, answered", (len(CALLS), status), (1, "3 jobs"))
t("the search is Philadelphia, 25 miles, 500 a page, full fields",
  url, "https://data.usajobs.gov/api/search?LocationName=Philadelphia,%20Pennsylvania&Radius=25&ResultsPerPage=500&Fields=Full")
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
t("hourly pay is not shown as a yearly range", cs.get("sal"), [0, 0])
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
        off = int(url.split("offset=")[1])
        return {"offset": off, "limit": 100, "totalFound": 150, "content": many[off:off + 100]}
    raise OSError("no description")


J._get = paged
J._sr_desc.clear()
CALLS.clear()
jobs, status = J._fetch_source(("smartrecruiters", "BigCo", "BigCo"))
lists = [u.split("?")[1] for u, _ in CALLS if "?" in u]
t("pages are read 100 at a time by offset", lists, ["limit=100&offset=0", "limit=100&offset=100"])
t("no more than 120 postings are kept, and no more than 120 descriptions read", (len(jobs), len([1 for u, _ in CALLS if "?" not in u])), (120, 120))


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
code, out = uaply_api.submit({"consent": True, "profile": {"name": "Feed Tester", "email": "feed.tester@example.com"},
                              "job": dict({k: job[k] for k in ("id", "co", "role", "url", "loc")}, via="via a site the browser made up", credit="made up")})
rec = uaply_api.APPS[-1]
t("a swipe right on a City job is a hand-off (finish on the City's site)", (code, out.get("status")), (200, "handoff"))
t("the record keeps the server's own credit, not what the browser sent", rec["job"].get("via"), "via City of Philadelphia on SmartRecruiters")
subject, text, page = emails.applicant_receipt(uaply_api._mail_ctx(uaply_api.config(), rec, "", "feed.tester@example.com"))
t("the applicant's receipt names the source", ("Source: via City of Philadelphia on SmartRecruiters" in text, "via City of Philadelphia on SmartRecruiters" in page), (True, True))
J._cache[USA_PHL] = {"at": time.time(), "jobs": [it], "status": "1 jobs"}
code, out = uaply_api.submit({"consent": True, "profile": {"name": "Feed Tester", "email": "feed.tester@example.com"}, "job": {k: it[k] for k in ("id", "co", "role", "url", "loc")}})
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


# ---------------- over HTTP, on a throwaway copy of the server ----------------
def http_checks(port):
    copy = os.path.join(TMP, "code")
    shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns(".git", "node_modules", "mobile", "marketing", "data", "uaply-config.json*", "uaply-partners.json*", "__pycache__"))
    data = os.path.join(TMP, "server-data")
    os.makedirs(data)
    # the job list starts from a saved copy of the recorded City jobs, so the server needs no network
    with open(os.path.join(data, "jobs-cache.json"), "w", encoding="utf-8") as f:
        json.dump({"|".join(CITY): {"at": time.time(), "jobs": city_jobs, "status": "67 jobs"}, "_version": J.CACHE_VERSION}, f)
    env = dict(os.environ, UAPLY_CONFIG_FILE="none", UAPLY_DATA_DIR=data, HOST="127.0.0.1",
               UAPLY_CONFIG_JSON=json.dumps({"feeds": ["smartrecruiters", "usajobs"], "delivery": "test", "smtp": {}, "google": {}, "owner_copy": ""}))
    env.pop("OWNER_PASSWORD", None)
    log = open(os.path.join(TMP, "server.log"), "w")
    srv = subprocess.Popen([sys.executable, os.path.join(copy, "serve.py"), str(port), os.path.join(copy, "dev"), "--api"], env=env, stdout=log, stderr=log)
    base = "http://127.0.0.1:%d" % port

    def call(method, path, body=None, origin=base):
        h = {"Content-Type": "application/json"}
        if origin:
            h["Origin"] = origin
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
        s, body = call("GET", "/api/jobs")
        data_out = json.loads(body)
        city = [j for j in data_out["jobs"] if j.get("via") == "City of Philadelphia on SmartRecruiters"]
        t("HTTP: the job list serves the City's 67 jobs, each with its via label", len(city), 67)
        t("HTTP: USAJOBS is listed as skipped (this server reads no settings file)", data_out["sources"].get("USAJOBS/philadelphia"), "no key")
        t("HTTP: the job list never contains a key", (KEY in body, MUSE in body), (False, False))
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
            t("browser: the card shows 'via ...' next to 'Opens employer site' (tools/ui-via.js)", r.returncode == 0 and "FAIL" not in r.stdout and "PASS" in r.stdout, True)
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
