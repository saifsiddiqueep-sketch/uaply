"""Tests the job type (jobType) every job carries, one case per feed kind, read through the same code that reads the real feeds, plus the
Simplify / Pitt CSC list reader (rows, closed rows, age, the check on the employer's own board, the credit) and the safety of its links.
No network: every answer is made up here in the shape the real API gives.
  python tools/test-job-types.py"""
import json
import os
import re
import sys
import tempfile
import time
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ["UAPLY_CONFIG_FILE"] = "none"
os.environ["UAPLY_CONFIG_JSON"] = "{}"
os.environ["UAPLY_DATA_DIR"] = tempfile.mkdtemp(prefix="uaply-types-")
for v in ("UAPLY_FEEDS", "UAPLY_FEEDS_OFF", "UAPLY_USAJOBS_KEY", "UAPLY_USAJOBS_EMAIL"):
    os.environ.pop(v, None)
import jobs_api as J  # noqa: E402

R = []


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


NOW_ISO = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 3 * 86400))
NOW_MS = int(time.time() * 1000) - 3 * 86400000
TEXT = "<p>Python and SQL. Work with our data team.</p>"
ANSWERS = {}            # url prefix -> answer (JSON value, text, or an exception to raise)
CALLS = []


def fake_get(url, headers=None, as_text=False):
    CALLS.append(url)
    one = re.match(r"(https://boards-api\.greenhouse\.io/v1/boards/[^/]+/jobs)/(\d+)$", url)
    if one and one.group(1) in ANSWERS and isinstance(ANSWERS[one.group(1)], dict):    # Greenhouse's single-posting answer, from its list
        return next((j for j in ANSWERS[one.group(1)].get("jobs", []) if str(j.get("id")) == one.group(2)), None) or ANSWERS.get(url)
    for prefix, ans in ANSWERS.items():
        if url.startswith(prefix):
            if isinstance(ans, Exception):
                raise ans
            return ans
    raise urllib.error.URLError("no made-up answer for " + url)


J._get = fake_get
J._get_items = lambda url, key=None: iter((lambda a: a.get(key, []) if key else a)(fake_get(url)))   # the boards' streaming reader, same answers


def types_of(src):
    J._cache.pop(src, None)
    jobs, status = J._fetch_source(src)
    # The Muse (2) and Himalayas (3) read several pages and get the same made-up page each time: each job is counted once (by its id)
    out, ids = [], set()
    for j in jobs:
        if j["id"] not in ids:
            ids.add(j["id"])
            out.append((j["role"], j["jobType"], j["type"]))
    return out


# ---------------- the classifier on its own ----------------
for title, emp, want in [("Software Engineer", "Full-time", "full-time"), ("Software Engineer Intern", "Full-time", "internship"),
                         ("Barista", "Part-time", "part-time"), ("Data Analyst (Contract)", "", "contract"), ("Contract Manager", "", "full-time"),
                         ("Seasonal Warehouse Associate", "", "temporary"), ("Engineering Co-op", "Intern", "co-op"), ("Analyst", "Contractor", "contract"),
                         ("Analyst", "FullTime", "full-time"), ("Analyst", "PartTime", "part-time"), ("Analyst", "Temporary", "temporary"),
                         ("Summer Intern", "Temporary", "internship"), ("Internal Auditor", "", "full-time"), ("Nurse", "Part-time Temporary", "part-time"),
                         ("Clerk", "", "full-time"), ("Engineer, 1099", "", "contract"), ("Developer - Contract", "", "contract")]:
    t("classifier: %r with the feed saying %r is %s" % (title, emp, want), J._job_type({"title": title, "emp": emp, "text": ""}), want)
t("classifier: part-time near the start of the text, when nothing else says", J._job_type({"title": "Cashier", "text": "This is a part-time role."}), "part-time")
t("classifier: an internship list's own kind, when the posting says nothing", J._job_type({"title": "Analyst", "text": "", "default_type": "internship"}), "internship")
t("classifier: the older type follows (the service tabs)", [J.LEGACY_TYPE.get(x, "job") for x in J.JOB_TYPES], ["job", "parttime", "internship", "coop", "job", "job"])

# ---------------- one case per feed kind, through the real readers ----------------
ANSWERS.clear()
ANSWERS["https://boards-api.greenhouse.io/v1/boards/acme/jobs"] = {"jobs": [
    {"id": 1, "title": "Store Associate", "location": {"name": "Philadelphia, PA"}, "content": TEXT, "absolute_url": "https://acme.example/1",
     "first_published": NOW_ISO, "updated_at": NOW_ISO, "metadata": [{"name": "Employment Type", "value": "Part-time"}]},
    {"id": 2, "title": "Data Analyst", "location": {"name": "Austin, TX"}, "content": TEXT, "absolute_url": "https://acme.example/2",
     "first_published": NOW_ISO, "updated_at": NOW_ISO, "metadata": None}]}
