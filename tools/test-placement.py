"""Where a job is: the server's point for each job's place (us-places.tsv.gz from the Census Gazetteer, jobs_api.job_geo), the app using
it for "near you" and the distance filter (shared/uaply-nav.js jgeo, with the app's own city list as the fallback), every US ZIP code's
first three digits for "where you live", careers sites reading co-ops, internships and tri-state pages first, and careers sites keeping
off the board readers' places. No network.
  python tools/test-placement.py"""
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ["UAPLY_CONFIG_FILE"] = "none"
os.environ["UAPLY_CONFIG_JSON"] = "{}"
os.environ["UAPLY_DATA_DIR"] = tempfile.mkdtemp(prefix="uaply-place-")
import jobs_api as J  # noqa: E402

R = []


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


def mi(a, b):
    r = math.pi / 180
    x = math.sin((b[0] - a[0]) * r / 2) ** 2 + math.cos(a[0] * r) * math.cos(b[0] * r) * math.sin((b[1] - a[1]) * r / 2) ** 2
    return 2 * 3958.8 * math.asin(math.sqrt(x))


PHL = (39.9526, -75.1652)
near = {loc: J.job_geo(loc) for loc in ("Cherry Hill, NJ", "Mount Laurel, NJ", "Horsham, PA", "King of Prussia, PA", "Wilmington, DE",
                                        "Newark, DE", "Plymouth Meeting, Pennsylvania, United States", "US-PA-Malvern", "Blue Bell, PA",
                                        "Philadelphia, PA 19103", "PA-Philadelphia, UNAVAILABLE")}
t("tri-state towns and townships the app's own list never knew are placed within 50 miles of Philadelphia",
  {k: bool(v) and mi(v, PHL) <= 50 for k, v in near.items()}, {k: True for k in near})
far = {loc: J.job_geo(loc) for loc in ("El Segundo, California, United States", "Cary,North Carolina,United States", "Abilene TX",
                                       "Fort Mill, South Carolina", "St. Louis, MO", "Cambridge, MA USA", "Washington, D.C.", "Bay Area",
                                       "HQ: San Francisco", "New York City, NY", "Union Square, New York City", "Seattle, WA; Remote")}
t("places anywhere in the US: City, ST; City, State, United States; City ST; Saint/Fort/Mount; D.C.; a big city named alone",
  [k for k, v in far.items() if not v], [])
t("a name shared by two states goes to the state named (Wilmington NC is not Wilmington DE, Newark CA is not Newark NJ)",
  (mi(J.job_geo("Wilmington, NC"), PHL) > 300, mi(J.job_geo("Newark, CA"), PHL) > 2000, mi(J.job_geo("Newark, NJ"), PHL) < 90), (True, True, True))
t("San Francisco is downtown (the Census point is out at the Farallon Islands)", mi(J.job_geo("San Francisco, CA"), (37.7749, -122.4194)) < 3, True)
t("no point for a job with no place, a bare country or a state alone, or a remote one",
  [J.job_geo(x) for x in ("", "United States", "US", "New Jersey", "Remote")] + [J.job_geo("Philadelphia, PA", remote=True)], [None] * 6)
t("a ZIP code alone places a job by its first three digits", mi(J.job_geo("19104"), PHL) < 15, True)
t("the lookup key: lower case, no punctuation, Saint/Fort/Mount shortened", (J.place_key("St. Louis", "MO"), J.place_key("Fort Worth", "TX"),
  J.place_key("Mount Laurel", "NJ"), J.place_key("Winston-Salem", "NC")), ("mo|st louis", "tx|ft worth", "nj|mt laurel", "nc|winston salem"))
job = J._normalize(dict(id=1, title="Engineering Co-op", company="Acme", loc="Horsham, PA", remote=None, text="Python.", url="https://x.example/1",
                        salary_text="", posted=0, country="us"), "lever", "Acme")
t("each job carries its point (geo), two decimals", (job["geo"], job["loc"]), (J.job_geo("Horsham, PA"), "Horsham, PA"))
rem = J._normalize(dict(id=2, title="Analyst", company="Acme", loc="Remote", remote=True, text="SQL.", url="https://x.example/2", salary_text="",
                        posted=0), "lever", "Acme")
t("a remote job has none", "geo" in rem, False)
t("the place table: about 44,000 places, read once, kept as one string and an index (under 2 MB)",
  (len(J._places["off"]) > 40000, len(J._places["text"]) < 2000000), (True, True))

