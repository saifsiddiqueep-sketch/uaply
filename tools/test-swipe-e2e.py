"""The swipe guarantee: one end-to-end run of everything a swipe right promises, on a local server with throwaway data. It FAILS loudly when
any step is not what the person was promised.
  python tools/test-swipe-e2e.py [first port]        (uses 3 ports from there; default 18830; needs Chrome, found by tools/cdp.js)

What it starts: tools/mock-ats.py (stand-ins for Greenhouse, Lever, Ashby, SmartRecruiters and Workable that check every request against their
published API and keep what they accept), tools/fake-smtp.py (a mail server that keeps every message), and a sandbox server in LIVE delivery
mode pointed at both, with a uaply-partners.json of employers who agreed. Then tools/ui-swipe-e2e.js plays the person in Chrome (sign-up
with the emailed code, a Word resume read into the profile, one swipe right per apply path) and this script checks the employer side:
  ats-*        each connected hiring system received one complete application: the name, email and phone from the resume, the resume
               file itself, and no voluntary answer
  email        the employer who agreed to email got one message with the resume attached and no voluntary answer
  email-posting a job posting that itself asks for applications by email (apply by email, October 23): one message to the posting's own
               address with the resume, the person's email as the reply address and the stop link; the person got the confirmation
  handoff      nothing reached anyone; Applied says Finish on their site with both links; the copied block is right (browser half)
  question     a required question only the person can answer: nothing was sent before the answer, then one application with it
  cannot-ask   a required file UAply cannot ask for: an honest hand-off, nothing sent, never dropped
  limit        with payments on, an account that used its 50 free applications this week is refused with the plain sentence, nothing is
               sent, and /api/billing/status shows the week used up
  status       /api/status reports the apply engine healthy, with jobs of each configured apply class
  readiness    (tools/ui-swipe-ready.js) the same paths with a half-finished profile: below the minimum, no phone, no resume, no work
               authorization, and an employer's own question: a swipe right ends only the way the employer's form calls for (Finish your
               profile first, the question box with only what is missing, Not sent yet, sent, or the hand-off); the card said so before the
               swipe; no hiring system ever refused an application (an incomplete one never got that far); the question types asked are
               counted for the owner in /api/status, with no answer and no person in them
  walk         (tools/ui-ready-walk.js, at 390x844 and 1280x800) a student with a half-finished profile swipes right with a finger, sees
               exactly what is missing, adds it in one tap, answers the employer's one question, and the application is sent
The per-system request rules live in tools/mock-ats.py and tools/test-ats-flow.py (42 checks, in-process); this run is the whole journey."""
import base64
import hashlib
import http.cookiejar
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
P = int(sys.argv[1]) if len(sys.argv) > 1 else 18830
MOCK, SMTP, APP = P, P + 1, P + 2
TMP = tempfile.mkdtemp(prefix="uaply-e2e-")
DATA = os.path.join(TMP, "data")
os.makedirs(DATA)
MAIL = os.path.join(TMP, "mail.jsonl")
RESUME = os.path.join(HERE, "fixtures", "resumes", "newgrad.docx")
EEO_WORDS = ("Non-binary", "protected veteran", "Native Hawaiian", "I have a disability")      # the voluntary answers the browser half sets
COUNT = {}
sys.path.insert(0, ROOT)
os.environ.update(UAPLY_CONFIG_FILE="none", UAPLY_DATA_DIR=DATA)
import jobs_api  # noqa: E402

# a public posting that asks for applications by email at the employer's own address: every Greenhouse board is seeded "fresh" (nothing is
# read from the internet) and the first one lists this posting
POST_SRC = [s_ for s_ in jobs_api.SOURCES if s_[0] == "greenhouse"][0]
POST_ADDR = "jobs@%s.com" % "".join(ch for ch in POST_SRC[2].lower() if ch.isalnum())
POSTING = jobs_api._normalize(dict(id="9101", title="Marketing Analyst", company=POST_SRC[2], loc="Boston, MA", remote=None,
                                   url="https://job-boards.greenhouse.io/%s/jobs/9101" % POST_SRC[1], salary_text="", posted=int(time.time()),
                                   text="SQL and Excel reporting for campaigns, with some Python. Plan campaigns with the team. 1 year of experience. To apply, send your resume to %s." % POST_ADDR),
                              "greenhouse", POST_SRC[2], POST_SRC[1])
