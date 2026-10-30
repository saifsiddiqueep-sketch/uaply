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
# Oct 30, 2026: UAply covers the US and Canada, so this posting is now kept as a Canadian job (before, it was dropped as outside the US)
n = j._normalize(raw("Software Engineering Intern 2027 (Toronto)", "Toronto, ON, CA"), "greenhouse", "Acme")
t("a Toronto internship listed as ', CA' is kept as Canadian, shown as 'Toronto, ON, Canada' (never California)",
  n and (n["country"], n["loc"], n.get("geo")), ("ca", "Toronto, ON, Canada", None))
t("'San Jose, CA' stays a California job", (j._normalize(raw("Software Engineer", "San Jose, CA"), "greenhouse", "Acme") or {}).get("country"), "us")
for loc, remote, want in [
    ("Toronto, ON, CA", False, ["ca"]), ("Vancouver, BC, Canada", False, ["ca"]), ("Remote - Canada", True, ["ca"]),
    ("San Jose, CA", False, ["us"]), ("Los Angeles, CA, USA", False, ["us"]), ("Ontario, CA", False, ["us"]),     # Ontario, California
    ("Vancouver, WA", False, ["us"]), ("London, ON", False, ["ca"]), ("Montreal, Quebec", False, ["ca"]), ("Calgary, AB", False, ["ca"]),
    ("Halifax, Nova Scotia", False, ["ca"]), ("Whitehorse, YT", False, ["ca"]), ("CA-ON-Toronto", False, ["ca"]), ("Ottawa", False, ["ca"]),
    ("Remote (US or Canada)", True, ["us", "ca"]), ("Austin, TX; Toronto, ON", False, ["us", "ca"]), ("Remote", True, ["us"]),
    ("London, UK", False, []), ("Munich, BY, DE", False, []), ("Remote - Mexico", True, []), ("Sydney, Australia", True, []),
]:
    t("job_countries(%r)" % loc, j.job_countries(loc, remote), want)
n = j._normalize(dict(raw("Data Analyst", "Toronto, ON"), text="Python and SQL. Salary: $80,000 - $95,000 CAD per year."), "greenhouse", "Acme")
t("CAD pay stays as the posting gives it (never converted, never called USD)", n and (n["sal"], n.get("cur")), ([80000, 95000], "CAD"))
n = j._normalize(dict(raw("Data Analyst", "Austin, TX"), text="Python and SQL. Salary: $80,000 - $95,000 per year."), "greenhouse", "Acme")
t("US dollar pay carries no currency mark (USD is the default)", n and (n["sal"], "cur" in n), ([80000, 95000], False))
t("USAJOBS stays US: a Canadian posting from it is dropped", j._normalize(raw("Analyst", "Toronto, ON, Canada"), "usajobs", "USAJOBS"), None)
t("an 'ANZ' role listed as just Remote is dropped", j._normalize(raw("Support Representative - ANZ (Australia / New Zealand)", "Remote", True), "greenhouse", "Acme"), None)
t("a 'LATAM' role listed as just Remote is dropped", j._normalize(raw("Developer Representative - LATAM", "Remote", True), "greenhouse", "Acme"), None)
t("a US remote role is kept", j._normalize(raw("Backend Engineer", "Remote - USA", True), "greenhouse", "Acme") is not None, True)
t("an http:// careers link is opened securely (https://), never as http", (j._normalize(dict(raw("Engineer", "Austin, TX"), url="http://example.com/x"), "greenhouse", "Acme") or {}).get("url"), "https://example.com/x")
t("a link that is not a web address is dropped", [j._normalize(dict(raw("Engineer", "Austin, TX"), url=u), "greenhouse", "Acme") for u in ("javascript:alert(1)", "mailto:jobs@example.com", "ftp://example.com/x")], [None, None, None])
t("a role in India is dropped, one in Indiana is kept (the \\b in FOREIGN_RE is a word boundary, not a backspace)",
  [bool(j.FOREIGN_RE.search(s)) for s in ("India", "Remote, India", "Hybrid - India", "Indiana", "Indianapolis, IN")], [True, True, True, False, False])
