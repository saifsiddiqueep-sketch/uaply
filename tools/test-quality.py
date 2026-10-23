"""Job quality fixes from the student walk (October 21, 2026):
  * company names without the careers-site label a board adds ("Perpay - Career's Page" -> "Perpay")
  * the education a job needs: licensed clinical and degree-gated roles are never "High school"; internships by what a student must
    have finished; graduate-only internships marked gradOnly
  * part-time from the schedule a posting describes (hours a week, "part-time" but not "full-time or part-time")
  * a per-feed deadline: one slow feed is dropped and retried, it never holds the others
  python tools/test-quality.py [port]      with a port, also the Internship stack's order in Chrome (tools/ui-intern-order.js)"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.environ["UAPLY_CONFIG_FILE"] = "none"
os.environ["UAPLY_CONFIG_JSON"] = "{}"
os.environ["UAPLY_DATA_DIR"] = tempfile.mkdtemp(prefix="uaply-quality-")
for v in ("UAPLY_FEEDS", "UAPLY_FEEDS_OFF"):
    os.environ.pop(v, None)
import jobs_api as J  # noqa: E402

R = []


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


# ---------------- company names (the board names seen in the live feeds) ----------------
for raw, want in [("Perpay - Career's Page", "Perpay"), ("Point72 ", "Point72"), (" sweetgreen", "sweetgreen"), ("ATOMS Careers page", "ATOMS"),
                  ("DRW - University Jobs", "DRW"), ("Tenstorrent University Jobs", "Tenstorrent"), ("Hometap Jobs", "Hometap"),
                  ("Astera Labs Early Career - North America 2027", "Astera Labs"), ("MORSE Corp Co-op Opportunities ", "MORSE Corp"),
                  ("Jobs at Acme", "Acme"), ("Acme Inc. | Careers", "Acme Inc."), ("Chewy Careers", "Chewy"), ("Angel City ", "Angel City"),
                  # names that only look like labels stay as they are
                  ("CourseCareers", "CourseCareers"), ("Jobs for Humanity", "Jobs for Humanity"), ("JobsOhio", "JobsOhio"), ("The Hiring Company", "The Hiring Company")]:
    t("company %r is shown as %r" % (raw, want), J._clean_company(raw, "Board"), want)
t("a name that is only a label becomes the board's own name", (J._clean_company("Careers", "Perpay"), J._clean_company("  ", "Perpay")), ("Perpay", "Perpay"))
n = J._normalize(dict(id=1, title="Data Analyst", company="Perpay - Career's Page", loc="Philadelphia, PA", remote=None, text="SQL and Excel.",
                      url="https://job-boards.greenhouse.io/perpay/jobs/1", salary_text="", posted=0), "greenhouse", "Perpay", "perpay")
t("the card and the credit carry the clean name", (n["co"], n["source"], n["via"]), ("Perpay", "Perpay's careers page", "Perpay on Greenhouse"))

# ---------------- education (real titles from the live feeds) ----------------
for title, text, jt, want in [
        ("Registered Nurse - Med/Surg", "Requires an active RN license.", "full-time", "Associate"),
        ("Licensed Practical Nurse (LPN/LVN) - Scottsdale, AZ - Onsite", "", "full-time", "Associate"),
        ("Licensed Clinical Social Worker (LCSW) - Part-Time + Up to $500", "", "part-time", "Master"),
        ("Licensed Mental Health Counselor (LMHC) - Part-Time", "", "part-time", "Master"),
        ("Mental Health Therapist - Part-Time + $500 Signing Bonus", "Licensed in PA.", "part-time", "Master"),
        ("Nurse Practitioner", "", "full-time", "Master"), ("Physician Assistant", "", "full-time", "Master"),
        ("Clinical Review Pharmacist (6-month, full-time contract)", "", "contract", "Doctorate"), ("Psychologist", "", "full-time", "Doctorate"),
        ("Physical Therapist", "", "full-time", "Doctorate"), ("Assistant City Solicitor", "Must be licensed to practice law.", "full-time", "Doctorate"),
        ("Research Scientist", "A PhD in machine learning is required.", "full-time", "Doctorate"),
        ("Data Scientist", "PhD preferred. Bachelor's degree in a quantitative field.", "full-time", "Bachelor"),
        ("Software Engineer", "Bachelor's degree in computer science or equivalent.", "full-time", "Bachelor"),
        ("Outreach Manager (MD, Annapolis)", "Based in MD; travel across the state.", "full-time", "High school"),
        ("Barista", "No experience needed.", "part-time", "High school"), ("Store Associate", "", "part-time", "High school"),
        ("Director of IT", "Microsoft certification required. Licensed software.", "full-time", "High school"),
        ("Software Engineering Intern", "Pursuing a bachelor's or master's degree in CS.", "internship", "High school"),
        ("Data Scientist, Intern (PhD)", "", "internship", "Bachelor"), ("2027 Summer Intern, MBA, Operations Planning", "", "internship", "Bachelor"),
        ("Research Intern", "Currently pursuing a PhD in physics.", "internship", "Bachelor")]:
    t("education for %r is %s" % (title[:50], want), J._edu(title, text, jt), want)
for title, text, want in [("Data Scientist, Intern (PhD)", "", True), ("Software Engineering Intern", "Pursuing a bachelor's or master's degree.", False),
                          ("Research Intern", "Currently pursuing a PhD in physics.", True), ("Marketing Intern", "Open to all majors.", False),
                          ("ML Intern", "Enrolled in a master's program; undergraduates with research experience also considered.", False)]:
    t("graduate-only %r: %s" % (title, want), J._grad_only(title, text), want)
g = J._normalize(dict(id=2, title="Research Intern", company="Acme", loc="Austin, TX", remote=None, text="Currently pursuing a PhD in physics. Python.",
                      url="https://x.example/2", salary_text="", posted=0), "greenhouse", "Acme")
t("a graduate-only internship carries gradOnly; an undergraduate one does not", (g.get("gradOnly"), "gradOnly" in J._normalize(
    dict(id=3, title="Marketing Intern", company="Acme", loc="Austin, TX", remote=None, text="Excel. Open to all majors.", url="https://x.example/3",
         salary_text="", posted=0), "greenhouse", "Acme")), (True, False))

# ---------------- part-time from the schedule ----------------
for text, want in [("This role is 15-25 hours per week.", True), ("Up to 20 hrs/week, flexible.", True), ("Part-time team member, evenings.", True),
                   ("Work 10 hours a week in our studio.", True), ("Full-time or part-time welcome.", False), ("We offer full-time and part-time roles.", False),
                   ("Full-time, 40 hours per week.", False), ("We work 50 hours per week.", False), ("Benefits for full-time employees. This part-time role...", False)]:
    t("part-time from %r: %s" % (text, want), J._part_time_text(text), want)
t("a store role whose text says 20 hours a week is part-time", J._job_type({"title": "Store Team Member", "text": "Flexible shifts, about 20 hours per week."}), "part-time")
t("...but the feed's own Full-time field still wins", J._job_type({"title": "Store Team Member", "emp": "Full-time", "text": "About 20 hours per week."}), "full-time")

# ---------------- one slow feed never holds the others ----------------
real_open, real_deadline = J.urllib.request.urlopen, J.FEED_DEADLINE


class Slow(io.RawIOBase):
    """An answer that trickles: a small part every 0.2 s, never finishing in time."""
    def read(self, n=-1):
        time.sleep(0.2)
        if not hasattr(self, "_s"):
            self._s = 0
            return b' {"jobs": ['
        self._s += 1
        return json.dumps({"id": self._s, "title": "Clerk", "location": {"name": "Austin, TX"}, "content": "Excel.", "absolute_url": "https://x.example/%d" % self._s}).encode() + b","

    def readable(self):
        return True


J.urllib.request.urlopen = lambda req, timeout=None: Slow()
J.FEED_DEADLINE = 1
try:
    t0 = time.time()
    jobs, status = J._fetch_source(("greenhouse", "slowco", "SlowCo"))
    took = time.time() - t0
    t("a feed past its deadline is dropped with a status, quickly (%.1f s)" % took, (jobs, status.startswith("error:"), "longer than" in status, took < 3), ([], True, True, True))
    t("...and is tried again at the next cycle (2 minutes), not at every request", ("greenhouse", "slowco", "SlowCo") in J._failed, True)
    t0 = time.time()
    try:
        J._get("https://slow.example/")
        whole = "no error"
    except TimeoutError:
        whole = "timed out"
    t("the whole-answer reader has the same deadline", (whole, time.time() - t0 < 3), ("timed out", True))
finally:
    J.urllib.request.urlopen, J.FEED_DEADLINE = real_open, real_deadline
t("the deadline is 180 s per feed, 20 s per network read", (J.FEED_DEADLINE, J.FEED_TIMEOUT), (180, 20))


# ---------------- places written without a comma (Lever boards) ----------------
for loc, us, tri in [("Abilene TX", True, False), ("Hoboken NJ", True, True), ("Philadelphia PA", True, True), ("Wilmington DE", True, True),
                     ("Munich DE", False, True), ("Berlin DE", False, True), ("London UK", False, False), ("Mumbai IN", False, False),
                     ("Bangalore IN", False, False), ("Indianapolis IN", True, False), ("Denver CO", True, False), ("Bogota CO", False, False),
                     # "India" inside Indiana and "Mexico" inside New Mexico dropped US jobs before
                     ("Indianapolis, IN", True, False), ("Fort Wayne, Indiana", True, False), ("Albuquerque, New Mexico", True, False), ("Mexico City, Mexico", False, False),
                     ("Remote - India", False, False), ("Hyderabad, India", False, False), ("Mumbai, MH, India", False, False)]:
    t("place %r: US %s, tri-state %s" % (loc, us, tri), (J._us_ok(loc, False), bool(J.LOCAL_RE.search(loc))), (us, tri))

# ---------------- evergreen part-time postings on an employer's own board ----------------
NOW = time.time() * 1000
old = NOW - 400 * J.DAY_MS
real_iter = J._iter_raw
J._iter_raw = lambda kind, token, name: iter([
    dict(id=1, title="Bakery Team Member", company="Cookies", loc="Philadelphia, PA", remote=None, text="Part-time, evenings. Customer service and Excel.", url="https://x.example/1", salary_text="", posted=old, emp="Part-time"),
    dict(id=2, title="Store Manager", company="Cookies", loc="Philadelphia, PA", remote=None, text="Lead the store. Excel.", url="https://x.example/2", salary_text="", posted=old, emp="Full-time")])
try:
    js, status = J._fetch_source(("lever", "cookies", "Cookies"))
    t("on the employer's own board an old part-time posting stays (one evergreen posting per store), an old full-time one goes",
      ([j["role"] for j in js], status), (["Bakery Team Member"], "1 jobs; 1 older than 60 days left out"))
    js, status = J._fetch_source(("jobicy", "cookies", "Jobicy"))
    t("...an aggregator's old part-time copy still goes", [j["role"] for j in js], [])
finally:
    J._iter_raw = real_iter
    J._cache.clear()

# ---------------- the Simplify check cache stays small ----------------
real_get = J._get
ROW = '<tr><td><strong>Acme</strong></td><td>Intern %d</td><td>Austin, TX</td><td><a href="https://job-boards.greenhouse.io/acme/jobs/%d"><img alt="Apply"></a></td><td>1d</td></tr>'
LISTS = {"README.md": "<table><tbody>" + "".join(ROW % (i, i) for i in range(1, 21)) + "</tbody></table>"}


def sgets(url, headers=None, as_text=False):
    if url.startswith(J.SIMPLIFY_REPO):
        return LISTS[url[len(J.SIMPLIFY_REPO):]]
    i = int(url.rsplit("/", 1)[1])
    return {"id": i, "title": "Intern %d" % i, "company_name": "Acme", "location": {"name": "Austin, TX"}, "content": "Excel and SQL. " * 2000,
            "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/%d" % i, "first_published": time.strftime("%Y-%m-%dT%H:%M:%SZ"), "metadata": [], "internal_job_id": 9}


J._get = sgets
try:
    J._simplify_checked.clear()
    J._fetch_source(("simplify", "README.md", "Simplify and Pitt CSC"))
    first = len(J._simplify_checked)
    e = next(iter(J._simplify_checked.values()))["raw"]
    t("a checked posting keeps only the fields used and the first %d characters of its text" % J.SIMPLIFY_TEXT,
      (len(e["text"]) <= J.SIMPLIFY_TEXT, "internal_job_id" in e, sorted(set(e) - set(J.SIMPLIFY_FIELDS))), (True, False, []))
    LISTS["README.md"] = "<table><tbody>" + "".join(ROW % (i, i) for i in range(1, 6)) + "</tbody></table>"     # 15 rows left the list
    J._cache.clear()
    J._fetch_source(("simplify", "README.md", "Simplify and Pitt CSC"))
    t("the map shrinks when rows leave the list (%d -> %d)" % (first, len(J._simplify_checked)), (first, len(J._simplify_checked)), (20, 5))
    for v in J._simplify_checked.values():
        v["at"] -= 3 * J.SIMPLIFY_CHECK_TTL                     # checked three days ago
    J._simplify_forget("README.md", set(J._simplify_checked))
    t("an entry checked more than two days ago is dropped even if still listed", len(J._simplify_checked), 0)
finally:
    J._get = real_get
    J._cache.clear()

# ---------------- the settings file is read once, not once per source or per key ----------------
real_keys, calls = J.feed_keys, []
J.feed_keys = lambda: calls.append(1) or real_keys()
real_start = J._start_refresh
J._start_refresh = lambda src: None
filled = J._disk["filled"]
try:
    J._disk["filled"] = False
    J._start_missing(J.SOURCES)
    t("starting the first fill reads the keys once for %d sources" % len(J.SOURCES), len(calls), 1)
    calls.clear()
    J._scrub("an error")
    t("taking keys out of an error reads them once, not once per key", len(calls), 1)
finally:
    J.feed_keys, J._start_refresh, J._disk["filled"] = real_keys, real_start, filled


# ---------------- the Internship stack in Chrome ----------------
def browser_checks(port):
    city = ("smartrecruiters", "CityofPhiladelphia", "City of Philadelphia")
    made = [("Intern Philadelphia", "Philadelphia, PA", None, "Excel and SQL. Open to undergraduates."),
            ("Intern Wilmington", "Wilmington, DE", None, "Excel and SQL. Open to undergraduates."),
            ("Intern Remote", "Remote", True, "Excel and SQL. Open to undergraduates."),
            ("Intern Seattle", "Seattle, WA", None, "Excel and SQL. Open to undergraduates."),
            ("PhD Research Intern Philadelphia", "Philadelphia, PA", None, "Excel and SQL. Currently pursuing a PhD."),
            ("MBA Intern Philadelphia", "Philadelphia, PA", None, "Excel and SQL. MBA students.")]
    jobs = [J._normalize(dict(id="74400000002%04d" % i, title=title, company="City of Philadelphia", loc=loc, remote=remote, text=text,
                              url="https://jobs.smartrecruiters.com/CityofPhiladelphia/74400000002%04d" % i, salary_text="", posted=int(time.time() * 1000),
                              emp="Intern"), "smartrecruiters", "City of Philadelphia", "CityofPhiladelphia") for i, (title, loc, remote, text) in enumerate(made)]
    t("browser setup: 6 internships, 2 of them graduate-only", (len(jobs), sum(1 for j in jobs if j.get("gradOnly"))), (6, 2))
    data = tempfile.mkdtemp(prefix="uaply-quality-server-")
    with open(os.path.join(data, "jobs-cache.json"), "w", encoding="utf-8") as f:
        json.dump({"|".join(city): {"at": time.time(), "jobs": jobs, "status": "6 jobs"}, "_version": J.CACHE_VERSION}, f)
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
        t("HTTP: a signed-in person gets all 6 internships from the server" , len(listing["jobs"]), 6)
        if not shutil.which("node"):
            print("SKIP browser: node is not installed")
            return
        r = subprocess.run(["node", os.path.join(HERE, "cdp.js"), os.path.join(HERE, "ui-intern-order.js")], env=dict(os.environ, PORT=str(port), W="390", H="844"),
                           capture_output=True, text=True, timeout=180)
        print(r.stdout.strip())
        t("browser: the Internship stack's order (tools/ui-intern-order.js)", r.returncode == 0 and "FAIL" not in r.stdout and r.stdout.count("PASS") >= 5, True)
    finally:
        srv.terminate()
        srv.wait(10)
        log.close()


if len(sys.argv) > 1:
    browser_checks(int(sys.argv[1]))
print(sum(R), "/", len(R))
sys.exit(0 if all(R) else 1)