_cache = {"_version": jobs_api.CACHE_VERSION}
for _k, _b, _n in jobs_api.SOURCES:
    if _k == "greenhouse":
        _cache["%s|%s|%s" % (_k, _b, _n)] = {"at": time.time(), "jobs": [], "status": "0 jobs"}
_cache["greenhouse|%s|%s" % POST_SRC[1:]]["jobs"] = [POSTING]
with open(os.path.join(DATA, "jobs-cache.json"), "w", encoding="utf-8") as _f:
    json.dump(_cache, _f)


def t(path, name, ok, extra=""):
    c = COUNT.setdefault(path, [0, 0])
    c[0 if ok else 1] += 1
    print(("PASS " if ok else "FAIL ") + "[" + path + "] " + name + ("" if ok or not extra else "  -> " + str(extra)[:300]))
    sys.stdout.flush()
    return ok


def jid(co, role):          # the id jobs_api gives a partner employer's job
    return 200000 + int(hashlib.sha1(("partner:%s:%s" % (co, role)).encode()).hexdigest()[:6], 16)


CONSENT = "Agreed in writing to receive applications through UAply (test)"
EMPLOYERS = [
    {"name": "Acme Robotics", "consent": CONSENT, "url": "https://acme.example/careers", "ats": {"kind": "greenhouse", "board": "acme", "api_key": "gh-secret-key-123"},
     "jobs": [{"role": "Marketing Coordinator", "skills": ["HubSpot", "Canva"], "ats_job_id": "1001", "loc": "Boston, MA", "mode": "onsite"},
              {"role": "Brand Storyteller", "skills": ["Copywriting"], "ats_job_id": "1003", "loc": "Remote (US)"},
              {"role": "Portfolio Designer", "skills": ["Canva"], "ats_job_id": "1009", "loc": "Remote (US)"}]},
    {"name": "Acme Lever", "consent": CONSENT, "url": "https://jobs.lever.co/acme", "ats": {"kind": "lever", "board": "acme", "api_key": "lever-key-456"},
     "jobs": [{"role": "Social Media Coordinator", "skills": ["Canva"], "ats_job_id": "posting-uuid-9", "loc": "Remote (US)"}]},
    {"name": "Acme Ashby", "consent": CONSENT, "url": "https://jobs.ashbyhq.com/acmeashby", "ats": {"kind": "ashby", "board": "acmeashby", "api_key": "ashby-key-789"},
     "jobs": [{"role": "Content Marketing Intern", "skills": ["Copywriting"], "ats_job_id": "11111111-1111-4111-8111-111111111111", "loc": "Remote (US)", "type": "internship"}]},
    {"name": "City of Philadelphia", "consent": CONSENT, "url": "https://jobs.smartrecruiters.com/CityofPhiladelphia",
     "ats": {"kind": "smartrecruiters", "board": "CityofPhiladelphia", "api_key": "sr-smarttoken-012"},
     "jobs": [{"role": "Communications Assistant", "skills": ["Excel"], "ats_job_id": "aaaaaaaa-0000-4000-8000-000000000001", "loc": "Philadelphia, PA", "mode": "onsite"}]},
    {"name": "Acme Works", "consent": CONSENT, "url": "https://apply.workable.com/acmeworks", "ats": {"kind": "workable", "board": "acmeworks", "api_key": "wk-token-345"},
     "jobs": [{"role": "Marketing Assistant", "skills": ["Mailchimp"], "ats_job_id": "WK00000001", "loc": "Remote (US)"}]},
    {"name": "Mail Co", "consent": CONSENT, "url": "https://mailco.example/jobs", "contact": "hr@mailco.example",
     "jobs": [{"role": "Marketing Associate", "skills": ["Google Analytics"], "loc": "Boston, MA", "mode": "hybrid"}]},
    {"name": "Handoff Co", "consent": CONSENT, "url": "https://boards.greenhouse.io/handoffco/jobs/77",
     "jobs": [{"role": "Growth Marketer", "skills": ["HubSpot"], "loc": "Remote (US)"}]},
]
# the readiness jobs: each apply path once per half-finished profile (distinct roles, so no swipe is a duplicate of another), and an
# employer's own question on four hiring systems. [path, employer, ats job id or None]
STATES = ["below-min", "no-phone", "no-resume", "no-auth"]
RPATHS = [("gh", "Acme Robotics", "1001"), ("ghphone", "Acme Robotics", "1010"), ("ghauth", "Acme Robotics", "1002"), ("lever", "Acme Lever", "posting-uuid-9"),
          ("ashby", "Acme Ashby", "11111111-1111-4111-8111-111111111111"), ("sr", "City of Philadelphia", "aaaaaaaa-0000-4000-8000-000000000001"),
          ("wk", "Acme Works", "WK00000001"), ("mail", "Mail Co", None), ("handoff", "Handoff Co", None)]