# ---------------- the app: jgeo, then its own city list; every ZIP3 for home ----------------
nav = open(os.path.join(ROOT, "shared", "uaply-nav.js"), encoding="utf-8").read()
cities = re.search(r"  var CITIES=\[.*?\]\.map\(function\(c\)\{return \[new w\.RegExp\([^\n]*?\]\}\);", nav, re.S).group(0)
zips = re.search(r"  var ZIP3=\[.*?\];", nav, re.S).group(0) + "\n" + re.search(r"  var ZIP3ALL=\"[^\"]*\";", nav).group(0)
fns = "".join(re.search(r"  function %s\(.*?\n" % f, nav).group(0) for f in ("geo", "jgeo", "zipGeo"))
jobs = [{"loc": "Horsham, PA", "geo": [40.18, -75.14]}, {"loc": "Philadelphia, PA"}, {"loc": "Somewhere", "geo": ["x", 1]}, {"loc": "Nowhere"}]
zipprobe = ["19104", "59801", "99501", "00601", "abc", "1"]
script = "var w={RegExp:RegExp};\n%s\n%s\n%s\nconsole.log(JSON.stringify({j:%s.map(jgeo),z:%s.map(zipGeo)}));" % (cities, zips, fns, json.dumps(jobs), json.dumps(zipprobe))
if shutil.which("node"):
    js = os.path.join(tempfile.mkdtemp(prefix="uaply-place-js-"), "place.js")
    with open(js, "w", encoding="utf-8") as f:
        f.write(script)
    r = subprocess.run(["node", js], capture_output=True, text=True, timeout=60)
    out = json.loads(r.stdout) if r.returncode == 0 else {"j": [], "z": []}
    if r.returncode:
        print(r.stderr[-1500:])
    t("the app uses the server's point first, its own city list when there is none or it is broken", out["j"],
      [[40.18, -75.14], [39.9526, -75.1652], None, None])
    z = out["z"]
    t("where you live: every US ZIP code's first three digits (Missoula 598, Anchorage 995, Puerto Rico 006), nothing for junk",
      [bool(x) for x in z], [True, True, True, True, False, False])
    t("...a Missoula ZIP is in Montana, an Anchorage one in Alaska", (mi(z[1], (46.87, -113.99)) < 60, z[2][0] > 55), (True, True))
else:
    print("SKIP node not found: the app's placement is not checked here")
for name in ("near=function(j){if(j.mode===\"remote\")return 1;var t=home&&jgeo(j);", "there=me&&jgeo(job);", "var home=homeGeo(),there=jgeo(j);"):
    t("the app places jobs with jgeo: " + name[:40], name in nav, True)

# ---------------- careers sites: co-ops, internships and tri-state pages first; their own reader places ----------------
pages = [(0, "", "https://x.wd5.myworkdayjobs.com/S/job/Austin-TX/Engineer_R%d" % i) for i in range(30)]
pages[20] = (0, "", "https://x.wd5.myworkdayjobs.com/S/job/Philadelphia-PA/Engineering-Co-op_R20")
pages[25] = (0, "", "https://x.wd5.myworkdayjobs.com/S/job/Newark-DE/Analyst_R25")
pages[28] = (0, "", "https://x.wd5.myworkdayjobs.com/S/job/Remote-de-Mexico/Analyst_R28")
got = sorted(pages[:J.CP_WINDOW], key=lambda x: (not J.CP_STUDENT_URL.search(x[2]), not J.CP_LOCAL_URL.search(x[2])))
t("a site's first read takes its co-ops and internships first, then Pennsylvania / New Jersey / Delaware pages ('-de-' in a word is not Delaware)",
  [u.rsplit("/", 2)[1] for _, _, u in got[:3]], ["Philadelphia-PA", "Newark-DE", "Austin-TX"])
held = {}
real = J._iter_raw


def fake_iter(kind, token, name):
    held[kind] = J._feed_slots._value
    return iter(())


J._iter_raw = fake_iter
try:
    J._fetch_source(("careerpage", "acme", "Acme"))
    J._fetch_source(("lever", "acme", "Acme"))
finally:
    J._iter_raw = real
t("a careers site never holds a board reader's place (16 sites waiting out crawl delays held all 8 on October 21)",
  (held.get("careerpage"), held.get("lever")), (J.FEED_PARALLEL, J.FEED_PARALLEL - 1))

print("%d / %d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