t("Greenhouse: the custom Employment Type field, else full-time", types_of(("greenhouse", "acme", "Acme")),
  [("Store Associate", "part-time", "parttime"), ("Data Analyst", "full-time", "job")])
ANSWERS["https://api.lever.co/v0/postings/acme"] = [
    {"id": "a", "text": "Data Analyst", "categories": {"location": "Austin, TX", "commitment": "Contract"}, "descriptionPlain": "Python and SQL.",
     "hostedUrl": "https://jobs.lever.co/acme/a", "createdAt": NOW_MS}]
t("Lever: categories.commitment", types_of(("lever", "acme", "Acme")), [("Data Analyst", "contract", "job")])
ANSWERS["https://api.ashbyhq.com/posting-api/job-board/acme"] = {"jobs": [
    {"id": "b", "title": "Data Analyst", "location": "Austin, TX", "descriptionPlain": "Python and SQL.", "jobUrl": "https://jobs.ashbyhq.com/acme/b",
     "publishedAt": NOW_ISO, "employmentType": "Intern", "isListed": True}]}
t("Ashby: employmentType", types_of(("ashby", "acme", "Acme")), [("Data Analyst", "internship", "internship")])
ANSWERS["https://www.workable.com/api/accounts/acme"] = {"jobs": [
    {"shortcode": "C1", "title": "Data Analyst", "city": "Austin", "state": "TX", "country": "United States", "description": TEXT,
     "url": "https://apply.workable.com/acme/j/C1", "published_on": NOW_ISO, "employment_type": "Temporary"}]}
t("Workable: employment_type", types_of(("workable", "acme", "Acme")), [("Data Analyst", "temporary", "job")])
ANSWERS["https://jobicy.com/api/v2/remote-jobs"] = {"jobs": [
    {"id": 5, "jobTitle": "Data Analyst", "companyName": "Acme", "jobGeo": "USA", "jobDescription": TEXT, "url": "https://jobicy.com/jobs/5",
     "pubDate": NOW_ISO, "jobType": ["part-time"]}]}
t("Jobicy: jobType", types_of(("jobicy", "engineering", "Jobicy")), [("Data Analyst", "part-time", "parttime")])
ANSWERS["https://www.themuse.com/api/public/jobs"] = {"results": [
    {"id": 6, "name": "Data Analyst", "company": {"name": "Acme"}, "locations": [{"name": "Austin, TX"}], "contents": TEXT,
     "refs": {"landing_page": "https://www.themuse.com/jobs/acme/6"}, "publication_date": NOW_ISO, "levels": [{"name": "Internship"}]}]}
t("The Muse: the Internship level", types_of(("muse", "Entry Level", "The Muse")), [("Data Analyst", "internship", "internship")])
ANSWERS["https://remotive.com/api/remote-jobs"] = {"jobs": [
    {"id": 7, "title": "Data Analyst", "company_name": "Acme", "candidate_required_location": "USA", "description": TEXT, "url": "https://remotive.com/7",
     "publication_date": NOW_ISO, "job_type": "contract"}]}
t("Remotive: job_type", types_of(("remotive", "software-dev", "Remotive")), [("Data Analyst", "contract", "job")])
ANSWERS["https://himalayas.app/jobs/api/search"] = {"jobs": [
    {"title": "Data Analyst", "companyName": "Acme", "employmentType": "Part Time", "locationRestrictions": ["United States"], "description": TEXT,
     "pubDate": int(time.time()) - 3 * 86400, "expiryDate": int(time.time()) + 86400, "applicationLink": "https://himalayas.app/companies/acme/jobs/data-analyst",
     "guid": "https://himalayas.app/companies/acme/jobs/data-analyst", "categories": ["Data-Analyst"]},
    {"title": "Berlin Analyst", "companyName": "Acme", "employmentType": "Full Time", "locationRestrictions": ["Germany"], "description": TEXT,
     "pubDate": int(time.time()), "guid": "https://himalayas.app/companies/acme/jobs/berlin"},
    {"title": "Old Analyst", "companyName": "Acme", "employmentType": "Full Time", "locationRestrictions": [], "description": TEXT,
     "pubDate": int(time.time()), "expiryDate": int(time.time()) - 60, "guid": "https://himalayas.app/companies/acme/jobs/old"}]}
