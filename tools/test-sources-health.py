"""Guardrails for a feed of many hundreds of sources (round 1 of the 20,000-job plan, October 21, 2026):
  * job-boards.json: verified boards from tools/find-boards.py become sources (checked names, no doubles with the hand-picked list)
  * per-source health for the owner (/api/feed-health): counts, successes, failures; a source is switched off after 3 failed refreshes
    in a row and tried again a day later
  * refreshes spread out (each board's refresh time moved by up to a quarter, the same way every time)
  * the first visitor on a fresh start is answered at once with what is ready ("pending" says how many are still loading)
  * tools/find-boards.py: slugs from a name or a domain, and the Simplify list reader
  python tools/test-sources-health.py"""
import json
import os
import sys
import tempfile
import time
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ["UAPLY_CONFIG_FILE"] = "none"
os.environ["UAPLY_CONFIG_JSON"] = "{}"
os.environ["UAPLY_DATA_DIR"] = tempfile.mkdtemp(prefix="uaply-health-")
for v in ("UAPLY_FEEDS", "UAPLY_FEEDS_OFF"):
    os.environ.pop(v, None)
import jobs_api as J  # noqa: E402

R = []


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


# ---------------- job-boards.json ----------------
with open(J.BOARDS_FILE, encoding="utf-8") as f:
    rows = json.load(f)["boards"]
t("job-boards.json: every row names a supported system (or a careers site with a public sitemap), a safe board token, a name and its counts",
  [r for r in rows if not ((r.get("kind") in J.BOARD_KINDS or (r.get("kind") == "careerpage" and J._public_https(r.get("sitemap", ""))))
                           and J.BOARD_TOKEN_RE.match(r.get("token", "")) and r.get("name") and r.get("us", 0) >= 1)], [])   # 1, not 5, until we have more real jobs (card 110)
keys = [(k, t_.lower()) for k, t_, _ in J.SOURCES]
t("no board is listed twice (hand-picked and file boards together)", len(keys), len(set(keys)))
t("the file's boards come after the hand-picked boards and before the public lists (so an employer's own copy wins)",
  (J.SOURCES.index(J.FILE_SOURCES[0]) > J.SOURCES.index(("ashby", "ramp", "Ramp")) if J.FILE_SOURCES else True,
   J.SOURCES.index(J.FILE_SOURCES[-1]) < J.SOURCES.index(("remotive", "software-dev", "Remotive")) if J.FILE_SOURCES else True), (True, True))
real_file = J.BOARDS_FILE
bad = os.path.join(tempfile.mkdtemp(), "boards.json")
with open(bad, "w", encoding="utf-8") as f:
    json.dump({"boards": [{"kind": "greenhouse", "token": "../etc", "name": "X"}, {"kind": "workday", "token": "acme", "name": "Acme"},
                          {"kind": "lever", "token": "acme", "name": ""}, {"kind": "greenhouse", "token": "stripe", "name": "Stripe again"},
                          {"kind": "lever", "token": "goodco", "name": "Good Co"}]}, f)
J.BOARDS_FILE = bad
try:
    t("a row with an unsafe token, an unsupported system, no name, or a board already listed is not read", J._file_boards(), [("lever", "goodco", "Good Co")])
finally:
    J.BOARDS_FILE = real_file

