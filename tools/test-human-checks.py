"""The human-check scan (tools/scan-human-checks.py) and what the server does with it (human-checks.json): which pages show a captcha or a
challenge, the kind of application page, robots.txt (with * and $) and its crawl delay honoured on every page and redirect, at most 3
attempts, a challenge never asked twice, and on the server the route label ("Ready, one tap" where a check is likely) with no job removed.
No network: every answer is made up here.
  python tools/test-human-checks.py"""
import importlib.util
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
os.environ["UAPLY_CONFIG_FILE"] = "none"
os.environ["UAPLY_CONFIG_JSON"] = "{}"
os.environ["UAPLY_DATA_DIR"] = tempfile.mkdtemp(prefix="uaply-hc-")
import jobs_api as J  # noqa: E402

spec = importlib.util.spec_from_file_location("scan_human_checks", os.path.join(HERE, "scan-human-checks.py"))
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)

R = []


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


GH = "https://job-boards.greenhouse.io/acme/jobs/1"
FORM = '<form action="/apply"><input name="a"><input name="b"><textarea name="c"></textarea></form>'


def cls(body, status=200, url=GH, final=None):
    return S.classify(status, url, final or url, body)


# ---------------- what a page shows ----------------
t("a reCAPTCHA script is a check", cls('<script src="https://www.google.com/recaptcha/api.js"></script>' + FORM)["kinds"], ["recaptcha"])
t("Greenhouse's invisible reCAPTCHA key in the page's settings is a check",
  cls('{"GOOGLE_RECAPTCHA_INVISIBLE_KEY":"6LfmcbcpAAAAAChN"}' + FORM)["check"], True)
t("Ashby's reCAPTCHA site key (a script app) is a check, and the page is a js-app",
  {k: v for k, v in cls('<div id="root"></div><script>{"recaptchaPublicSiteKey":"6LeFb_YUAAAAALUD"}</script>').items() if k in ("kinds", "formKind")},
  {"kinds": ["recaptcha"], "formKind": "js-app"})
t("Lever's hCaptcha (secure-api.js) is a check on an html form",
  {k: v for k, v in cls('<script src="https://js.hcaptcha.com/1/secure-api.js?host=jobs.lever.co"></script>' + FORM).items() if k in ("kinds", "formKind")},
  {"kinds": ["hcaptcha"], "formKind": "html-form"})
t("Turnstile (a widget key, or its script) is a check",
  (cls('<script>{"turnstileWidgetSiteKey":"0x4AAAAAAAVY8"}</script>')["kinds"],
   cls('<script src="https://challenges.cloudflare.com/turnstile/v0/api.js"></script>')["kinds"]), (["turnstile"], ["turnstile"]))
t("Arkose (FunCaptcha) is a check", cls('<script src="https://client-api.arkoselabs.com/v2/api.js"></script>')["kinds"], ["arkose"])
wall = cls('<html><head><title>Just a moment...</title></head><body><script>window._cf_chl_opt={}</script></body></html>', status=403)
t("a Cloudflare challenge page is a check on the page itself (a wall), and its form cannot be seen",
  (wall["check"], wall["kinds"], wall["formKind"]), (True, ["wall"], "unknown"))
t("'Verify you are human' is a wall", cls("<p>Please verify you are a human to continue.</p>")["kinds"], ["wall"])
t("a DataDome challenge (403 from geo.captcha-delivery.com) is a wall",
  cls("<script>var dd={'host':'geo.captcha-delivery.com'}</script>", status=403)["kinds"], ["wall"])
t("a style rule (.grecaptcha-badge, .g-recaptcha div) and a switched-off flag (\"recaptcha\":false) are not checks",
  cls('<style>.grecaptcha-badge{display:none}.g-recaptcha div{margin:0}</style><script>{"recaptcha":false}</script>' + FORM)["check"], False)
quiet = cls("<script>a.src='/cdn-cgi/challenge-platform/scripts/jsd/main.js'</script>" + FORM)
t("Cloudflare's quiet bot script is recorded but is not a human check", (quiet["check"], quiet["quiet"]), (False, True))
t("a 403 without a challenge is not a check: it cannot be seen (unknown)", cls("<h1>Forbidden</h1>", status=403)["check"], None)
t("a form with three fields is an html-form; a page of scripts is a js-app",
  (cls(FORM)["formKind"], cls('<div id="root"></div><script src="/app.js"></script>')["formKind"]), ("html-form", "js-app"))