CALLS.clear()
t("Himalayas: employmentType; a Germany-only and an expired job are left out", types_of(("himalayas", "US", "Himalayas")), [("Data Analyst", "part-time", "parttime")])
t("Himalayas: three pages at most", len([u for u in CALLS if u.startswith("https://himalayas.app/")]), 3)
ANSWERS["https://remoteok.com/api"] = [{"legal": "link back"},
                                       {"id": "8", "position": "Data Analyst (Contract)", "company": "Acme", "location": "", "description": TEXT, "tags": ["python"],
                                        "url": "https://remoteOK.com/remote-jobs/remote-data-analyst-acme-8", "date": NOW_ISO}]
js, _ = J._fetch_source(("remoteok", "all", "Remote OK"))
t("Remote OK: the title, and the job links back to Remote OK (credited by name)", [(j["jobType"], j["url"], j["via"]) for j in js],
  [("contract", "https://remoteok.com/remote-jobs/remote-data-analyst-acme-8", "Remote OK")])
# SmartRecruiters: the list, then each posting's own record
ANSWERS["https://api.smartrecruiters.com/v1/companies/Acme/postings?"] = {"totalFound": 1, "content": [
    {"id": "744000000000001", "name": "Data Analyst", "location": {"city": "Philadelphia", "region": "PA", "country": "us"}, "releasedDate": NOW_ISO,
     "typeOfEmployment": {"label": "Part-time"}, "company": {"name": "Acme"}}]}
ANSWERS["https://api.smartrecruiters.com/v1/companies/Acme/postings/744000000000001"] = {"jobAd": {"sections": {"jobDescription": {"text": TEXT}}}}
J._sr_desc.clear()
t("SmartRecruiters: typeOfEmployment", types_of(("smartrecruiters", "Acme", "Acme")), [("Data Analyst", "part-time", "parttime")])
# USAJOBS: the schedule, and the Pathways hiring path
os.environ["UAPLY_USAJOBS_KEY"] = "FAKEtypesKey0123456789abcdefABCDEF"
try:
    def usa(i, title, sched, paths, offer="Permanent"):
        return {"MatchedObjectId": i, "MatchedObjectDescriptor": {"PositionTitle": title, "OrganizationName": "Navy", "PositionLocationDisplay": "Philadelphia, Pennsylvania",
                "PositionSchedule": [{"Name": sched}], "PositionOfferingType": [{"Name": offer}], "PublicationStartDate": NOW_ISO.replace("Z", ""),
                "PositionURI": "https://www.usajobs.gov/job/%d" % i, "ApplyURI": ["https://www.usajobs.gov/job/%d" % i],
                "UserArea": {"Details": {"JobSummary": "Python and SQL.", "HiringPath": paths}}, "JobCategory": [{"Name": "Analyst"}]}}
    ANSWERS["https://data.usajobs.gov/api/search"] = {"SearchResult": {"SearchResultItems": [
        usa(1, "Program Analyst", "Full-time", ["public"]), usa(2, "Program Analyst", "Part-time", ["public"]),
        usa(3, "Student Trainee (Program Analyst)", "Full-time", ["student"]), usa(4, "Clerk", "Full-time", ["public"], "Temporary")]}}
    CALLS.clear()
    got = types_of(("usajobs", "parttime", "USAJOBS"))
    t("USAJOBS: PositionSchedule (part-time), Pathways (internship), a Temporary offering", sorted(x[1] for x in got), ["full-time", "internship", "part-time", "temporary"])
    t("USAJOBS: the part-time search asks for part-time schedules (PositionScheduleTypeCode=2)", "PositionScheduleTypeCode=2" in CALLS[-1], True)
finally:
    os.environ.pop("UAPLY_USAJOBS_KEY", None)

