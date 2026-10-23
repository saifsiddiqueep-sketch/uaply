"""Tests for serving the whole US with Pennsylvania, New Jersey and Delaware covered best (October 21, 2026):
  * which places count as US jobs and which as tri-state (the extras a board may keep), New Jersey and Delaware included
  * the app's own city table and ZIP prefixes (node): Wilmington DE vs NC, Newark DE vs NJ vs CA, Trenton, Cherry Hill, ZIP 197xx and 08xxx
  * CareerOneStop: "no key" until both variables are set, the documented request, the parser, the credit, secrets kept out of errors,
    and the same job from an employer board shown once (against tools/fixtures/careeronestop-sample.json, made up in the documented shape)
  python tools/test-tristate.py [port]      with a port, also the distance filter in Chrome (tools/ui-places.js)"""
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ["UAPLY_CONFIG_FILE"] = "none"
os.environ["UAPLY_CONFIG_JSON"] = "{}"
os.environ["UAPLY_DATA_DIR"] = tempfile.mkdtemp(prefix="uaply-tristate-")
for v in ("UAPLY_FEEDS", "UAPLY_FEEDS_OFF", "UAPLY_USAJOBS_KEY", "UAPLY_COS_USER_ID", "UAPLY_COS_TOKEN"):
    os.environ.pop(v, None)
import jobs_api as J  # noqa: E402

R = []


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


# ---------------- places on the server ----------------
for loc, us, tri in [("Wilmington, DE", True, True), ("Wilmington, Delaware", True, True), ("Dover, DE", True, True), ("Newark, DE", True, True),
                     ("Cherry Hill, NJ", True, True), ("Trenton", True, True), ("Princeton", True, True), ("Newark, New Jersey", True, True),
                     ("Hybrid - Jersey City", True, True), ("New Jersey", True, True), ("Delaware", True, True), ("Greater Philadelphia", True, True),
                     ("Greater Philadelphia Area", True, True), ("Philadelphia", True, True), ("King of Prussia", True, True), ("Camden, NJ, US", True, True),
                     ("Remote - US", True, False), ("Austin, TX, US", True, False), ("Newark, CA", True, False), ("Wilmington, NC", True, False),
                     ("Munich, BY, DE", False, True), ("Berlin, DE", False, True), ("Mumbai, MH, IN", False, False), ("Toronto, ON, CA", False, False),
                     ("London, UK", False, False), ("Paris, IDF, FR", False, False)]:
    t("place %r: a US job %s, tri-state %s" % (loc, us, tri), (J._us_ok(loc, False), bool(J.LOCAL_RE.search(loc))), (us, tri))
t("a German ', DE' never becomes a Delaware job (the US rule runs first)",
  J._normalize(dict(id=1, title="Engineer", company="Acme", loc="Munich, BY, DE", remote=None, text="Python.", url="https://x.example/1", salary_text="", posted=0), "greenhouse", "Acme"), None)
t("a posting that names a country other than the US is dropped",
  J._normalize(dict(id=1, title="Engineer", company="Acme", loc="Dover", remote=None, text="Python.", url="https://x.example/1", salary_text="", posted=0, country="gb"), "smartrecruiters", "Acme"), None)
kept = J._normalize(dict(id=1, title="Engineer", company="Acme", loc="Wilmington, DE", remote=None, text="Python.", url="https://x.example/1", salary_text="", posted=0, country="us"), "smartrecruiters", "Acme")
t("...and a US one is kept, its place as listed", (kept or {}).get("loc"), "Wilmington, DE")
t("a remote US job is shown to everyone (work style remote, place United States)",
  [(x["mode"], x["loc"]) for x in [J._normalize(dict(id=2, title="Analyst", company="Acme", loc="Remote", remote=True, text="SQL.", url="https://x.example/2", salary_text="", posted=0), "lever", "Acme")]],
  [("remote", "United States")])

