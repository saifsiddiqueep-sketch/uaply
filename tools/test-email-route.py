"""Apply by email (Saif, October 23, 2026; docs/apply-by-email.md): a posting that itself asks for applications by email at the employer's
own address gets the application emailed there on a swipe right, with every safeguard of the email route. In this process (the address
reader in jobs_api) and over HTTP against throwaway servers it starts and stops (a stand-in mail server keeps every message: nothing leaves
this computer):
  python tools/test-email-route.py [port]      (default 20470; uses that port and the next two)"""
import base64
import email
import email.policy
import http.client
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 20470
SMTP_PORT, PORT2 = PORT + 1, PORT + 2
TMP = tempfile.mkdtemp(prefix="uaply-emailroute-")
os.environ.update(UAPLY_CONFIG_FILE="none", UAPLY_CONFIG_JSON="{}", UAPLY_DATA_DIR=os.path.join(TMP, "unit"), UAPLY_DNS_CHECK="off")
R = []
PROCS = []


def t(name, got, want):
    ok = got == want
    R.append(ok)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else "  -> got %r, wanted %r" % (got, want)))


import jobs_api  # noqa: E402

# ---------- the address reader: only the posting's own "send your resume to" sentence, at the employer's own domain ----------
A = jobs_api.apply_address
T = jobs_api._text
CASES = [
    ("To apply, send your resume and cover letter to jobs@acmerobotics.com.", "Acme Robotics", "", "jobs@acmerobotics.com"),
    ("Interested candidates should email their resume to careers@acme.com by Friday.", "Acme, Inc.", "", "careers@acme.com"),
    ("Applications should be sent to hr@pennmedicine.org", "Penn Medicine", "", "hr@pennmedicine.org"),
    ("Please submit your application via email to hiring@initech.co.uk with the subject line.", "Initech Ltd", "", "hiring@initech.co.uk"),
    ("Send your CV <a href=\"mailto:talent@globex.io\">here</a> and we will reply.", "Globex", "", "talent@globex.io"),
    ("Email your resume to Jobs@AcmeBoard.com", "Zeta Labs", "acmeboard", "jobs@acmeboard.com"),
    ("If you need an accommodation during the application process, email accommodations@acme.com.", "Acme", "", ""),
    ("Questions about the role? Email recruiting@acme.com.", "Acme", "", ""),
    ("Agencies: please do not send resumes to hr@acme.com.", "Acme", "", ""),
    ("Send your resume to acme.jobs@gmail.com", "Acme", "", ""),
    ("Send your resume to jobs@staffingpartners.com", "Acme", "", ""),
    ("Send your resume to jobs@acme.com or to hr@acme.com.", "Acme", "", ""),
    ("We are hiring. Contact us at info@acme.com for anything.", "Acme", "", ""),
    ("Email your resume to jobs@foo.myworkdayjobs.com", "Foo", "", ""),
    ("To report fraud, email security@acme.com. To apply, use the button above.", "Acme", "", ""),
    ("Send your resume to noreply@acme.com", "Acme", "", ""),
    ("Send your resume to jobs@acme.example.com", "Acme", "", ""),
]
for text, co, board, want in CASES:
    t("address read: %r (%s)" % (text[:60], co), A(T(text), co, board, ""), want)
t("the employer's own careers page counts as its domain", A("Email your resume to jobs@careers-site.com", "Hooli", "", "https://careers-site.com/jobs/1"), "jobs@careers-site.com")
t("a mailto link keeps its address in the posting's text", "talent@globex.io" in T('<p>Send your CV <a href="mailto:talent@globex.io">here</a></p>'), True)


def posting(kind, board, name, rid, title, extra):
    return jobs_api._normalize(dict(id=rid, title=title, company=name, loc="Philadelphia, PA", remote=None,
                                    url="https://job-boards.greenhouse.io/%s/jobs/%s" % (board, rid), salary_text="", posted=int(time.time()),
                                    text="Python and SQL. Build data tools with the team. 1 year of experience. " + extra), kind, name, board)


