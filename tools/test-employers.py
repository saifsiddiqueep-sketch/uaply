"""Tests Hiring mode (employers_api.py): sandbox only, company and posting checks, logos, the job feed, delivery to the employer's
verified email, closed postings, who may see applicants, the pipeline, and the hiring team contact staying on the server.
  python tools/test-employers.py"""
import base64
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
TMP = tempfile.mkdtemp(prefix="uaply-employers-")
os.environ.update(UAPLY_DATA_DIR=TMP, UAPLY_CONFIG_JSON="{}")
os.environ.pop("UAPLY_FEEDS", None)
import employers_api  # noqa: E402
import jobs_api  # noqa: E402
import uaply_api  # noqa: E402

R = []


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


cfg = {"delivery": "test", "smtp": {}}
uaply_api.config = lambda: cfg
EMP = {"id": 1, "email": "hiring@northwind.test", "emailVerified": True}
OTHER = {"id": 2, "email": "boss@globex.test", "emailVerified": True}
NEW = {"id": 3, "email": "new@acme.test", "emailVerified": False}
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
COMPANY = {"name": "Northwind Freight", "industry": "Transportation and logistics", "size": "201-500", "country": "US", "region": "PA",
           "city": "Philadelphia", "website": "https://northwind.example", "about": "Freight for 400 stores.", "consent": True}
JOB = {"role": "Junior Logistics Analyst", "type": "job", "mode": "hybrid", "country": "US", "city": "Philadelphia", "region": "PA",
       "sal_min": 58000, "sal_max": 68000, "yrs": 1, "edu": "Bachelor", "skills": ["Excel", "SQL", "Python"], "majors": ["Supply Chain"],
       "gpa": "3.0", "grad_from": "2026-05", "grad_to": "2027-06", "auth": "any", "sponsor": "no", "start": "grad", "reloc": True,
       "perks": ["health", "pto", "nonsense"], "blurb": "Turn route data into weekly reports for 400 stores.", "desc": "Line one.\nLine two.",
       "manager": {"name": "Dana Ortiz", "title": "Analytics Manager", "email": "dana@northwind.test", "linkedin": "https://www.linkedin.com/in/dana"},
       "show_manager": True}

# ---- only the sandbox has it ----
uaply_api.init("dev")
employers_api.init("dev")
t("off outside the sandbox", employers_api.me(EMP)[0], 404)
t("no postings in the feed outside the sandbox", employers_api.feed_jobs(), [])
uaply_api.init("sandbox")
employers_api.init("sandbox")

# ---- company ----
t("signed out is asked to sign in", employers_api.save_company(None, COMPANY)[0], 401)
t("an unverified email cannot set up a company", employers_api.save_company(NEW, COMPANY)[0], 403)
for field, bad in (("industry", ""), ("size", "lots"), ("country", "MX"), ("consent", False), ("website", "northwind.example")):
    code, out = employers_api.save_company(EMP, dict(COMPANY, **{field: bad}))
    t("company without a valid %s is refused and says which field" % field, (code, out.get("field")), (400, field))
t("an SVG logo is refused (it can carry script)", employers_api.save_company(EMP, dict(COMPANY, logo="data:image/svg+xml;base64,PHN2Zz4="))[0], 400)
t("a file that only claims to be a PNG is refused", employers_api.save_company(EMP, dict(COMPANY, logo="data:image/png;base64," + base64.b64encode(b"not an image").decode()))[0], 400)
code, out = employers_api.save_company(EMP, dict(COMPANY, logo="data:image/png;base64," + base64.b64encode(PNG).decode()))
t("a real PNG logo is saved", code, 200)
t("the logo is served from the server with its type", employers_api.logo(1), ("image/png", PNG))
t("applications go to the verified account email", out["company"]["email"], "hiring@northwind.test")

# ---- postings ----
t("a posting needs a company first", employers_api.save_job(OTHER, JOB)[1].get("code"), "company")
for field, change in (("mode", {"mode": ""}), ("city", {"city": "", "mode": "onsite"}), ("sal_min", {"sal_max": 1000}), ("skills", {"skills": []}),
                      ("blurb", {"blurb": "short"}), ("mgr_email", {"manager": dict(JOB["manager"], email="dana")}),
                      ("mgr_linkedin", {"manager": dict(JOB["manager"], linkedin="https://example.com/dana")}), ("grad_to", {"grad_to": "2025-01"})):
    code, out = employers_api.save_job(EMP, dict(JOB, **change))
    t("posting with a bad %s is refused and says which field" % field, (code, out.get("field")), (400, field))
code, out = employers_api.save_job(EMP, JOB)
t("a complete posting is published", code, 200)
jid = out["job"]["id"]
t("unknown benefits are dropped", out["job"]["perks"], ["health", "pto"])
remote = employers_api.save_job(EMP, dict(JOB, role="Remote Analyst", mode="remote", city="", region="", country="CA"))[1]["job"]
t("a remote posting needs no city", remote["mode"], "remote")