moved = cls('<script src="/app.js"></script>', final="https://jobs.example.com/listing/1")
t("a page that ends on another system is a redirect, and without a visible captcha its check cannot be seen",
  (moved["formKind"], moved["check"]), ("redirect", None))
t("the hiring systems are told apart by host (a subdomain of icims.com is iCIMS; any other site by its domain)",
  [S.site_of(u) for u in ("https://careers-acme.icims.com/jobs/1", "https://jobs.lever.co/x", "https://www.acme.co.uk/jobs", "https://jobs.acme.com/x")],
  ["icims", "lever", "acme.co.uk", "acme.com"])
t("each system's application page: Lever /apply, Ashby /application, Workable /apply/, SmartRecruiters' one-click page",
  [S.apply_url({"ats": {"kind": k, "board": "acme", "id": "abc"}})[0] for k in ("greenhouse", "lever", "ashby", "workable", "smartrecruiters")],
  ["https://job-boards.greenhouse.io/acme/jobs/abc", "https://jobs.lever.co/acme/abc/apply", "https://jobs.ashbyhq.com/acme/abc/application",
   "https://apply.workable.com/acme/j/abc/apply/", "https://jobs.smartrecruiters.com/oneclick-ui/company/acme/publication/abc?dcr_ci=acme"])
t("a Simplify row's Lever link goes to its /apply page; a careers site's job page is followed to its Apply link",
  (S.from_url("https://jobs.lever.co/acme/123"), S.from_url("https://careers-acme.icims.com/jobs/1/x/job")),
  (("https://jobs.lever.co/acme/123/apply", False), ("https://careers-acme.icims.com/jobs/1/x/job", True)))
t("the Apply link: the button that says Apply, never a company link that only has 'apply' in its tracking query or a LinkedIn one",
  S.apply_link('<a href="https://acme.com/?utm_campaign=apply">Website</a><a href="https://www.linkedin.com/x/apply">Apply with LinkedIn</a>'
               '<a class="iCIMS_ApplyOnlineButton" href="/jobs/1/x/job?mode=apply">Apply for this job online</a>', "https://careers-acme.icims.com/jobs/1/x/job"),
  "https://careers-acme.icims.com/jobs/1/x/job?mode=apply")

t("the careers-site reader skips a page that shows a check, not one with Cloudflare's quiet tag",
  (bool(J.HUMAN_CHECK_RE.search("<script src='/cdn-cgi/challenge-platform/scripts/jsd/main.js'></script>")),
   bool(J.HUMAN_CHECK_RE.search("<script src='/cdn-cgi/challenge-platform/h/b/orchestrate/chl_page/v1'></script>"))), (False, True))

# ---------------- robots.txt as RFC 9309 reads it ----------------
rp = J.RobotsTxt()
rp.parse("User-agent: *\nSitemap: https://x/s.xml\nDisallow: /jobs/*login\nDisallow: /connect\nAllow: /connect/ok$\nCrawl-delay: 3\n\n"
         "User-agent: UAplyBot\nUser-agent: other\nDisallow: /private\nDisallow:\n".splitlines())
t("* in a rule matches anything (iCIMS' Disallow: /jobs/*login), with a query too",
  (rp.can_fetch(S.UA_TOKEN, "https://h/jobs/1/x/login?in_iframe=1"), rp.can_fetch(S.UA_TOKEN, "https://h/jobs/1/x/job")), (False, True))
t("the longest rule wins, and a final $ ends the path", (rp.can_fetch(S.UA_TOKEN, "https://h/connect/ok"), rp.can_fetch(S.UA_TOKEN, "https://h/connect/ok2")),
  (True, False))
t("a group named for the bot is used instead of the * group (its crawl delay too)",
  (rp.can_fetch("UAplyBot/1.0 (+https://uaply.net)", "https://h/jobs/1/login"), rp.can_fetch("UAplyBot/1.0", "https://h/private/x"),
   rp.crawl_delay(S.UA_TOKEN), rp.crawl_delay("UAplyBot/1.0")), (True, False, 3.0, None))
t("robots.txt itself may always be read", rp.can_fetch(S.UA_TOKEN, "https://h/robots.txt"), True)

# ---------------- the scan: plain GETs only, robots.txt and its crawl delay, 3 attempts, a challenge asked once ----------------
S.HOSTS = {k: (4, 0.0) for k in S.HOSTS}
S.OTHER = (4, 0.0)
S.time.sleep = lambda s: None                       # no real waiting in a test
CALLS, ANSWERS = [], {}