G = [s for s in jobs_api.SOURCES if s[0] == "greenhouse"][:2]
DOM = ["%s.com" % re.sub(r"[^a-z0-9]", "", s[2].lower()) for s in G]
ADDR = ["jobs@" + d for d in DOM]
P1 = posting("greenhouse", G[0][1], G[0][2], "7001", "Data Analyst", "To apply, send your resume to %s." % ADDR[0])
P2 = posting("greenhouse", G[0][1], G[0][2], "7002", "Data Engineer", "To apply, send your resume to %s." % ADDR[0])
P3 = posting("greenhouse", G[0][1], G[0][2], "7003", "Data Intern", "If you need an accommodation, email accommodations@%s." % DOM[0])
P4 = posting("greenhouse", G[1][1], G[1][2], "7004", "Analytics Lead", "Applications should be sent to %s" % ADDR[1])
P5 = posting("greenhouse", G[1][1], G[1][2], "7005", "Analytics Intern", "Applications should be sent to %s" % ADDR[1])
t("a posting that asks for applications by email: contact is that address, apply is email, and the card says it applies instantly",
  (P1["contact"], P1["apply"], P1.get("instant")), (ADDR[0], "email", True))
t("...and one that only names an accommodations address is an ordinary hand-off", (P3["contact"], P3["apply"], P3.get("instant", False)), ("", "link", False))


# ---------- over HTTP ----------
def req(port, method, path, body=None, cookie="", headers=None):
    h = {"Host": "127.0.0.1:%d" % port, "Origin": "http://127.0.0.1:%d" % port}
    if cookie:
        h["Cookie"] = cookie
    if body is not None:
        h["Content-Type"] = "application/json"
    h.update(headers or {})
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
    c.request(method, path, body=json.dumps(body) if body is not None else None, headers=h)
    r = c.getresponse()
    raw = r.read()
    ck = [v.split(";", 1)[0] for k, v in r.getheaders() if k.lower() == "set-cookie"]
    c.close()
    try:
        return r.status, json.loads(raw), ck
    except ValueError:
        return r.status, raw.decode("utf-8", "replace"), ck


MAILS = os.path.join(TMP, "mail.jsonl")


def mails():
    try:
        return [json.loads(x) for x in open(MAILS, encoding="utf-8") if x.strip()]
    except (OSError, ValueError):
        return []


def to(addr):
    return [m for m in mails() if addr in [x.lower() for x in (m.get("to") or [])]]


def body_of(raw):
    """The plain text of a message as the person reading it sees it (the raw message may be quoted-printable)."""
    try:
        msg = email.message_from_string(raw, policy=email.policy.default)
        part = msg.get_body(preferencelist=("plain",))
        return part.get_content() if part else ""
    except Exception:
        return ""


def seed(data, cfg):
    os.makedirs(data, exist_ok=True)
    cache = {"_version": jobs_api.CACHE_VERSION}
    for kind, board, name in jobs_api.SOURCES:              # every Greenhouse board is "fresh": nothing is read from the internet
        if kind == "greenhouse":
            cache["%s|%s|%s" % (kind, board, name)] = {"at": time.time(), "jobs": [], "status": "0 jobs"}
    cache["greenhouse|%s|%s" % G[0][1:]]["jobs"] = [P1, P2, P3]
    cache["greenhouse|%s|%s" % G[1][1:]]["jobs"] = [P4, P5]
    with open(os.path.join(data, "jobs-cache.json"), "w", encoding="utf-8") as f:
        json.dump(cache, f)
    return cfg