# ---------------- the Simplify / Pitt CSC lists ----------------
ROW = '<tr>\n<td>%s</td>\n<td>%s</td>\n<td>%s</td>\n%s<td><div align="center"><a href="%s"><img src="x" width="50" alt="Apply"></a></div></td>\n<td>%s</td>\n</tr>\n'
GH = "https://job-boards.greenhouse.io/acme/jobs/111?utm_source=Simplify&ref=Simplify"
LV = "https://jobs.lever.co/acme/0f0e0d0c-0b0a-4909-8807-060504030201"
summer = "<table><tbody>" + "".join([
    ROW % ("<strong>Acme</strong>", "Software Engineer Intern", "Philadelphia, PA", "", GH, "2d"),
    ROW % ("↳", "Data Intern", "Austin, TX", "", LV, "5d"),                                  # same company as above
    ROW % ("<strong>Old Co</strong>", "Intern", "Austin, TX", "", "https://job-boards.greenhouse.io/old/jobs/222", "3mo"),   # too old
    ROW % ("<strong>Shut Co</strong>", "Intern \U0001f512", "Austin, TX", "", "https://job-boards.greenhouse.io/shut/jobs/333", "1d"),   # closed
    ROW % ("<strong>Far Co</strong>", "Intern", "London, UK", "", "https://job-boards.greenhouse.io/far/jobs/444", "1d"),                # not US
    ROW % ("<strong>Work Co</strong>", "Intern", "Austin, TX", "", "https://work.wd1.myworkdayjobs.com/x/job/1", "1d"),               # cannot be checked
    ROW % ("<strong>Gone Co</strong>", "Intern", "Austin, TX", "", "https://job-boards.greenhouse.io/gone/jobs/555", "1d"),           # gone from its board
    ROW % ("<strong>Evil Co</strong>", "Intern", "Austin, TX", "", "https://job-boards.greenhouse.io/x/jobs/1@169.254.169.254/", "1d"),  # not a board link
]) + "</tbody></table>"
offseason = "<table><tbody>" + ROW % ("<strong>Acme</strong>", "Engineering Co-op", "Pittsburgh, PA", "<td>Fall 2027</td>\n", GH.replace("111", "112"), "4d") + "</tbody></table>"
ANSWERS.clear()
ANSWERS[J.SIMPLIFY_REPO + "README.md"] = summer
ANSWERS[J.SIMPLIFY_REPO + "README-Off-Season.md"] = offseason
ANSWERS["https://boards-api.greenhouse.io/v1/boards/acme/jobs/111"] = {"id": 111, "title": "Software Engineer Intern", "company_name": "Acme", "location": {"name": "Philadelphia, PA"},
                                                                       "content": TEXT, "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/111", "first_published": NOW_ISO, "updated_at": NOW_ISO}
ANSWERS["https://boards-api.greenhouse.io/v1/boards/acme/jobs/112"] = {"id": 112, "title": "Engineering Co-op", "company_name": "Acme", "location": {"name": "Pittsburgh, PA"},
                                                                       "content": TEXT, "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/112", "first_published": NOW_ISO, "updated_at": NOW_ISO}
ANSWERS["https://api.lever.co/v0/postings/acme/0f0e0d0c-0b0a-4909-8807-060504030201"] = {
    "id": "0f0e0d0c-0b0a-4909-8807-060504030201", "text": "Data Intern", "categories": {"location": "Austin, TX", "commitment": "Full-time"},
    "descriptionPlain": "Python and SQL.", "hostedUrl": LV, "createdAt": NOW_MS}
ANSWERS["https://boards-api.greenhouse.io/v1/boards/gone/jobs/555"] = urllib.error.HTTPError("u", 404, "Not Found", {}, None)
CALLS.clear()
J._simplify_checked.clear()
js, status = J._fetch_source(("simplify", "README.md", "Simplify and Pitt CSC"))
t("Simplify: only open, recent, US rows whose posting is still on its own board", sorted((j["co"], j["role"], j["jobType"]) for j in js),
  [("Acme", "Data Intern", "internship"), ("Acme", "Software Engineer Intern", "internship")])
t("Simplify: the board was asked, never the row's own address", sorted(u for u in CALLS if not u.startswith(J.SIMPLIFY_REPO)),
  ["https://api.lever.co/v0/postings/acme/0f0e0d0c-0b0a-4909-8807-060504030201?mode=json",
   "https://boards-api.greenhouse.io/v1/boards/acme/jobs/111", "https://boards-api.greenhouse.io/v1/boards/gone/jobs/555"])
gh = [j for j in js if j["role"] == "Software Engineer Intern"][0]
t("Simplify: credited, and the employer's own posting is the link", (gh["via"], gh["url"], gh["source"]),
  ("Acme on Greenhouse, listed by Simplify and Pitt CSC", "https://job-boards.greenhouse.io/acme/jobs/111", "Acme's careers page"))
t("Simplify: a row has the same id as the employer's own board would give it (shown once)",
  gh["id"], J._normalize(dict(id=111, title="Software Engineer Intern", company="Acme", loc="Philadelphia, PA", remote=None, text="Python and SQL.",
                              url="https://job-boards.greenhouse.io/acme/jobs/111", salary_text="", posted=NOW_MS), "greenhouse", "Acme", "acme")["id"])