# ---------------- the app's city table (shared/uaply-nav.js), in node ----------------
nav = open(os.path.join(ROOT, "shared", "uaply-nav.js"), encoding="utf-8").read()
cities = re.search(r"  var CITIES=\[.*?\]\.map\(function\(c\)\{return \[new w\.RegExp\([^\n]*?\]\}\);", nav, re.S).group(0)
zips = re.search(r"  var ZIP3=\[.*?\];", nav, re.S).group(0)
fns = re.search(r"  function geo\(text\)\{.*?\n", nav).group(0) + re.search(r"  function zipGeo\(z\)\{.*?\n", nav).group(0)
probe = ["Wilmington, DE", "Wilmington, NC", "Newark, DE", "Newark, NJ", "Newark, CA", "Trenton, NJ", "Cherry Hill, NJ", "Camden, NJ", "Camden, SC",
         "Greater Philadelphia", "Dover, DE", "New Brunswick, NJ", "Hoboken, NJ", "Princeton, NJ", "Pittsburgh, PA"]
zipprobe = ["19801", "19711", "19901", "08002", "08608", "08901", "07030", "19104", "18015", "19380"]
script = "var w={RegExp:RegExp};\n" + cities + "\n" + zips + "\n" + fns + "\nconsole.log(JSON.stringify({g:%s.map(geo),z:%s.map(zipGeo)}));" % (json.dumps(probe), json.dumps(zipprobe))
if shutil.which("node"):
    js = os.path.join(tempfile.mkdtemp(prefix="uaply-geo-"), "geo.js")
    with open(js, "w", encoding="utf-8") as f:
        f.write(script)
    r = subprocess.run(["node", js], capture_output=True, text=True, timeout=60)
    if r.returncode:
        print(r.stderr[-1500:])
    out = json.loads(r.stdout)
    g, z = dict(zip(probe, out["g"])), dict(zip(zipprobe, out["z"]))

    def mi(a, b):
        r = math.pi / 180
        x = math.sin((b[0] - a[0]) * r / 2) ** 2 + math.cos(a[0] * r) * math.cos(b[0] * r) * math.sin((b[1] - a[1]) * r / 2) ** 2
        return 2 * 3958.8 * math.asin(math.sqrt(x))
    phl = g["Greater Philadelphia"]
    t("the app knows every tri-state place it is asked about", [p for p in probe if not g[p]], [])
    t("Wilmington DE is about 26 miles from Philadelphia; Wilmington NC is not near it", (round(mi(g["Wilmington, DE"], phl)) in range(24, 30), mi(g["Wilmington, NC"], phl) > 300), (True, True))
    t("Newark DE, Newark NJ and Newark CA are three different places", (mi(g["Newark, DE"], g["Newark, NJ"]) > 80, mi(g["Newark, CA"], g["Newark, NJ"]) > 2000), (True, True))
    t("Camden SC is not Camden NJ", mi(g["Camden, SC"], g["Camden, NJ"]) > 400, True)
    t("Trenton is about 30 miles from Philadelphia, Cherry Hill about 8", (round(mi(g["Trenton, NJ"], phl)) in range(26, 34), round(mi(g["Cherry Hill, NJ"], phl)) in range(5, 11)), (True, True))
    t("ZIP codes in Delaware, South and Central Jersey and the Philadelphia suburbs point to a place", [p for p in zipprobe if not z[p]], [])
    t("ZIP 19711 (Newark DE) and 19901 (Dover DE) are in Delaware, not New Jersey", (mi(z["19711"], g["Newark, DE"]) < 5, mi(z["19901"], g["Dover, DE"]) < 5), (True, True))
else:
    print("SKIP the city table: node is not installed")

# ---------------- CareerOneStop ----------------
RECENT = time.strftime("%Y-%m-%dT%H:%M:%S-04:00", time.gmtime(time.time() - 2 * 86400))
SAMPLE = json.loads(open(os.path.join(HERE, "fixtures", "careeronestop-sample.json"), encoding="utf-8").read().replace("__RECENT__", RECENT))
CALLS = []
USER, TOKEN = "FAKEuser01", "FAKEcosToken0123456789abcdefABCDEF+/="


def fake_get(url, headers=None, as_text=False):
    CALLS.append((url, dict(headers or {})))
    if url.startswith("https://api.careeronestop.org/"):
        return SAMPLE
    raise urllib.error.URLError("no made-up answer")