QPATHS = [("ghq", "Acme Robotics", "1003"), ("ashbyq", "Acme Ashby", "33333333-3333-4333-8333-333333333333"),
          ("srq", "City of Philadelphia", "aaaaaaaa-0000-4000-8000-000000000003"), ("wkq", "Acme Works", "WK00000003")]
WALK = {"390": ("Acme Robotics", "Campus Ambassador (walk 390)", "1002"), "1280": ("Acme Robotics", "Campus Ambassador (walk 1280)", "1002")}
READY = {"jobs": {}, "expect": {}, "asks": {}, "cards": {}}
by_name = {e["name"]: e for e in EMPLOYERS}


def add_job(co, role, ats_id):
    j = {"role": role, "skills": ["Canva", "HubSpot"], "loc": "Remote (US)"}
    if ats_id:
        j["ats_job_id"] = ats_id
    by_name[co]["jobs"].append(j)
    return jid(co, role)


for st in STATES:
    for path, co, ats_id in RPATHS:
        key = st + "|" + path
        READY["jobs"][key] = add_job(co, "Readiness %s %s" % (path, st), ats_id)
        # what the employer's form calls for, from the stand-in forms (tools/mock-ats.py): not from what the app happens to do
        want = "handoff" if path == "handoff" else "sent"
        if st == "below-min":
            want = "profile"                                    # nothing has the minimum: no path may apply
        elif st == "no-phone" and path == "ghphone":
            want = "ask"                                        # Greenhouse 1010 requires a phone number
            READY["asks"][key] = "phone"
        elif st == "no-resume" and path in ("gh", "ghphone", "ghauth", "ashby"):
            want = "ask-file"                                   # these forms require a resume (file or text) and the profile has neither
        elif st == "no-auth" and path == "ghauth":
            want = "ask"                                        # Greenhouse 1002 asks "Are you legally authorized to work in the United States?"
            READY["asks"][key] = "authorized"
        READY["expect"][key] = want
        READY["cards"][key] = {"profile": "", "ask": "^1 answer needed$", "ask-file": "^1 answer needed$",
                               "handoff": "^Ready$", "sent": "^Ready" + ("$" if path == "mail" else " to apply$")}[want]
for path, co, ats_id in QPATHS:
    key = "question|" + path
    READY["jobs"][key] = add_job(co, "Readiness %s question" % path, ats_id)
    READY["expect"][key], READY["asks"][key], READY["cards"][key] = "ask", "favorite color", "^1 answer needed$"
WALK_IDS = {k: add_job(v[0], v[1], v[2]) for k, v in WALK.items()}
ATS_JOBS = sum(len(e["jobs"]) for e in EMPLOYERS if e.get("ats"))
JOBS = {"gh": jid("Acme Robotics", "Marketing Coordinator"), "question": jid("Acme Robotics", "Brand Storyteller"), "file": jid("Acme Robotics", "Portfolio Designer"),
        "lever": jid("Acme Lever", "Social Media Coordinator"), "ashby": jid("Acme Ashby", "Content Marketing Intern"),
        "sr": jid("City of Philadelphia", "Communications Assistant"), "wk": jid("Acme Works", "Marketing Assistant"),
        "mail": jid("Mail Co", "Marketing Associate"), "handoff": jid("Handoff Co", "Growth Marketer"), "postmail": POSTING["id"]}
with open(os.path.join(DATA, "uaply-partners.json"), "w", encoding="utf-8") as f:
    json.dump({"employers": EMPLOYERS}, f)

CFG = {"feeds": ["greenhouse"], "delivery": "live", "grace_seconds": 0, "daily_limit": 100, "google": {}, "owner_copy": "", "anthropic_api_key": "",
       "smtp": {"host": "127.0.0.1", "port": SMTP, "starttls": False, "from_addr": "uaply@example.com"}}