def fake_raw(url, follow=False):
    CALLS.append(url)
    a = ANSWERS.get(url)
    if a is None:
        if url.endswith("/robots.txt"):
            return 404, {}, ""
        raise OSError("no answer")
    if callable(a):
        a = a()
    return a


S._raw = fake_raw
DL = time.monotonic() + 600
ICIMS = "https://careers-acme.icims.com"
ANSWERS.update({
    ICIMS + "/robots.txt": (200, {}, "User-agent: *\nDisallow: /jobs/*login\nCrawl-delay: 2\n"),
    ICIMS + "/jobs/1/clerk/job": (200, {}, '<html><iframe src="https://www.googletagmanager.com/ns.html"></iframe>'
                                           '<iframe src="/jobs/1/clerk/job?in_iframe=1"></iframe></html>'),
    ICIMS + "/jobs/1/clerk/job?in_iframe=1": (200, {}, '<a class="iCIMS_ApplyOnlineButton" href="/jobs/1/clerk/job?mode=apply&amp;in_iframe=1">Apply for this job online</a>'),
    ICIMS + "/jobs/1/clerk/job?mode=apply&in_iframe=1": (302, {"Location": ICIMS + "/jobs/1/clerk/login?in_iframe=1"}, ""),
    ICIMS + "/jobs/1/clerk/login?in_iframe=1": (200, {}, '<script src="https://js.hcaptcha.com/1/api.js"></script>'),
})
got = S.scan_job({"url": ICIMS + "/jobs/1/clerk/job", "via": "Acme careers site"}, DL, "careerpage")
t("iCIMS: the job page's own frame, its Apply button, then a redirect to the sign-in page that robots.txt closes: not followed, unknown",
  (got["check"], got["formKind"], ICIMS + "/jobs/1/clerk/login?in_iframe=1" in CALLS, "https://www.googletagmanager.com/ns.html" in CALLS),
  (None, "sign-in", False, False))
t("the crawl delay of robots.txt makes that host one request at a time, at least 2 s apart",
  (S._lanes["careers-acme.icims.com"].gap, S._lanes["careers-acme.icims.com"].sem._value), (2.0, 1))
ANSWERS["https://shut.example.com/robots.txt"] = (200, {}, "User-agent: *\nDisallow: /\n")
CALLS.clear()
got = S.scan_job({"url": "https://shut.example.com/jobs/1"}, DL, "careerpage")
t("a page robots.txt closes is never fetched (only robots.txt is)", (got["check"], CALLS), (None, ["https://shut.example.com/robots.txt"]))
ANSWERS["https://jobs.lever.co/robots.txt"] = (200, {}, "User-agent: *\nAllow: /\n")
ANSWERS["https://jobs.lever.co/acme/w/apply"] = (403, {}, "<title>Just a moment...</title><script>_cf_chl_opt={}</script>")
CALLS.clear()
got = S.scan_job({"ats": {"kind": "lever", "board": "acme", "id": "w"}}, DL, "lever")
t("a challenge page is recorded and never asked for again (one GET)", (got["kinds"], CALLS.count("https://jobs.lever.co/acme/w/apply")), (["wall"], 1))
busy = iter([(429, {"Retry-After": "1"}, "slow down"), (200, {}, '<script src="https://js.hcaptcha.com/1/secure-api.js"></script>' + FORM)])
ANSWERS["https://jobs.lever.co/acme/b/apply"] = lambda: next(busy)
got = S.scan_job({"ats": {"kind": "lever", "board": "acme", "id": "b"}}, DL, "lever")
t("a busy answer (429) is asked again after the wait it asks for", got["kinds"], ["hcaptcha"])
CALLS.clear()
got = S.scan_job({"ats": {"kind": "lever", "board": "acme", "id": "down"}}, DL, "lever")
t("a page that never answers: 3 attempts, then nothing", (got, CALLS.count("https://jobs.lever.co/acme/down/apply")), (None, 3))
ANSWERS["https://job-boards.greenhouse.io/robots.txt"] = (200, {}, "User-agent: *\nDisallow: /embed/\n")
for i in range(14):
    ANSWERS["https://job-boards.greenhouse.io/acme/jobs/%d" % i] = (403, {}, "<TITLE>ERROR: The request could not be satisfied</TITLE>")
CALLS.clear()
got = [S.scan_job({"ats": {"kind": "greenhouse", "board": "acme", "id": str(i)}}, DL, "greenhouse") for i in range(14)]
t("a host that refuses (403, no challenge) is not a check, and after 10 refusals in a row it is not asked again in this run",
  (got[0]["check"], "refused" in got[0]["note"], sum(1 for u in CALLS if "/acme/jobs/" in u), got[13]), (None, True, 10, None))