import time as _time  # noqa: E402
_now = _time.time()
n = j._normalize(dict(raw("Data Analyst", "Austin, TX"), posted=int(_now) - 86400, updated=int(_now)), "greenhouse", "Acme")
t("a date given in seconds is kept in epoch ms (never read as 1970 and dropped by the 60-day rule)",
  (n["posted"] > 1e12, n.get("updated", 0) > n["posted"], j._too_old(n, _now * 1000)), (True, True, False))
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

# ---- the dead-link check opens only public pages and follows redirects only to public ones (October 22 review) ----
# A stand-in employer site on this computer, reached as if it were the public jobs.acme.example (93.184.216.34): the names are looked up
# and checked for real; only the final connection to that public address is sent here.
import http.server  # noqa: E402
import socket  # noqa: E402
import threading  # noqa: E402


class Site(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        p = self.path
        if p.startswith("/hop/"):
            n = int(p.rsplit("/", 1)[1])
            return self.go("http://jobs.acme.example/hop/%d" % (n + 1))
        go = {"/moved": "http://jobs.acme.example/open", "/meta": "http://169.254.169.254/latest/meta-data/",
              "/inside": "https://inside.acme.example/admin", "/ip": "http://10.0.0.5/admin", "/gh": "http://jobs.acme.example/board?error=true",
              "/port": "http://jobs.acme.example:8080/open"}.get(p)
        if go:
            return self.go(go)
        code, body = {"/open": (200, "Apply now"), "/gone": (404, "Not found"), "/closed": (200, "This job is no longer available"),
                      "/board?error=true": (200, "Our open roles")}.get(p, (500, "oops"))
        self.send_response(code)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body.encode())

    def go(self, where):
        self.send_response(302)
        self.send_header("Location", where)
        self.end_headers()


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Site)
threading.Thread(target=srv.serve_forever, daemon=True).start()
PUBLIC = {"jobs.acme.example": "93.184.216.34", "down.acme.example": "93.184.216.35", "inside.acme.example": "10.1.2.3"}
real_gai, real_cc, dialled = socket.getaddrinfo, socket.create_connection, []


def fake_gai(host, port, *a, **k):
    if host in PUBLIC:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (PUBLIC[host], port))]
    if host == "nowhere.acme.example":
        raise socket.gaierror("no such name")
    return real_gai(host, port, *a, **k)


def fake_cc(addr, *a, **k):
    dialled.append(addr[0])
    if addr[0] == "93.184.216.34":
        return real_cc(("127.0.0.1", srv.server_address[1]), *a, **k)
    raise ConnectionRefusedError("nothing here")


socket.getaddrinfo, socket.create_connection = fake_gai, fake_cc
try:
    base = "http://jobs.acme.example"
    for path, want, why in (("/open", True, "a page that answers is alive"), ("/gone", False, "a 404 is dead"),
                            ("/closed", False, "the board's own 'no longer available' page is dead"),
                            ("/moved", True, "a redirect to another public page is followed"),
                            ("/gh", False, "Greenhouse's closed posting (sent to its board with ?error=true) is dead"),
                            ("/meta", False, "a redirect to the cloud metadata address 169.254.169.254 is dead, never followed"),
                            ("/inside", False, "a redirect to a name that resolves to a private address is dead, never connected to"),
                            ("/ip", False, "a redirect to a private IP address is dead"),
                            ("/port", False, "a redirect to another port is not followed"),
                            ("/hop/0", None, "a redirect chain longer than urllib's cap of 10 cannot tell (not dead)")):
        dialled.clear()
        got = j._link_alive(base + path)
        t("dead-link check: %s" % why, (got, [d for d in dialled if d != "93.184.216.34"]), (want, []))
    t("dead-link check: an internal start address is dead without a request",
      [j._link_alive(u) for u in ("http://10.0.0.5/job", "https://localhost/job", "http://169.254.169.254/latest/", "https://intranet.local/job")],
      [False, False, False, False])
    t("dead-link check: the default ports are fine, another is not", (j._link_alive("http://jobs.acme.example:80/open"), j._link_alive("https://jobs.acme.example:8443/open")),
      (True, False))
    t("dead-link check: a site that does not answer, or a name that does not resolve, cannot tell (never counted as dead)",
      (j._link_alive("http://down.acme.example/job"), j._link_alive("http://nowhere.acme.example/job")), (None, None))
finally:
    socket.getaddrinfo, socket.create_connection = real_gai, real_cc
    srv.shutdown()

print(sum(R), "/", len(R))
sys.exit(0 if all(R) else 1)