ENV = dict(os.environ, UAPLY_DATA_DIR=DATA, UAPLY_CONFIG_FILE="none", UAPLY_DNS_CHECK="off", UAPLY_REQUEST_LOG="off",
           **{"UAPLY_ATS_BASE_" + k: "http://127.0.0.1:%d" % MOCK for k in ("GREENHOUSE", "LEVER", "ASHBY", "SMARTRECRUITERS", "WORKABLE")})
for k in ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "STRIPE_PRICE_PLUS", "STRIPE_PRICE_PRO", "ANTHROPIC_API_KEY", "OWNER_PASSWORD"):
    ENV.pop(k, None)
procs = []


def start(args, env=None):
    p = subprocess.Popen(args, cwd=ROOT, env=env or ENV, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    procs.append(p)
    return p


def wait(port, path="/"):
    for _ in range(80):
        try:
            urllib.request.urlopen("http://127.0.0.1:%d%s" % (port, path), timeout=2)
            return True
        except urllib.error.HTTPError:
            return True
        except Exception:
            time.sleep(0.25)
    return False


def get(port, path):
    return json.loads(urllib.request.urlopen("http://127.0.0.1:%d%s" % (port, path), timeout=10).read())


def server(cfg):
    p = start([sys.executable, "serve.py", str(APP), "sandbox", "--api"], dict(ENV, UAPLY_CONFIG_JSON=json.dumps(cfg)))
    if not wait(APP, "/healthz"):
        print("TEST SCRIPT FAILED: the sandbox server did not start on %d" % APP)
        sys.exit(1)
    return p


def mails():
    if not os.path.exists(MAIL):
        return []
    with open(MAIL, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


try:
    start([sys.executable, os.path.join(HERE, "mock-ats.py"), str(MOCK)])
    start([sys.executable, os.path.join(HERE, "fake-smtp.py"), str(SMTP), MAIL])
    if not wait(MOCK, "/__received"):
        print("TEST SCRIPT FAILED: the stand-in hiring systems did not start on %d" % MOCK)
        sys.exit(1)
    time.sleep(0.8)                                             # the mail stand-in has no HTTP side to wait on
    app = server(CFG)

    # ---------- status: the apply engine and the job classes, as tools/live-check.py reads them on uaply.net ----------
    st = get(APP, "/api/status").get("apply") or {}
    t("status", "/api/status says the apply engine is healthy (its records folder is writable) in live delivery", st.get("ok") is True and st.get("mode") == "live", st)
    cl, cf = st.get("classes") or {}, st.get("configured") or {}
    t("status", "...with jobs for each configured way of applying: hiring systems %d, email %d (one a posting's own address), hand-off %d" % (ATS_JOBS, len(by_name["Mail Co"]["jobs"]) + 1, len(by_name["Handoff Co"]["jobs"])),
      (cl.get("ats"), cl.get("email"), cl.get("postingEmail"), cl.get("handoff"), cf.get("ats"), cf.get("email"))
      == (ATS_JOBS, len(by_name["Mail Co"]["jobs"]) + 1, 1, len(by_name["Handoff Co"]["jobs"]), True, True), st)

    # ---------- the person, in Chrome ----------
    env = dict(os.environ, PORT=str(APP), SMTP_FILE=MAIL, E2E_JOBS=json.dumps(JOBS), RESUME=RESUME, MOCK_PORT=str(MOCK), W="390", H="844", CDP_LIMIT_MS="480000")
    out = subprocess.run(["node", os.path.join(HERE, "cdp.js"), os.path.join(HERE, "ui-swipe-e2e.js")], cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", timeout=560)
    summary = {}
    for line in out.stdout.splitlines():
        if line.startswith("E2E-SUMMARY "):
            summary = json.loads(line[len("E2E-SUMMARY "):])
        elif line.startswith(("PASS ", "FAIL ")):
            path = line.split("[", 1)[1].split("]", 1)[0] if "[" in line else "browser"
            COUNT.setdefault(path, [0, 0])[0 if line.startswith("PASS") else 1] += 1
            print(line)
        elif line.startswith(("TEST SCRIPT FAILED", "CONSOLE ISSUES")) or "EXC" in line:
            print(line)
    t("browser", "the browser half ran to its end", bool(summary) and out.returncode in (0, 1), (out.stdout[-400:] + out.stderr[-400:]))
    env = dict(env, E2E_PASSWORD=summary.get("password", ""))

    # ---------- what each employer really received ----------
    got = get(MOCK, "/__received")

    def one(system, **match):
        return [g for g in got if g.get("system") == system and all(g.get(k) == v for k, v in match.items())]

    def no_eeo(obj):
        s = json.dumps(obj)
        return not any(w.lower() in s.lower() for w in EEO_WORDS)

    gh = one("greenhouse", job="1001")
    if t("ats-greenhouse", "Greenhouse received exactly one application for the job", len(gh) == 1, [g.get("job") for g in got if g.get("system") == "greenhouse"]):
        f, files = gh[0]["fields"], gh[0].get("files") or {}
        t("ats-greenhouse", "...with the name, email and phone read from the resume", (f.get("first_name"), f.get("last_name"), f.get("email"), (f.get("phone") or "").replace("-", "").replace(" ", "")[-10:])
          == ("Elena", "Rossi", "elena.rossi@example.com", "6175550110"), f)
        t("ats-greenhouse", "...the resume file itself", any("resume" in k for k in files) and json.dumps(files).find("newgrad") > -1, list(files))
        t("ats-greenhouse", "...and no voluntary answer", no_eeo(gh[0]), "")
    lv = one("lever", posting="posting-uuid-9")
    if t("ats-lever", "Lever received exactly one application for the posting", len(lv) == 1, len(lv)):
        f = lv[0]["fields"]
        t("ats-lever", "...with the name, email and phone", (f.get("name"), f.get("email"), (f.get("phone") or "").replace("-", "")[-10:]) == ("Elena Rossi", "elena.rossi@example.com", "6175550110"), f)
        t("ats-lever", "...the resume file", "newgrad" in json.dumps(lv[0].get("files") or {}), list(lv[0].get("files") or {}))
        t("ats-lever", "...and no voluntary answer", no_eeo(lv[0]), "")
    ab = one("ashby", posting="11111111-1111-4111-8111-111111111111")
    if t("ats-ashby", "Ashby received exactly one application for the posting", len(ab) == 1, len(ab)):
        v = ab[0]["values"]
        t("ats-ashby", "...with the name and email", (v.get("_systemfield_name"), v.get("_systemfield_email")) == ("Elena Rossi", "elena.rossi@example.com"), v)
        t("ats-ashby", "...the resume file", len(ab[0].get("files") or {}) == 1 and "newgrad" in json.dumps(ab[0]["files"]), list(ab[0].get("files") or {}))
        t("ats-ashby", "...and no voluntary answer", no_eeo(ab[0]), "")
    sr = one("smartrecruiters", posting="aaaaaaaa-0000-4000-8000-000000000001")
    if t("ats-smartrecruiters", "SmartRecruiters received exactly one candidate for the posting", len(sr) == 1, len(sr)):
        b = sr[0]["body"]
        t("ats-smartrecruiters", "...with the name, email and phone", (b.get("firstName"), b.get("lastName"), b.get("email"), (b.get("phoneNumber") or "").replace("-", "")[-10:])
          == ("Elena", "Rossi", "elena.rossi@example.com", "6175550110"), {k: b.get(k) for k in ("firstName", "lastName", "email", "phoneNumber")})
        t("ats-smartrecruiters", "...the resume file", "newgrad" in json.dumps(b.get("resume") or {}) and "bytes" in json.dumps(b.get("resume") or {}), b.get("resume"))
        t("ats-smartrecruiters", "...and no voluntary answer", no_eeo(sr[0]), "")
    wk = one("workable", job="WK00000001")
    if t("ats-workable", "Workable received exactly one candidate for the job", len(wk) == 1, len(wk)):
        c = wk[0]["body"]["candidate"]
        t("ats-workable", "...with the name and email, not as a sourced candidate", (c.get("name"), c.get("email"), wk[0]["body"].get("sourced")) == ("Elena Rossi", "elena.rossi@example.com", False), c)
        t("ats-workable", "...the resume file", (c.get("resume") or {}).get("name") == "newgrad.docx", c.get("resume"))
        t("ats-workable", "...and no voluntary answer", no_eeo(wk[0]), "")
    qa = one("greenhouse", job="1003")
    t("question", "the employer got the application once, only after the answer, with that answer", len(qa) == 1 and "Blue, it is calm." in json.dumps(qa[0]["fields"]), len(qa))
    t("cannot-ask", "the job whose form needs a file UAply cannot ask for received nothing", one("greenhouse", job="1009") == [], len(one("greenhouse", job="1009")))
    t("handoff", "the hand-off employer received nothing (no hiring system, no email)", not any("handoffco" in json.dumps(g) for g in got)
      and not any("handoff" in ",".join(m.get("to") or []).lower() for m in mails()), "")

    # the employer who agreed to email
    to_hr = [m for m in mails() if "hr@mailco.example" in [x.lower() for x in (m.get("to") or [])]]
    if t("email", "the employer who agreed to email got exactly one message", len(to_hr) == 1, len(to_hr)):
        raw = to_hr[0]["raw"]
        t("email", "...about this job, from the person", "Marketing Associate" in raw and "Elena Rossi" in raw and "elena.rossi@example.com" in raw, raw[:300])
        t("email", "...with the resume attached", "Content-Disposition: attachment" in raw and "newgrad.docx" in raw, "")
        t("email", "...and no voluntary answer", not any(w.lower() in raw.lower() for w in EEO_WORDS), "")
    # a posting that asks for applications by email: one message to its own address
    to_post = [m for m in mails() if POST_ADDR in [x.lower() for x in (m.get("to") or [])]]
    if t("email-posting", "the posting's own address got exactly one message", len(to_post) == 1, len(to_post)):
        raw = to_post[0]["raw"]
        import email as _email
        import email.policy as _policy
        _msg = _email.message_from_string(raw, policy=_policy.default)
        body = (_msg.get_body(preferencelist=("plain",)) or _msg).get_content()
        t("email-posting", "...about this job, from the person, with their email as the reply address", "Marketing Analyst" in body and "Elena Rossi" in body
          and "elena.rossi@example.com" in str(_msg.get("Reply-To")), str(_msg.get("Reply-To")))
        t("email-posting", "...with the resume attached", "Content-Disposition: attachment" in raw and "newgrad.docx" in raw, "")
        t("email-posting", "...saying why it came, with the stop link", "asks for applications by email at this address" in " ".join(body.split()) and "/employer/stop?a=" in body, body[-300:])
        t("email-posting", "...and no voluntary answer", not any(w.lower() in raw.lower() for w in EEO_WORDS), "")
    t("email-posting", "the person got the confirmation email for it", any("Marketing Analyst" in m.get("raw", "") for m in mails() if "elena.rossi@example.com" in [x.lower() for x in (m.get("to") or [])]), "")
    t("email", "the hiring systems got exactly the 6 applications the person made (5 swipes + 1 after the answer), nothing twice or extra",
      len([g for g in got]) == 6, [(g.get("system"), g.get("job") or g.get("posting")) for g in got])

    # ---------- readiness: every path with a half-finished profile (tools/ui-swipe-ready.js) ----------
    def browser(script, extra, tag, limit=900):
        env2 = dict(env, CDP_LIMIT_MS=str(limit * 1000), **extra)
        o = subprocess.run(["node", os.path.join(HERE, "cdp.js"), os.path.join(HERE, script)], cwd=ROOT, env=env2, capture_output=True, text=True, encoding="utf-8", timeout=limit + 60)
        res = {}
        for line in o.stdout.splitlines():
            if line.startswith(tag + " "):
                res = json.loads(line[len(tag) + 1:])
            elif line.startswith(("PASS ", "FAIL ")):
                path = line.split("[", 1)[1].split("]", 1)[0] if "[" in line else "browser"
                COUNT.setdefault(path, [0, 0])[0 if line.startswith("PASS") else 1] += 1
                print(line)
            elif line.startswith(("TEST SCRIPT FAILED", "CONSOLE ISSUES", "     ")) or "EXC" in line:
                print(line)
        t("browser", script + " ran to its end", bool(res), (o.stdout[-400:] + o.stderr[-400:]))
        return res

    before_ready = len(get(MOCK, "/__received"))
    ready = browser("ui-swipe-ready.js", {"E2E_READY": json.dumps(READY)}, "E2E-READY")
    got2 = get(MOCK, "/__received")[before_ready:]
    outs = ready.get("outcomes") or {}
    sent_into = [k for k, v in outs.items() if v.get("got", "").endswith("sent") and k.split("|")[1] not in ("mail", "handoff")]
    t("readiness", "the hiring systems received exactly the %d applications that were sent, and nothing else" % len(sent_into), len(got2) == len(sent_into),
      (len(got2), sorted(sent_into)))
    rej = get(MOCK, "/__rejected")
    t("readiness", "no hiring system refused anything: an incomplete application never reached an employer", rej == [], rej[:3])
    k = "no-phone|ghphone"
    gp = [g for g in got2 if g.get("system") == "greenhouse" and g.get("job") == "1010"]
    t("readiness", "Greenhouse's required phone arrived: the number typed in the question box once (no phone in the profile), the profile's otherwise",
      sorted((g["fields"].get("phone") or "").replace("-", "") for g in gp) == sorted(["6175550199"] + ["6175550110"] * (len(gp) - 1)) and len(gp) >= 1,
      [g["fields"].get("phone") for g in gp])
    ga = [g for g in got2 if g.get("system") == "greenhouse" and g.get("job") == "1002"]
    t("readiness", "Greenhouse's work-authorization questions arrived answered (authorized: Yes, sponsorship: No)",
      len(ga) >= 1 and all(g["fields"].get("question_101") == "1" and g["fields"].get("question_102") == "0" for g in ga), [(g["fields"].get("question_101"), g["fields"].get("question_102")) for g in ga])
    gq = [g for g in got2 if "Blue, it is calm." in json.dumps(g)]
    t("readiness", "each employer's own question arrived answered, once per hiring system (Greenhouse, Ashby, SmartRecruiters, Workable)",
      sorted(g["system"] for g in gq) == ["ashby", "greenhouse", "smartrecruiters", "workable"], sorted(g["system"] for g in gq))
    t("readiness", "nothing the readiness swipes sent carries a voluntary answer", all(no_eeo(g) for g in got2), "")
    mails_ready = [m for m in mails() if "hr@mailco.example" in [x.lower() for x in (m.get("to") or [])]]
    t("readiness", "the email employer got one message per readiness swipe that was sent (no-phone, no-resume, no-auth), plus the one saved below the minimum and sent once the profile was complete",
      len(mails_ready) == 2 + sum(1 for k2, v in outs.items() if k2.endswith("|mail") and v.get("got") == "sent"), len(mails_ready))
    qs = get(APP, "/api/status").get("questions") or {}
    keys = [q2.get("key") for q2 in qs.get("top") or []]
    t("readiness", "the owner's /api/status counts the question types asked (the employers' own question, phone, work authorization), by kind",
      qs.get("asked", 0) >= 4 and any("favorite color" in (k3 or "") for k3 in keys) and isinstance(qs.get("kinds"), dict) and qs["kinds"], qs)
    t("readiness", "...with no answer, name or email in them", not any(x in json.dumps(qs) for x in ("Blue, it is calm", "elena", "Elena", "617-555")), json.dumps(qs)[:200])

    # ---------- the walk: a student with a half-finished profile, at phone and laptop size ----------
    for size, (wd, ht) in (("390", (390, 844)), ("1280", (1280, 800))):
        n0 = len(get(MOCK, "/__received"))
        walk = browser("ui-ready-walk.js", {"W": str(wd), "H": str(ht), "WALK_JOB": str(WALK_IDS[size]), "WALK_EMAIL": "student.walk%s@example.com" % size,
                                            "SHOTS": os.environ.get("E2E_SHOTS", "")}, "E2E-WALK", 480)
        new = get(MOCK, "/__received")[n0:]
        t("walk-" + size, "the walk's one application reached Greenhouse complete: the phone and the resume file added on the way, work authorization answered in the box",
          len(new) == 1 and new[0].get("job") == "1002" and (new[0]["fields"].get("phone") or "").replace("-", "").endswith("2155550142") and new[0]["fields"].get("question_101") == "1"
          and "sam-rivera-resume.docx" in json.dumps(new[0].get("files") or {}),
          [(g.get("job"), g["fields"].get("phone"), g["fields"].get("question_101"), list(g.get("files") or {})) for g in new])

    # ---------- the weekly limit: payments on, 50 applications already this week ----------
    app.terminate()
    app.wait(10)
    jar = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

    def call(path, body=None):
        req = urllib.request.Request("http://127.0.0.1:%d%s" % (APP, path), data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json", "Origin": "http://127.0.0.1:%d" % APP})
        try:
            r = op.open(req, timeout=20)
            return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    cfg2 = dict(CFG, stripe={"secret_key": "sk_test_e2eNOTREAL1234", "price_plus": "price_e2eplus", "price_pro": "price_e2epro"})
    # sign in as the person from the browser half, then give the account 50 sent applications this week (the server reads them at start)
    app = server(cfg2)
    s, j = call("/api/auth/login", {"email": "elena.rossi@example.com", "password": summary.get("password", "")}) if summary.get("password") else (0, {})
    uid = (j.get("user") or {}).get("id")
    if not t("limit", "the person signs in again (payments now on, Stripe test settings with no network use)", s == 200 and uid, (s, j)):
        raise SystemExit
    app.terminate()
    app.wait(10)
    now = time.time()
    with open(os.path.join(DATA, "sandbox", "applications.jsonl"), "a", encoding="utf-8") as f:
        for i in range(50):
            f.write(json.dumps({"id": "e2e-%d" % i, "at": now - 3600 - i, "mode": "live", "status": "sent", "user": uid, "job": {"id": 900000 + i, "co": "Past Co", "role": "Past"},
                                "profile": {"email": "elena.rossi@example.com"}, "to": "", "channels": []}) + "\n")
    app = server(cfg2)
    call("/api/auth/login", {"email": "elena.rossi@example.com", "password": summary["password"]})
    s, b = call("/api/billing/status")
    # (9: plus the job saved below the minimum, sent from Job Tracker once the profile was complete) the first browser half sent 8: five hiring systems, the email employer, the email posting and the answered question
    sent_run = 9 + len(sent_into) + sum(1 for k2, v in outs.items() if k2.endswith("|mail") and v.get("got") == "sent")
    t("limit", "Plan and billing shows the week used up on Free: %d of 50 (the 50 above plus the %d sent in this run)" % (50 + sent_run, sent_run),
      (s, (b.get("used") or 0) >= 50 + sent_run, b.get("cap"), b.get("plan")) == (200, True, 50, "free"), b)   # hand-offs count too since October 25: at least these
    before = len(get(MOCK, "/__received"))
    payload = {"consent": True, "confirm_real": True, "match": 80, "note": "", "job": {"id": JOBS["lever"], "co": "Acme Lever", "role": "Social Media Coordinator",
               "url": "https://jobs.lever.co/acme"}, "profile": {"name": "Elena Rossi", "email": "elena.rossi@example.com", "title": "Marketing Coordinator", "years": 1,
               "skills": ["Canva"], "loc": "Boston, MA", "edu": "Bachelor", "ext": {"phone": "617-555-0110", "auth": "citizen", "sponsor": "no"}},
               "resume": {"name": "newgrad.docx", "data": "data:application/octet-stream;base64," + base64.b64encode(open(RESUME, "rb").read()).decode()}}
    s, j = call("/api/apply", payload)
    t("limit", "one more swipe right is refused with the plain sentence and the code the app turns into See plans",
      400 <= s < 500 and j.get("code") == "limit" and "used your 50 applications this week" in (j.get("error") or ""), (s, j))
    t("limit", "...and nothing reached the employer", len(get(MOCK, "/__received")) == before, "")
    # Job Tracker's Mark as applied reaches the server (the day's reminder stops listing that job)
    s, j = call("/api/apply/mark", {"job": JOBS["handoff"], "marked": True})
    t("limit", "Mark as applied: POST /api/apply/mark answers ok with how many jobs still wait for the reminder",
      s == 200 and j.get("ok") is True and isinstance(j.get("waiting"), int), (s, j))
    s, j = call("/api/apply/mark", {"job": "not a number"})
    t("limit", "...a job that is not a number is refused", s == 400, (s, j))
    call("/api/auth/logout", {})
    s, j = call("/api/apply/mark", {"job": JOBS["handoff"]})
    t("limit", "...and signed out it asks to sign in first", s == 401, (s, j))
    s, j = call("/api/auth/signup", {"email": "not.verified.e2e@example.com", "password": "not verified 99", "agree": True})
    s2, j2 = call("/api/apply/mark", {"job": JOBS["handoff"], "marked": True})
    t("limit", "...and an account whose email is not verified yet is asked to verify it first (reminders go only to verified addresses)",
      (s, s2, j2.get("code")) == (200, 403, "verify"), (s, s2, j2))
finally:
    for p in procs:
        try:
            p.terminate()
            p.wait(10)
        except Exception:
            pass
    shutil.rmtree(TMP, ignore_errors=True)

print()
for path in sorted(COUNT):
    print("  %-22s %d passed, %d failed" % (path, COUNT[path][0], COUNT[path][1]))
total, bad = sum(c[0] for c in COUNT.values()), sum(c[1] for c in COUNT.values())
print("%d / %d" % (total, total + bad))
sys.exit(1 if bad or not total else 0)