real_get = J._get
J._get = fake_get
COS = ("careeronestop", "philadelphia", "CareerOneStop")
t("CareerOneStop without its keys is skipped with the status 'no key', nothing asked", (J._fetch_source(COS), CALLS), (([], "no key"), []))
os.environ["UAPLY_COS_USER_ID"] = USER
t("...one of the two is not enough", J._fetch_source(COS), ([], "no key"))
os.environ["UAPLY_COS_TOKEN"] = TOKEN
try:
    jobs, status = J._fetch_source(COS)
    url, hdr = CALLS[-1]
    t("the documented request: user id, keyword 0 (every job), Philadelphia, 50 miles, newest first, 100 a page, the last 7 days",
      url, "https://api.careeronestop.org/v1/jobsearch/FAKEuser01/0/Philadelphia%2C%20PA/50/acquisitiondate/DESC/0/100/7")
    t("the token goes in 'Authorization: Bearer'", hdr.get("Authorization"), "Bearer " + TOKEN)
    t("4 of the 6 sample postings are kept (an http link and an empty title are not)", (status, sorted(j["role"] for j in jobs)),
      ("4 jobs", ["Accounting Intern", "Certified Nursing Assistant (Part-Time)", "Data Analyst", "Warehouse Associate"]))
    by = {j["role"]: j for j in jobs}
    cna = by["Certified Nursing Assistant (Part-Time)"]
    t("title, company and place are shown as given; the link is the NLx posting", (cna["co"], cna["loc"], cna["url"]),
      ("Riverside Nursing Center", "Cherry Hill, NJ", "https://de.jobsyn.org/25206ecfe4954376b3943722f89fd1c08003"))
    t("lower-case field names are read too", by["Warehouse Associate"]["loc"], "Camden, NJ")
    t("job types: part-time and internship from the titles", (cna["jobType"], by["Accounting Intern"]["jobType"]), ("part-time", "internship"))
    t("the credit names CareerOneStop, the Department of Labor and Minnesota DEED (the license asks for both)",
      (cna["via"], cna["credit"]), ("CareerOneStop (U.S. Department of Labor ETA and Minnesota DEED)", "via CareerOneStop (U.S. Department of Labor ETA and Minnesota DEED)"))
    t("link-out only, never a recruiter address", (cna["apply"], cna["contact"]), ("link", ""))
    CALLS.clear()
    J._cache.pop(("careeronestop", "remote", "CareerOneStop"), None)
    J._fetch_source(("careeronestop", "remote", "CareerOneStop"))
    t("the remote search is nationwide with a real keyword", CALLS[-1][0], "https://api.careeronestop.org/v1/jobsearch/FAKEuser01/remote/US/0/acquisitiondate/DESC/0/100/7")
    t("16 searches (five places x all, internship, part-time, and remote), every 3 hours = 128 requests a day",
      (len([s for s in J.SOURCES if s[0] == "careeronestop"]), 24 // (J.TTL["careeronestop"] // 3600) * 16), (16, 128))
    t("both secrets are taken out of any error text", J._scrub("HTTP 401 for /v1/jobsearch/%s/0 token %s" % (USER, TOKEN)), "HTTP 401 for /v1/jobsearch/[key]/0 token [key]")
    os.environ["UAPLY_COS_TOKEN"] = "short"
    t("a malformed token is not used (status 'no key')", J._fetch_source(COS), ([], "no key"))
    os.environ["UAPLY_COS_TOKEN"] = TOKEN
    # the same job on an employer's own board and on CareerOneStop is shown once: the board's copy
    J._cache.clear()
    board = J._normalize(dict(id=77, title="Data Analyst", company="Acme", loc="Philadelphia, PA", remote=None, text="Python and SQL.",
                              url="https://job-boards.greenhouse.io/acme/jobs/77", salary_text="", posted=int(time.time() * 1000)), "greenhouse", "Acme", "acme")
    real_sources, real_allowed, real_load = J.SOURCES, J.feeds_allowed, J._load_source
    J.SOURCES = [("greenhouse", "acme", "Acme"), COS]
    J.feeds_allowed = lambda: {"greenhouse", "careeronestop"}
    J._load_source = lambda src: ([board], "1 jobs") if src[0] == "greenhouse" else J._fetch_source(src)
    try:
        out = J.get_jobs()
    finally:
        J.SOURCES, J.feeds_allowed, J._load_source = real_sources, real_allowed, real_load
    analysts = [j for j in out["jobs"] if j["role"] == "Data Analyst"]
    t("'Data Analyst, Acme, Inc., Philadelphia, PA' from CareerOneStop is the employer's own posting: shown once, the board's copy",
      ([j["via"] for j in analysts], out["merged"]), (["Acme on Greenhouse"], 1))
finally:
    J._get = real_get
    os.environ.pop("UAPLY_COS_USER_ID", None)
    os.environ.pop("UAPLY_COS_TOKEN", None)


# ---------------- the distance filter in Chrome ----------------
def browser_checks(port):
    city = ("smartrecruiters", "CityofPhiladelphia", "City of Philadelphia")
    places = ["Wilmington, DE", "Philadelphia, PA", "Trenton, NJ", "Cherry Hill, NJ", "Pittsburgh, PA", "Wilmington, NC", "Newark, CA", "Remote"]
    jobs = [J._normalize(dict(id="74400000001%04d" % i, title="Clerk %d" % i, company="City of Philadelphia", loc=p, remote=True if p == "Remote" else None,
                              text="Excel and customer service.", url="https://jobs.smartrecruiters.com/CityofPhiladelphia/74400000001%04d" % i,
                              salary_text="", posted=int(time.time() * 1000), emp="Full-time"), "smartrecruiters", "City of Philadelphia", "CityofPhiladelphia")
            for i, p in enumerate(places)]
    t("browser setup: 8 made-up jobs", len([j for j in jobs if j]), 8)
    data = tempfile.mkdtemp(prefix="uaply-tristate-server-")
    with open(os.path.join(data, "jobs-cache.json"), "w", encoding="utf-8") as f:
        json.dump({"|".join(city): {"at": time.time(), "jobs": jobs, "status": "8 jobs"}, "_version": J.CACHE_VERSION}, f)
    env = dict(os.environ, UAPLY_CONFIG_FILE="none", UAPLY_DATA_DIR=data, HOST="127.0.0.1", UAPLY_FEEDS="smartrecruiters", UAPLY_CONFIG_JSON="{}",
               UAPLY_SIGNUP_TEST="1")          # sign-up test mode (never public): the browser half signs a test person up past the sign-in gate
    env.pop("OWNER_PASSWORD", None)
    log = open(os.path.join(data, "server.log"), "w")
    srv = subprocess.Popen([sys.executable, os.path.join(ROOT, "serve.py"), str(port), os.path.join(ROOT, "dev"), "--api"], env=env, stdout=log, stderr=log)
    try:
        import urllib.request
        for _ in range(40):
            try:
                urllib.request.urlopen("http://127.0.0.1:%d/healthz" % port, timeout=2)
                break
            except Exception:
                time.sleep(0.25)
        sys.path.insert(0, HERE)
        import gate_session                    # the sign-in gate: the job list needs a signed-in, confirmed person
        base = "http://127.0.0.1:%d" % port
        listing = gate_session.get_json(gate_session.session(base), base + "/api/jobs")
        t("HTTP: a signed-in person gets all 8 made-up jobs from the server" , len(listing["jobs"]), 8)
        if not shutil.which("node"):
            print("SKIP browser: node is not installed")
            return
        r = subprocess.run(["node", os.path.join(HERE, "cdp.js"), os.path.join(HERE, "ui-places.js")], env=dict(os.environ, PORT=str(port), W="390", H="844"),
                           capture_output=True, text=True, timeout=180)
        print(r.stdout.strip())
        t("browser: the distance filter for Wilmington DE and Trenton NJ, remote for everyone (tools/ui-places.js)",
          r.returncode == 0 and "FAIL" not in r.stdout and r.stdout.count("PASS") >= 7, True)
    finally:
        srv.terminate()
        srv.wait(10)
        log.close()


if len(sys.argv) > 1:
    browser_checks(int(sys.argv[1]))
print(sum(R), "/", len(R))
sys.exit(0 if all(R) else 1)