# ---------------- refreshes spread out ----------------
src = ("greenhouse", "stripe", "Stripe")
ttls = [J._ttl(s) for s in J.SOURCES if s[0] == "greenhouse"]
t("a board's refresh time is its kind's, moved by at most a quarter, the same every time",
  (all(0.75 * 1800 <= x <= 1.25 * 7200 for x in ttls), J._ttl(src) == J._ttl(src), len({round(x) for x in ttls}) > len(ttls) // 2), (True, True, True))
if J.FILE_SOURCES:
    t("a job-boards.json board is read about every 2 hours", 0.75 * 7200 <= J._ttl(J.FILE_SOURCES[0]) <= 1.25 * 7200, True)

# ---------------- health and switching a failing source off ----------------
real_iter = J._iter_raw
calls = []


def failing(kind, token, name):
    calls.append(token)
    raise urllib.error.URLError("board unreachable")


J._iter_raw = failing
bad_src = ("greenhouse", "brokenco", "BrokenCo")
J.SOURCES.append(bad_src)
try:
    for _ in range(3):
        J._failed.pop(bad_src, None)
        J._fetch_source(bad_src)
    h = {x["source"]: x for x in J.feed_health()["sources"]}["greenhouse/brokenco"]
    t("three failed refreshes in a row: counted, and the source is switched off for a day", (h["failures"], h["inARow"], h["off"], bool(h["retry"])), (3, 3, True, True))
    calls.clear()
    jobs, status = J._load_source(bad_src)
    t("a switched-off source is not read, and says why", (calls, status.startswith("off: failed 3 refreshes in a row")), ([], True))
    t("...and the owner's health list names it", "greenhouse/brokenco" in J.feed_health()["off"], True)
    J._health[bad_src]["off_until"] = time.time() - 1             # its day is over
    J._iter_raw = lambda kind, token, name: iter([dict(id=1, title="Analyst", company="BrokenCo", loc="Austin, TX", remote=None, text="SQL and Excel.",
                                                       url="https://x.example/1", salary_text="", posted=int(time.time() * 1000))])
    t("after its day it is tried again, and a success switches it back on", (J._disabled(bad_src), J._fetch_source(bad_src)[1]), (False, "1 jobs"))
    h = {x["source"]: x for x in J.feed_health()["sources"]}["greenhouse/brokenco"]
    t("...with its counts kept (1 success, 3 failures, none in a row now)", (h["ok"], h["failures"], h["inARow"], h["off"], h["jobs"]), (1, 3, 0, False, 1))
    t("the health list holds counts and names only (no key, no address)", any("http" in json.dumps(x) for x in J.feed_health()["sources"]), False)
finally:
    J._iter_raw = real_iter
    J.SOURCES.remove(bad_src)
    J._health.pop(bad_src, None)
    J._cache.pop(bad_src, None)

# ---------------- the first visitor on a fresh start is answered at once ----------------
slow_src = ("greenhouse", "slowboard", "SlowBoard")
real_sources, real_allowed, real_wait = J.SOURCES, J.feeds_allowed, J.FIRST_WAIT


def slow(kind, token, name):
    time.sleep(30)
    return iter([])


J._iter_raw = slow
J.SOURCES = [slow_src]
J.feeds_allowed = lambda: {"greenhouse"}
filled = J._disk["filled"]
J._disk["filled"], J._disk["first_wait_until"] = False, 0
J._disk.pop("first_wait_until", None)
try:
    t0 = time.time()
    out = J.get_jobs()
    took = time.time() - t0
    t("a fresh start answers in about FIRST_WAIT (%d s), not when every board is in (%.1f s)" % (J.FIRST_WAIT, took), took < J.FIRST_WAIT + 3, True)
    t("...and says 1 source is still loading, so the app asks again", (out["pending"], out["sources"].get("SlowBoard")), (1, "loading"))
finally:
    J._iter_raw, J.SOURCES, J.feeds_allowed = real_iter, real_sources, real_allowed
    J._disk["filled"] = filled

# ---------------- Greenhouse: the list without descriptions, each kept posting's description read once ----------------
real_get, real_items = J._get, J._get_items
NOWISO = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 86400))
BOARD = {"jobs": [{"id": i, "title": ("Clerk %d" % i) if i % 5 else ("Marketing Intern %d" % i), "location": {"name": "Austin, TX"},
                   "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/%d" % i, "first_published": NOWISO, "updated_at": NOWISO, "metadata": []}
                  for i in range(1, 61)]}
read = []


def gh_get(url, headers=None, as_text=False):
    read.append(url)
    i = int(url.rsplit("/", 1)[1])
    j = next(x for x in BOARD["jobs"] if x["id"] == i)
    return dict(j, content="<p>Excel and SQL.</p>" if i != 7 else "<p>Nothing we can score.</p>", departments=[{"name": "Operations"}] if i != 7 else [])


def gh_items(url, key=None):
    if "content=true" in url:                    # a small board read whole: every posting with its description, one answer
        read.append(url)
        return iter([gh_get_quiet(x["id"]) for x in BOARD["jobs"]])
    return iter(BOARD["jobs"])


def gh_get_quiet(i):
    j = next(x for x in BOARD["jobs"] if x["id"] == i)
    return dict(j, content="<p>Excel and SQL.</p>" if i != 7 else "<p>Nothing we can score.</p>", departments=[{"name": "Operations"}] if i != 7 else [])