ANSWERS["https://acme.wd5.myworkdayjobs.com/robots.txt"] = (200, {}, "User-agent: *" + chr(10) + "Allow: /Site/" + chr(10))
ANSWERS["https://acme.wd5.myworkdayjobs.com/Site/job/Newark-DE/Nurse_R1"] = (200, {}, '<div id="root"></div><script src="/app.js"></script>')
got = S.scan_job({"url": "https://acme.wd5.myworkdayjobs.com/Site/job/Newark-DE/Nurse_R1", "via": "Acme careers site"}, DL, "careerpage")
t("a careers-site job page whose Apply step a script draws (Workday): the check cannot be seen, not 'none'", (got["check"], got["formKind"]), (None, "js-app"))
ANSWERS["https://jobicy.example/robots.txt"] = (200, {}, "")
ANSWERS["https://jobicy.example/jobs/1"] = (200, {}, '<a href="https://jobicy.example/jobs/1">Apply now</a><a href="#job-application">Apply for this job</a>')
got = S.scan_job({"url": "https://jobicy.example/jobs/1", "via": "Jobicy"}, DL, "jobicy")
t("a board whose own button (a script) leads to the employer: a redirect whose check cannot be seen", (got["check"], got["formKind"]), (None, "redirect"))

seen = {}

# summarize and sample
P = {"check": True, "kinds": ["recaptcha"], "formKind": "html-form", "quiet": False}
N = {"check": False, "kinds": [], "formKind": "html-form", "quiet": False}
U = {"check": None, "kinds": [], "formKind": "unknown", "quiet": False}
t("a source's verdict: always / sometimes / none / unknown over the pages seen (pages that could not be seen do not count)",
  [S.summarize(x)["humanCheck"] for x in ([P, P, U], [P, N], [N, N, None], [U, None])], ["always", "sometimes", "none", "unknown"])
t("20 postings spread over a long list; every posting of a short one", (len(S.sample(list(range(50)), 20)), S.sample([1, 2, 3], 20)), (20, [1, 2, 3]))


# ---------------- the plain GET itself ----------------
class Resp:
    status, headers = 200, {"Content-Encoding": ""}

    def __init__(self):
        self.parts = [b"<html>ok</html>", b""]

    def read(self, n=-1):
        return self.parts.pop(0)

    def close(self):
        pass


class Opener:
    def open(self, req, timeout=None):
        seen.update(method=req.get_method(), data=req.data, ua=req.get_header("User-agent"), cookie=req.get_header("Cookie"))
        return Resp()


real_raw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(real_raw)
real_raw.OPENER = Opener()
status, _, text = real_raw._raw("https://jobs.lever.co/acme/x/apply")
t("each page is one plain GET (no body, no cookie), named as UAplyApplyCheck with a link back",
  (seen["method"], seen["data"], seen["cookie"], "UAplyApplyCheck/1.0" in seen["ua"] and "uaply.net" in seen["ua"], text), ("GET", None, None, True, "<html>ok</html>"))

# ---------------- the server: route labels from human-checks.json, nothing removed ----------------
d = tempfile.mkdtemp(prefix="uaply-hc-file-")
path = os.path.join(d, "human-checks.json")
with open(path, "w", encoding="utf-8") as f:
    json.dump({"sampled": "2026-10-21", "jobs": 5, "share": {"none": 1, "sometimes": 0, "always": 3, "unknown": 1},
               "systems": {"lever": {"sources": 4, "none": 0, "sometimes": 1, "always": 3, "unknown": 0},
                           "ashby": {"sources": 3, "none": 3, "sometimes": 0, "always": 0, "unknown": 0}},
               "sources": {"lever/acme": {"humanCheck": "always", "formKind": "html-form", "sampled": "2026-10-21", "pages": 20, "withCheck": 20,
                                          "kinds": {"hcaptcha": 20}},
                           "ashby/calm": {"humanCheck": "none", "formKind": "js-app", "sampled": "2026-10-21", "pages": 20, "withCheck": 0, "kinds": {}},
                           "himalayas": {"humanCheck": "sometimes", "formKind": "redirect", "sampled": "2026-10-21", "pages": 4, "withCheck": 1,
                                         "kinds": {"wall": 1}}}}, f)