feed = {j["id"]: j for j in employers_api.feed_jobs()}
f = feed[jid]
t("the feed uses the same fields the app scores on", (f["loc"], f["mode"], f["sal"], f["yrs"], f["edu"], f["type"]), ("Philadelphia, PA", "hybrid", [58000, 68000], 1, "Bachelor", "job"))
t("remote in Canada reads as such", feed[remote["id"]]["loc"], "Remote (Canada)")
t("the card shows the hiring team's name and title only", f["manager"], {"name": "Dana Ortiz", "title": "Analytics Manager"})
t("the logo travels as a server address", f["logo"].startswith("/api/employer/logo/1?v="), True)
t("employer postings apply instantly", (f["instant"], f["apply"]), (True, "direct"))
browser = {j["id"]: j for j in jobs_api.get_jobs()["jobs"]}
t("browsers never receive the employer's email", "contact" in browser[jid], False)
t("the server still knows where to send applications", jobs_api.known_contact(jid), "hiring@northwind.test")
t("the hiring team's email stays on the server for the Plus/Pro message", employers_api.manager_for(jid)["email"], "dana@northwind.test")

# ---- applying ----
APPLY = {"consent": True, "match": 92, "job": {"id": jid, "co": "Northwind Freight", "role": "Junior Logistics Analyst", "url": "https://northwind.example", "contact": ""},
         "profile": {"name": "Maya Chen", "email": "maya@example.test", "skills": ["Excel"], "ext": {"phone": "215-555-0100", "auth": "citizen", "sponsor": "no", "gpa": "3.4", "grad": "2026-05"}}}
code, out = uaply_api.submit(APPLY)
t("an application is delivered to the employer's verified email (test mode)", (code, out.get("status"), out.get("to")), (200, "delivered_test", "hiring@northwind.test"))
t("another employer cannot change this posting", employers_api.save_job(dict(OTHER), dict(JOB, id=jid))[0] in (400, 404), True)
employers_api.save_company(OTHER, dict(COMPANY, name="Globex"))
t("another employer does not see these applicants", employers_api.me(OTHER)[1]["applicants"], [])
apps = employers_api.me(EMP)[1]["applicants"]
t("the owner sees the applicant with their details", (len(apps), apps[0]["name"], apps[0]["match"], float(apps[0]["gpa"])), (1, "Maya Chen", 92, 3.4))
t("a new applicant starts in New", apps[0]["stage"], "new")
t("another employer cannot move this applicant", employers_api.set_stage(OTHER, {"id": apps[0]["id"], "stage": "hired"})[0], 404)
t("an unknown stage is refused", employers_api.set_stage(EMP, {"id": apps[0]["id"], "stage": "maybe"})[0], 400)
employers_api.set_stage(EMP, {"id": apps[0]["id"], "stage": "interview", "note": "Strong SQL"})
a = employers_api.me(EMP)[1]["applicants"][0]
t("the owner moves an applicant and keeps a private note", (a["stage"], a["private"]), ("interview", "Strong SQL"))
t("the job shows its applicant count", [j["applicants"] for j in employers_api.me(EMP)[1]["jobs"] if j["id"] == jid], [1])

# ---- closing ----
employers_api.set_status(EMP, {"id": jid, "status": "closed"})
t("a closed posting is marked closed in the feed", {j["id"]: j for j in employers_api.feed_jobs()}[jid]["closed"], True)
code, out = uaply_api.submit(dict(APPLY, profile=dict(APPLY["profile"], email="late@example.test")))
t("a closed posting takes no new applications", code, 410)
employers_api.set_status(EMP, {"id": jid, "status": "open"})
t("reopening puts it back", {j["id"]: j for j in employers_api.feed_jobs()}[jid]["closed"], False)
employers_api.set_status(EMP, {"id": remote["id"], "status": "deleted"})
t("a deleted posting leaves the feed", remote["id"] in {j["id"] for j in employers_api.feed_jobs()}, False)

# ---- reading an existing job post from a link (no network needed for these) ----
t("importing needs a signed-in account", employers_api.import_page(None, "https://example.com/job")[0], 401)
t("LinkedIn links are not read (its terms forbid it); the employer pastes the text", employers_api.import_page(EMP, "https://www.linkedin.com/jobs/view/1")[1].get("code"), "no_read")
t("Indeed links are not read either", employers_api.import_page(EMP, "https://www.indeed.com/viewjob?jk=1")[1].get("code"), "no_read")
t("links to this computer are refused", employers_api.import_page(EMP, "http://127.0.0.1:8766/")[0], 400)
t("links to cloud metadata addresses are refused", employers_api.import_page(EMP, "http://169.254.169.254/latest/meta-data")[0], 400)
t("only web links are accepted", employers_api.import_page(EMP, "file:///etc/passwd")[0], 400)
PAGE = ('<html><head><title>Analyst | Acme</title><script type="application/ld+json">{"@context":"https://schema.org","@graph":[{"@type":"Organization","name":"Acme"},'
        '{"@type":"JobPosting","title":"Junior Analyst","description":"<p>You will build reports.</p>","jobLocation":{"address":{"addressLocality":"Philadelphia","addressRegion":"PA"}}}]}'
        '</script><style>.x{}</style></head><body><nav>Menu</nav><h1>Junior Analyst</h1><p>You will build weekly reports.</p><script>var a=1</script></body></html>')
page = employers_api.extract_page(PAGE)
t("the job-posting block is found inside a @graph", (page["jsonld"] or {}).get("title"), "Junior Analyst")
t("page text keeps the words and drops scripts, styles and menus", ("You will build weekly reports." in page["text"], "var a" in page["text"], "Menu" in page["text"]), (True, False, False))

# ---- kept on disk ----
employers_api.init("sandbox")
t("company and postings survive a restart", (employers_api.me(EMP)[1]["company"]["name"], len(employers_api.me(EMP)[1]["jobs"])), ("Northwind Freight", 1))

print("%d / %d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