CALLS.clear()
J._cache.pop(("simplify", "README.md", "Simplify and Pitt CSC"), None)
J._fetch_source(("simplify", "README.md", "Simplify and Pitt CSC"))
t("Simplify: a posting checked today (found or gone) is not asked again", [u for u in CALLS if not u.startswith(J.SIMPLIFY_REPO)], [])
js, _ = J._fetch_source(("simplify", "README-Off-Season.md", "Simplify and Pitt CSC"))
t("Simplify: the off-season list (with its Terms column) and a co-op", [(j["role"], j["jobType"], j["type"]) for j in js], [("Engineering Co-op", "co-op", "coop")])
for link in ("https://job-boards.greenhouse.io/x/jobs/1@169.254.169.254/", "https://jobs.lever.co/acme/not-a-uuid", "http://jobs.lever.co/acme/0f0e0d0c-0b0a-4909-8807-060504030201",
             "https://boards.greenhouse.io.evil.example/acme/jobs/1", "https://jobs.smartrecruiters.com/Acme/../../x"):
    t("Simplify: %r is not taken as a board posting" % link, any(rx.match(link) for _, rx, _ in J.SIMPLIFY_ATS), False)



# ---------------- in a real browser: the Job type chips and the card (python tools/test-job-types.py <port>) ----------------
def browser_checks(port):
    import shutil
    import subprocess
    city = ("smartrecruiters", "CityofPhiladelphia", "City of Philadelphia")
    made = [("Clerk %d" % i, "Full-time") for i in range(3)] + [("Analyst %d" % i, "Contract") for i in range(2)] +            [("Cashier %d" % i, "Part-time") for i in range(2)] + [("Summer Intern %d" % i, "Intern") for i in range(2)] + [("Engineering Co-op", "Intern")]
    jobs = [J._normalize(dict(id="74400000000%04d" % i, title=title, company="City of Philadelphia", loc="Philadelphia, PA", remote=None,
                              text="Python, SQL and Excel. Serve the public.", url="https://jobs.smartrecruiters.com/CityofPhiladelphia/74400000000%04d" % i,
                              salary_text="", posted=NOW_MS, emp=emp), "smartrecruiters", "City of Philadelphia", "CityofPhiladelphia")
            for i, (title, emp) in enumerate(made)]
    t("browser setup: the made-up City jobs have the types the page test expects", sorted(j["jobType"] for j in jobs),
      sorted(["full-time"] * 3 + ["contract"] * 2 + ["part-time"] * 2 + ["internship"] * 2 + ["co-op"]))
    data = tempfile.mkdtemp(prefix="uaply-types-server-")
    with open(os.path.join(data, "jobs-cache.json"), "w", encoding="utf-8") as f:
        json.dump({"|".join(city): {"at": time.time(), "jobs": jobs, "status": "%d jobs" % len(jobs)}, "_version": J.CACHE_VERSION}, f)
    env = dict(os.environ, UAPLY_CONFIG_FILE="none", UAPLY_DATA_DIR=data, HOST="127.0.0.1", UAPLY_FEEDS="smartrecruiters", UAPLY_CONFIG_JSON="{}")
    env.pop("OWNER_PASSWORD", None)
    root = os.path.dirname(HERE)
    log = open(os.path.join(data, "server.log"), "w")
    srv = subprocess.Popen([sys.executable, os.path.join(root, "serve.py"), str(port), os.path.join(root, "dev"), "--api"], env=env, stdout=log, stderr=log)
    try:
        import urllib.request
        for _ in range(40):
            try:
                urllib.request.urlopen("http://127.0.0.1:%d/healthz" % port, timeout=2)
                break
            except Exception:
                time.sleep(0.25)
        listing = json.loads(urllib.request.urlopen("http://127.0.0.1:%d/api/jobs" % port, timeout=30).read())
        t("HTTP: every job in the list carries its jobType", sorted(j.get("jobType") for j in listing["jobs"]), sorted(j["jobType"] for j in jobs))
        if not shutil.which("node"):
            print("SKIP browser: node is not installed")
            return
        r = subprocess.run(["node", os.path.join(HERE, "cdp.js"), os.path.join(HERE, "ui-job-type.js")], env=dict(os.environ, PORT=str(port), W="390", H="844"),
                           capture_output=True, text=True, timeout=180)
        print(r.stdout.strip())
        if "Chrome" in r.stderr and r.returncode:
            print("SKIP browser:", r.stderr.strip()[-200:])
            return
        t("browser: the Job type chips and the card line (tools/ui-job-type.js)", r.returncode == 0 and "FAIL" not in r.stdout and r.stdout.count("PASS") >= 12, True)
    finally:
        srv.terminate()
        srv.wait(10)
        log.close()


if len(sys.argv) > 1:
    browser_checks(int(sys.argv[1]))
print(sum(R), "/", len(R))
sys.exit(0 if all(R) else 1)