def start(port, data, cfg, extra=None):
    env = dict(os.environ, UAPLY_DATA_DIR=data, UAPLY_CONFIG_JSON=json.dumps(cfg), UAPLY_DNS_CHECK="off", UAPLY_REQUEST_LOG="off", **(extra or {}))
    for k in ("UAPLY_SIGNUP_TEST", "RENDER", "OWNER_PASSWORD"):
        if k not in (extra or {}):
            env.pop(k, None)
    p = subprocess.Popen([sys.executable, os.path.join(ROOT, "serve.py"), str(port), "dev", "--api"], cwd=ROOT, env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    PROCS.append(p)
    for _ in range(80):
        try:
            if req(port, "GET", "/healthz")[0] == 200:
                return p
        except OSError:
            time.sleep(0.25)
    raise SystemExit("a test server did not start")


def account(port, email, consent=True, auto=False):
    """A verified account, the way a person makes one: sign up, type the emailed code, agree in the first-swipe box."""
    s, out, ck = req(port, "POST", "/api/auth/signup", {"email": email, "password": "pass for %s" % email, "agree": True, "first": "Test", "last": "Person"})
    cookie = ck[0] if ck else ""
    code = ""
    for _ in range(60):
        hit = [re.search(r"([0-9]{6}) is your UAply verification code", m.get("raw", "")) for m in to(email)]
        hit = [h for h in hit if h]
        if hit:
            code = hit[-1].group(1)
            break
        if out.get("user", {}).get("emailVerified"):
            break
        time.sleep(0.1)
    if code:
        req(port, "POST", "/api/auth/verify", {"code": code}, cookie)
    if consent:
        import consent_api
        req(port, "POST", "/api/consent", {"version": consent_api.VERSION, "text": consent_api.full_text(auto), "auto": auto}, cookie)
    return cookie


RESUME = {"name": "resume.txt", "data": "data:text/plain;base64," + base64.b64encode(b"Test Person. Python and SQL. Two years of data work.").decode()}


def apply(port, cookie, job, email, contact=None, plan=False):
    body = {"consent": True, "confirm_real": True, "match": 70, "job": {"id": job["id"], "co": job["co"], "role": job["role"], "url": job["url"],
                                                                         "contact": job["contact"] if contact is None else contact},
            "profile": {"name": "Test Person", "email": email, "ext": {"phone": "215-555-0100"}}, "resume": RESUME}
    if plan:
        body["plan_only"] = True
    return req(port, "POST", "/api/apply/plan" if plan else "/api/apply", body, cookie)[:2]


try:
    PROCS.append(subprocess.Popen([sys.executable, os.path.join(HERE, "fake-smtp.py"), str(SMTP_PORT), MAILS], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
    SMTP = {"host": "127.0.0.1", "port": SMTP_PORT, "starttls": False, "from_addr": "apply@uaply.example"}
    SECRET = "test-events-secret-0123456789abcdef"
    live = seed(os.path.join(TMP, "live"), {"feeds": ["greenhouse"], "delivery": "live", "smtp": SMTP, "owner_copy": "", "daily_limit": 3,
                                            "email_domain_daily": 2, "email_events_secret": SECRET, "google": {}})
    start(PORT, os.path.join(TMP, "live"), live)
    a = account(PORT, "ann@example.org")
    s, jobs, _ = req(PORT, "GET", "/api/jobs", cookie=a)
    by = {j["id"]: j for j in (jobs.get("jobs") or [])}
    t("the job list gives the posting's own address, Ready, and applies instantly", [(by.get(P1["id"]) or {}).get(k) for k in ("contact", "apply", "instant", "route")],
      [ADDR[0], "email", True, "Ready"])
    t("...and the accommodations-only posting stays a hand-off", (by.get(P3["id"]) or {}).get("apply"), "link")
    t("the card's plan says ready (a swipe right sends it)", apply(PORT, a, P1, "ann@example.org", plan=True)[1].get("status"), "ready")
    s, out = apply(PORT, a, P1, "ann@example.org", contact="attacker@evil.example")
    t("a swipe right is sent to the posting's address (whatever address the browser claims)", (s, out.get("status"), out.get("to")), (200, "sent", ADDR[0]))
    got = to(ADDR[0])
    t("the employer's address got exactly one message, and the claimed address nothing", (len(got), len(to("attacker@evil.example"))), (1, 0))
    raw = got[0]["raw"] if got else ""
    text = body_of(raw)
    t("...about this job, from the person, with their email as the reply address", ("Data Analyst" in text, "Test Person" in text, bool(re.search(r"Reply-To: .*ann@example\.org", raw))), (True, True, True))
    t("...with the resume attached", ("Content-Disposition: attachment" in raw, "resume.txt" in raw), (True, True))
    m = re.search(r"(http://127\.0\.0\.1:%d/employer/stop\?a=[A-Za-z0-9_-]+&s=[0-9a-f]{32})" % PORT, text)
    t("...and says why it came, with the link that stops UAply sending more", ("asks for applications by email at this address" in re.sub(r"\s+", " ", text), bool(m)), (True, True))
    t("the person gets the confirmation at their own address", (out.get("receipt") or {}).get("status"), "sent")
    t("swiping right again is the same application, not a second email", (apply(PORT, a, P1, "ann@example.org")[1].get("status"), len(to(ADDR[0]))), ("duplicate", 1))
    s, out = apply(PORT, a, P2, "ann@example.org")
    t("a second job at the same employer is sent too (2 of the domain's 2 a day)", (out.get("status"), len(to(ADDR[0]))), ("sent", 2))
    b = account(PORT, "bob@example.org")
    s, out = apply(PORT, b, P1, "bob@example.org")
    t("the employer's domain had its share today: the next swipe is a hand-off, nothing is emailed", (s, out.get("status"), len(to(ADDR[0]))), (200, "handoff", 2))
    s, out = apply(PORT, b, P4, "bob@example.org")
    t("another employer's posting is still sent (UAply's third email of its 3 a day)", (out.get("status"), len(to(ADDR[1]))), ("sent", 1))
    c = account(PORT, "cy@example.org")
    s, out = apply(PORT, c, P5, "cy@example.org")
    t("UAply's own daily limit reached: a hand-off, nothing is emailed", (s, out.get("status"), len(to(ADDR[1]))), (200, "handoff", 1))
    off = account(PORT, "off@example.org")
    req(PORT, "POST", "/api/auth/send-for-me", {"on": False}, off)
    s, out = apply(PORT, off, P5, "off@example.org")
    t("Send applications for me off: the posting's swipe is only saved (and says why), nothing is emailed", (s, out.get("status"), out.get("sendForMe"), len(to(ADDR[1]))),
      (200, "handoff", False, 1))
    nc = account(PORT, "noconsent@example.org", consent=False)
    s, out = apply(PORT, nc, P4, "noconsent@example.org")
    t("no agreement on record: nothing is sent (403 consent)", (s, out.get("code")), (403, "consent"))
    # the stop link: a page that asks first, then the address is never emailed again and its postings are hand-offs
    s, page, _ = req(PORT, "GET", urllib.parse.urlsplit(m.group(1)).path + "?" + urllib.parse.urlsplit(m.group(1)).query if m else "/employer/stop")
    t("the stop link opens a page that asks first (a scanner opening it changes nothing)", (s, str(page).startswith("<!doctype html>"), ADDR[0] in str(page), "Stop applications to this address" in str(page)), (200, True, True, True))
    still = {j["id"]: j for j in req(PORT, "GET", "/api/jobs", cookie=a)[1]["jobs"]}
    t("...and the posting is still listed for email until the button is pressed", still[P1["id"]]["apply"], "email")
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(m.group(1)).query)) if m else {}
    t("a stop with a wrong signature is refused", req(PORT, "POST", "/api/employer/stop", {"a": q.get("a"), "s": "0" * 32})[0], 400)
    t("the stop button works", req(PORT, "POST", "/api/employer/stop", {"a": q.get("a"), "s": q.get("s")})[:2], (200, {"ok": True}))
    after = {j["id"]: j for j in req(PORT, "GET", "/api/jobs", cookie=a)[1]["jobs"]}
    t("...after which its postings are hand-offs again (no address, not instant)", [(after[P1["id"]].get(k)) for k in ("contact", "apply", "instant")], ["", "link", False])
    d = account(PORT, "dee@example.org")
    t("...and a swipe on one sends nothing", (apply(PORT, d, P2, "dee@example.org")[1].get("status"), len(to(ADDR[0]))), ("handoff", 2))
    # a hard bounce reported by the mail service does the same
    s, out, _ = req(PORT, "POST", "/api/email/events", {"event": "hard_bounce", "email": ADDR[1]}, headers={"Authorization": "Bearer " + SECRET})
    after = {j["id"]: j for j in req(PORT, "GET", "/api/jobs", cookie=a)[1]["jobs"]}
    t("a hard bounce from the mail service turns that employer's postings back into hand-offs", (s, after[P4["id"]]["apply"], after[P5["id"]]["apply"]), (200, "link", "link"))
    # ...and the server's own rule says so (Reviewer 3, October 23: the list's display was checked, not job_policy, which decides what
    # a swipe does; the rest of this run is past UAply's daily limit, so a swipe here would be a hand-off whatever the rule said)
    import jobs_api as _ja  # noqa: E402
    import mailer as _ml  # noqa: E402
    keep = (_ja.partner_jobs, _ja.ats_connections, _ja._find_job, _ml.suppressed)
    try:
        _ja.partner_jobs, _ja.ats_connections = (lambda: []), (lambda: {})
        _ja._find_job = lambda jid: {"id": jid, "apply": "email", "contact": "jobs@bounced.example"}
        _ml.suppressed = lambda a: "hard_bounce" if a == "jobs@bounced.example" else ""
        bounced = _ja.job_policy(4242)
        _ml.suppressed = lambda a: ""
        fine = _ja.job_policy(4242)
    finally:
        _ja.partner_jobs, _ja.ats_connections, _ja._find_job, _ml.suppressed = keep
    t("...and job_policy (what a swipe does) is the hand-off for a bounced address, the email route otherwise", (bounced, fine), ("link", "email"))
    s, st, _ = req(PORT, "GET", "/api/status")
    t("/api/status counts the postings that take applications by email", isinstance(((st.get("apply") or {}).get("classes") or {}).get("postingEmail"), int), True)
    for p in PROCS[1:]:
        p.terminate()
        p.wait(10)
    del PROCS[1:]
    # test mode: the same posting goes to the test inbox, nothing reaches the mail server
    start(PORT2, os.path.join(TMP, "test"), seed(os.path.join(TMP, "test"), {"feeds": ["greenhouse"], "delivery": "test", "smtp": SMTP, "owner_copy": "", "google": {}}))
    e = account(PORT2, "eve@example.org")
    s, out = apply(PORT2, e, P1, "eve@example.org")
    t("test delivery: the application is in the test inbox for the posting's address, not emailed", (out.get("status"), out.get("to"), len(to(ADDR[0]))), ("delivered_test", ADDR[0], 2))
    req(PORT2, "POST", "/api/auth/send-for-me", {"on": False}, e)
    s, out = apply(PORT2, e, P2, "eve@example.org")
    t("test delivery with Send applications for me off: not even the test inbox, only saved", (out.get("status"), out.get("sendForMe")), ("handoff", False))
    PROCS[-1].terminate()
    PROCS[-1].wait(10)
    time.sleep(1.0)                                    # the test-mode server's last mail (the receipt) is through
    n1 = len(mails())
    # UAPLY_SIGNUP_TEST=1 (filler accounts): no email of any kind leaves, even in live delivery with real settings
    start(PORT2, os.path.join(TMP, "filler"), seed(os.path.join(TMP, "filler"), {"feeds": ["greenhouse"], "delivery": "live", "smtp": SMTP, "owner_copy": "", "google": {}}),
          {"UAPLY_SIGNUP_TEST": "1"})
    f = account(PORT2, "filler@example.org")
    s, out = apply(PORT2, f, P4, "filler@example.org")
    time.sleep(1.0)
    t("test mode with live settings: a hand-off, and nothing at all reached the mail server", (out.get("status"), len(mails()) - n1), ("handoff", 0))
finally:
    for p in PROCS:
        try:
            p.terminate()
            p.wait(10)
        except Exception:
            pass
    shutil.rmtree(TMP, ignore_errors=True)

print(sum(R), "/", len(R))
sys.exit(0 if all(R) else 1)
