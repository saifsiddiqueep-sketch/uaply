"""Unit tests for the job feed rules (no network): which postings count as US jobs, and how they are classified.
  python tools/test-jobs.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import jobs_api as j  # noqa: E402

R = []


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


# (location, remote flag, should it be offered to a person in the US?)
for loc, remote, want in [
    ("Toronto, ON, CA", False, False),                      # ', CA' here is Canada, not California
    ("San Francisco, CA", False, True),
    ("Remote", True, True),
    ("Remote", False, False),
    ("Remote - USA", True, True),
    ("Remote, Canada", True, False),
    ("London, UK", False, False),
    ("Berlin, Germany", True, False),
    ("Austin, TX", False, True),
    ("New York, NY", False, True),
    ("Canada; United States", False, True),                 # one posting, several cities: a US one is enough
    ("Bellevue, Washington; Mountain View, California; Vancouver, Canada", False, True),
    ("Sydney, Australia", True, False),
]:
    t("location %r (remote=%s)" % (loc, remote), j._us_ok(loc, remote), want)


def raw(title, loc, remote=None):
    return dict(id=1, title=title, company="Acme", loc=loc, remote=remote, text="Python and SQL required. 2 years of experience.",
                url="https://example.com/job/1", salary_text="", posted=0)


t("a plain US job is kept", j._normalize(raw("Software Engineer", "Austin, TX"), "greenhouse", "Acme") is not None, True)
t("a Toronto internship listed as ', CA' is dropped", j._normalize(raw("Software Engineering Intern 2027 (Toronto)", "Toronto, ON, CA"), "greenhouse", "Acme"), None)
t("an 'ANZ' role listed as just Remote is dropped", j._normalize(raw("Support Representative - ANZ (Australia / New Zealand)", "Remote", True), "greenhouse", "Acme"), None)
t("a 'LATAM' role listed as just Remote is dropped", j._normalize(raw("Developer Representative - LATAM", "Remote", True), "greenhouse", "Acme"), None)
t("a US remote role is kept", j._normalize(raw("Backend Engineer", "Remote - USA", True), "greenhouse", "Acme") is not None, True)
t("an http:// careers link is opened securely (https://), never as http", (j._normalize(dict(raw("Engineer", "Austin, TX"), url="http://example.com/x"), "greenhouse", "Acme") or {}).get("url"), "https://example.com/x")
t("a link that is not a web address is dropped", [j._normalize(dict(raw("Engineer", "Austin, TX"), url=u), "greenhouse", "Acme") for u in ("javascript:alert(1)", "mailto:jobs@example.com", "ftp://example.com/x")], [None, None, None])
n = j._normalize(raw("Software Engineer Intern", "Austin, TX"), "greenhouse", "Acme")
t("an intern title is classified as an internship", n and n["type"], "internship")
n = j._normalize(raw("Hardware Engineer (Winter Co-op)", "Austin, TX"), "greenhouse", "Acme")
t("a co-op title is classified as a co-op", n and n["type"], "coop")
n = j._normalize(raw("Engineer", "Austin, TX"), "greenhouse", "Acme")
t("a feed job is link-out only and never has a recruiter address", (n["apply"], n["contact"]), ("link", ""))
# "recruiting" in a company's boilerplate must not become a skill on an engineering job (it did: a firmware co-op listed "Hiring")
boiler = dict(raw("Firmware Engineer Co-Op", "Austin, TX"), text="Python and SQL. Samsara is an equal opportunity employer. Our recruiting process and recruiting privacy notice apply to all applicants. " * 3)
n = j._normalize(boiler, "greenhouse", "Acme")
t("boilerplate 'recruiting' does not add a Hiring skill to an engineering job", n and "Hiring" in n["skills"], False)
n = j._normalize(dict(boiler, title="Technical Recruiter"), "greenhouse", "Acme")
t("a recruiter role does get the Hiring skill", n and "Hiring" in n["skills"], True)

# a remote job's place must not repeat the word "Remote" the work-style tag already shows ("Remote - USA  Remote" on the card)
for loc, want in [("Remote - USA", "USA"), ("Remote (US)", "US"), ("Remote, US", "US"), ("Remote", "United States"), ("remote", "United States"),
                  ("Remote - United States", "United States"), ("Remote / Austin, TX", "Austin, TX"), ("Remotely hosted office, Austin, TX", "Remotely hosted office, Austin, TX"),
                  # real places from the live feeds: anything that does not start with the word is left exactly as listed, brackets included
                  ("San Francisco Bay Area (or Remote U.S.)", "San Francisco Bay Area (or Remote U.S.)"), ("CA Remote (BC & ON only); U.S. Remote", "CA Remote (BC & ON only); U.S. Remote"),
                  ("US: Select locations", "US: Select locations"), ("U.S.", "U.S."), ("Remote (US) - Austin, TX", "US - Austin, TX")]:
    t("remote place %r is shown as %r" % (loc, want), j._place(loc, "remote"), want)
t("an on-site place is left exactly as listed", j._place("Remote Control Way, Austin, TX", "onsite"), "Remote Control Way, Austin, TX")
t("an empty place reads Not listed", j._place("", "onsite"), "Not listed")
n = j._normalize(raw("Backend Engineer", "Remote - USA", True), "greenhouse", "Acme")
t("a remote feed job no longer repeats Remote in its place", (n["loc"], n["mode"]), ("USA", "remote"))

# the public job list must not show a visitor a raw network error from a feed (it names hosts and addresses); the owner's own computer still sees it
real_load, real_feeds, real_sources = j._load_source, j.feeds_allowed, j.SOURCES
j.SOURCES = [("greenhouse", "acme", "Acme")]
j.feeds_allowed = lambda: {"greenhouse"}
j._load_source = lambda src: ([], "error: <urlopen error [Errno 11001] getaddrinfo failed for boards.internal.example>")
try:
    j.hide_errors = False
    owner_view = j.get_jobs()["sources"]["Acme"]
    j.hide_errors = True
    public_view = j.get_jobs()["sources"]["Acme"]
finally:
    j.hide_errors = False
    j._load_source, j.feeds_allowed, j.SOURCES = real_load, real_feeds, real_sources
t("on the owner's computer a failing feed shows its reason", "getaddrinfo" in owner_view, True)
t("on a hosted server the public list says only 'unavailable right now'", public_view, "unavailable right now")
t("the documentation example employer is never served as jobs", [e for e in j.partner_jobs() if e["co"] == "Example Partner Co"], [])

# the job description shown in emails: the role, not the company's introduction, and always ending on a whole sentence
intro = "About Acme: We are a company that builds things people love and we are growing. " * 4
body = "About the Role: We need an intern to help build the checkout flow. You will write code, add tests and learn from senior engineers. " + "More detail about the team and tools. " * 40
d = j._role_summary(intro + body)
t("the description starts at the role section", d.startswith("About the Role:"), True)
t("the description is short enough to read in an email", len(d) <= 660, True)
t("the description ends on a whole sentence", d.rstrip().endswith("."), True)
t("a posting with no role heading still gets a clean summary", j._role_summary("We build robots. " * 100).endswith("robots."), True)
t("a short posting is kept whole", j._role_summary("A short posting."), "A short posting.")

# ---------------- stale postings: older than MAX_AGE_DAYS (60) by their newest date are left out ----------------
NOW = 1792540800000                                    # a fixed clock: 2026-10-20 00:00 UTC, in ms
D = j.DAY_MS
t("the rule is 60 days", j.MAX_AGE_DAYS, 60)
t("posted 61 days ago, never updated: too old", j._too_old({"posted": NOW - 61 * D}, NOW), True)
t("posted 59 days ago: kept", j._too_old({"posted": NOW - 59 * D}, NOW), False)
t("posted 3 years ago but updated last week (Greenhouse): kept", j._too_old({"posted": NOW - 1100 * D, "updated": NOW - 7 * D}, NOW), False)
t("no date at all: kept (nothing says it is old)", j._too_old({"posted": 0}, NOW), False)
a = j._with_age({"id": 1, "posted": NOW - 3 * D - 5000, "updated": NOW - D}, NOW)
t("postedDays and updatedDays are whole days", (a["postedDays"], a["updatedDays"]), (3, 1))
t("a job with no date gets no postedDays", "postedDays" in j._with_age({"id": 1, "posted": 0}, NOW), False)
src_job = {"id": 1, "posted": NOW}
j._with_age(src_job, NOW)
t("the cached job itself is not changed (a copy is returned)", "postedDays" in src_job, False)
gh = j._normalize(dict(raw("Engineer", "Austin, TX"), posted=NOW - 900 * D, updated=NOW - 2 * D), "greenhouse", "Acme")
t("a Greenhouse posting keeps its update date next to its first-published date", (gh["posted"], gh["updated"]), (NOW - 900 * D, NOW - 2 * D))
t("an update date no newer than the posting date is not stored", "updated" in j._normalize(dict(raw("Engineer", "Austin, TX"), posted=NOW, updated=NOW), "greenhouse", "Acme"), False)

# ---------------- one board read: stale postings skipped before the caps, Pennsylvania roles kept past them ----------------
real_iter, real_time = j._iter_raw, j.time.time


def board(*postings):
    j._iter_raw = lambda kind, token, name: iter([dict(raw(title, loc), id=i, posted=posted) for i, (title, loc, posted) in enumerate(postings)])


j.time.time = lambda: NOW / 1000
try:
    fresh, old = NOW - 5 * D, NOW - 90 * D
    # 20 stale roles first, then 14 fresh ones: the stale ones must not use up the 14 places
    board(*([("Old Engineer %d" % i, "Austin, TX", old) for i in range(20)] + [("Engineer %d" % i, "Austin, TX", fresh) for i in range(14)]))
    js, status = j._fetch_source(("greenhouse", "acme", "Acme"))
    t("stale postings are skipped before the caps: all 14 fresh ones are kept", (len(js), all(x["role"].startswith("Engineer") for x in js)), (14, True))
    t("the status says how many were left out for age", status, "14 jobs; 20 older than 60 days left out")
    # 30 roles elsewhere first, then 12 in Pennsylvania: 14 + 10 Pennsylvania extras
    board(*([("Engineer %d" % i, "Austin, TX", fresh) for i in range(30)] + [("PA Engineer %d" % i, "Philadelphia, PA", fresh) for i in range(12)]))
    js, status = j._fetch_source(("greenhouse", "acme", "Acme"))
    pa = [x for x in js if x["loc"] == "Philadelphia, PA"]
    t("a board keeps up to 10 Pennsylvania roles past its 14", (len(js), len(pa)), (24, 10))
    t("...each one once", len({x["id"] for x in js}), 24)
    board(*[("Engineer %d" % i, "Pittsburgh, PA" if i % 2 else "Austin, TX", fresh) for i in range(40)])
    js, _ = j._fetch_source(("greenhouse", "acme", "Acme"))
    t("Pennsylvania roles inside the first 14 are not counted twice", (len(js), len({x["id"] for x in js})), (24, 24))
    board(*[("Engineer %d" % i, "Austin, TX", fresh) for i in range(30)])
    t("a board with no Pennsylvania roles still keeps 14", len(j._fetch_source(("greenhouse", "acme", "Acme"))[0]), 14)
    board(*[("Program Analyst %d" % i, "Philadelphia, PA", old) for i in range(5)])
    os.environ["UAPLY_USAJOBS_KEY"] = "FAKEtestKey0123456789abcdefABCDEF"          # made up: only so the source is not skipped as "no key"
    try:
        t("USAJOBS announcements open for 90 days are kept (USAJOBS lists only open ones)", j._fetch_source(("usajobs", "philadelphia", "USAJOBS")),
          (j._cache[("usajobs", "philadelphia", "USAJOBS")]["jobs"], "5 jobs"))
    finally:
        os.environ.pop("UAPLY_USAJOBS_KEY", None)
    t("', Pennsylvania' and ', PA' both count as Pennsylvania", (bool(j.LOCAL_RE.search("Erie, Pennsylvania")), bool(j.LOCAL_RE.search("Erie, PA"))), (True, True))
    t("'Palo Alto' and 'Spain' do not", (bool(j.LOCAL_RE.search("Palo Alto, CA")), bool(j.LOCAL_RE.search("Madrid, Spain"))), (False, False))
finally:
    j._iter_raw, j.time.time = real_iter, real_time
    j._cache.clear()

# ---------------- the same job from two feeds is shown once ----------------
def job(i, co, role, loc, posted=None):
    return {"id": i, "co": co, "role": role, "loc": loc, "posted": NOW - D if posted is None else posted}


feeds = {("greenhouse", "acme", "Acme"): [job(1, "Acme", "Data Analyst", "Philadelphia, PA"), job(2, "Acme", "Data Analyst", "Austin, TX"),
                                          job(3, "Acme", "Data Analyst", "Philadelphia, PA")],                 # the employer listed it twice: kept
         ("usajobs", "philadelphia", "USAJOBS"): [job(10, "Department of the Navy", "Program Analyst", "Philadelphia, PA", NOW - 90 * D)],   # open: kept
         ("muse", "Entry Level", "The Muse"): [job(4, "Acme, Inc.", "Data  Analyst", "philadelphia, pa"),     # the same job via The Muse
                                               job(5, "Acme Robotics", "Data Analyst", "Philadelphia, PA"),   # another company
                                               job(6, "Acme", "Senior Data Analyst", "Philadelphia, PA"),     # another title
                                               job(7, "Acme", "Old Analyst", "Philadelphia, PA", NOW - 70 * D)]}
real_partners = j.partner_jobs
j.SOURCES = list(feeds)
j.feeds_allowed = lambda: {"greenhouse", "muse", "usajobs"}
j._load_source = lambda src: (feeds[src], "%d jobs" % len(feeds[src]))
j.partner_jobs = lambda: [dict(job(8, "Partner Co", "Cashier", "Philadelphia, PA"), apply="direct"),
                          dict(job(9, "Partner Co", "Cashier", "Philadelphia, PA"), apply="direct")]     # a partner's two openings stay two
real_clock = j.time.time
j.time.time = lambda: NOW / 1000
try:
    out = j.get_jobs()
finally:
    j._load_source, j.feeds_allowed, j.SOURCES, j.partner_jobs, j.time.time = real_load, real_feeds, real_sources, real_partners, real_clock
ids = [x["id"] for x in out["jobs"]]
t("the employer's own copies are kept (both: one board listing a title twice can be two openings); The Muse's copy is not", ids, [8, 9, 1, 2, 3, 10, 5, 6])
t("merged counts the copy left out, aged_out the stale one (not the open federal announcement)", (out["merged"], out["aged_out"]), (1, 1))
t("every served job says how many days ago it was posted", [x.get("postedDays") for x in out["jobs"]], [1] * 5 + [90] + [1] * 2)
t("a feed's copy of a partner's posting is dropped (the partner's can really be applied to)",
  j._same_job_key(job(0, "Partner Co.", "Cashier", "Philadelphia, PA")) == j._same_job_key(job(8, "Partner Co", "Cashier", "Philadelphia, PA")), True)
t("company suffixes, case, punctuation and spacing are set aside; words inside names are not",
  (j._same_job_key(job(0, "The Acme Co.", "Data-Analyst", "Austin,  TX")) == j._same_job_key(job(0, "acme", "data analyst", "austin tx")),
   j._same_job_key(job(0, "Coinbase", "x", "y"))[0]), (True, "coinbase"))

# ---------------- a board read as it arrives (_get_items), a small part at a time ----------------
import io  # noqa: E402
import json as _json  # noqa: E402
real_open, real_chunk = j.urllib.request.urlopen, j.STREAM_CHUNK
ANSWER = {}
j.urllib.request.urlopen = lambda req, timeout=None: io.BytesIO(ANSWER["body"])
try:
    j.STREAM_CHUNK = 7                                                   # tiny parts: every value, word and letter gets cut somewhere
    board_ = {"apiVersion": "1", "meta": {"n": [1, 2.5, None, True]}, "jobs": [{"id": i, "title": "Ingénieur № %d — 日本" % i, "n": 10 ** 12 + i,
              "x": [None, False, {"a": "}]\",["}]} for i in range(40)], "after": {"ignored": 1}}
    ANSWER["body"] = _json.dumps(board_, ensure_ascii=False).encode("utf-8")
    t("a {..., \"jobs\": [...]} answer read in 7-byte parts gives every posting, unchanged (UTF-8 cut mid-letter, numbers cut mid-digit)",
      list(j._get_items("https://x.example/", "jobs")), board_["jobs"])
    ANSWER["body"] = _json.dumps(board_["jobs"]).encode("utf-8")
    t("a top-level list (Lever) the same way", list(j._get_items("https://x.example/")), board_["jobs"])
    for body, want in ((b'{"jobs": []}', []), (b'[]', []), (b' { "other": 1 , "jobs" : [ {"id": 1} ] } ', [{"id": 1}]), (b'{"meta": 1}', [])):
        ANSWER["body"] = body
        t("the answer %r gives %r" % (body, want), list(j._get_items("https://x.example/", None if body.strip().startswith(b"[") else "jobs")), want)
    for body in (b'{"jobs": [{"id": 1}, {"id": 2', b'<html>Not found</html>', b'{"jobs": [{"id": 1} {"id": 2}]}'):
        ANSWER["body"] = body
        try:
            list(j._get_items("https://x.example/", "jobs"))
            bad = "no error"
        except ValueError:
            bad = "refused"
        t("a cut-off or broken answer %r is refused, not half-read" % body[:30], bad, "refused")
    j.STREAM_CHUNK = 64 * 1024
    real_max, j.MAX_FEED_BYTES = j.MAX_FEED_BYTES, 1000
    ANSWER["body"] = _json.dumps({"jobs": [{"id": i, "t": "x" * 50} for i in range(100)]}).encode("utf-8")
    try:
        list(j._get_items("https://x.example/", "jobs"))
        capped = "read"
    except ValueError as e:
        capped = "refused" if "larger than" in str(e) else str(e)
    finally:
        j.MAX_FEED_BYTES = real_max
    t("an answer past MAX_FEED_BYTES is refused (the 40 MB cap still holds)", capped, "refused")
finally:
    j.urllib.request.urlopen, j.STREAM_CHUNK = real_open, real_chunk

print(sum(R), "/", len(R))
sys.exit(0 if all(R) else 1)