J._get = gh_get
J._get_items = gh_items
gsrc = ("greenhouse", "acmegh", "Acme")
try:
    jobs, status = J._fetch_source(gsrc)
    first = len(read)
    t("Greenhouse: a board of 60 postings (at most GH_WHOLE_MAX) is read whole once, plus one posting for the place an unscorable one left (%d reads), %d jobs kept" % (first, len(jobs)),
      (first, len(jobs) >= 14), (2, True))
    t("Greenhouse: descriptions are read only for the postings picked from the list (%d of 60), and %d are kept" % (first, len(jobs)),
      (first <= J.PER_SOURCE + J.STUDENT_PER_SOURCE + J.LOCAL_PER_SOURCE + 1, len(jobs) >= 14, all(j.get("desc") for j in jobs)), (True, True, True))
    read.clear()
    jobs2, _ = J._fetch_source(gsrc)
    t("...the next refresh reads no description: every kept job's posting is unchanged (%d read)" % len(read),
      (len(read), sorted(j["id"] for j in jobs2) == sorted(j["id"] for j in jobs)), (0, True))
    kept = jobs2[0]
    BOARD["jobs"] = [dict(x, updated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ")) if J._jid("greenhouse", x["id"]) == kept["id"] else x for x in BOARD["jobs"]]
    read.clear()
    J._fetch_source(gsrc)
    t("...a posting whose updated_at changed is read again", any(u.endswith("/%d" % next(x["id"] for x in BOARD["jobs"] if J._jid("greenhouse", x["id"]) == kept["id"])) for u in read), True)
    t("a posting with nothing to score it on is remembered and not read again while unchanged", ("acmegh", "7") in J._gh_skip, True)
    BOARD["jobs"] = BOARD["jobs"][:10]
    J._fetch_source(gsrc)
    t("postings that left the board are forgotten", all(int(k[1]) <= 10 for k in list(J._gh_seen) + list(J._gh_skip) if k[0] == "acmegh"), True)
finally:
    J._get, J._get_items = real_get, real_items
    J._cache.pop(gsrc, None)

# ---------------- a fixed set of reader threads, not a thread per source ----------------
import threading  # noqa: E402
real_ref = J._refresh_in_background
gate = threading.Event()
J._refresh_in_background = lambda src, ev: (gate.wait(5), J._refreshing.pop(src, None), ev.set())
try:
    before = threading.active_count()
    with J._lock:
        evs = [J._start_refresh(("greenhouse", "pool%d" % i, "P")) for i in range(60)]
    t("60 boards waiting to be read use %d reader threads, not 60" % J.FEED_PARALLEL, threading.active_count() - before <= J.FEED_PARALLEL, True)
    gate.set()
    t("...and every one of them is read", all(e.wait(10) for e in evs), True)
finally:
    J._refresh_in_background = real_ref

# ---------------- the list the app gets: written straight into gzip, the same as get_jobs ----------------
import gzip  # noqa: E402
J._cache[("greenhouse", "listco", "ListCo")] = {"at": time.time(), "status": "2 jobs", "jobs": [
    J._normalize(dict(id=i, title="Analyst %d" % i, company="ListCo", loc="Austin, TX", remote=None, text="SQL and Excel. " * 80,
                      url="https://x.example/%d" % i, salary_text="", posted=int(time.time() * 1000)), "greenhouse", "ListCo") for i in (1, 2)]}
real_sources, real_allowed = J.SOURCES, J.feeds_allowed
J.SOURCES, J.feeds_allowed = [("greenhouse", "listco", "ListCo")], (lambda: {"greenhouse"})
try:
    J._json_memo.update(key=None, gz=b"")
    streamed = json.loads(gzip.decompress(J.get_json(compressed=True)))
    plain = J.get_jobs()
    streamed.pop("fetched_at"), plain.pop("fetched_at")
    t("the compressed list the app gets is exactly get_jobs (2 jobs, no email description, postedDays)",
      (streamed == plain, len(streamed["jobs"]), "desc" in streamed["jobs"][0], streamed["jobs"][0].get("postedDays")), (True, 2, False, 0))
    t("...and a client without gzip gets the same list plain", json.loads(J.get_json())["jobs"] == streamed["jobs"], True)
finally:
    J.SOURCES, J.feeds_allowed = real_sources, real_allowed
    J._cache.pop(("greenhouse", "listco", "ListCo"), None)
    J._json_memo.update(key=None, gz=b"")

# ---------------- apply-link proof: dead links hidden, a source with too many switched off ----------------
lsrc = ("lever", "linkco", "LinkCo")
J._cache[lsrc] = {"at": time.time(), "status": "20 jobs", "jobs": [
    J._normalize(dict(id="l%d" % i, title="Analyst %d" % i, company="LinkCo", loc="Austin, TX", remote=None, text="SQL and Excel.",
                      url="https://jobs.lever.co/linkco/%d" % i, salary_text="", posted=int(time.time() * 1000)), "lever", "LinkCo") for i in range(20)]}
real_alive = J._link_alive
dead_set = {"https://jobs.lever.co/linkco/3"}
J._link_alive = lambda url: False if url in dead_set else (None if url.endswith("/5") else True)
try:
    rec = J.check_links(lsrc)
    t("20 links checked: 1 dead, 1 could not tell (not counted), 18 alive; the source stays on (1 of 19 is under 10%)",
      (rec["ok"], rec["dead"], rec["unknown"], rec["off"]), (18, 1, 1, False))
    real_sources2, real_allowed2 = J.SOURCES, J.feeds_allowed
    J.SOURCES, J.feeds_allowed = [lsrc], (lambda: {"lever"})
    try:
        shown = [j["url"] for j in J.get_jobs()["jobs"]]
        t("the job with the dead link is not shown, the others are", ("https://jobs.lever.co/linkco/3" in shown, len(shown)), (False, 19))
    finally:
        J.SOURCES, J.feeds_allowed = real_sources2, real_allowed2
    dead_set.update("https://jobs.lever.co/linkco/%d" % i for i in range(6, 9))
    J._links.pop(lsrc, None)
    rec = J.check_links(lsrc)
    t("4 dead of 19 counted (over 10%): the source is switched off, with the reason for the owner",
      (rec["off"], J._disabled(lsrc), "apply links checked were dead" in J._health[lsrc]["error"]), (True, True, True))
    J.SOURCES.append(lsrc)
    try:
        h = {x["source"]: x for x in J.feed_health()["sources"]}["lever/linkco"]
    finally:
        J.SOURCES.remove(lsrc)
    t("the owner's health list shows the source's apply path and link results", (h["applyPath"].startswith("hand-off"), h["links"]["checked"], h["links"]["dead"], h["off"]),
      (True, 19, 4, True))
finally:
    J._link_alive = real_alive
    J._cache.pop(lsrc, None)
    J._links.pop(lsrc, None)
    J._health.pop(lsrc, None)
t("the background link check is off unless serve.py turns it on (hosted server)", J.link_check_on, False)

# ---------------- tools/find-boards.py ----------------
import importlib.util  # noqa: E402
spec = importlib.util.spec_from_file_location("fb", os.path.join(HERE, "find-boards.py"))
fb = importlib.util.module_from_spec(spec)
sys.argv = [sys.argv[0]]
spec.loader.exec_module(fb)
t("slugs from a name: squashed, hyphenated, the Inc/careers/hq forms", [x for x in fb.slugs("Cross River Bank") if x in ("crossriverbank", "cross-river-bank", "crossriverbankinc")],
  ["crossriverbank", "cross-river-bank", "crossriverbankinc"])
t("slugs from a domain: its first label", fb.slugs("toasttab.com"), ["toasttab"])
t("a trailing Inc/LLC/Corp is taken off", "acme" in fb.slugs("Acme, Inc."), True)
t("every slug is a safe board token", all(fb.TOKEN_RE.match(x) for n in ("Johnson & Johnson", "L'Oreal USA", "Day & Zimmermann", "St Lukes") for x in fb.slugs(n)), True)

# ---------------- no stray control characters in the code (a "\b" typed through a shell once became a backspace, and "India" stopped matching) ----------------
import glob  # noqa: E402
bad = []
for path in [os.path.join(ROOT, n) for n in ("jobs_api.py", "serve.py", "setup_api.py", "uaply_api.py", "ats_api.py")] + glob.glob(os.path.join(ROOT, "shared", "*.js")) + glob.glob(os.path.join(HERE, "*.py")):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if any(ch in text for ch in [chr(c) for c in range(32) if c not in (9, 10, 13)]):
        bad.append(os.path.relpath(path, ROOT))
t("no source file holds a control character (backspace, form feed ...)", bad, [])

print(sum(R), "/", len(R))
sys.exit(0 if all(R) else 1)