J.load_human_checks(path)
t("route labels: a check always or sometimes is one tap; none is Ready; a board not sampled on a system where checks are the rule is one tap; "
  "otherwise Ready; a feed that mixes employers by its kind",
  [J.route_label(s) for s in (("lever", "acme", "A"), ("ashby", "calm", "C"), ("lever", "newco", "N"), ("ashby", "newco", "N"),
                               ("himalayas", "US", "Himalayas"), ("careerpage", "x", "X"))],
  ["Ready, one tap", "Ready", "Ready, one tap", "Ready", "Ready, one tap", "Ready"])

NOW = time.time() * 1000


def job(i, co, ats=None):
    return {"id": i, "co": co, "role": "Analyst %d" % i, "loc": "Philadelphia, PA", "posted": NOW - 86400000, "apply": "link", "ats": ats}


feeds = {("lever", "acme", "Acme"): [job(1, "Acme", {"kind": "lever", "board": "acme", "id": "a1"}), job(2, "Acme", {"kind": "lever", "board": "acme", "id": "a2"})],
         ("ashby", "calm", "Calm"): [job(3, "Calm", {"kind": "ashby", "board": "calm", "id": "c1"})],
         ("ashby", "conn", "Conn"): [job(4, "Conn", {"kind": "ashby", "board": "conn", "id": "k1"})]}
real = (J.SOURCES, J.feeds_allowed, J._load_source, J.partner_jobs, J.ats_connections)
J.SOURCES = list(feeds)
J.feeds_allowed = lambda: {"lever", "ashby"}
J._load_source = lambda src: (feeds[src], "%d jobs" % len(feeds[src]))
J.partner_jobs = lambda: [{"id": 9, "co": "Partner", "role": "Cashier", "loc": "Philadelphia, PA", "posted": NOW, "apply": "direct", "instant": True}]
J.ats_connections = lambda: {("ashby", "conn"): "k"}
try:
    out = J.get_jobs()
    routes = {x["id"]: x["route"] for x in out["jobs"]}
    J.load_human_checks(os.path.join(d, "missing.json"))
    without = J.get_jobs()
    J.load_human_checks(path)
    health = J.feed_health()
finally:
    J.SOURCES, J.feeds_allowed, J._load_source, J.partner_jobs, J.ats_connections = real
t("each job's route: one tap on a board with a check; Ready on one without; Ready for a connected employer and a partner (sent in UAply)",
  routes, {9: "Ready", 1: "Ready, one tap", 2: "Ready, one tap", 3: "Ready", 4: "Ready"})
t("no job is removed because of a human check (the same jobs with and without the scan's file; without it every route is Ready)",
  ([x["id"] for x in out["jobs"]] == [x["id"] for x in without["jobs"]], {x["route"] for x in without["jobs"]}), (True, {"Ready"}))
t("the cached jobs are not changed (the label is only on the copies sent)", "route" in feeds[("lever", "acme", "Acme")][0], False)
h = {x["source"]: x for x in health["sources"]}
t("the owner health page shows each source's humanCheck, formKind, sample date, pages, kinds and route",
  {k: h["lever/acme"][k] for k in ("humanCheck", "formKind", "checkSampled", "checkPages", "withCheck", "checkKinds", "route")},
  {"humanCheck": "always", "formKind": "html-form", "checkSampled": "2026-10-21", "checkPages": 20, "withCheck": 20, "checkKinds": "hcaptcha",
   "route": "Ready, one tap"})
t("a source never sampled says unknown", (h["ashby/conn"]["humanCheck"], h["ashby/conn"]["formKind"]), ("unknown", "unknown"))
t("and the page's summary: the sample date, the share of jobs per bucket, the systems, sources per bucket",
  (health["humanChecks"]["sampled"], health["humanChecks"]["share"]["always"], health["humanChecks"]["systems"]["lever"]["likely"],
   dict(health["humanChecks"]["sources"]), health["humanChecks"]["oneTap"]),
  ("2026-10-21", 3, True, {"always": 1, "none": 1, "unknown": 1}, 1))
t("a broken file means nothing known (every route Ready), never an error",
  (J.load_human_checks(__file__)["sources"], J.route_label(("lever", "acme", "A"))), ({}, "Ready"))
J.load_human_checks()
with open(os.path.join(os.path.dirname(HERE), "human-checks.json"), encoding="utf-8") as f:
    real_file = json.load(f)
t("the repository's human-checks.json: every source has a verdict, a form kind and a sample date",
  all(v.get("humanCheck") in ("none", "sometimes", "always", "unknown") and v.get("formKind") and v.get("sampled") for v in real_file["sources"].values())
  and len(real_file["sources"]) > 100, True)

print("%d / %d" % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
